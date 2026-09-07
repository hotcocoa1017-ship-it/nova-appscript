from pathlib import Path
import sys

client = Path('Client.html').read_text(encoding='utf-8')
mirror = Path('RealtimeDailySync.js').read_text(encoding='utf-8')
indicator = Path('06_Indicator.js').read_text(encoding='utf-8')


def require(text: str, needle: str, label: str):
    if needle not in text:
        raise SystemExit(f'ERROR: missing {label}: {needle}')


def forbid(text: str, needle: str, label: str):
    if needle in text:
        raise SystemExit(f'ERROR: forbidden {label}: {needle}')


require(client, 'CHECKOUT_DB_FIRST_CLIENT_V1', 'client marker')
require(client, "|| mappedAction === 'CHANGE_ROOM_STATUS';", 'all room-status Realtime routing')
require(client, "if (action === 'CHANGE_ROOM_STATUS' && optimisticPatch) {", 'checkout realtimeRoomPatch build')
forbid(
    client,
    "mappedAction === 'CHANGE_ROOM_STATUS'\n        && String(safe.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT'",
    'CHECKED_OUT Realtime routing exclusion'
)
forbid(
    client,
    "action === 'CHANGE_ROOM_STATUS'\n        && String(payload.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT'",
    'CHECKED_OUT realtimeRoomPatch exclusion'
)

# Existing optimistic state rules are intentionally reused for CHECKED_OUT.
require(
    client,
    "['CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU', 'STOCK', 'STOCK_RC', 'STOCK_HU'].includes(nextRoomStatus)",
    'checkout optimistic status family'
)
require(client, "cleaningStatus: 'WAITING'", 'checkout optimistic WAITING state')
require(client, 'sheetExpectedVersion:', 'legacy fallback Sheet-version preservation')
require(client, 'roomStatusProtections.set', 'stale Sheet protection')

# DB event -> Sheet mirror must preserve the established room-status semantics/history.
require(mirror, "if (action === 'CHANGE_ROOM_STATUS') {", 'CHANGE_ROOM_STATUS event mirror')
require(mirror, 'buildIndicatorPreviousCycleArchiveUpdates_(rowInfo.data)', 'previous cycle archive mirror')
require(mirror, "updates['객실상태'] = requestedRoomStatus", 'Sheet room status mirror')
require(mirror, 'resolveManualRoomStatusState_(requestedRoomStatus, rowInfo.data)', 'cleaning-state compatibility mirror')
require(mirror, 'NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE', 'room status history record type')
require(mirror, "status: 'CHANGE_ROOM_STATUS'", 'room status history status')
require(mirror, 'specialDepartureStarted:', 'special checkout parity metadata')

# Realtime-disabled/legacy fallback remains intact; DB-first only changes the active Realtime route.
require(indicator, 'function changeIndicatorRoomCheckoutFast_', 'legacy checkout fallback')
require(indicator, "String(safe.roomStatus || '').trim().toUpperCase() === 'CHECKED_OUT'", 'legacy checkout dispatch')
require(indicator, "updates['객실상태'] = requestedRoomStatus", 'legacy checkout room-state update')

print('CHECKOUT_DB_FIRST_V1 validation: PASS')
