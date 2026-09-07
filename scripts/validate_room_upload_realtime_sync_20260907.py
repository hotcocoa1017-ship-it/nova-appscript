from pathlib import Path

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

# Existing upload semantics remain Sheet-first for this bridge phase.
require(upload, "function applyRoomStatusUpload", 'existing upload apply')
require(upload, "sheet.getRange(firstWrittenRow, 1, newRows.length, lastColumn).setValues(newRows)", 'in-place Sheet upload write')
require(upload, "appendUnifiedHistory_({", 'upload unified history')
require(upload, "NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD", 'upload history type')

print('ROOM_UPLOAD_REALTIME_CONVERGENCE_V1 validation: PASS')
