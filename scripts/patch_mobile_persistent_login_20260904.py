from pathlib import Path
import re

# -----------------------------------------------------------------------------
# 1) Server authentication: keep existing 12h access token, add revocable
#    persistent mobile session used only to mint a fresh normal access token.
# -----------------------------------------------------------------------------
auth_path = Path('03_Auth.js')
auth = auth_path.read_text(encoding='utf-8')

old = """function loginNovaBootstrap(name, employeeNo, clientType, site) { // (로그인·초기화 1회 통신)
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
"""
new = """function loginNovaBootstrap(name, employeeNo, clientType, site, persistentLogin) { // (로그인·초기화 1회 통신)
  return measureResponse_('loginNovaBootstrap', () => {
    const user = authenticateNovaUser_(name, employeeNo, site);
    const token = createLoginToken_(user.employeeNo, user.sessionSite);
    const mobilePersistent = String(clientType || '').trim().toLowerCase() === 'mobile' && persistentLogin !== false;
    return {
      ok: true,
      token,
      persistentSessionToken: mobilePersistent ? createPersistentLoginSession_(user) : '',
      bootstrap: buildBootstrapPayload_(user, clientType)
    };
  });
}

const NOVA_PERSISTENT_SESSION_PREFIX_ = 'NOVA_PERSIST_SESSION_V1_';

function persistentLoginError_(message, code) { // (지속세션 오류코드 통일)
  const error = new Error(message);
  error.code = String(code || 'PERSISTENT_SESSION_INVALID');
  return error;
}

function persistentLoginPropertyKey_(sessionId) { // (원문 세션ID를 ScriptProperties 키에 노출하지 않음)
  const bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    String(sessionId || ''),
    Utilities.Charset.UTF_8
  );
  const digest = Utilities.base64EncodeWebSafe(bytes).replace(/=+$/g, '').slice(0, 40);
  return `${NOVA_PERSISTENT_SESSION_PREFIX_}${digest}`;
}

function encodePersistentLoginToken_(payload) { // (기존 NOVA 서명키를 사용하는 지속세션 토큰)
  const body = Utilities.base64EncodeWebSafe(JSON.stringify(payload), Utilities.Charset.UTF_8);
  return `${body}.${signTokenBody_(body)}`;
}

function parsePersistentLoginToken_(token) { // (지속세션 토큰 서명·형식 검증)
  const parts = String(token || '').split('.');
  if (parts.length !== 2) throw persistentLoginError_('저장된 로그인 세션이 올바르지 않습니다. 다시 로그인하세요.');
  const [body, signature] = parts;
  if (signTokenBody_(body) !== signature) {
    throw persistentLoginError_('저장된 로그인 세션이 변경되었습니다. 다시 로그인하세요.');
  }
  let payload;
  try {
    const json = Utilities.newBlob(Utilities.base64DecodeWebSafe(body)).getDataAsString('UTF-8');
    payload = JSON.parse(json);
  } catch (error) {
    throw persistentLoginError_('저장된 로그인 세션을 확인할 수 없습니다. 다시 로그인하세요.');
  }
  if (String(payload && payload.type || '') !== 'NOVA_PERSIST_V1'
      || !String(payload && payload.sessionId || '').trim()
      || !String(payload && payload.employeeNo || '').trim()) {
    throw persistentLoginError_('저장된 로그인 세션 정보가 부족합니다. 다시 로그인하세요.');
  }
  return payload;
}

function createPersistentLoginSession_(user) { // (모바일 명시 로그아웃 전까지 유지되는 서버 취소가능 세션)
  const sessionId = `${Utilities.getUuid()}${Utilities.getUuid()}`;
  const employeeNo = String(user && user.employeeNo || '').trim();
  const site = normalizeNovaLoginSite_(user && user.sessionSite);
  const now = Date.now();
  const record = {
    employeeNo,
    site,
    createdAt: now,
    lastUsedAt: now
  };
  PropertiesService.getScriptProperties().setProperty(
    persistentLoginPropertyKey_(sessionId),
    JSON.stringify(record)
  );
  return encodePersistentLoginToken_({
    type: 'NOVA_PERSIST_V1',
    sessionId,
    employeeNo,
    site,
    issuedAt: now
  });
}

function resolvePersistentLoginUser_(payload, record, propertyKey) { // (계정 비활성·사업장 변경은 지속세션도 즉시 차단)
  const employeeNo = String(record && record.employeeNo || '').trim();
  if (!employeeNo || employeeNo !== String(payload && payload.employeeNo || '').trim()) {
    PropertiesService.getScriptProperties().deleteProperty(propertyKey);
    throw persistentLoginError_('저장된 로그인 세션이 일치하지 않습니다. 다시 로그인하세요.');
  }
  const sourceUser = getActiveUserByEmployeeNo_(employeeNo);
  if (!sourceUser) {
    PropertiesService.getScriptProperties().deleteProperty(propertyKey);
    throw persistentLoginError_('사용할 수 없는 계정입니다. 다시 로그인하세요.', 'PERSISTENT_ACCOUNT_DISABLED');
  }
  const scopedRole = isNovaSiteScopedRole_(sourceUser.role);
  const tokenSite = normalizeNovaLoginSite_(record.site || payload.site);
  const configuredSite = normalizeNovaLoginSite_(sourceUser.defaultSite);
  if (scopedRole && tokenSite && configuredSite && tokenSite !== configuredSite) {
    PropertiesService.getScriptProperties().deleteProperty(propertyKey);
    throw persistentLoginError_('계정 사업장이 변경되었습니다. 다시 로그인하세요.', 'PERSISTENT_SITE_CHANGED');
  }
  const sessionSite = scopedRole ? (tokenSite || configuredSite) : '';
  return Object.assign({}, sourceUser, {
    sessionSite,
    siteScopeLocked: Boolean(scopedRole && sessionSite),
    defaultSite: sessionSite || sourceUser.defaultSite
  });
}

function resumePersistentLogin(persistentSessionToken, clientType) { // (모바일 지속세션으로 새 12시간 업무토큰 발급)
  return measureResponse_('resumePersistentLogin', () => {
    if (String(clientType || '').trim().toLowerCase() !== 'mobile') {
      throw persistentLoginError_('지속 로그인은 모바일 화면에서만 사용할 수 있습니다.', 'PERSISTENT_MOBILE_ONLY');
    }
    const payload = parsePersistentLoginToken_(persistentSessionToken);
    const propertyKey = persistentLoginPropertyKey_(payload.sessionId);
    const properties = PropertiesService.getScriptProperties();
    const raw = properties.getProperty(propertyKey);
    if (!raw) throw persistentLoginError_('로그아웃된 세션입니다. 다시 로그인하세요.', 'PERSISTENT_SESSION_REVOKED');
    let record;
    try { record = JSON.parse(raw); } catch (error) {
      properties.deleteProperty(propertyKey);
      throw persistentLoginError_('저장된 로그인 세션을 복원할 수 없습니다. 다시 로그인하세요.');
    }
    const user = resolvePersistentLoginUser_(payload, record, propertyKey);
    record.lastUsedAt = Date.now();
    properties.setProperty(propertyKey, JSON.stringify(record));
    const token = createLoginToken_(user.employeeNo, user.sessionSite);
    return {
      ok: true,
      token,
      persistentSessionToken: String(persistentSessionToken || ''),
      bootstrap: buildBootstrapPayload_(user, 'mobile')
    };
  });
}

function revokePersistentLogin(persistentSessionToken) { // (명시적 로그아웃 시 지속세션 서버 폐기)
  return measureResponse_('revokePersistentLogin', () => {
    if (!String(persistentSessionToken || '').trim()) return { ok: true, revoked: false };
    let payload;
    try { payload = parsePersistentLoginToken_(persistentSessionToken); }
    catch (error) { return { ok: true, revoked: false }; }
    const key = persistentLoginPropertyKey_(payload.sessionId);
    const properties = PropertiesService.getScriptProperties();
    const existed = Boolean(properties.getProperty(key));
    properties.deleteProperty(key);
    return { ok: true, revoked: existed };
  });
}

function authenticateNovaUser_(name, employeeNo, loginSite) { // (이름·사번·사업장 로그인 검증 공통)
"""
assert old in auth, 'Auth loginNovaBootstrap anchor not found'
auth = auth.replace(old, new, 1)
auth_path.write_text(auth, encoding='utf-8')

