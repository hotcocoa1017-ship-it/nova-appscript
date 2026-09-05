from pathlib import Path

client = Path('Client.html').read_text(encoding='utf-8')
mobile = Path('10_Mobile.js').read_text(encoding='utf-8')
guard = Path('RoommaidDueOutGuard.html').read_text(encoding='utf-8')

checks = {
    'client marker': 'ROOMMAID_DUE_OUT_START_GUARD_V2' in client,
    'card status code attribute': 'data-room-status=' in client,
    'due-out code render check': "String(room.roomStatus || '').trim().toUpperCase() === 'DUE_OUT'" in client,
    'disabled start rendering': 'data-due-out-start-guard="Y"' in client and 'aria-disabled="true"' in client,
    'pre-action due-out guard': "mobileRoomAction === 'START'" in client and "String(room?.roomStatus || '').trim().toUpperCase() === 'DUE_OUT'" in client,
    'server realtime due-out guard': "action === 'CLEANING_START' && currentRoomStatus === 'DUE_OUT'" in mobile,
    'server legacy due-out guard': "role === 'ROOMMAID' && action === 'START' && currentRoomStatus === 'DUE_OUT'" in mobile,
    'dom guard v2': 'ROOMMAID_DUE_OUT_START_GUARD_V2' in guard,
    'dom guard uses code': "card?.dataset?.roomStatus" in guard and "return status === 'DUE_OUT'" in guard,
    'dom guard ignores translated label': ".mobile-room-status b" not in guard,
    'due-out remains visible disabled': "startButton.hidden = false;" in guard and "startButton.disabled = true;" in guard,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('ROOMMAID_DUE_OUT_START_GUARD_V2 validation failed: ' + ', '.join(failed))

# Policy simulation: only DUE_OUT is blocked; stock and checked-out states remain eligible.
def allowed(status):
    return str(status or '').strip().upper() != 'DUE_OUT'

expected_allowed = ['STOCK', 'STOCK_RC', 'STOCK_HU', 'CHECKED_OUT']
for status in expected_allowed:
    if not allowed(status):
        raise SystemExit(f'{status} must remain start-enabled')
if allowed('DUE_OUT'):
    raise SystemExit('DUE_OUT must be start-disabled')
if not allowed('CHECKED_OUT'):
    raise SystemExit('DUE_OUT -> CHECKED_OUT must reactivate start')

print('ROOMMAID_DUE_OUT_START_GUARD_V2 validation PASS')
