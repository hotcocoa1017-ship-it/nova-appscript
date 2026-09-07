from pathlib import Path
import sys

CLIENT = Path('Client.html').read_text(encoding='utf-8')
SYNC = Path('RealtimeDailySync.js').read_text(encoding='utf-8')
MARKER = 'ROOM_PREVIOUS_CYCLE_DB_AUTHORITY_V1'


def require(text: str, needle: str, label: str):
    if needle not in text:
        print(f'ERROR: missing {label}: {needle}', file=sys.stderr)
        raise SystemExit(91)


require(SYNC, MARKER, 'sync marker')
require(CLIENT, MARKER, 'client marker')

for header, field in [
    ('마지막객실상태', 'lastRoomStatus'),
    ('이전객실상태', 'previousRoomStatus'),
    ('이전청소상태', 'previousCleaningStatus'),
    ('이전룸메이드사번', 'previousRoommaidEmployeeNo'),
    ('이전보조룸메이드사번', 'previousSecondaryRoommaidEmployeeNo'),
]:
    require(SYNC, f"map['{header}']", f'{header} header mapping')
    require(SYNC, f'{field}:', f'{field} forward payload')
    require(CLIENT, f"'{field}'", f'{field} DB-owned field')

require(CLIENT, 'NOVA_REALTIME_CLEANING_TARGET_ROOM_STATUSES_', 'cleaning-target status list')
for status in ['CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU', 'STOCK', 'STOCK_RC', 'STOCK_HU']:
    require(CLIENT, f"'{status}'", f'{status} target status')

require(CLIENT, 'hasDbPreviousCycleMetadata', 'DB previous-cycle merge gate')
require(CLIENT, "currentRoomStatus === 'VACANT_CLEAN'", 'VACANT_CLEAN display base rule')
require(CLIENT, 'merged.displayBaseRoomStatus', 'displayBaseRoomStatus reconstruction')
require(CLIENT, 'merged.previousCycle = {', 'previousCycle reconstruction')
require(CLIENT, 'merged.previousCycle = null;', 'previousCycle clear rule')
require(CLIENT, 'room.previousCycle?.roomStatus', 'visual signature previous room status')
require(CLIENT, 'room.previousCycle?.cleaningStatus', 'visual signature previous cleaning status')
require(CLIENT, 'room.previousCycle?.roommaidEmployeeNo', 'visual signature previous primary')
require(CLIENT, 'room.previousCycle?.secondaryRoommaidEmployeeNo', 'visual signature previous secondary')

# Existing DB read authority and operation flags must remain in the same field list.
for field in ['roomStatus', 'cleaningStatus', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt']:
    require(CLIENT, f"'{field}'", f'existing DB-owned field {field}')

# Existing signed sync endpoint must remain unchanged.
require(SYNC, "novaRealtimeFinalSignedPost_('/v1/admin/sync-current-rooms'", 'signed current-room sync endpoint')

print('PASS: room previous-cycle/display metadata DB authority is prepared without removing existing room DB authority.')
