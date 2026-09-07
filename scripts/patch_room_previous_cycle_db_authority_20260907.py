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
    old_sync = """      qmEmployeeNo: String(row[map['QM사번']] || '').trim(),\n      // ROOM_OPERATION_FLAGS_FORWARD_SYNC_V2 · DB-first 운영표시가 5분 정방향 동기화에서 유실되지 않게 명시합니다.\n"""
    new_sync = """      qmEmployeeNo: String(row[map['QM사번']] || '').trim(),\n      // ROOM_PREVIOUS_CYCLE_DB_AUTHORITY_V1 · 마지막상태/이전 정비주기 5필드를 DB mirror에 함께 보존합니다.\n      lastRoomStatus: map['마지막객실상태'] !== undefined\n        ? String(row[map['마지막객실상태']] || '').trim().toUpperCase() : '',\n      previousRoomStatus: map['이전객실상태'] !== undefined\n        ? String(row[map['이전객실상태']] || '').trim().toUpperCase() : '',\n      previousCleaningStatus: map['이전청소상태'] !== undefined\n        ? String(row[map['이전청소상태']] || '').trim().toUpperCase() : '',\n      previousRoommaidEmployeeNo: map['이전룸메이드사번'] !== undefined\n        ? String(row[map['이전룸메이드사번']] || '').trim() : '',\n      previousSecondaryRoommaidEmployeeNo: map['이전보조룸메이드사번'] !== undefined\n        ? String(row[map['이전보조룸메이드사번']] || '').trim() : '',\n      // ROOM_OPERATION_FLAGS_FORWARD_SYNC_V2 · DB-first 운영표시가 5분 정방향 동기화에서 유실되지 않게 명시합니다.\n"""
    sync = replace_once(sync, old_sync, new_sync, 'Realtime 5-field forward payload')
    changed = True

