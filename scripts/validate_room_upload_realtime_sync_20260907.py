from pathlib import Path
import re

client = Path('Client.html').read_text(encoding='utf-8')
sync = Path('RealtimeDailySync.js').read_text(encoding='utf-8')
upload = Path('09_RoomStatusUpload.js').read_text(encoding='utf-8')


def require(text: str, needle: str, label: str):
    if needle not in text:
        raise SystemExit(f'ERROR: missing {label}: {needle}')


def require_order(text: str, first: str, second: str, label: str):
    a = text.find(first)
    b = text.find(second)
    if a < 0 or b < 0 or a >= b:
        raise SystemExit(f'ERROR: invalid order for {label}')


def require_regex(text: str, pattern: str, label: str):
    if not re.search(pattern, text, flags=re.S):
        raise SystemExit(f'ERROR: missing {label}: {pattern}')


require(client, 'ROOM_UPLOAD_REALTIME_CONVERGENCE_V1', 'client convergence marker')
require(client, "callServer('syncRoomStatusUploadRealtimeNow'", 'post-upload sync call')
require(client, "if (novaRealtimeIsEnabled_())", 'Realtime enabled guard')
require(client, "syncResult?.deferred", 'backlog deferred handling')
require(client, "예약동기화로 재반영", 'scheduled fallback status')

require(sync, 'ROOM_UPLOAD_REALTIME_CONVERGENCE_V1', 'server convergence marker')
require(sync, "requireRole_(token, ['ADMIN', 'ORDER'])", 'role guard')
require(sync, "if (!novaRealtimeFinalEnabled_())", 'Realtime server guard')
require(sync, "mirrorNovaRealtimeEventsDrain_({ maxBatches: 2, timeBudgetMs: 45000 })", 'mirror-first drain')
require(sync, "reason: 'REALTIME_EVENT_BACKLOG'", 'backlog fail-safe')
require(sync, "syncNovaRealtimeCurrentBusinessDate(dateText, siteText, {})", 'targeted forward sync')
require(sync, 'NOVA_REALTIME_FINAL.LAST_FORWARD_SYNC_MS', 'forward-sync cadence reset')
require_order(
    sync,
    "mirrorNovaRealtimeEventsDrain_({ maxBatches: 2, timeBudgetMs: 45000 })",
    "syncNovaRealtimeCurrentBusinessDate(dateText, siteText, {})",
    'DB events must mirror before forward sync'
)

# ROOM_STATUS_DB_READ_AUTHORITY_V1 · DB hydrate/reconcile is now the read authority for roomStatus.
require(client, 'ROOM_STATUS_DB_READ_AUTHORITY_V1', 'roomStatus DB read-authority marker')
require_regex(
    client,
    r"const NOVA_REALTIME_ROOM_FIELDS_ = Object\.freeze\(\[.*?'roomStatus',\s*'cleaningStatus'",
    'roomStatus is owned by the Realtime merge field list'
)
require(client, "roomStatus: String(row.room_status ?? row.roomStatus ?? '')", 'full DB row maps roomStatus')
require(client, "putText('roomStatus', 'room_status', 'roomStatus');", 'partial DB row maps roomStatus')
require(client, 'NOVA_REALTIME_ROOM_FIELDS_.forEach(key => {', 'single DB merge authority remains')
require_regex(
    client,
    r"function novaRealtimeProtectRoomArray_\(incomingRooms, currentRooms\).*?novaRealtimeMergeRoom_\(room, previous\)",
    'Sheet delta cannot overwrite current DB-owned roomStatus'
)
require_regex(
    client,
    r"async function novaRealtimeHydrateCurrentView_\(\).*?novaRealtimeLoadRoomsForSite_.*?novaRealtimeMergeRoom_",
    'initial view hydrate reads and merges DB roomStatus'
)
require_regex(
    client,
    r"async function novaRealtimeReconcileIndicatorRooms_\(\).*?novaRealtimeLoadRoomsForSite_.*?novaRealtimeMergeRoom_",
    'indicator reconcile continues to merge DB roomStatus'
)
require(client, 'roomStatusProtections: new Map()', 'post-write roomStatus protection remains')
require(client, 'CHECKOUT_DB_FIRST_CLIENT_V1', 'CHECKED_OUT DB-first path remains')
require(client, "|| mappedAction === 'CHANGE_ROOM_STATUS';", 'CHANGE_ROOM_STATUS Realtime routing remains')
require(sync, "roomStatus: String(row[map['객실상태']] || '').trim().toUpperCase()", 'Sheet-to-DB fallback still carries roomStatus')
require(sync, "action === 'CHANGE_ROOM_STATUS'", 'DB event to Sheet room-status mirror remains')
if '객실상태/배정/객실운영상태(고장·객실확인)는 기존 Sheets가 원본이므로' in client:
    raise SystemExit('ERROR: old Sheet-owned roomStatus authority statement still present')

# Existing upload semantics remain Sheet-first for this bridge phase; only read authority changes here.
require(upload, "function applyRoomStatusUpload", 'existing upload apply')
require(upload, "sheet.getRange(firstWrittenRow, 1, newRows.length, lastColumn).setValues(newRows)", 'in-place Sheet upload write')
require(upload, "appendUnifiedHistory_({", 'upload unified history')
require(upload, "NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD", 'upload history type')

print('ROOM_UPLOAD_REALTIME_CONVERGENCE_V1 + ROOM_STATUS_DB_READ_AUTHORITY_V1 validation: PASS')