# -----------------------------------------------------------------------------
# 2) Login UI: opt-in remember name/employeeNo. Site is remembered internally
#    so a remembered ordinary employee can enter with one Login button tap.
# -----------------------------------------------------------------------------
index_path = Path('Index.html')
index = index_path.read_text(encoding='utf-8')
old = """      <label>
        <span>사번</span>
        <input id=\"loginEmployeeNo\" name=\"employeeNo\" type=\"password\" inputmode=\"numeric\" autocomplete=\"current-password\" required>
      </label>
      <button id=\"loginButton\" type=\"submit\">로그인</button>
"""
new = """      <label>
        <span>사번</span>
        <input id=\"loginEmployeeNo\" name=\"employeeNo\" type=\"password\" inputmode=\"numeric\" autocomplete=\"current-password\" required>
      </label>
      <label class=\"login-remember-option\">
        <input id=\"loginRemember\" type=\"checkbox\">
        <span><strong>이름·사번 저장</strong><small>개인 기기에서만 사용하세요.</small></span>
      </label>
      <button id=\"loginButton\" type=\"submit\">로그인</button>
"""
assert old in index, 'Index login employee anchor not found'
index = index.replace(old, new, 1)
index_path.write_text(index, encoding='utf-8')

styles_path = Path('Styles.html')
styles = styles_path.read_text(encoding='utf-8')
marker = '</style>'
assert marker in styles, 'Styles closing style not found'
css = """
  .login-remember-option {
    display: flex !important;
    align-items: center;
    gap: 9px;
    text-align: left;
    cursor: pointer;
  }
  .login-remember-option input {
    width: 18px !important;
    height: 18px;
    margin: 0;
    flex: 0 0 auto;
    accent-color: #171717;
  }
  .login-remember-option > span {
    display: grid;
    gap: 2px;
  }
  .login-remember-option strong { font-size: 13px; }
  .login-remember-option small { color: #6b7280; font-size: 11px; font-weight: 500; }
"""
if '.login-remember-option {' not in styles:
    styles = styles.replace(marker, css + marker, 1)
