from pathlib import Path

CLIENT = Path('Client.html')
text = CLIENT.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    text = text.replace(old, new, 1)

# 1) HOUSEMAN PostgreSQL direct-read helper.
old_load_rooms = """  async function novaRealtimeLoadRoomsForSite_(businessDate, site) {
    if (!businessDate || !site) return [];
    const query = new URLSearchParams({ businessDate: String(businessDate), site: String(site) });
    const result = await novaRealtimeFetch_(`/v1/rooms?${query.toString()}`);
    return Array.isArray(result.rooms) ? result.rooms : [];
  }
"""
new_load_rooms = old_load_rooms + """
  async function novaRealtimeLoadHousemanOrders_(businessDate, site) { // (HOUSEMAN 본인 배정오더 DB 직접조회)
    if (!businessDate || !site) return [];
    const query = new URLSearchParams({ businessDate: String(businessDate), site: String(site) });
    const result = await novaRealtimeFetch_(`/v1/houseman-orders?${query.toString()}`);
    return Array.isArray(result.orders) ? result.orders : [];
  }
"""
replace_once(old_load_rooms, new_load_rooms, 'houseman DB read helper')

# 2) ROOMMAID + QM: DB result is the current assignment list itself, so rebuild rather than map-only.
old_assigned_branch = """      if (role === 'ROOMMAID' && state.activeMenu === 'cleaning') {
        // /v1/rooms는 ROOMMAID 토큰이면 DB에서 본인 배정객실만 반환한다.
        // 기존 모바일 배열을 map()만 하면 신규 배정객실을 추가할 수 없으므로,
        // DB의 현재 배정목록 자체를 기준으로 목록을 재구성한다.
        const employeeNo = String(state.bootstrap.user?.employeeNo || '').trim();
        const employeeName = String(state.bootstrap.user?.name || '').trim();
        const legacyMap = new Map((state.mobile.data.rooms || []).map(room => [`${room.site}|${room.roomNo}`, room]));
        state.mobile.data.rooms = realtimeRows.map(rawRoom => {
          const realtimeRoom = novaRealtimeMapPartialRoom_(rawRoom);
          const key = `${realtimeRoom.site}|${realtimeRoom.roomNo}`;
          const legacyRoom = legacyMap.get(key);
          if (legacyRoom) return novaRealtimeMergeRoom_(legacyRoom, realtimeRoom);

          const primaryNo = String(realtimeRoom.roommaidEmployeeNo || '').trim();
          const secondaryNo = String(realtimeRoom.secondaryRoommaidEmployeeNo || '').trim();
          return Object.assign({
            rowNumber: 0,
            roommaidName: primaryNo === employeeNo ? employeeName : primaryNo,
            secondaryRoommaidName: secondaryNo === employeeNo ? employeeName : secondaryNo,
            qmName: String(realtimeRoom.qmEmployeeNo || '').trim(),
            pendingOrderCount: 0,
            __sheetVersion: 0
          }, realtimeRoom);
        });
      } else {
"""
new_assigned_branch = """      const assignedRoomMobile = (role === 'ROOMMAID' && state.activeMenu === 'cleaning')
        || (role === 'QM' && state.activeMenu === 'qm');
      if (assignedRoomMobile) {
        // /v1/rooms는 ROOMMAID/QM 토큰이면 DB에서 본인 배정객실만 반환한다.
        // 신규 배정·재배정·배정취소를 Sheet 미러와 무관하게 반영하도록 목록 자체를 재구성한다.
        const employeeNo = String(state.bootstrap.user?.employeeNo || '').trim();
        const employeeName = String(state.bootstrap.user?.name || '').trim();
        const legacyMap = new Map((state.mobile.data.rooms || []).map(room => [`${room.site}|${room.roomNo}`, room]));
        state.mobile.data.rooms = realtimeRows.map(rawRoom => {
          const realtimeRoom = novaRealtimeMapPartialRoom_(rawRoom);
          const key = `${realtimeRoom.site}|${realtimeRoom.roomNo}`;
          const legacyRoom = legacyMap.get(key);
          if (legacyRoom) return novaRealtimeMergeRoom_(legacyRoom, realtimeRoom);

          const primaryNo = String(realtimeRoom.roommaidEmployeeNo || '').trim();
          const secondaryNo = String(realtimeRoom.secondaryRoommaidEmployeeNo || '').trim();
          const qmNo = String(realtimeRoom.qmEmployeeNo || '').trim();
          return Object.assign({
            rowNumber: 0,
            roommaidName: role === 'ROOMMAID' && primaryNo === employeeNo ? employeeName : primaryNo,
            secondaryRoommaidName: role === 'ROOMMAID' && secondaryNo === employeeNo ? employeeName : secondaryNo,
            qmName: role === 'QM' && qmNo === employeeNo ? employeeName : qmNo,
            pendingOrderCount: 0,
            __sheetVersion: 0
          }, realtimeRoom);
        });
      } else {
"""
replace_once(old_assigned_branch, new_assigned_branch, 'QM assigned list rebuild')

