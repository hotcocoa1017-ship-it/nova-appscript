from pathlib import Path

CLIENT_PATH = Path('Client.html')
SYNC_PATH = Path('RealtimeDailySync.js')
client = CLIENT_PATH.read_text(encoding='utf-8')
sync = SYNC_PATH.read_text(encoding='utf-8')
MARKER = 'ROOM_PREVIOUS_CYCLE_DB_AUTHORITY_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected=1')
    return text.replace(old, new, 1)

changed = False

if MARKER not in sync:
    old_sync = """      qmEmployeeNo: String(row[map['QM사번']] || '').trim(),
      // ROOM_OPERATION_FLAGS_FORWARD_SYNC_V2 · DB-first 운영표시가 5분 정방향 동기화에서 유실되지 않게 명시합니다.
"""
    new_sync = """      qmEmployeeNo: String(row[map['QM사번']] || '').trim(),
      // ROOM_PREVIOUS_CYCLE_DB_AUTHORITY_V1 · 마지막상태/이전 정비주기 5필드를 DB mirror에 함께 보존합니다.
      lastRoomStatus: map['마지막객실상태'] !== undefined
        ? String(row[map['마지막객실상태']] || '').trim().toUpperCase() : '',
      previousRoomStatus: map['이전객실상태'] !== undefined
        ? String(row[map['이전객실상태']] || '').trim().toUpperCase() : '',
      previousCleaningStatus: map['이전청소상태'] !== undefined
        ? String(row[map['이전청소상태']] || '').trim().toUpperCase() : '',
      previousRoommaidEmployeeNo: map['이전룸메이드사번'] !== undefined
        ? String(row[map['이전룸메이드사번']] || '').trim() : '',
      previousSecondaryRoommaidEmployeeNo: map['이전보조룸메이드사번'] !== undefined
        ? String(row[map['이전보조룸메이드사번']] || '').trim() : '',
      // ROOM_OPERATION_FLAGS_FORWARD_SYNC_V2 · DB-first 운영표시가 5분 정방향 동기화에서 유실되지 않게 명시합니다.
"""
    sync = replace_once(sync, old_sync, new_sync, 'Realtime 5-field forward payload')
    changed = True

if MARKER not in client:
    old_fields = """  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze([
    // ROOM_STATUS_DB_READ_AUTHORITY_V1 · 객실상태를 포함한 현재 객실 운영필드는 DB 읽기를 원본으로 사용합니다.
    // 기존 Sheet snapshot/version은 이력·fallback 용도로 유지하되 DB hydrate/reconcile 이후에는
    // Sheet delta가 최신 DB 객실상태를 되돌리지 못하도록 동일 merge 경로에서 보호합니다.
    'roomStatus', 'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'
  ]);
"""
    new_fields = """  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze([
    // ROOM_STATUS_DB_READ_AUTHORITY_V1 · 객실상태를 포함한 현재 객실 운영필드는 DB 읽기를 원본으로 사용합니다.
    // ROOM_PREVIOUS_CYCLE_DB_AUTHORITY_V1 · 마지막상태/이전 정비주기 flat 필드도 DB hydrate/reconcile이 소유합니다.
    // 기존 Sheet snapshot/version은 이력·fallback 용도로 유지하되 DB hydrate/reconcile 이후에는
    // Sheet delta가 최신 DB 상태를 되돌리지 못하도록 동일 merge 경로에서 보호합니다.
    'roomStatus', 'lastRoomStatus', 'previousRoomStatus', 'previousCleaningStatus', 'previousRoommaidEmployeeNo', 'previousSecondaryRoommaidEmployeeNo',
    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'
  ]);
  const NOVA_REALTIME_CLEANING_TARGET_ROOM_STATUSES_ = Object.freeze([
    'CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU', 'STOCK', 'STOCK_RC', 'STOCK_HU'
  ]);
"""
    client = replace_once(client, old_fields, new_fields, 'Client DB-owned metadata field list')

    old_merge = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;

    // ROOM_STATE_SYNC_HARDENING_V1 · 청소시작/완료 optimistic 상태는 DB가 확정하거나 더 앞선 상태로 진행할 때까지 보호합니다.