styles_path.write_text(styles, encoding='utf-8')

# -----------------------------------------------------------------------------
# 3) Client: local remembered credentials + persistent-session auto resume and
#    access-token refresh. Persistent session is mobile-only; desktop unchanged.
# -----------------------------------------------------------------------------
client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')

old = """  function init() { // (클라이언트 초기화)
    bindEvents();
    if (!state.token) return showView('loginView');
    loadBootstrap();
  }
"""
new = """  const NOVA_REMEMBER_LOGIN_KEY_ = 'novaRememberLoginV1';
  const NOVA_PERSISTENT_SESSION_KEY_ = 'novaPersistentSessionV1';
  let persistentLoginRefreshTimer_ = null;
  let persistentLoginRefreshInFlight_ = null;

  function isMobileLoginClient_() { // (지속로그인은 모바일 화면만)
    return window.matchMedia('(max-width: 760px)').matches;
  }

  function readRememberedLogin_() { // (사용자가 체크한 경우에만 기기 로컬정보 복원)
    try {
      const parsed = JSON.parse(localStorage.getItem(NOVA_REMEMBER_LOGIN_KEY_) || 'null');
      return parsed && parsed.enabled === true ? parsed : null;
    } catch (error) {
      return null;
    }
  }

  function restoreRememberedLogin_(clearWhenMissing = false) {
    const saved = readRememberedLogin_();
    const remember = $('loginRemember');
    if (remember) remember.checked = Boolean(saved);
    if (!saved) {
      if (clearWhenMissing) {
        if ($('loginName')) $('loginName').value = '';
        if ($('loginEmployeeNo')) $('loginEmployeeNo').value = '';
        if ($('loginSite')) $('loginSite').value = '';
      }
      return false;
    }
    if ($('loginName')) $('loginName').value = String(saved.name || '');
    if ($('loginEmployeeNo')) $('loginEmployeeNo').value = String(saved.employeeNo || '');
    if ($('loginSite')) $('loginSite').value = String(saved.site || '');
    return true;
  }

  function saveRememberedLogin_(name, employeeNo, site) {
    if (!$('loginRemember')?.checked) {
      localStorage.removeItem(NOVA_REMEMBER_LOGIN_KEY_);
      return false;
    }
    localStorage.setItem(NOVA_REMEMBER_LOGIN_KEY_, JSON.stringify({
      enabled: true,
      name: String(name || ''),
      employeeNo: String(employeeNo || ''),
      site: String(site || '')
    }));
    return true;
  }

  function persistentSessionToken_() {
    return String(localStorage.getItem(NOVA_PERSISTENT_SESSION_KEY_) || '').trim();
  }

  function setPersistentSessionToken_(token) {
    const value = String(token || '').trim();
    if (value) localStorage.setItem(NOVA_PERSISTENT_SESSION_KEY_, value);
    else localStorage.removeItem(NOVA_PERSISTENT_SESSION_KEY_);
  }

  function novaTokenExpiresAt_(token) { // (서명 검증은 서버가 담당, 클라이언트는 갱신시각 계산만)
    try {
      const body = String(token || '').split('.')[0] || '';
      if (!body) return 0;
      const base64 = body.replace(/-/g, '+').replace(/_/g, '/');
      const padded = base64 + '='.repeat((4 - base64.length % 4) % 4);
      const binary = window.atob(padded);
      const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
      const payload = JSON.parse(new TextDecoder('utf-8').decode(bytes));
      return Number(payload.expiresAt || 0);
    } catch (error) {
      return 0;
    }
  }

  function schedulePersistentLoginRefresh_() { // (12시간 업무토큰 만료 30분 전 자동교체)
    if (persistentLoginRefreshTimer_) window.clearTimeout(persistentLoginRefreshTimer_);
    persistentLoginRefreshTimer_ = null;
    if (!isMobileLoginClient_() || !state.token || !persistentSessionToken_()) return;
    const expiresAt = novaTokenExpiresAt_(state.token);
    const fallbackDelay = 6 * 60 * 60 * 1000;
    const delay = expiresAt
      ? Math.max(60 * 1000, expiresAt - Date.now() - 30 * 60 * 1000)
      : fallbackDelay;
    persistentLoginRefreshTimer_ = window.setTimeout(() => {
      persistentLoginRefreshTimer_ = null;
      void refreshPersistentLogin_(false);
    }, Math.min(delay, 0x7fffffff));
  }

  async function refreshPersistentLogin_(applyBootstrap) { // (지속세션 → 새 일반 업무토큰)
    if (!isMobileLoginClient_()) return false;
    const persistentToken = persistentSessionToken_();
    if (!persistentToken) return false;
    if (persistentLoginRefreshInFlight_) return persistentLoginRefreshInFlight_;

    const task = (async () => {
      try {
        const result = await callServer('resumePersistentLogin', persistentToken, 'mobile');
        if (!result?.ok || !result.token) {
          const code = String(result?.code || '');
          if (code.startsWith('PERSISTENT_')) {
            setPersistentSessionToken_('');
            state.token = '';
            localStorage.removeItem('novaToken');
          }
          return false;
        }
        state.token = result.token;
        localStorage.setItem('novaToken', result.token);
        if (result.persistentSessionToken) setPersistentSessionToken_(result.persistentSessionToken);
        schedulePersistentLoginRefresh_();
        if (applyBootstrap && result.bootstrap?.ok) {
          applyBootstrapResult_(result.bootstrap, 0, result.performance?.elapsedMs);
        }
        return true;
      } catch (error) {
        console.warn('[NOVA] 모바일 지속로그인 갱신 지연:', error);
        return false;
      }
    })();
    persistentLoginRefreshInFlight_ = task;
    try { return await task; }
    finally {
      if (persistentLoginRefreshInFlight_ === task) persistentLoginRefreshInFlight_ = null;
    }
  }

  async function init() { // (클라이언트 초기화)
    bindEvents();
    restoreRememberedLogin_();
    if (!state.token) {
      if (isMobileLoginClient_() && persistentSessionToken_()) {
        showView('loadingView');
        if (await refreshPersistentLogin_(true)) return;
      }
      showView('loginView');
      return;
    }
    await loadBootstrap();
  }
"""
assert old in client, 'Client init anchor not found'
client = client.replace(old, new, 1)

