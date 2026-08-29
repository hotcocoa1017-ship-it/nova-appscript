/**
 * 웹앱 진입 및 공통 초기 API
 */
function doGet(e) { // (웹앱 진입)
  // TEMP 2026-08-29: Cloud Run Realtime 토큰 재검증. 결과 확인 즉시 제거합니다.
  const diagnosticKey = 'p6M8v2ZqY7xC4nR9sT1uK5wF0hJ3bL';
  if (e && e.parameter && String(e.parameter.nova_diag || '') === diagnosticKey) {
    return ContentService
      .createTextOutput(JSON.stringify(runNovaRealtimeLiveDiagnostic_()))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // TEMP 2026-08-29: Apps Script가 실제로 참조하는 공개 Cloud Run 호스트 비교용.
  const apiHostDiagnosticKey = 'NOVA-RT-HOST-20260829-k9x7p2';
  if (e && e.parameter && String(e.parameter.nova_api_host || '') === apiHostDiagnosticKey) {
    const apiBase = String(PropertiesService.getScriptProperties().getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
    const host = apiBase.replace(/^https?:\/\//i, '').split('/')[0];
    return ContentService.createTextOutput(JSON.stringify({ ok: Boolean(host), host: host })).setMimeType(ContentService.MimeType.JSON);
  }

  const template = HtmlService.createTemplateFromFile('Index');
  template.appName = NOVA.APP_NAME;
  template.version = NOVA.VERSION;
  return template.evaluate()
    .setTitle(NOVA.APP_NAME)
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, viewport-fit=cover');
}

function include_(filename) { // (HTML 부분파일 포함)
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

function getBootstrap(token, clientType) { // (로그인 후 최소 초기데이터 조회)
  return measureResponse_('getBootstrap', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) {
      return { ok: false, code: 'UNAUTHORIZED', message: auth.message || '로그인이 필요합니다.' };
    }
    return buildBootstrapPayload_(auth.user, clientType);
  });
}

function buildBootstrapPayload_(user, clientType) { // (권한별 초기 화면 데이터 구성)
  const role = String(user.role || '').toUpperCase();
  return {
    ok: true,
    app: {
      name: NOVA.APP_NAME,
      version: NOVA.VERSION,
      businessDate: businessDateText_(),
      serverTime: nowText_(),
      performanceLimitMs: NOVA.PERFORMANCE_LIMIT_MS,
      indicatorSyncMs: NOVA.INDICATOR_SYNC_MS,
      orderVisibleRows: NOVA.ORDER_VISIBLE_ROWS,
      mobileSyncMs: NOVA.MOBILE_SYNC_MS,
      syncJitterRatio: NOVA.SYNC_JITTER_RATIO
    },
    user: getPublicUser_(user),
    clientType: clientType === 'mobile' ? 'mobile' : 'desktop',
    defaultMenu: getDefaultMenuForRole_(role, clientType),
    menu: getMenuForRole_(role)
  };
}


function getDefaultMenuForRole_(role, clientType) { // (권한·기기별 첫 화면)
  const normalized = String(role || '').toUpperCase();
  const map = {
    ADMIN: 'indicator', ORDER: 'indicator', QM: 'qm', HOUSEMAN: 'houseman',
    ROOMMAID: 'cleaning', PUBLIC: 'public'
  };
  return map[normalized] || 'home';
}
function getMenuForRole_(role) { // (권한별 최소 메뉴 구성)
  const common = [{ id: 'home', label: '홈' }];
  const menus = {
    ADMIN: [
      { id: 'indicator', label: '통합 인디케이터' },
      { id: 'departure', label: '퇴실지연' },
      { id: 'monthly', label: '월별조회' },
      { id: 'roommaidStats', label: '룸메이드 실적' },
      { id: 'roommaidClose', label: '룸메이드 마감일지' },
      { id: 'adminMetrics', label: '운영 성과지표' },
      { id: 'shifts', label: '근무조 관리' },
      { id: 'qmChecklist', label: 'QM 체크리스트' },
      { id: 'settings', label: '설정' }
    ],
    ORDER: [
      { id: 'indicator', label: '통합 인디케이터' },
      { id: 'departure', label: '퇴실지연' },
      { id: 'monthly', label: '월별조회' },
      { id: 'roommaidStats', label: '룸메이드 실적' },
      { id: 'roommaidClose', label: '룸메이드 마감일지' },
      { id: 'shifts', label: '근무조 관리' },
      { id: 'qmChecklist', label: 'QM 체크리스트' }
    ],
    QM: [{ id: 'qm', label: 'QM 점검' }],
    HOUSEMAN: [{ id: 'houseman', label: '하우스맨 오더' }],
    ROOMMAID: [{ id: 'cleaning', label: '오늘의 정비' }, { id: 'roommaidStats', label: '내 정비실적' }],
    PUBLIC: [{ id: 'public', label: '퇴실 여부 조회' }]
  };
  return common.concat(menus[String(role || '').toUpperCase()] || []);
}

function invalidateUserAccountCache(token) { // (사용자계정 수정 후 캐시 갱신)
  const auth = verifyNovaToken(token);
  if (!auth.ok || auth.user.role !== 'ADMIN') throw new Error('관리자 권한이 필요합니다.');
  clearNovaCaches_();
  return { ok: true, message: '사용자계정 캐시를 갱신했습니다.' };
}
