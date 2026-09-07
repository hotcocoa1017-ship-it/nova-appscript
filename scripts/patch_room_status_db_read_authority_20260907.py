from pathlib import Path

PATH = Path('Client.html')
MARKER = 'ROOM_STATUS_DB_READ_AUTHORITY_V1'

text = PATH.read_text(encoding='utf-8')

if MARKER in text:
    print(f'{MARKER} already applied.')
    raise SystemExit(0)

old = """  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze([\n    // Phase 1 Realtime owns cleaning progress and DB version metadata only.\n    // 객실상태/배정/객실운영상태(고장·객실확인)는 기존 Sheets가 원본이므로\n    // PostgreSQL의 지연·빈 값으로 덮어쓰지 않습니다.\n    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'\n  ]);"""

new = """  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze([\n    // ROOM_STATUS_DB_READ_AUTHORITY_V1 · 객실상태를 포함한 현재 객실 운영필드는 DB 읽기를 원본으로 사용합니다.\n    // 기존 Sheet snapshot/version은 이력·fallback 용도로 유지하되 DB hydrate/reconcile 이후에는\n    // Sheet delta가 최신 DB 객실상태를 되돌리지 못하도록 동일 merge 경로에서 보호합니다.\n    'roomStatus', 'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'\n  ]);"""

if old not in text:
    raise SystemExit('ERROR: NOVA_REALTIME_ROOM_FIELDS_ baseline block not found; refusing broad rewrite.')

text = text.replace(old, new, 1)
PATH.write_text(text, encoding='utf-8')
print(f'Applied {MARKER}: roomStatus now follows the existing DB hydrate/reconcile merge authority.')