old = """      const result = await callServer('loginNovaBootstrap', name, employeeNo, clientType, site);
      const networkElapsed = Math.round(performance.now() - startedAt);
      if (!result || !result.ok || !result.bootstrap?.ok) {
        $('loginMessage').textContent = result?.message || result?.bootstrap?.message || '로그인하지 못했습니다.';
        return;
      }
      state.token = result.token;
      localStorage.setItem('novaToken', result.token);
      applyBootstrapResult_(result.bootstrap, networkElapsed, result.performance?.elapsedMs);
"""
new = """      const result = await callServer('loginNovaBootstrap', name, employeeNo, clientType, site, clientType === 'mobile');
      const networkElapsed = Math.round(performance.now() - startedAt);
      if (!result || !result.ok || !result.bootstrap?.ok) {
        $('loginMessage').textContent = result?.message || result?.bootstrap?.message || '로그인하지 못했습니다.';
        return;
      }
      state.token = result.token;
      localStorage.setItem('novaToken', result.token);
      saveRememberedLogin_(name, employeeNo, site);
      if (clientType === 'mobile' && result.persistentSessionToken) {
        setPersistentSessionToken_(result.persistentSessionToken);
      } else if (clientType !== 'mobile') {
        setPersistentSessionToken_('');
      }
      schedulePersistentLoginRefresh_();
      applyBootstrapResult_(result.bootstrap, networkElapsed, result.performance?.elapsedMs);
"""
assert old in client, 'Client handleLogin anchor not found'
client = client.replace(old, new, 1)