# 3) Persist selected business dates in this browser tab/session.
replace_once("      businessDate: '',\n      site: '',\n      filter: 'ALL',", "      businessDate: sessionStorage.getItem('novaIndicatorBusinessDate') || '',\n      site: '',\n      filter: 'ALL',", 'indicator state business date')
replace_once("      businessDate: '',\n      site: '',\n      filter: 'ACTIVE',", "      businessDate: sessionStorage.getItem('novaMobileBusinessDate') || '',\n      site: '',\n      filter: 'ACTIVE',", 'mobile state business date')

old_save_ui = """  function saveUiState() { // (스크롤 및 메뉴 위치 저장)
    sessionStorage.setItem('novaScrollY', String(window.scrollY || 0));
    sessionStorage.setItem('novaActiveMenu', state.activeMenu);
  }
"""
new_save_ui = """  function saveUiState() { // (스크롤·메뉴·선택 업무일자 저장)
    sessionStorage.setItem('novaScrollY', String(window.scrollY || 0));
    sessionStorage.setItem('novaActiveMenu', state.activeMenu);
    if (state.indicator.businessDate) sessionStorage.setItem('novaIndicatorBusinessDate', state.indicator.businessDate);
    if (state.mobile.businessDate) sessionStorage.setItem('novaMobileBusinessDate', state.mobile.businessDate);
  }
"""
replace_once(old_save_ui, new_save_ui, 'save selected business dates')

old_indicator_change = """    $('indicatorDate').addEventListener('change', event => {
      state.indicator.businessDate = event.target.value;
      state.indicator.building = '';
"""
new_indicator_change = """    $('indicatorDate').addEventListener('change', event => {
      state.indicator.businessDate = event.target.value;
      if (state.indicator.businessDate) sessionStorage.setItem('novaIndicatorBusinessDate', state.indicator.businessDate);
      state.indicator.building = '';
"""
replace_once(old_indicator_change, new_indicator_change, 'indicator date change persistence')

old_mobile_change = """    $('mobileDate').addEventListener('change', event => {
      state.mobile.businessDate = event.target.value;
      state.mobile.building = '';
"""
new_mobile_change = """    $('mobileDate').addEventListener('change', event => {
      state.mobile.businessDate = event.target.value;
      if (state.mobile.businessDate) sessionStorage.setItem('novaMobileBusinessDate', state.mobile.businessDate);
      state.mobile.building = '';
"""
replace_once(old_mobile_change, new_mobile_change, 'mobile date change persistence')

old_indicator_apply = """    state.indicator.businessDate = result.selection?.businessDate || state.indicator.businessDate;
    state.indicator.site = result.selection?.site ?? state.indicator.site;
"""
new_indicator_apply = """    state.indicator.businessDate = result.selection?.businessDate || state.indicator.businessDate;
    if (state.indicator.businessDate) sessionStorage.setItem('novaIndicatorBusinessDate', state.indicator.businessDate);
    state.indicator.site = result.selection?.site ?? state.indicator.site;
"""
replace_once(old_indicator_apply, new_indicator_apply, 'indicator snapshot date persistence')

old_mobile_apply = """    state.mobile.businessDate = result.selection?.businessDate || state.mobile.businessDate || state.bootstrap.app.businessDate;
    state.mobile.site = result.selection?.site ?? state.mobile.site;
    renderMobileData();
    if (novaRealtimeIsEnabled_() && state.bootstrap?.user?.role === 'ROOMMAID') {
      // 무료모드: 모바일은 DB hydrate만 하고 Realtime 채널은 열지 않습니다.
      void novaRealtimeHydrateCurrentView_();
    }
"""
new_mobile_apply = """    state.mobile.businessDate = result.selection?.businessDate || state.mobile.businessDate || state.bootstrap.app.businessDate;
    if (state.mobile.businessDate) sessionStorage.setItem('novaMobileBusinessDate', state.mobile.businessDate);
    state.mobile.site = result.selection?.site ?? state.mobile.site;
    renderMobileData();
    const mobileRole = String(state.bootstrap?.user?.role || '').toUpperCase();
    if (novaRealtimeIsEnabled_() && ['ROOMMAID', 'QM'].includes(mobileRole)) {
      // ROOMMAID/QM은 Sheet 첫 화면 이후 DB의 본인 배정목록을 바로 보정한다.
      void novaRealtimeHydrateCurrentView_();
    } else if (novaRealtimeIsEnabled_() && mobileRole === 'HOUSEMAN') {
      // HOUSEMAN도 첫 Sheet 화면 직후 DB 배정목록을 바로 보조조회한다.
      window.setTimeout(() => { void syncMobileDelta(); }, 0);
    }
"""
replace_once(old_mobile_apply, new_mobile_apply, 'mobile initial DB hydrate')

