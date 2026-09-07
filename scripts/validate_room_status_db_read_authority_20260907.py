from pathlib import Path
import re

CLIENT = Path('Client.html').read_text(encoding='utf-8')
SYNC = Path('RealtimeDailySync.js').read_text(encoding='utf-8')


def require(text, needle, label):
    if needle not in text:
        raise SystemExit(f'ERROR: missing {label}: {needle}')
    print(f'[OK] {label}')


def require_regex(text, pattern, label):
    if not re.search(pattern, text, flags=re.S):
        raise SystemExit(f'ERROR: missing {label}: {pattern}')
    print(f'[OK] {label}')

require(CLIENT, 'ROOM_STATUS_DB_READ_AUTHORITY_V1', 'roomStatus DB read-authority marker')
require_regex(
    CLIENT,
    r"const NOVA_REALTIME_ROOM_FIELDS_ = Object\.freeze\(\[.*?'roomStatus',\s*'cleaningStatus'",
    'roomStatus is owned by the Realtime merge field list',
)
require(CLIENT, "roomStatus: String(row.room_status ?? row.roomStatus ?? '')", 'full DB row maps roomStatus')
require(CLIENT, "putText('roomStatus', 'room_status', 'roomStatus');", 'partial DB row maps roomStatus')
require(CLIENT, 'NOVA_REALTIME_ROOM_FIELDS_.forEach(key => {', 'single merge authority remains')
require_regex(
    CLIENT,
    r"function novaRealtimeProtectRoomArray_\(incomingRooms, currentRooms\).*?novaRealtimeMergeRoom_\(room, previous\)",
    'Sheet delta protection keeps current DB-owned fields over incoming Sheet snapshot',
)
require_regex(
    CLIENT,
    r"async function novaRealtimeHydrateCurrentView_\(\).*?novaRealtimeLoadRoomsForSite_.*?novaRealtimeMergeRoom_",
    'initial hydrate reads DB rooms and merges them into the current view',
)
require_regex(
    CLIENT,
    r"async function novaRealtimeReconcileIndicatorRooms_\(\).*?novaRealtimeLoadRoomsForSite_.*?novaRealtimeMergeRoom_",
    'indicator reconciliation keeps reading DB room state',
)
require(CLIENT, 'roomStatusProtections: new Map()', 'post-write roomStatus protection remains')
require(CLIENT, 'CHECKOUT_DB_FIRST_CLIENT_V1', 'CHECKED_OUT DB-first path remains')
require(CLIENT, "|| mappedAction === 'CHANGE_ROOM_STATUS';", 'CHANGE_ROOM_STATUS Realtime routing remains')
require(SYNC, "roomStatus: String(row[map['객실상태']] || '').trim()", 'Sheet-to-DB fallback/forward sync still carries roomStatus')
require(SYNC, "action === 'CHANGE_ROOM_STATUS'", 'DB event to Sheet room-status mirror remains')

# Guard against accidentally reintroducing the old explicit design statement that roomStatus is Sheet-owned.
old_comment = '객실상태/배정/객실운영상태(고장·객실확인)는 기존 Sheets가 원본이므로'
if old_comment in CLIENT:
    raise SystemExit('ERROR: old Sheet-owned roomStatus design comment still present')
print('[OK] old Sheet-owned roomStatus authority statement removed')

print('ROOM_STATUS_DB_READ_AUTHORITY_V1 validation: PASS')