old = """        if (result?.code === 'UNAUTHORIZED') {
          state.token = '';
          localStorage.removeItem('novaToken');
          showView('loginView');
          $('loginMessage').textContent = result?.message || '다시 로그인해 주세요.';
          return;
        }
"""
new = """        if (result?.code === 'UNAUTHORIZED') {
          if (clientType === 'mobile' && persistentSessionToken_() && await refreshPersistentLogin_(true)) return;
          state.token = '';
          localStorage.removeItem('novaToken');
          showView('loginView');
          restoreRememberedLogin_();
          $('loginMessage').textContent = result?.message || '다시 로그인해 주세요.';
          return;
        }
"""
assert old in client, 'Client loadBootstrap unauthorized anchor not found'
client = client.replace(old, new, 1)

# Schedule refresh whenever a valid bootstrap is applied.
old = """    renderApp();
    setSyncStatus(`초기 로딩 ${networkElapsed}ms · 서버 ${serverElapsed ?? '-'}ms`);
    void initNovaRealtime_();
"""
new = """    renderApp();
    schedulePersistentLoginRefresh_();
    setSyncStatus(`초기 로딩 ${networkElapsed}ms · 서버 ${serverElapsed ?? '-'}ms`);
    void initNovaRealtime_();
"""
assert old in client, 'Client applyBootstrap anchor not found'
client = client.replace(old, new, 1)

# On return from mobile background, renew before subsequent sync if token is near expiry.
old = """  function handleVisibilityChange_() { // (백그라운드 탭 서버요청 중지·복귀 분산)
    if (document.hidden) {
      stopIndicatorSync();
      stopMobileSync();
      return;
    }
"""
new = """  function handleVisibilityChange_() { // (백그라운드 탭 서버요청 중지·복귀 분산)
    if (document.hidden) {
      stopIndicatorSync();
      stopMobileSync();
      return;
    }
    if (isMobileLoginClient_() && persistentSessionToken_()) {
      const expiresAt = novaTokenExpiresAt_(state.token);
      if (!expiresAt || expiresAt - Date.now() < 60 * 60 * 1000) void refreshPersistentLogin_(false);
    }
"""
assert old in client, 'Client visibility anchor not found'
client = client.replace(old, new, 1)

# Replace explicit logout block while preserving the following ORDER context marker.
pattern = re.compile(r"  function handleLogout\(\) \{ // \(명시적 로그아웃\).*?\n  \}\n\n  /\* ORDER_SHARED_SITE_CONTEXT_V1", re.S)
match = pattern.search(client)
assert match, 'Client handleLogout block not found'
new_logout = """  function handleLogout() { // (명시적 로그아웃 · 모바일 지속세션도 함께 폐기)
    saveUiState();
    stopIndicatorSync();
    stopMobileSync();
    void novaRealtimeDisconnect_();
    novaRealtime_.enabled = false;
    novaRealtime_.apiBase = '';
    novaRealtime_.configLoaded = false;
    if (persistentLoginRefreshTimer_) window.clearTimeout(persistentLoginRefreshTimer_);
    persistentLoginRefreshTimer_ = null;
    const persistentToken = persistentSessionToken_();
    setPersistentSessionToken_('');
    state.token = '';
    state.bootstrap = null;
    localStorage.removeItem('novaToken');
    showView('loginView');
    restoreRememberedLogin_(true);
    $('loginMessage').textContent = '';
    if (persistentToken) {
      void callServer('revokePersistentLogin', persistentToken)
        .catch(error => console.warn('[NOVA] 지속세션 서버 로그아웃 지연:', error));
    }
  }

  /* ORDER_SHARED_SITE_CONTEXT_V1"""
client = client[:match.start()] + new_logout + client[match.end():]
client_path.write_text(client, encoding='utf-8')

print('Mobile persistent login + remembered credentials patch applied.')