# 4) Mobile cadence: ROOMMAID remains as verified; QM/HOUSEMAN target <5 seconds.
old_schedule = """  function scheduleMobileSync_() { // (직원별 요청시점 분산)
    if (document.hidden || !['qm', 'houseman', 'cleaning', 'public'].includes(state.activeMenu) || !state.mobile.loaded) return;
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').toUpperCase();
    const roommaidRealtime = novaRealtimeIsEnabled_() && role === 'ROOMMAID' && state.activeMenu === 'cleaning';
    const base = roommaidRealtime
      ? 5000
      : Number(state.bootstrap.app.mobileSyncMs || 16000);
    // ROOMMAID Realtime 조회는 서버에서 본인 배정객실만 반환하므로 5초 주기로 경량 조회한다.
    // 0~1.2초 지터로 다수 단말의 동시 요청을 분산한다.
    const delay = roommaidRealtime
      ? base + Math.round(Math.random() * 1200)
      : nextSyncDelay_(base);
    state.mobile.syncTimer = window.setTimeout(async () => {
      state.mobile.syncTimer = null;
      await syncMobileDelta();
      scheduleMobileSync_();
    }, delay);
  }
"""
new_schedule = """  function scheduleMobileSync_() { // (직원별 요청시점 분산)
    if (document.hidden || !['qm', 'houseman', 'cleaning', 'public'].includes(state.activeMenu) || !state.mobile.loaded) return;
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').toUpperCase();
    const roommaidRealtime = novaRealtimeIsEnabled_() && role === 'ROOMMAID' && state.activeMenu === 'cleaning';
    const qmRealtime = novaRealtimeIsEnabled_() && role === 'QM' && state.activeMenu === 'qm';
    const housemanRealtime = novaRealtimeIsEnabled_() && role === 'HOUSEMAN' && state.activeMenu === 'houseman';
    let delay;
    if (roommaidRealtime) {
      // 검증 완료된 ROOMMAID는 기존 5.0~6.2초를 유지한다.
      delay = 5000 + Math.round(Math.random() * 1200);
    } else if (qmRealtime || housemanRealtime) {
      // QM/HOUSEMAN은 본인 배정목록만 경량조회하므로 3.0~3.7초로 분산한다.
      delay = 3000 + Math.round(Math.random() * 700);
    } else {
      delay = nextSyncDelay_(Number(state.bootstrap.app.mobileSyncMs || 16000));
    }
    state.mobile.syncTimer = window.setTimeout(async () => {
      state.mobile.syncTimer = null;
      await syncMobileDelta();
      scheduleMobileSync_();
    }, delay);
  }
"""
replace_once(old_schedule, new_schedule, 'mobile refresh cadence')

