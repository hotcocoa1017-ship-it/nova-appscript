from pathlib import Path
import sys

MARKER = 'HOUSEMAN_REALTIME_PUSH_V1'
path = Path('Client.html')
text = path.read_text(encoding='utf-8')

if MARKER in text:
    print('Houseman Realtime Push V1 already applied.')
    raise SystemExit(0)

# 1) HOUSEMAN 모바일도 로그인 사업장 Realtime 채널 구독 대상으로 포함합니다.
old_mobile_role = """    const mobileRealtimeRole = (state.activeMenu === 'cleaning' && role === 'ROOMMAID')
      || (state.activeMenu === 'qm' && role === 'QM');"""
new_mobile_role = """    const mobileRealtimeRole = (state.activeMenu === 'cleaning' && role === 'ROOMMAID')
      || (state.activeMenu === 'qm' && role === 'QM')
      || (state.activeMenu === 'houseman' && role === 'HOUSEMAN'); // HOUSEMAN_REALTIME_PUSH_V1"""
if old_mobile_role not in text:
    print('ERROR: mobile Realtime role anchor not found.', file=sys.stderr)
    raise SystemExit(90)
text = text.replace(old_mobile_role, new_mobile_role, 1)

# 2) 하우스맨 화면 진입 시 Polling과 별개로 private Broadcast 구독을 보장합니다.
old_start_mobile = """  function startMobileSync() { // (지터 기반 모바일 동기화 시작)
    stopMobileSync();
    if (!['qm', 'houseman', 'cleaning', 'public'].includes(state.activeMenu)) return;
    scheduleMobileSync_();
  }"""
new_start_mobile = """  function startMobileSync() { // (지터 기반 모바일 동기화 시작)
    stopMobileSync();
    if (!['qm', 'houseman', 'cleaning', 'public'].includes(state.activeMenu)) return;
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').toUpperCase();
    if (novaRealtimeIsEnabled_() && role === 'HOUSEMAN' && state.activeMenu === 'houseman') {
      // HOUSEMAN_REALTIME_PUSH_V1 · 신규/재배정 오더는 Push 우선, 3~3.7초 DB 조회는 fallback 유지
      void novaRealtimeEnsureSubscriptions_().catch(error => {
        console.warn('[NOVA Realtime] 하우스맨 Push 구독 실패 · DB 주기조회로 계속 동작합니다.', error);
      });
    }
    scheduleMobileSync_();
  }"""
if old_start_mobile not in text:
    print('ERROR: startMobileSync anchor not found.', file=sys.stderr)
    raise SystemExit(91)
text = text.replace(old_start_mobile, new_start_mobile, 1)

# 3) nova_houseman_orders INSERT/UPDATE Broadcast 수신 즉시 본인 DB 목록을 재조회합니다.
# payload를 그대로 화면에 넣지 않고 기존 인증된 /v1/houseman-orders 조회를 다시 사용하여
# 후보/배정 권한과 최신 상태를 서버 기준으로 확정합니다.
old_handler = """  function novaRealtimeHandleHousemanOrderBroadcast_(payload) { // (관리자간 신규 오더 즉시 전파)
    if (state.activeMenu !== 'indicator' || !state.indicator.data) return;
    const raw = novaRealtimeBroadcastRow_(payload);
    if (!raw || !(raw.order_id || raw.orderId)) return;
    const order = novaRealtimeMapHousemanOrder_(raw);"""
new_handler = """  let novaHousemanPushRefreshTimer_ = null;

  function novaRealtimeScheduleHousemanPushRefresh_() { // HOUSEMAN_REALTIME_PUSH_V1 · Push 수신 즉시 안전 재조회
    if (novaHousemanPushRefreshTimer_) window.clearTimeout(novaHousemanPushRefreshTimer_);
    novaHousemanPushRefreshTimer_ = window.setTimeout(async () => {
      novaHousemanPushRefreshTimer_ = null;
      const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').toUpperCase();
      if (role !== 'HOUSEMAN' || state.activeMenu !== 'houseman' || document.hidden || !state.mobile.loaded) return;
      if (state.mobile.loading || state.mobile.syncInFlight || state.mobile.actionInFlight) {
        novaHousemanPushRefreshTimer_ = window.setTimeout(novaRealtimeScheduleHousemanPushRefresh_, 250);
        return;
      }
      try {
        await syncMobileDelta();
      } catch (error) {
        console.warn('[NOVA Realtime] 하우스맨 Push 즉시조회 실패 · 주기조회로 복구합니다.', error);
      }
    }, 80);
  }

  function novaRealtimeHandleHousemanOrderBroadcast_(payload) { // (관리자 + HOUSEMAN 신규/재배정 오더 즉시 전파 · HOUSEMAN_REALTIME_PUSH_V1)
    const raw = novaRealtimeBroadcastRow_(payload);
    if (!raw || !(raw.order_id || raw.orderId)) return;

    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').toUpperCase();
    if (role === 'HOUSEMAN' && state.activeMenu === 'houseman') {
      const selectedSite = String(state.mobile.site || state.bootstrap?.user?.defaultSite || '').trim();
      const selectedDate = String(state.mobile.businessDate || state.bootstrap?.app?.businessDate || '').trim();
      const rowSite = String(raw.site || '').trim();
      const rowDate = String(raw.business_date || raw.businessDate || '').trim();
      if ((!rowSite || !selectedSite || rowSite === selectedSite)
          && (!rowDate || !selectedDate || rowDate === selectedDate)) {
        novaRealtimeScheduleHousemanPushRefresh_();
      }
      return;
    }

    if (state.activeMenu !== 'indicator' || !state.indicator.data) return;
    const order = novaRealtimeMapHousemanOrder_(raw);"""
if old_handler not in text:
    print('ERROR: houseman broadcast handler anchor not found.', file=sys.stderr)
    raise SystemExit(92)
text = text.replace(old_handler, new_handler, 1)

# 안전 검증: 기존 fallback 폴링 및 DB 직접조회 경로는 반드시 보존합니다.
required = [
    "delay = 3000 + Math.round(Math.random() * 700);",
    "novaRealtimeLoadHousemanOrders_(businessDate, site)",
    ".on('broadcast', { event: 'INSERT' }",
    ".on('broadcast', { event: 'UPDATE' }",
    "HOUSEMAN_REALTIME_PUSH_V1",
]
missing = [item for item in required if item not in text]
if missing:
    print('ERROR: Houseman Push safety validation failed: ' + ', '.join(missing), file=sys.stderr)
    raise SystemExit(93)

path.write_text(text, encoding='utf-8')
print('Applied HOUSEMAN_REALTIME_PUSH_V1: Push-first mobile refresh with polling fallback.')
