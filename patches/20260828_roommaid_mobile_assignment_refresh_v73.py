from pathlib import Path

CLIENT = Path('Client.html')
text = CLIENT.read_text(encoding='utf-8')

old_hydrate = """    if (mobileRealtimeRole && state.mobile.data) {
      const sites = novaRealtimeRelevantSites_();
      const lists = await Promise.all(sites.map(site =>
        novaRealtimeLoadRoomsForSite_(state.mobile.businessDate || state.bootstrap.app.businessDate, site)
          .catch(error => { console.error('[NOVA Realtime] 모바일 객실 조회 실패', site, error); return []; })
      ));
      const realtimeMap = new Map(lists.flat().map(room => [`${room.site}|${room.roomNo}`, room]));
      state.mobile.data.rooms = (state.mobile.data.rooms || []).map(room =>
        novaRealtimeMergeRoom_(room, realtimeMap.get(`${room.site}|${room.roomNo}`))
      );
      renderMobileData();
    }
"""

new_hydrate = """    if (mobileRealtimeRole && state.mobile.data) {
      const sites = novaRealtimeRelevantSites_();
      const lists = await Promise.all(sites.map(site =>
        novaRealtimeLoadRoomsForSite_(state.mobile.businessDate || state.bootstrap.app.businessDate, site)
          .catch(error => { console.error('[NOVA Realtime] 모바일 객실 조회 실패', site, error); return []; })
      ));
      const realtimeRows = lists.flat();

      if (role === 'ROOMMAID' && state.activeMenu === 'cleaning') {
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
        const realtimeMap = new Map(realtimeRows.map(room => [`${room.site}|${room.roomNo}`, room]));
        state.mobile.data.rooms = (state.mobile.data.rooms || []).map(room =>
          novaRealtimeMergeRoom_(room, realtimeMap.get(`${room.site}|${room.roomNo}`))
        );
      }
      renderMobileData();
    }
"""

if text.count(old_hydrate) != 1:
    raise SystemExit(f'PATCH_ERROR: roommaid realtime hydrate target expected 1 match, found {text.count(old_hydrate)}')
text = text.replace(old_hydrate, new_hydrate, 1)

old_schedule = """  function scheduleMobileSync_() { // (직원별 요청시점 분산)
    if (document.hidden || !['qm', 'houseman', 'cleaning', 'public'].includes(state.activeMenu) || !state.mobile.loaded) return;
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').toUpperCase();
    const base = novaRealtimeIsEnabled_() && role === 'ROOMMAID'
      ? 30000
      : Number(state.bootstrap.app.mobileSyncMs || 16000);
    state.mobile.syncTimer = window.setTimeout(async () => {
      state.mobile.syncTimer = null;
      await syncMobileDelta();
      scheduleMobileSync_();
    }, nextSyncDelay_(base));
  }
"""

new_schedule = """  function scheduleMobileSync_() { // (직원별 요청시점 분산)
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

if text.count(old_schedule) != 1:
    raise SystemExit(f'PATCH_ERROR: mobile sync schedule target expected 1 match, found {text.count(old_schedule)}')
text = text.replace(old_schedule, new_schedule, 1)

CLIENT.write_text(text, encoding='utf-8')

check = CLIENT.read_text(encoding='utf-8')
required = [
    "DB의 현재 배정목록 자체를 기준으로 목록을 재구성한다.",
    "const realtimeRows = lists.flat();",
    "role === 'ROOMMAID' && state.activeMenu === 'cleaning'",
    "? 5000",
    "Math.random() * 1200",
]
for marker in required:
    if marker not in check:
        raise SystemExit(f'PATCH_ERROR: missing marker: {marker}')
if '? 30000' in check:
    raise SystemExit('PATCH_ERROR: old 30-second ROOMMAID realtime interval remains')

print('ROOMMAID_MOBILE_ASSIGNMENT_REFRESH_V73_OK')
print('Changed: Client.html only')
print('ROOMMAID mobile: rebuild assigned-room list from authenticated DB result')
print('Refresh target: 5.0-6.2 seconds while cleaning screen is active')
print('Other mobile roles and admin/QM/houseman flows unchanged')