# 5) HOUSEMAN: DB assists assignment visibility without overwriting newer Sheet action status.
old_sync_start = """    try {
      const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').toUpperCase();
      if (novaRealtimeIsEnabled_() && role === 'ROOMMAID' && state.activeMenu === 'cleaning') {
        const previousY = window.scrollY;
        await novaRealtimeHydrateCurrentView_();
        requestAnimationFrame(() => window.scrollTo({ top: previousY, behavior: 'auto' }));
        setSyncStatus('룸메이드 DB 동기화 완료');
        return;
      }

      const result = await callReadServerWithRetry_('getMobileDelta', state.token, {
"""
new_sync_start = """    try {
      const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').toUpperCase();
      if (novaRealtimeIsEnabled_() && role === 'HOUSEMAN' && state.activeMenu === 'houseman') {
        const previousY = window.scrollY;
        const businessDate = state.mobile.businessDate || state.bootstrap.app.businessDate;
        const site = state.mobile.site || state.bootstrap.user.defaultSite || '';
        const dbRows = await novaRealtimeLoadHousemanOrders_(businessDate, site);
        const existing = state.mobile.data?.orders || [];
        const dbIds = new Set(dbRows.map(raw => String(raw.order_id ?? raw.orderId ?? '')).filter(Boolean));
        const existingMap = new Map(existing.map(order => [String(order.orderId || ''), order]));

        // DB에서 한번 확인된 Realtime 오더가 더 이상 본인 목록에 없으면 재배정된 것이므로 제거한다.
        const kept = existing.filter(order => order.__dbAssignmentTracked !== true || dbIds.has(String(order.orderId || '')));
        const keptMap = new Map(kept.map(order => [String(order.orderId || ''), order]));
        dbRows.forEach(raw => {
          const mapped = novaRealtimeMapHousemanOrder_(raw);
          if (!mapped?.orderId) return;
          const previous = existingMap.get(String(mapped.orderId)) || keptMap.get(String(mapped.orderId));
          const dbUpdated = novaRealtimeUpdatedAtMs_(mapped.updatedAt);
          const sheetUpdated = novaRealtimeUpdatedAtMs_(previous?.updatedAt);
          let next;
          if (previous && sheetUpdated > dbUpdated) {
            // 접수·처리·완료 등 Sheet 액션이 DB의 배정시각보다 최신이면 그 상태를 보존한다.
            next = Object.assign({}, previous, {
              assignedEmployeeNo: mapped.assignedEmployeeNo || previous.assignedEmployeeNo,
              assignedName: mapped.assignedName || previous.assignedName,
              routeCandidateEmployeeNos: mapped.routeCandidateEmployeeNos || previous.routeCandidateEmployeeNos,
              routeCandidateNames: mapped.routeCandidateNames || previous.routeCandidateNames,
              routeCandidateSummary: mapped.routeCandidateSummary || previous.routeCandidateSummary,
              routeLocked: mapped.routeLocked,
              __dbAssignmentTracked: true,
              __dbVersion: Number(mapped.version || 0)
            });
          } else {
            next = Object.assign({}, mapped, {
              // Apps Script updateHousemanOrder의 version은 Sheet 도메인이다. DB version을 넘기지 않는다.
              rowNumber: Number(previous?.rowNumber || 0),
              version: Number(previous?.version || 0),
              __dbAssignmentTracked: true,
              __dbVersion: Number(mapped.version || 0)
            });
          }
          const idx = kept.findIndex(order => String(order.orderId || '') === String(next.orderId || ''));
          if (idx >= 0) kept[idx] = next; else kept.push(next);
        });
        state.mobile.data.orders = kept;
        sortMobileHousemanOrdersLocal_();
        refreshHousemanMobileSummaryLocal_();
        renderMobileSummary();
        renderMobileList();
        requestAnimationFrame(() => window.scrollTo({ top: previousY, behavior: 'auto' }));
        setSyncStatus('하우스맨 DB 배정 동기화 완료');
        return;
      }

      if (novaRealtimeIsEnabled_()
          && ((role === 'ROOMMAID' && state.activeMenu === 'cleaning')
            || (role === 'QM' && state.activeMenu === 'qm'))) {
        const previousY = window.scrollY;
        await novaRealtimeHydrateCurrentView_();
        requestAnimationFrame(() => window.scrollTo({ top: previousY, behavior: 'auto' }));
        setSyncStatus(role === 'QM' ? 'QM DB 배정 동기화 완료' : '룸메이드 DB 동기화 완료');
        return;
      }

      const result = await callReadServerWithRetry_('getMobileDelta', state.token, {
"""
replace_once(old_sync_start, new_sync_start, 'HOUSEMAN/QM mobile direct DB sync')

CLIENT.write_text(text, encoding='utf-8')

check = CLIENT.read_text(encoding='utf-8')
required = [
    "novaRealtimeLoadHousemanOrders_",
    "assignedRoomMobile",
    "role === 'QM' && state.activeMenu === 'qm'",
    "role === 'HOUSEMAN' && state.activeMenu === 'houseman'",
    "delay = 3000 + Math.round(Math.random() * 700)",
    "__dbAssignmentTracked",
    "__dbVersion",
    "novaIndicatorBusinessDate",
    "novaMobileBusinessDate",
    "sessionStorage.getItem('novaIndicatorBusinessDate')",
    "sessionStorage.getItem('novaMobileBusinessDate')",
]
for marker in required:
    if marker not in check:
        raise SystemExit(f'PATCH_ERROR: missing marker: {marker}')
if "mapped.version = Number(mapped.version" in check:
    raise SystemExit('PATCH_ERROR: possible DB version leakage into Sheet version path')

print('HOUSEMAN_QM_MOBILE_DATE_V75_OK')
print('Changed: Client.html only')
print('QM: rebuild assigned-room list from authenticated DB result; refresh 3.0-3.7s')
print('HOUSEMAN: DB-assisted assignment visibility; preserve newer Sheet action states; refresh 3.0-3.7s')
print('ROOMMAID: existing verified 5.0-6.2s path preserved')
print('Business date: indicator/mobile sessionStorage persistence across page refresh')
