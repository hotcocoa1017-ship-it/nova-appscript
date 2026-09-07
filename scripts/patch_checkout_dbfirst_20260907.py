from pathlib import Path
import sys

PATH = Path('Client.html')
text = PATH.read_text(encoding='utf-8')
MARKER = 'CHECKOUT_DB_FIRST_CLIENT_V1'


def replace_once(old: str, new: str, label: str):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected=1')
    text = text.replace(old, new, 1)


if MARKER in text:
    print(f'{MARKER} already applied.')
    sys.exit(0)

replace_once(
    """    // 일반 객실상태 Realtime 저장 직후 Sheet 미러가 따라올 때까지만 상태를 보호한다.\n    // CHECKED_OUT은 이 보호맵을 사용하지 않으므로 기존 Apps Script 퇴실 결과가 stale DB에 의해 되돌아가지 않는다.\n""",
    """    // CHECKOUT_DB_FIRST_CLIENT_V1 · 일반 퇴실을 포함한 Realtime 객실상태 저장 직후\n    // DB 이벤트의 Sheet 미러가 따라올 때까지만 확정 상태를 보호한다.\n""",
    'checkout protection comment marker'
)

replace_once(
    """    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_CLEAR', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)\n      || (mappedAction === 'CHANGE_ROOM_STATUS'\n        && String(safe.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT');\n""",
    """    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_CLEAR', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)\n      || mappedAction === 'CHANGE_ROOM_STATUS';\n""",
    'checkout realtime routing'
)

replace_once(
    """    if (action === 'CHANGE_ROOM_STATUS'\n        && String(payload.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT'\n        && optimisticPatch) {\n""",
    """    if (action === 'CHANGE_ROOM_STATUS' && optimisticPatch) {\n""",
    'checkout realtime room patch'
)

PATH.write_text(text, encoding='utf-8')
print(f'Applied {MARKER}: CHECKED_OUT uses existing CHANGE_ROOM_STATUS Realtime DB-first path.')
