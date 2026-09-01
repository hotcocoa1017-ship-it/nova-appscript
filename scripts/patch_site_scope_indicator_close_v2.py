from pathlib import Path
import re
import sys

MARKER = 'SITE_SCOPE_INDICATOR_CLOSE_V2'


def read(path):
    return Path(path).read_text(encoding='utf-8')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 anchor, found {count}')
    return text.replace(old, new, 1)


def replace_between(text, start_anchor, end_anchor, replacement, label):
    start = text.find(start_anchor)
    end = text.find(end_anchor, start + 1)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(f'{label}: anchors not found')
    return text[:start] + replacement + text[end:]


try:
    # ------------------------------------------------------------------
    # 1) 로그인 UI: 사업장 -> 이름 -> 사번. ADMIN/ORDER는 사업장 생략 가능.
    # ------------------------------------------------------------------
    index_path = 'Index.html'
    index = read(index_path)
    if MARKER not in index:
        index = replace_once(
            index,
            '<p class="muted login-guide">이름과 사번으로 로그인합니다.</p>\n      <label>\n        <span>이름</span>',
            '<p class="muted login-guide">일반 직원은 사업장 · 이름 · 사번 순으로 로그인합니다. 관리자·오더테이커는 사업장 선택을 생략할 수 있습니다.</p>\n      <!-- SITE_SCOPE_INDICATOR_CLOSE_V2 -->\n      <label>\n        <span>사업장</span>\n        <select id="loginSite" name="site" autocomplete="organization">\n          <option value="">관리자·오더테이커는 선택하지 않음</option>\n          <option value="쏘라노">쏘라노</option>\n          <option value="별관">별관</option>\n        </select>\n      </label>\n      <label>\n        <span>이름</span>',
            'Index login form'
        )
        write(index_path, index)

    # ------------------------------------------------------------------
    # 2) 서버 로그인/토큰: 일반계정 site를 토큰에 고정. 기존 토큰은 호환.
    # ------------------------------------------------------------------
    auth_path = '03_Auth.js'
    auth = read(auth_path)
    if MARKER not in auth:
        start = auth.find('function loginNova(name, employeeNo)')
        end = auth.find('function parseAndVerifyToken_(token)')
        if start < 0 or end < 0:
            raise RuntimeError('Auth login anchors not found')
        replacement = r'''// SITE_SCOPE_INDICATOR_CLOSE_V2
const NOVA_LOGIN_SITES_ = Object.freeze(['쏘라노', '별관']);

function normalizeNovaLoginSite_(value) { // (로그인·세션 사업장 정규화)
  return String(value || '').trim();
}

function isNovaSiteScopedRole_(role) { // (관리자·오더테이커 제외 사업장 고정 역할)
  return !['ADMIN', 'ORDER'].includes(String(role || '').trim().toUpperCase());
}

function resolveNovaLoginSite_(user, selectedSite) { // (신규 로그인 사업장 검증)
  const role = String(user && user.role || '').trim().toUpperCase();
  if (!isNovaSiteScopedRole_(role)) return '';
  const site = normalizeNovaLoginSite_(selectedSite);
  if (!site) throw new Error('사업장을 선택하세요.');
  if (!NOVA_LOGIN_SITES_.includes(site)) throw new Error('사용할 수 없는 사업장입니다.');
  const configured = normalizeNovaLoginSite_(user && user.defaultSite);
  if (configured && configured !== site) {
    throw new Error(`계정 기본사업장(${configured})과 선택한 사업장(${site})이 다릅니다.`);
  }
  return site;
}

function resolveUserSessionSite_(user, requestedSite) { // (API 요청 사업장을 로그인 세션 범위로 고정)
  const role = String(user && user.role || '').trim().toUpperCase();
  const requested = normalizeNovaLoginSite_(requestedSite);
  if (!isNovaSiteScopedRole_(role)) return requested;
  const sessionSite = normalizeNovaLoginSite_(user && (user.sessionSite || user.defaultSite));
  // 배포 이전 토큰은 site가 없을 수 있으므로 기존 세션은 만료 전까지 호환합니다.
  if (!sessionSite) return requested;
  if (requested && requested !== sessionSite) {
    throw new Error(`로그인 사업장(${sessionSite})과 다른 사업장은 조회하거나 처리할 수 없습니다.`);
  }
  return sessionSite;
}

function loginNova(name, employeeNo, site) { // (사용자 로그인)
  return measureResponse_('loginNova', () => {
    const user = authenticateNovaUser_(name, employeeNo, site);
    const token = createLoginToken_(user.employeeNo, user.sessionSite);
    return {
      ok: true,
      token,
      user: getPublicUser_(user)
    };
  });
}

function loginNovaBootstrap(name, employeeNo, clientType, site) { // (로그인·초기화 1회 통신)
  return measureResponse_('loginNovaBootstrap', () => {
    const user = authenticateNovaUser_(name, employeeNo, site);
    const token = createLoginToken_(user.employeeNo, user.sessionSite);
    return {
      ok: true,
      token,
      bootstrap: buildBootstrapPayload_(user, clientType)
    };
  });
}

function authenticateNovaUser_(name, employeeNo, loginSite) { // (이름·사번·사업장 로그인 검증 공통)
  const safeName = String(name || '').trim();
  const safeEmployeeNo = String(employeeNo || '').trim();
  if (!safeName || !safeEmployeeNo) {
    throw new Error('이름과 사번을 입력하세요.');
  }

  const matchedByName = getActiveUsersByName_(safeName);
  const sourceUser = matchedByName.find(item => item.employeeNo === safeEmployeeNo);
  if (!sourceUser) throw new Error('이름 또는 사번이 일치하지 않습니다.');
  const sessionSite = resolveNovaLoginSite_(sourceUser, loginSite);
  return Object.assign({}, sourceUser, {
    sessionSite,
    siteScopeLocked: Boolean(isNovaSiteScopedRole_(sourceUser.role) && sessionSite),
    defaultSite: sessionSite || sourceUser.defaultSite
  });
}

function verifyNovaToken(token) { // (로그인 토큰 검증·사업장 세션 복원)
  try {
    const payload = parseAndVerifyToken_(token);
    const sourceUser = getActiveUserByEmployeeNo_(payload.employeeNo);
    if (!sourceUser) return { ok: false, code: 'UNAUTHORIZED' };
    const scopedRole = isNovaSiteScopedRole_(sourceUser.role);
    const tokenSite = normalizeNovaLoginSite_(payload.site);
    const configuredSite = normalizeNovaLoginSite_(sourceUser.defaultSite);
    // 신규 토큰은 tokenSite를 원본으로 사용합니다. 배포 이전 토큰(site 없음)은 기존 기본사업장으로 호환합니다.
    const sessionSite = scopedRole ? (tokenSite || configuredSite) : '';
    if (scopedRole && tokenSite && configuredSite && tokenSite !== configuredSite) {
      return { ok: false, code: 'SITE_SCOPE_CHANGED', message: '계정 사업장이 변경되었습니다. 다시 로그인하세요.' };
    }
    const user = Object.assign({}, sourceUser, {
      sessionSite,
      siteScopeLocked: Boolean(scopedRole && sessionSite),
      defaultSite: sessionSite || sourceUser.defaultSite
    });
    return { ok: true, user };
  } catch (error) {
    return { ok: false, code: 'UNAUTHORIZED', message: error.message };
  }
}

function createLoginToken_(employeeNo, site) { // (서명 로그인 토큰 생성·사업장 범위 포함)
  const now = Date.now();
  const payload = {
    employeeNo: String(employeeNo),
    site: normalizeNovaLoginSite_(site),
    issuedAt: now,
    expiresAt: now + NOVA.LOGIN_TOKEN_HOURS * 60 * 60 * 1000
  };
  const body = Utilities.base64EncodeWebSafe(JSON.stringify(payload), Utilities.Charset.UTF_8);
  const signature = signTokenBody_(body);
  return `${body}.${signature}`;
}

'''
        auth = auth[:start] + replacement + auth[end:]
        write(auth_path, auth)

    # ------------------------------------------------------------------
    # 3) 사용자 공개정보·채용구분 캐시 재사용.
    # ------------------------------------------------------------------
    repo_path = '02_Repository.js'
    repo = read(repo_path)
    if MARKER not in repo:
        repo = replace_once(
            repo,
            "    job: value('직무'),\n    role: value('권한').toUpperCase(),",
            "    job: value('직무'),\n    employmentType: value('채용구분'),\n    role: value('권한').toUpperCase(),",
            'Repository employmentType'
        )
        repo = replace_once(
            repo,
            "    defaultSite: user.defaultSite,\n    defaultBuildings: user.defaultBuildings",
            "    defaultSite: user.defaultSite,\n    sessionSite: String(user.sessionSite || ''),\n    siteScopeLocked: Boolean(user.siteScopeLocked),\n    defaultBuildings: user.defaultBuildings\n    // SITE_SCOPE_INDICATOR_CLOSE_V2",
            'Repository public user site scope'
        )
        write(repo_path, repo)

    # ------------------------------------------------------------------
    # 4) 모바일 API는 일반계정 요청 site를 세션 site로 강제.
    # ------------------------------------------------------------------
    mobile_path = '10_Mobile.js'
    mobile = read(mobile_path)
    if MARKER not in mobile:
        mobile = mobile.replace(
            "    sites: getSiteList_(),",
            "    sites: user.siteScopeLocked && request.site ? [request.site] : getSiteList_(), // SITE_SCOPE_INDICATOR_CLOSE_V2",
            1
        )
        mobile = mobile.replace(
            "  const site = String(safe.site || user.defaultSite || '').trim();",
            "  const site = resolveUserSessionSite_(user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2",
            2
        )
        mobile = replace_once(
            mobile,
            "    const safe = normalizeHousemanPayload_(payload);\n    if (!safe.roomNo)",
            "    const safe = normalizeHousemanPayload_(payload);\n    safe.site = resolveUserSessionSite_(user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2\n    if (!safe.roomNo)",
            'Mobile houseman request scope'
        )
        mobile = replace_once(
            mobile,
            "    site: String(safe.site || user.defaultSite || '').trim()\n  };",
            "    site: resolveUserSessionSite_(user, safe.site) // SITE_SCOPE_INDICATOR_CLOSE_V2\n  };",
            'Mobile normalize options'
        )
        if mobile.count('SITE_SCOPE_INDICATOR_CLOSE_V2') < 4:
            raise RuntimeError('Mobile site-scope replacements incomplete')
        write(mobile_path, mobile)

    qm_path = 'QmMobileBrowse.js'
    qm = read(qm_path)
    if MARKER not in qm:
        count = qm.count("    const site = String(safe.site || user.defaultSite || '').trim();")
        if count != 2:
            raise RuntimeError(f'QM browse site anchors expected 2, found {count}')
        qm = qm.replace(
            "    const site = String(safe.site || user.defaultSite || '').trim();",
            "    const site = resolveUserSessionSite_(user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2"
        )
        write(qm_path, qm)

    realtime_path = 'RealtimeDailySync.js'
    realtime = read(realtime_path)
    if MARKER not in realtime:
        realtime = replace_once(
            realtime,
            "  const site = String(safe.site || auth.user.defaultSite || '').trim();",
            "  const site = resolveUserSessionSite_(auth.user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2",
            'Realtime JIT site scope'
        )
        write(realtime_path, realtime)

    # ------------------------------------------------------------------
    # 5) Client 로그인 사업장 + 모바일 site 잠금 + 인디케이터 명시적 조회.
    # ------------------------------------------------------------------
    client_path = 'Client.html'
    client = read(client_path)
    if MARKER not in client:
        client = replace_once(
            client,
            "    const name = $('loginName').value.trim();\n    const employeeNo = $('loginEmployeeNo').value.trim();",
            "    const site = $('loginSite') ? $('loginSite').value.trim() : ''; // SITE_SCOPE_INDICATOR_CLOSE_V2\n    const name = $('loginName').value.trim();\n    const employeeNo = $('loginEmployeeNo').value.trim();",
            'Client login site read'
        )
        client = replace_once(
            client,
            "      const result = await callServer('loginNovaBootstrap', name, employeeNo, clientType);",
            "      const result = await callServer('loginNovaBootstrap', name, employeeNo, clientType, site);",
            'Client login bootstrap call'
        )
        client = replace_once(
            client,
            "    state.bootstrap = bootstrap;\n    const available = new Set((bootstrap.menu || []).map(item => item.id));",
            "    state.bootstrap = bootstrap;\n    const bootstrapRole = String(bootstrap.user?.role || '').toUpperCase();\n    const sessionSite = String(bootstrap.user?.sessionSite || '').trim();\n    if (!['ADMIN', 'ORDER'].includes(bootstrapRole) && bootstrap.user?.siteScopeLocked && sessionSite) {\n      state.mobile.site = sessionSite;\n      sessionStorage.setItem('novaMobileSite', sessionSite);\n      if (state.roommaidStats) state.roommaidStats.site = sessionSite;\n    }\n    const available = new Set((bootstrap.menu || []).map(item => item.id));",
            'Client bootstrap site scope'
        )

        # mobile site selector: scoped users only see/keep their login site.
        old_mobile_select = """    const siteSelect = $('mobileSite');
    const selectedSite = String(state.mobile.site || '').trim();
    const sites = [...new Set([
      ...(state.mobile.data.sites || []),
      selectedSite,
      String(state.bootstrap.user.defaultSite || '').trim()
    ].map(site => String(site || '').trim()).filter(Boolean))];
    if (siteSelect) {
      siteSelect.innerHTML = '<option value=\"\">전체 사업장</option>' + sites.map(site => `<option value=\"${escapeAttr(site)}\">${escapeHtml(site)}</option>`).join('');
      siteSelect.value = selectedSite;
    }"""
        new_mobile_select = """    const siteSelect = $('mobileSite');
    const sessionSite = String(state.bootstrap.user?.sessionSite || '').trim();
    const siteScopeLocked = Boolean(state.bootstrap.user?.siteScopeLocked && sessionSite);
    const selectedSite = siteScopeLocked ? sessionSite : String(state.mobile.site || '').trim();
    const sites = siteScopeLocked ? [sessionSite] : [...new Set([
      ...(state.mobile.data.sites || []),
      selectedSite,
      String(state.bootstrap.user.defaultSite || '').trim()
    ].map(site => String(site || '').trim()).filter(Boolean))];
    if (siteSelect) {
      siteSelect.innerHTML = siteScopeLocked
        ? sites.map(site => `<option value=\"${escapeAttr(site)}\">${escapeHtml(site)}</option>`).join('')
        : '<option value=\"\">전체 사업장</option>' + sites.map(site => `<option value=\"${escapeAttr(site)}\">${escapeHtml(site)}</option>`).join('');
      siteSelect.value = selectedSite;
      siteSelect.disabled = siteScopeLocked;
      if (siteScopeLocked) {
        state.mobile.site = sessionSite;
        sessionStorage.setItem('novaMobileSite', sessionSite);
      }
    } // SITE_SCOPE_INDICATOR_CLOSE_V2"""
        client = replace_once(client, old_mobile_select, new_mobile_select, 'Client mobile site selector')

        # indicator state flags.
        client = replace_once(
            client,
            "      loaded: false,\n      loading: false,\n      data: null,\n      version: 0,\n      businessDate: sessionStorage.getItem('novaIndicatorBusinessDate') || '',",
            "      loaded: false,\n      loading: false,\n      data: null,\n      version: 0,\n      queryApplied: false,\n      queryDirty: true,\n      businessDate: sessionStorage.getItem('novaIndicatorBusinessDate') || '',",
            'Indicator state flags'
        )

        # entering indicator must not auto-query.
        client = replace_once(
            client,
            "      if (state.indicator.loaded && state.indicator.data) {\n        renderIndicatorData();\n        startIndicatorSync();\n      } else {\n        loadIndicatorSnapshot();\n      }",
            "      if (state.indicator.loaded && state.indicator.data && state.indicator.queryApplied && !state.indicator.queryDirty) {\n        renderIndicatorData();\n        startIndicatorSync();\n      } else {\n        renderIndicatorAwaitingQuery_();\n      } // SITE_SCOPE_INDICATOR_CLOSE_V2",
            'Indicator initial auto load'
        )

        # site control gets explicit options and query button.
        client = replace_once(
            client,
            '<select id="indicatorSite"><option value="">전체</option></select>',
            '<select id="indicatorSite"><option value="">사업장 선택</option><option value="쏘라노">쏘라노</option><option value="별관">별관</option></select>\n            </div>\n            <div class="control-group indicator-query-action">\n              <span class="control-label">조회</span>\n              <button id="indicatorQueryButton" class="filter-button primary-inline" type="button">조회하기</button>\n            </div>\n            <div class="control-group hidden" aria-hidden="true"><span class="control-label">",
            'Indicator site select/query button'
        )
        # The replacement above deliberately consumes the original closing div by opening a hidden no-op group.
        # Clean the no-op group at the next known controls anchor if present.
        client = client.replace(
            '<div class="control-group hidden" aria-hidden="true"><span class="control-label">\n            </div>',
            '',
            1
        )

        # replace the two auto-query listeners with dirty-only behavior and explicit query listener.
        listener_pattern = re.compile(
            r"\s*\$\('indicatorDate'\)\.addEventListener\('change', event => \{.*?\n\s*\}\);\n\s*\$\('indicatorSite'\)\.addEventListener\('change', event => \{.*?\n\s*\}\);",
            re.S
        )
        match = listener_pattern.search(client)
        if not match:
            raise RuntimeError('Indicator change listeners not found')
        listeners = r'''
    $('indicatorDate').addEventListener('change', event => {
      state.indicator.businessDate = event.target.value;
      state.indicator.building = '';
      state.indicator.floor = '';
      markIndicatorQueryDirty_();
    });
    $('indicatorSite').addEventListener('change', event => {
      state.indicator.site = event.target.value;
      state.indicator.building = '';
      state.indicator.floor = '';
      markIndicatorQueryDirty_();
    });
    $('indicatorQueryButton').addEventListener('click', () => {
      const businessDate = String($('indicatorDate')?.value || '').trim();
      const site = String($('indicatorSite')?.value || '').trim();
      if (!businessDate) return showToast('업무일자를 선택하세요.');
      if (!site) return showToast('사업장을 선택하세요.');
      state.indicator.businessDate = businessDate;
      state.indicator.site = site;
      state.indicator.queryDirty = false;
      state.indicator.queryApplied = true;
      state.indicator.version = 0;
      sessionStorage.setItem('novaIndicatorBusinessDate', businessDate);
      sessionStorage.setItem('novaIndicatorSite', site);
      loadIndicatorSnapshot({ force: true, silent: false });
    }); // SITE_SCOPE_INDICATOR_CLOSE_V2'''
        client = client[:match.start()] + listeners + client[match.end():]

        # helper before bindIndicatorShellEvents.
        helper_anchor = '  function bindIndicatorShellEvents() { // (통합 화면 이벤트 연결)'
        helper = r'''  function renderIndicatorAwaitingQuery_() { // (업무일자·사업장 확정 전 조회 대기화면)
    if ($('indicatorSummary')) $('indicatorSummary').innerHTML = '<span class="summary-pill">업무일자와 사업장을 선택한 후 조회하기를 눌러주세요.</span>';
    if ($('orderScroll')) $('orderScroll').innerHTML = '<div class="empty-state">조회 조건을 먼저 선택하세요.</div>';
    if ($('roomGrid')) $('roomGrid').innerHTML = '<div class="empty-state">업무일자 · 사업장 선택 후 조회하기</div>';
  }

  function markIndicatorQueryDirty_() { // (조건 변경만 기록하고 서버조회는 조회하기 버튼에서 1회 실행)
    state.indicator.queryDirty = true;
    state.indicator.queryApplied = false;
    state.indicator.loaded = false;
    state.indicator.data = null;
    state.indicator.version = 0;
    stopIndicatorSync();
    novaRealtimeStopIndicatorDbFallback_();
    renderIndicatorAwaitingQuery_();
    setSyncStatus('업무일자 · 사업장 선택 후 조회하기');
    if (novaRealtimeIsEnabled_()) void novaRealtimeEnsureSubscriptions_().catch(() => {});
  }

'''
        if helper_anchor not in client:
            raise RuntimeError('Indicator bind helper anchor missing')
        client = client.replace(helper_anchor, helper + helper_anchor, 1)

        # on successful snapshot, confirm query state.
        client = replace_once(
            client,
            "    state.indicator.loaded = true;\n    state.indicator.version = Number(result.version || 0);",
            "    state.indicator.loaded = true;\n    state.indicator.queryApplied = true;\n    state.indicator.queryDirty = false;\n    state.indicator.version = Number(result.version || 0);",
            'Indicator snapshot success state'
        )
        client = replace_once(
            client,
            "    siteSelect.innerHTML = `<option value=\"\">전체</option>${(data.sites || []).map(site => `<option value=\"${escapeAttr(site)}\">${escapeHtml(site)}</option>`).join('')}`;",
            "    siteSelect.innerHTML = `<option value=\"\">사업장 선택</option>${(data.sites || []).map(site => `<option value=\"${escapeAttr(site)}\">${escapeHtml(site)}</option>`).join('')}`;",
            'Indicator site options after load'
        )

        # Realtime should not subscribe before explicit query.
        client = replace_once(
            client,
            "    if (state.activeMenu === 'indicator' && ['ADMIN', 'ORDER'].includes(role)) {\n      const selected = String(state.indicator.site || '').trim();",
            "    if (state.activeMenu === 'indicator' && ['ADMIN', 'ORDER'].includes(role)) {\n      if (!state.indicator.queryApplied || state.indicator.queryDirty || !state.indicator.loaded) return []; // SITE_SCOPE_INDICATOR_CLOSE_V2\n      const selected = String(state.indicator.site || '').trim();",
            'Realtime relevant indicator sites'
        )
        client = replace_once(
            client,
            "      if (['ADMIN', 'ORDER'].includes(role) && state.activeMenu === 'indicator') {",
            "      if (['ADMIN', 'ORDER'].includes(role) && state.activeMenu === 'indicator' && state.indicator.queryApplied && state.indicator.loaded && !state.indicator.queryDirty) {",
            'Realtime indicator init gate'
        )
        write(client_path, client)

    # ------------------------------------------------------------------
    # 6) 마감일지 V2: 미마감은 Cloud Run/Postgres 현재객실 우선, 업무이력은 날짜 TextFinder.
    #    저장된 마감은 기존 Sheet signature 비교를 유지해 false stale을 방지합니다.
    # ------------------------------------------------------------------
    close_path = '19_RoommaidCloseJournal.js'
    close = read(close_path)
    if 'ROOMMAID_CLOSE_READ_ACCEL_V2' not in close:
        start = close.find('function getRoommaidCloseJournal(token, filters) {')
        end = close.find('function readRoommaidCloseCurrentSelection_(', start)
        if start < 0 or end < 0:
            raise RuntimeError('Close journal get/current anchors missing')
        replacement = r'''function getRoommaidCloseJournal(token, filters) { // (룸메이드 마감일지 조회 · ROOMMAID_CLOSE_READ_ACCEL_V2)
  return measureResponse_('getRoommaidCloseJournal', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = filters || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const requestedSite = String(safe.site || '').trim();
    const hasAttendanceOverride = Array.isArray(safe.attendanceEmployeeNos);
    const requestedAttendance = hasAttendanceOverride ? uniqueEmployeeNos_(safe.attendanceEmployeeNos) : [];
    const sites = getSiteList_();
    const defaultSite = String(user.defaultSite || '').trim();
    const preferredSite = requestedSite || (sites.includes(defaultSite) ? defaultSite : sites[0] || '');
    if (!preferredSite) throw new Error(`${businessDate} 조회할 사업장이 없습니다.`);
    if (!sites.includes(preferredSite)) throw new Error(`${preferredSite} 사업장을 확인할 수 없습니다.`);

    const sourceVersion = getSyncVersion_(['ROOM', 'ORDER', 'REPORT'], businessDate, preferredSite);
    const cacheKey = buildDeltaCacheKey_('ROOMMAID_CLOSE_READ_V2', [
      NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION,
      businessDate,
      preferredSite,
      String(user.employeeNo || ''),
      sourceVersion,
      hasAttendanceOverride ? requestedAttendance.slice().sort().join(',') : 'AUTO'
    ]);
    const cached = getCachedJson_(cacheKey);
    if (cached && cached.ok) {
      return Object.assign({}, cached, {
        optimization: Object.assign({}, cached.optimization || {}, { cacheHit: true })
      });
    }

    // 업무이력은 날짜 TextFinder로 후보행만 읽습니다. 전체 업무이력 열 스캔을 제거합니다.
    const historyBundle = readRoommaidCloseHistoryBundleFast_(businessDate, preferredSite);
    const historyRows = historyBundle.historyRows;
    const saved = historyBundle.saved;

    // 미마감 조회는 PostgreSQL 현재객실을 우선 사용합니다. 저장된 마감은 기존 Sheet 기반 sourceSignature를
    // 그대로 비교해야 과거 저장서명과 DB updated_at 차이로 false stale이 생기지 않습니다.
    let currentRows = [];
    let currentSource = 'SHEET';
    if (!saved) {
      try {
        currentRows = readRoommaidCloseRealtimeCurrentRows_(token, businessDate, preferredSite);
        if (currentRows.length) currentSource = 'REALTIME_DB';
      } catch (error) {
        currentRows = [];
      }
    }
    if (!currentRows.length) {
      const currentSelection = readRoommaidCloseCurrentSelection_(businessDate, preferredSite, defaultSite);
      currentRows = currentSelection.currentRows;
      currentSource = 'SHEET';
    }
    if (!currentRows.length) throw new Error(`${businessDate} ${preferredSite} 현재객실현황이 없습니다.`);

    const users = getUserIndex_().byEmployeeNo;
    const employmentIndex = readRoommaidCloseEmploymentIndex_();
    const inferredAttendance = inferRoommaidCloseAttendance_(currentRows, historyRows);
    const savedAttendance = saved && Array.isArray(saved.attendanceEmployeeNos) ? saved.attendanceEmployeeNos : [];
    const attendanceEmployeeNos = uniqueEmployeeNos_(
      hasAttendanceOverride ? requestedAttendance : (savedAttendance.length ? savedAttendance : inferredAttendance)
    );

    const liveSnapshot = buildDailyCloseSnapshot_(businessDate, preferredSite, {
      closedBy: saved ? saved.closedBy : '',
      closedByName: saved ? saved.closedByName : '',
      closedAt: saved ? saved.closedAt : '',
      includeRooms: false,
      currentRows,
      historyRows,
      attendanceEmployeeNos
    });
    const latestSourceAt = latestRoommaidCloseSourceAt_(currentRows, historyRows);
    const savedHasJournal = Boolean(saved && saved.roommaidCloseJournal);
    const savedJournalSchemaChanged = Boolean(
      savedHasJournal && Number(saved.roommaidCloseJournal.schemaVersion || 0) !== NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION
    );
    const signatureChanged = Boolean(saved && saved.sourceSignature && saved.sourceSignature !== liveSnapshot.sourceSignature);
    const legacyTimestampChanged = Boolean(saved && !saved.sourceSignature && saved.closedAt && latestSourceAt && latestSourceAt > saved.closedAt);
    const isStale = Boolean(saved && (!savedHasJournal || savedJournalSchemaChanged || signatureChanged || legacyTimestampChanged));
    const useSaved = Boolean(saved && !isStale && savedHasJournal && !hasAttendanceOverride);
    const selected = useSaved ? saved : liveSnapshot;
    const journal = selected.roommaidCloseJournal || liveSnapshot.roommaidCloseJournal;
    const baseWarning = journal && journal.initialStatusDetailAvailable
      ? ''
      : '해당 업무일자의 객실현황 업로드가 RC6.4 이전에 적용되어 최초 재고·퇴실의 객실별 상세가 없습니다. 현재 상태를 기준으로 보정 표시됩니다.';

    const result = {
      ok: true,
      businessDate,
      site: preferredSite,
      sites,
      source: saved ? (isStale ? 'CLOSED_STALE' : 'CLOSED') : 'LIVE',
      isClosed: Boolean(saved),
      isStale,
      closedAt: saved ? String(saved.closedAt || '') : '',
      closedBy: saved ? String(saved.closedByName || saved.closedBy || '') : '',
      latestSourceAt,
      attendanceEmployeeNos: uniqueEmployeeNos_(journal && journal.attendanceEmployeeNos || attendanceEmployeeNos),
      attendanceOptions: buildRoommaidCloseAttendanceOptions_(users, preferredSite, inferredAttendance, journal && journal.attendanceEmployeeNos || attendanceEmployeeNos, employmentIndex),
      journal,
      warning: baseWarning,
      message: saved
        ? (isStale ? '마감 이후 객실 또는 정비실적이 수정되었습니다. 수정 후 재마감이 필요합니다.' : '저장된 마감자료입니다.')
        : '실시간 미마감 자료입니다.',
      optimization: {
        marker: 'ROOMMAID_CLOSE_READ_ACCEL_V2',
        cacheHit: false,
        sourceVersion,
        currentSource,
        currentRowCount: currentRows.length,
        historyRowCount: historyRows.length,
        historyLookup: 'DATE_TEXTFINDER'
      }
    };
    putCachedJson_(cacheKey, result, Math.min(30, Number(NOVA.SNAPSHOT_CACHE_SECONDS || 45)));
    return result;
  });
}

function readRoommaidCloseRealtimeCurrentRows_(token, businessDate, site) { // (PostgreSQL 현재객실 조회 · 조회전용·실패시 Sheet fallback)
  const props = PropertiesService.getScriptProperties();
  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() === 'Y';
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  if (!enabled || !apiBase) return [];
  const query = `businessDate=${encodeURIComponent(String(businessDate || ''))}&site=${encodeURIComponent(String(site || ''))}`;
  const response = UrlFetchApp.fetch(`${apiBase}/v1/rooms?${query}`, {
    method: 'get',
    headers: { Authorization: `Bearer ${String(token || '').trim()}` },
    muteHttpExceptions: true,
    followRedirects: true
  });
  const status = Number(response.getResponseCode() || 0);
  let body = {};
  try { body = JSON.parse(response.getContentText() || '{}'); } catch (error) { body = {}; }
  if (status < 200 || status >= 300 || !body.ok || !Array.isArray(body.rooms)) return [];
  const seen = new Set();
  return body.rooms.map(raw => {
    const roomNo = String(raw && (raw.roomNo || raw.room_no) || '').trim();
    const roomSite = String(raw && raw.site || site || '').trim();
    const rowDate = String(raw && (raw.businessDate || raw.business_date) || businessDate || '').trim();
    if (!roomNo || roomSite !== site || rowDate !== businessDate) return null;
    const key = `${roomSite}|${roomNo}`;
    if (seen.has(key)) return null;
    seen.add(key);
    return {
      '업무일자': rowDate,
      '객실번호': roomNo,
      '사업장': roomSite,
      '동': String(raw.building || ''),
      '객실상태': String(raw.roomStatus ?? raw.room_status ?? ''),
      '청소상태': String(raw.cleaningStatus ?? raw.cleaning_status ?? ''),
      '정비유형': String(raw.cleaningType ?? raw.cleaning_type ?? NOVA.CLEANING_TYPES.NORMAL),
      '배정유형': String(raw.assignmentType ?? raw.assignment_type ?? NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO),
      '룸메이드사번': String(raw.roommaidEmployeeNo ?? raw.roommaid_employee_no ?? ''),
      '보조룸메이드사번': String(raw.secondaryRoommaidEmployeeNo ?? raw.secondary_roommaid_employee_no ?? ''),
      'QM사번': String(raw.qmEmployeeNo ?? raw.qm_employee_no ?? ''),
      '마지막변경버전': Number(raw.version || 0),
      '수정일시': String(raw.updatedAt ?? raw.updated_at ?? ''),
      '하우스맨상태': '',
      '하우스맨미완료수': '',
      '객실운영상태': String(raw.operationalStatus ?? raw.operational_status ?? '')
    };
  }).filter(Boolean);
}

function readRoommaidCloseHistoryBundleFast_(businessDate, site) { // (업무일자 후보행만 TextFinder로 읽기)
  const liveTypes = new Set([
    NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD,
    NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE,
    NOVA.RECORD_TYPES.CLEANING,
    NOVA.RECORD_TYPES.QM,
    NOVA.RECORD_TYPES.QM_CHECKLIST,
    NOVA.RECORD_TYPES.HOUSEMAN_ORDER,
    NOVA.RECORD_TYPES.DEPARTURE_DELAY
  ]);
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { historyRows: [], saved: null };
  const headerMap = getHeaderMap_(sheet);
  const dateColumn = headerMap['업무일자'];
  if (!dateColumn) return readRoommaidCloseHistoryBundle_(businessDate, site);

  let matches = [];
  try {
    matches = sheet.getRange(2, dateColumn, lastRow - 1, 1)
      .createTextFinder(String(businessDate || ''))
      .matchEntireCell(true)
      .findAll();
  } catch (error) {
    return readRoommaidCloseHistoryBundle_(businessDate, site);
  }
  const rowNumbers = matches.map(range => range.getRow()).filter(row => row >= 2);
  if (!rowNumbers.length) return { historyRows: [], saved: null };
  const rows = readRowsByNumbersForClose_(sheet, headerMap, rowNumbers);
  const historyRows = [];
  let saved = null;
  rows.forEach(data => {
    if (String(data['업무일자'] || '').trim() !== businessDate) return;
    if (site && String(data['사업장'] || '').trim() !== site) return;
    if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') return;
    const type = String(data['기록구분'] || '').trim();
    const status = String(data['처리상태'] || '').trim();
    if (liveTypes.has(type)) {
      historyRows.push(data);
      return;
    }
    if (type !== NOVA.RECORD_TYPES.DAILY_CLOSE || status !== NOVA_DAILY_CLOSE.SUMMARY_STATUS || saved) return;
    let detail = {};
    try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    if (detail.roommaidCloseJournal) detail.roommaidCloseJournal = expandRoommaidCloseJournalFromStorage_(detail.roommaidCloseJournal);
    saved = Object.assign({}, detail, {
      businessDate: String(data['업무일자'] || detail.businessDate || '').trim(),
      site: String(data['사업장'] || detail.site || '').trim(),
      closedAt: String(detail.closedAt || data['등록일시'] || '').trim(),
      closedBy: String(detail.closedBy || data['등록사번'] || '').trim()
    });
  });
  return { historyRows, saved };
}

'''
        close = close[:start] + replacement + close[end:]

        # 채용구분은 이미 캐시된 사용자 인덱스를 우선 사용해 사용자계정 시트 재읽기를 제거.
        employment_start = close.find('function readRoommaidCloseEmploymentIndex_()')
        employment_end = close.find('function parseRoommaidCloseEmploymentType_', employment_start)
        if employment_start < 0 or employment_end < 0:
            raise RuntimeError('Employment index anchors missing')
        employment_replacement = r'''function readRoommaidCloseEmploymentIndex_() { // (사용자 인덱스 채용구분 재사용 · ROOMMAID_CLOSE_READ_ACCEL_V2)
  const result = {};
  const users = getUserIndex_().byEmployeeNo || {};
  Object.keys(users).forEach(employeeNo => {
    result[employeeNo] = String(users[employeeNo] && users[employeeNo].employmentType || '').trim();
  });
  return result;
}

'''
        close = close[:employment_start] + employment_replacement + close[employment_end:]
        write(close_path, close)

    print('Applied SITE_SCOPE_INDICATOR_CLOSE_V2 patch.')
except Exception as exc:
    print(f'ERROR: {exc}', file=sys.stderr)
    sys.exit(88)
