from pathlib import Path

PATH = Path('cloudrun/index.js')
MARKER = 'ROOM_PREVIOUS_CYCLE_METADATA_SYNC_V1'
text = PATH.read_text(encoding='utf-8')

if MARKER in text:
    print(f'{MARKER} already applied.')
    raise SystemExit(0)


def replace_exact(old, new, expected, label):
    global text
    count = text.count(old)
    if count != expected:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected={expected}')
    text = text.replace(old, new)

# 1) Full room DTO exposes the five Sheet previous-cycle/display metadata fields.
replace_exact(
    """    operationalStatus: r.operational_status || '',\n    // ROOM_OPERATION_FLAGS_SYNC_V1 · independent room operation flags\n""",
    """    operationalStatus: r.operational_status || '',\n    // ROOM_PREVIOUS_CYCLE_METADATA_SYNC_V1 · Sheet previous-cycle/display metadata mirrored into DB\n    lastRoomStatus: r.last_room_status || '',\n    previousRoomStatus: r.previous_room_status || '',\n    previousCleaningStatus: r.previous_cleaning_status || '',\n    previousRoommaidEmployeeNo: r.previous_roommaid_employee_no || '',\n    previousSecondaryRoommaidEmployeeNo: r.previous_secondary_roommaid_employee_no || '',\n    // ROOM_OPERATION_FLAGS_SYNC_V1 · independent room operation flags\n""",
    1,
    'roomDto metadata'
)

# 2) Normalize signed Sheet->DB migration/sync payloads.
replace_exact(
    """    operationalStatus:\n      cleanText_(raw?.operationalStatus, 80),\n    preassigned: raw?.preassigned === true,\n""",
    """    operationalStatus:\n      cleanText_(raw?.operationalStatus, 80),\n    lastRoomStatus:\n      cleanText_(raw?.lastRoomStatus, 40).toUpperCase(),\n    previousRoomStatus:\n      cleanText_(raw?.previousRoomStatus, 40).toUpperCase(),\n    previousCleaningStatus:\n      cleanText_(raw?.previousCleaningStatus, 40).toUpperCase(),\n    previousRoommaidEmployeeNo:\n      cleanText_(raw?.previousRoommaidEmployeeNo, 40),\n    previousSecondaryRoommaidEmployeeNo:\n      cleanText_(raw?.previousSecondaryRoommaidEmployeeNo, 40),\n    preassigned: raw?.preassigned === true,\n""",
    1,
    'normalizeMigrationRoom metadata'
)

# 3) Both bootstrap-import and sync-current-rooms room tuples expand from 15 -> 20 values.
replace_exact('const n = i * 15;', 'const n = i * 20;', 2, 'room tuple width')
replace_exact(
    """          r.operationalStatus,\n          r.preassigned,\n          r.vip,\n          r.importantRoom\n""",
    """          r.operationalStatus,\n          r.lastRoomStatus,\n          r.previousRoomStatus,\n          r.previousCleaningStatus,\n          r.previousRoommaidEmployeeNo || null,\n          r.previousSecondaryRoommaidEmployeeNo || null,\n          r.preassigned,\n          r.vip,\n          r.importantRoom\n""",
    2,
    'room tuple params'
)
replace_exact(
    """          $${n + 12},\n          $${n + 13}::boolean,\n          $${n + 14}::boolean,\n          $${n + 15}::boolean\n""",
    """          $${n + 12},\n          $${n + 13},\n          $${n + 14},\n          $${n + 15},\n          $${n + 16},\n          $${n + 17},\n          $${n + 18}::boolean,\n          $${n + 19}::boolean,\n          $${n + 20}::boolean\n""",
    2,
    'room tuple SQL placeholders'
)
replace_exact(
    """          operational_status,\n          preassigned,\n          vip,\n          important_room\n""",
    """          operational_status,\n          last_room_status,\n          previous_room_status,\n          previous_cleaning_status,\n          previous_roommaid_employee_no,\n          previous_secondary_roommaid_employee_no,\n          preassigned,\n          vip,\n          important_room\n""",
    2,
    'room insert metadata columns'
)

# 4) The recurrent sync upsert must retain the Sheet metadata mirror just like existing non-cleaning fields.
replace_exact(
    """            operational_status=\n              excluded.operational_status,\n\n            preassigned=excluded.preassigned,\n""",
    """            operational_status=\n              excluded.operational_status,\n\n            last_room_status=excluded.last_room_status,\n            previous_room_status=excluded.previous_room_status,\n            previous_cleaning_status=excluded.previous_cleaning_status,\n            previous_roommaid_employee_no=excluded.previous_roommaid_employee_no,\n            previous_secondary_roommaid_employee_no=excluded.previous_secondary_roommaid_employee_no,\n\n            preassigned=excluded.preassigned,\n""",
    1,
    'sync current metadata upsert'
)

PATH.write_text(text, encoding='utf-8')
print(f'Applied {MARKER}: five previous-cycle/display metadata fields normalized, persisted, upserted, and returned.')