if MARKER not in client:
    old_fields = """  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze([\n    // ROOM_STATUS_DB_READ_AUTHORITY_V1 · 객실상태를 포함한 현재 객실 운영필드는 DB 읽기를 원본으로 사용합니다.\n    // 기존 Sheet snapshot/version은 이력·fallback 용도로 유지하되 DB hydrate/reconcile 이후에는\n    // Sheet delta가 최신 DB 객실상태를 되돌리지 못하도록 동일 merge 경로에서 보호합니다.\n    'roomStatus', 'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'\n  ]);\n"""
    new_fields = """  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze([\n    // ROOM_STATUS_DB_READ_AUTHORITY_V1 · 객실상태를 포함한 현재 객실 운영필드는 DB 읽기를 원본으로 사용합니다.\n    // ROOM_PREVIOUS_CYCLE_DB_AUTHORITY_V1 · 마지막상태/이전 정비주기 flat 필드도 DB hydrate/reconcile이 소유합니다.\n    // 기존 Sheet snapshot/version은 이력·fallback 용도로 유지하되 DB hydrate/reconcile 이후에는\n    // Sheet delta가 최신 DB 상태를 되돌리지 못하도록 동일 merge 경로에서 보호합니다.\n    'roomStatus', 'lastRoomStatus', 'previousRoomStatus', 'previousCleaningStatus', 'previousRoommaidEmployeeNo', 'previousSecondaryRoommaidEmployeeNo',\n    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'\n  ]);\n  const NOVA_REALTIME_CLEANING_TARGET_ROOM_STATUSES_ = Object.freeze([\n    'CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU', 'STOCK', 'STOCK_RC', 'STOCK_HU'\n  ]);\n"""
    client = replace_once(client, old_fields, new_fields, 'Client DB-owned metadata field list')

    old_merge = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;\n\n    // ROOM_STATE_SYNC_HARDENING_V1 · 청소시작/완료 optimistic 상태는 DB가 확정하거나 더 앞선 상태로 진행할 때까지 보호합니다.\n"""
    new_merge = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;\n\n    // ROOM_PREVIOUS_CYCLE_DB_AUTHORITY_V1 · DB flat metadata를 기존 UI 구조로 재조립합니다.\n    const hasDbPreviousCycleMetadata = [\n      'lastRoomStatus', 'previousRoomStatus', 'previousCleaningStatus',\n      'previousRoommaidEmployeeNo', 'previousSecondaryRoommaidEmployeeNo'\n    ].some(key => Object.prototype.hasOwnProperty.call(realtimeRoom, key));\n    if (hasDbPreviousCycleMetadata) {\n      const currentRoomStatus = String(merged.roomStatus || '').trim().toUpperCase();\n      const lastRoomStatus = String(merged.lastRoomStatus || '').trim().toUpperCase();\n      merged.displayBaseRoomStatus = NOVA_REALTIME_CLEANING_TARGET_ROOM_STATUSES_.includes(currentRoomStatus)\n        ? currentRoomStatus\n        : (currentRoomStatus === 'VACANT_CLEAN' && NOVA_REALTIME_CLEANING_TARGET_ROOM_STATUSES_.includes(lastRoomStatus) ? lastRoomStatus : '');\n\n      const previousRoomStatus = String(merged.previousRoomStatus || '').trim().toUpperCase();\n      if (previousRoomStatus) {\n        const primaryNo = String(merged.previousRoommaidEmployeeNo || '').trim();\n        const secondaryNo = String(merged.previousSecondaryRoommaidEmployeeNo || '').trim();\n        const legacyPreviousCycle = legacyRoom && legacyRoom.previousCycle ? legacyRoom.previousCycle : {};\n        const roommaids = state.indicator.data?.staff?.roommaids || [];\n        const primaryStaff = roommaids.find(user => String(user.employeeNo || '').trim() === primaryNo);\n        const secondaryStaff = roommaids.find(user => String(user.employeeNo || '').trim() === secondaryNo);\n        merged.previousCycle = {\n          roomStatus: previousRoomStatus,\n          cleaningStatus: String(merged.previousCleaningStatus || '').trim().toUpperCase(),\n          roommaidEmployeeNo: primaryNo,\n          roommaidName: primaryNo\n            ? String(primaryStaff?.name || (String(legacyPreviousCycle.roommaidEmployeeNo || '').trim() === primaryNo ? legacyPreviousCycle.roommaidName || '' : ''))\n            : '',\n          secondaryRoommaidEmployeeNo: secondaryNo,\n          secondaryRoommaidName: secondaryNo\n            ? String(secondaryStaff?.name || (String(legacyPreviousCycle.secondaryRoommaidEmployeeNo || '').trim() === secondaryNo ? legacyPreviousCycle.secondaryRoommaidName || '' : ''))\n            : ''\n        };\n      } else {\n        merged.previousCycle = null;\n      }\n    }\n\n    // ROOM_STATE_SYNC_HARDENING_V1 · 청소시작/완료 optimistic 상태는 DB가 확정하거나 더 앞선 상태로 진행할 때까지 보호합니다.\n"""
    client = replace_once(client, old_merge, new_merge, 'Client previous-cycle UI reconstruction')

    old_signature = """      room.roomStatus || '', room.displayBaseRoomStatus || '', room.cleaningStatus || '', room.cleaningType || '', room.assignmentType || '',\n"""
    new_signature = """      room.roomStatus || '', room.displayBaseRoomStatus || '',\n      room.previousCycle?.roomStatus || '', room.previousCycle?.cleaningStatus || '',\n      room.previousCycle?.roommaidEmployeeNo || '', room.previousCycle?.secondaryRoommaidEmployeeNo || '',\n      room.cleaningStatus || '', room.cleaningType || '', room.assignmentType || '',\n"""
    client = replace_once(client, old_signature, new_signature, 'Client room visual signature previous-cycle fields')
    changed = True

CLIENT_PATH.write_text(client, encoding='utf-8')
SYNC_PATH.write_text(sync, encoding='utf-8')
print(f'{MARKER}: ' + ('prepared.' if changed else 'already prepared.'))