"""
    new_merge = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;

    // ROOM_PREVIOUS_CYCLE_DB_AUTHORITY_V1 · DB flat metadata를 기존 UI 구조로 재조립합니다.
    const hasDbPreviousCycleMetadata = [
      'lastRoomStatus', 'previousRoomStatus', 'previousCleaningStatus',
      'previousRoommaidEmployeeNo', 'previousSecondaryRoommaidEmployeeNo'
    ].some(key => Object.prototype.hasOwnProperty.call(realtimeRoom, key));
    if (hasDbPreviousCycleMetadata) {
      const currentRoomStatus = String(merged.roomStatus || '').trim().toUpperCase();
      const lastRoomStatus = String(merged.lastRoomStatus || '').trim().toUpperCase();
      merged.displayBaseRoomStatus = NOVA_REALTIME_CLEANING_TARGET_ROOM_STATUSES_.includes(currentRoomStatus)
        ? currentRoomStatus
        : (currentRoomStatus === 'VACANT_CLEAN' && NOVA_REALTIME_CLEANING_TARGET_ROOM_STATUSES_.includes(lastRoomStatus) ? lastRoomStatus : '');

      const previousRoomStatus = String(merged.previousRoomStatus || '').trim().toUpperCase();
      if (previousRoomStatus) {
        const primaryNo = String(merged.previousRoommaidEmployeeNo || '').trim();
        const secondaryNo = String(merged.previousSecondaryRoommaidEmployeeNo || '').trim();
        const legacyPreviousCycle = legacyRoom && legacyRoom.previousCycle ? legacyRoom.previousCycle : {};
        const roommaids = state.indicator.data?.staff?.roommaids || [];
        const primaryStaff = roommaids.find(user => String(user.employeeNo || '').trim() === primaryNo);
        const secondaryStaff = roommaids.find(user => String(user.employeeNo || '').trim() === secondaryNo);
        merged.previousCycle = {
          roomStatus: previousRoomStatus,
          cleaningStatus: String(merged.previousCleaningStatus || '').trim().toUpperCase(),
          roommaidEmployeeNo: primaryNo,
          roommaidName: primaryNo
            ? String(primaryStaff?.name || (String(legacyPreviousCycle.roommaidEmployeeNo || '').trim() === primaryNo ? legacyPreviousCycle.roommaidName || '' : ''))
            : '',
          secondaryRoommaidEmployeeNo: secondaryNo,
          secondaryRoommaidName: secondaryNo
            ? String(secondaryStaff?.name || (String(legacyPreviousCycle.secondaryRoommaidEmployeeNo || '').trim() === secondaryNo ? legacyPreviousCycle.secondaryRoommaidName || '' : ''))
            : ''
        };
      } else {
        merged.previousCycle = null;
      }
    }

    // ROOM_STATE_SYNC_HARDENING_V1 · 청소시작/완료 optimistic 상태는 DB가 확정하거나 더 앞선 상태로 진행할 때까지 보호합니다.
"""
    client = replace_once(client, old_merge, new_merge, 'Client previous-cycle UI reconstruction')

    old_signature = """  function roomVisualSignature_(room) { // (서버확정 후 재렌더 필요 여부 비교)
    if (!room) return '';
    return JSON.stringify([
      room.roomStatus || '', room.displayBaseRoomStatus || '', room.cleaningStatus || '', room.cleaningType || '', room.assignmentType || '',
      room.roommaidEmployeeNo || '', room.roommaidName || '', room.secondaryRoommaidEmployeeNo || '',
      room.secondaryRoommaidName || '', room.qmEmployeeNo || '', room.qmName || '', normalizeIndicatorRoomOperationalStatus_(room.operationalStatus), Number(room.pendingOrderCount || 0)
    ]);
  }
"""
    new_signature = """  function roomVisualSignature_(room) { // (서버확정 후 재렌더 필요 여부 비교)
    if (!room) return '';
    return JSON.stringify([
      room.roomStatus || '', room.displayBaseRoomStatus || '',
      room.previousCycle?.roomStatus || '', room.previousCycle?.cleaningStatus || '',
      room.previousCycle?.roommaidEmployeeNo || '', room.previousCycle?.secondaryRoommaidEmployeeNo || '',
      room.cleaningStatus || '', room.cleaningType || '', room.assignmentType || '',
      room.roommaidEmployeeNo || '', room.roommaidName || '', room.secondaryRoommaidEmployeeNo || '',
      room.secondaryRoommaidName || '', room.qmEmployeeNo || '', room.qmName || '', normalizeIndicatorRoomOperationalStatus_(room.operationalStatus), Number(room.pendingOrderCount || 0)
    ]);
  }
"""
    client = replace_once(client, old_signature, new_signature, 'Client roomVisualSignature previous-cycle fields')
    changed = True

CLIENT_PATH.write_text(client, encoding='utf-8')
SYNC_PATH.write_text(sync, encoding='utf-8')
print(f'{MARKER}: ' + ('prepared.' if changed else 'already prepared.'))
