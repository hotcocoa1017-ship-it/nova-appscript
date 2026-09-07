from pathlib import Path
import sys

PATH = Path('cloudrun/index.js')
text = PATH.read_text(encoding='utf-8')
MARKER = 'CHECKOUT_DB_FIRST_V1'

if MARKER in text:
    print(f'{MARKER} already applied.')
    sys.exit(0)

old = """        if (requestedRoomStatus === 'CHECKED_OUT') {\n          throw httpError(400, 'CHECKOUT_LEGACY_ONLY', '퇴실은 기존 전용 저장경로를 사용합니다.');\n        }\n\n        const rawPatch = body.realtimeRoomPatch && typeof body.realtimeRoomPatch === 'object'\n"""
new = """        // CHECKOUT_DB_FIRST_V1 · 일반 퇴실도 기존 CHANGE_ROOM_STATUS DB 트랜잭션을 사용합니다.\n        // R/C·H/U와 동일하게 room_status + 정비상태 patch + event를 한 트랜잭션으로 확정합니다.\n        const rawPatch = body.realtimeRoomPatch && typeof body.realtimeRoomPatch === 'object'\n"""

count = text.count(old)
if count != 1:
    raise SystemExit(f'ERROR: checkout legacy guard anchor count={count}, expected=1')

text = text.replace(old, new, 1)
PATH.write_text(text, encoding='utf-8')
print(f'Applied {MARKER}: CHECKED_OUT now uses CHANGE_ROOM_STATUS DB-first transaction.')
