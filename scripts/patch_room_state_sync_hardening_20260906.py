from pathlib import Path
import sys

CLIENT = Path('Client.html')
MARKER = 'ROOM_STATE_SYNC_HARDENING_V1'


def fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(97)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly 1 anchor, found {count}')
    return text.replace(old, new, 1)


def main():
    text = CLIENT.read_text(encoding='utf-8')
    if MARKER in text:
        print('Room state sync hardening already applied.')
        return

    # 1) Track periodic full DB reconciliation separately from the light event cursor.
    old_state = """    indicatorEventCursorTime: '',\n    indicatorEventCursorRequestId: '',\n    roomStatusProtections: new Map(),"""
    new_state = """    indicatorEventCursorTime: '',\n    indicatorEventCursorRequestId: '',\n    indicatorFullReconcileAt: 0, // ROOM_STATE_SYNC_HARDENING_V1\n    roomStatusProtections: new Map(),"""
    text = replace_once(text, old_state, new_state, 'indicator full reconcile state')

    # 2) Bound Realtime HTTP waits. A hung mobile fetch must never leave actionInFlight > 0 forever.
    fetch_anchor = "  async function novaRealtimeFetch_(path, options = {}, attempt = 0) {\n"
    bounded_helper = r'''  function novaRealtimeBoundedFetch_(url, options = {}, timeoutMs = 7000) { // ROOM_STATE_SYNC_HARDENING_V1
    if (typeof AbortController !== 'function') return fetch(url, options);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), Math.max(1000, Number(timeoutMs || 7000)));
    const requestOptions = Object.assign({}, options, { signal: controller.signal });
    return fetch(url, requestOptions).finally(() => window.clearTimeout(timeout));
  }

'''
    if text.count(fetch_anchor) != 1:
        fail(f'bounded fetch insertion anchor count={text.count(fetch_anchor)}')
    text = text.replace(fetch_anchor, bounded_helper + fetch_anchor, 1)
    text = replace_once(
        text,
        "    const response = await fetch(`${novaRealtime_.apiBase}${path}`, {",
        "    const response = await novaRealtimeBoundedFetch_(`${novaRealtime_.apiBase}${path}`, {",
        'bound primary Realtime fetch'
    )
    text = replace_once(
        text,
        "      body: options.body\n    }).catch(error => {",
        "      body: options.body\n    }, Number(options.timeoutMs || 7000)).catch(error => {",
        'primary fetch timeout argument'
    )
    text = replace_once(
        text,
        "    const response = await fetch(`${novaRealtime_.apiBase}/v1/room-changes`, {",
        "    const response = await novaRealtimeBoundedFetch_(`${novaRealtime_.apiBase}/v1/room-changes`, {",
        'bound room-changes fetch'
    )
    text = replace_once(
        text,
        "      method: 'POST',\n      body: form\n    }).catch(error => {",
        "      method: 'POST',\n      body: form\n    }, 6500).catch(error => {",
        'room-changes timeout argument'
    )

    # 3) Protect optimistic cleaning state from unrelated/stale DB broadcasts, but clear it as soon as DB confirms/advances.
    merge_anchor = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;\n\n    // QM을 Realtime으로 전환하기 전 생성된 과거행은 Sheet의 완료/재정비가 DB의"""
    merge_new = r'''    if (realtimeRoom.building) merged.building = realtimeRoom.building;

    // ROOM_STATE_SYNC_HARDENING_V1 · 청소시작/완료 optimistic 상태는 DB가 확정하거나 더 앞선 상태로 진행할 때까지 보호합니다.
    const pendingCleaningAction = String(legacyRoom?.__pendingAction || '').trim().toUpperCase();
    if (['CLEANING_START', 'CLEANING_COMPLETE'].includes(pendingCleaningAction)
        && Object.prototype.hasOwnProperty.call(realtimeRoom, 'cleaningStatus')) {
      const dbCleaningStatus = String(realtimeRoom.cleaningStatus || '').trim().toUpperCase();
      const startConfirmed = pendingCleaningAction === 'CLEANING_START'
        && ['CLEANING', 'COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED'].includes(dbCleaningStatus);
      const completeConfirmed = pendingCleaningAction === 'CLEANING_COMPLETE'
        && ['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED'].includes(dbCleaningStatus);
      if (startConfirmed || completeConfirmed) {
        delete merged.__pending;
        delete merged.__pendingAction;
      } else {
        merged.cleaningStatus = String(legacyRoom.cleaningStatus || merged.cleaningStatus || '');
        if (legacyRoom.__pending === true) merged.__pending = true;
        merged.__pendingAction = pendingCleaningAction;
      }
    }

    // QM을 Realtime으로 전환하기 전 생성된 과거행은 Sheet의 완료/재정비가 DB의'''
    text = replace_once(text, merge_anchor, merge_new, 'optimistic cleaning merge protection')

    # 4) Add a full-current-state indicator reconciliation. This closes the old 15-second first-cursor blind spot.
    indicator_anchor = "  async function novaRealtimeHydrateIndicatorHousemanOrders_() { // (ADMIN/ORDER 하우스맨 DB 상태 직접 보정)\n"
    indicator_helper = r'''  async function novaRealtimeReconcileIndicatorRooms_() { // ROOM_STATE_SYNC_HARDENING_V1 · Broadcast/event 누락 최종복구
    if (!novaRealtimeIsEnabled_() || document.hidden || state.activeMenu !== 'indicator' || !state.indicator.loaded || !state.indicator.data) return 0;
    const role = String(state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (!['ADMIN', 'ORDER'].includes(role)) return 0;
    const businessDate = String(state.indicator.businessDate || state.bootstrap?.app?.businessDate || '').trim();
    const sites = novaRealtimeRelevantSites_();
    if (!businessDate || !sites.length) return 0;

    const lists = await Promise.all(sites.map(site =>
      novaRealtimeLoadRoomsForSite_(businessDate, site)
        .catch(error => { console.warn('[NOVA Realtime] 인디게이터 전체상태 보정 실패', site, error); return []; })
    ));
    const dbMap = new Map();
    lists.flat().forEach(raw => {
      const mapped = novaRealtimeMapPartialRoom_(raw);
      if (mapped?.roomNo && mapped?.site) dbMap.set(`${mapped.site}|${mapped.roomNo}`, mapped);
    });

    const rooms = state.indicator.data.rooms || [];
    const touched = [];
    rooms.forEach((current, index) => {
      const dbRoom = dbMap.get(`${current.site}|${current.roomNo}`);
      if (!dbRoom) return;
      const before = novaRealtimeRoomSignature_(current);
      const merged = novaRealtimeMergeRoom_(current, dbRoom);
      if (before === novaRealtimeRoomSignature_(merged)) return;
      rooms[index] = merged;
      touched.push({ roomNo: merged.roomNo, site: merged.site });
    });

    touched.forEach(item => renderIndicatorRoomLocal_(item.roomNo, item.site));
    if (touched.length) renderIndicatorSummary();
    novaRealtime_.indicatorFullReconcileAt = Date.now();
    return touched.length;
  }

'''
    if text.count(indicator_anchor) != 1:
        fail(f'indicator reconcile insertion anchor count={text.count(indicator_anchor)}')
    text = text.replace(indicator_anchor, indicator_helper + indicator_anchor, 1)

    old_fallback_run = r'''    // 화면/업무일/사업장 전환 시 새 서버커서로 시작한다. 첫 호출은 서버가 최근 15초 이벤트를 보정한다.
    novaRealtime_.indicatorEventCursorTime = '';
    novaRealtime_.indicatorEventCursorRequestId = '';
    const run = async () => {
      if (!novaRealtimeIsEnabled_() || document.hidden || state.activeMenu !== 'indicator' || !state.indicator.loaded) {
        novaRealtime_.indicatorDbTimer = null;
        return;
      }
      try { await novaRealtimeHydrateIndicatorFallback_(); } catch (error) {
        console.warn('[NOVA Realtime] 관리자 DB 변경보조동기화 오류', error);
      }
      novaRealtime_.indicatorDbTimer = window.setTimeout(run, 2500);
    };
    novaRealtime_.indicatorDbTimer = window.setTimeout(run, 800);'''
    new_fallback_run = r'''    // ROOM_STATE_SYNC_HARDENING_V1 · 이벤트 커서만 믿지 않습니다.
    // 시작/복귀 즉시 현재 DB 전체상태를 1회 맞추고, 이후 Broadcast + 2.5초 이벤트 + 15초 전체보정을 병행합니다.
    novaRealtime_.indicatorEventCursorTime = '';
    novaRealtime_.indicatorEventCursorRequestId = '';
    novaRealtime_.indicatorFullReconcileAt = 0;
    const run = async () => {
      if (!novaRealtimeIsEnabled_() || document.hidden || state.activeMenu !== 'indicator' || !state.indicator.loaded) {
        novaRealtime_.indicatorDbTimer = null;
        return;
      }
      try {
        const fullDue = !novaRealtime_.indicatorFullReconcileAt
          || Date.now() - Number(novaRealtime_.indicatorFullReconcileAt || 0) >= 15000;
        if (fullDue) {
          const fullChanged = await novaRealtimeReconcileIndicatorRooms_();
          if (fullChanged) setSyncStatus(`DB 전체확인 · ${fullChanged}실 보정`);
        }
        await novaRealtimeHydrateIndicatorFallback_();
      } catch (error) {
        console.warn('[NOVA Realtime] 관리자 DB 변경보조동기화 오류', error);
      }
      novaRealtime_.indicatorDbTimer = window.setTimeout(run, 2500);
    };
    novaRealtime_.indicatorDbTimer = window.setTimeout(run, 80);'''
    text = replace_once(text, old_fallback_run, new_fallback_run, 'indicator fallback full reconciliation')

    # 5) ROOMMAID/QM also subscribe to the already-existing room Broadcast handler; polling remains as fallback.
    old_mobile_start = r'''  function startMobileSync() { // (지터 기반 모바일 동기화 시작)
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
  }'''
    new_mobile_start = r'''  function startMobileSync() { // (지터 기반 모바일 동기화 시작)
    stopMobileSync();
    if (!['qm', 'houseman', 'cleaning', 'public'].includes(state.activeMenu)) return;
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    const realtimeMobileRole = novaRealtimeIsEnabled_() && (
      (role === 'ROOMMAID' && state.activeMenu === 'cleaning')
      || (role === 'QM' && state.activeMenu === 'qm')
      || (role === 'HOUSEMAN' && state.activeMenu === 'houseman')
    );
    if (realtimeMobileRole) {
      // ROOM_STATE_SYNC_HARDENING_V1 · Push 우선 + 3~3.7초 DB polling 이중화.
      void novaRealtimeEnsureSubscriptions_().catch(error => {
        console.warn(`[NOVA Realtime] ${role} Push 구독 실패 · DB 주기조회로 계속 동작합니다.`, error);
      });
      // 화면 진입/백그라운드 복귀 시 첫 3초를 기다리지 않고 현재 DB를 즉시 맞춥니다.
      window.setTimeout(() => { void syncMobileDelta(); }, 0);
    }
    scheduleMobileSync_();
  }'''
    text = replace_once(text, old_mobile_start, new_mobile_start, 'ROOMMAID/QM mobile subscriptions')

    # 6) Roommaid optimistic state now carries the exact pending action so DB broadcasts can distinguish stale vs confirmed state.
    text = replace_once(
        text,
        "    const patch = { __pending: true };\n    if (action === 'START') {",
        "    const patch = { __pending: true, __pendingAction: action === 'START' ? 'CLEANING_START' : action === 'COMPLETE' ? 'CLEANING_COMPLETE' : '' }; // ROOM_STATE_SYNC_HARDENING_V1\n    if (action === 'START') {",
        'roommaid optimistic pending action'
    )
    text = replace_once(
        text,
        "    const confirmed = Object.assign({}, room);\n    delete confirmed.__pending;",
        "    const confirmed = Object.assign({}, room);\n    delete confirmed.__pending;\n    delete confirmed.__pendingAction; // ROOM_STATE_SYNC_HARDENING_V1",
        'clear confirmed roommaid pending action'
    )

    # 7) Normalize role detection and always reconcile the roommaid after an action finishes, including ambiguous network failures.
    text = replace_once(
        text,
        "    const role = state.mobile.data?.role;\n    const action = String(safePayload.action || '').trim().toUpperCase();",
        "    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase(); // ROOM_STATE_SYNC_HARDENING_V1\n    const action = String(safePayload.action || '').trim().toUpperCase();",
        'normalize mobile action role'
    )
    old_finally = r'''    } finally {
      state.mobile.actionInFlight = Math.max(0, Number(state.mobile.actionInFlight || 1) - 1);
      if (button && button.isConnected) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        if (button.dataset.originalText) button.textContent = button.dataset.originalText;
      }
    }
  }

  function applyOptimisticHousemanOrder_'''
    new_finally = r'''    } finally {
      state.mobile.actionInFlight = Math.max(0, Number(state.mobile.actionInFlight || 1) - 1);
      if (button && button.isConnected) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        if (button.dataset.originalText) button.textContent = button.dataset.originalText;
      }
      // ROOM_STATE_SYNC_HARDENING_V1 · 응답 유실/타임아웃으로 로컬을 복원했더라도 실제 DB가 성공했을 수 있습니다.
      // actionInFlight를 먼저 해제한 뒤 본인 배정목록을 즉시 재조회해 최종 DB 상태로 수렴시킵니다.
      if (roommaidFastPath && !document.hidden) {
        window.setTimeout(() => { void syncMobileDelta(); }, 80);
      }
    }
  }

  function applyOptimisticHousemanOrder_'''
    text = replace_once(text, old_finally, new_finally, 'post-roommaid-action reconciliation')

    # 8) Room actions get a tighter per-attempt bound while keeping the same requestId across existing retries.
    text = replace_once(
        text,
        "      noRetry: mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' && !String(safe.operationalStatus || '').trim(),\n      body: JSON.stringify(safe)",
        "      noRetry: mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' && !String(safe.operationalStatus || '').trim(),\n      timeoutMs: ['CLEANING_START', 'CLEANING_COMPLETE'].includes(mappedAction) ? 5000 : 7000, // ROOM_STATE_SYNC_HARDENING_V1\n      body: JSON.stringify(safe)",
        'room action bounded timeout'
    )

    CLIENT.write_text(text, encoding='utf-8')
    print('Applied ROOM_STATE_SYNC_HARDENING_V1.')


if __name__ == '__main__':
    main()
