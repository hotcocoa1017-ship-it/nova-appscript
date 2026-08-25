#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
BASE_PATCH = REPO / 'tools' / 'apply_realtime_roommaid_assignment_v20.py'
CLIENT = REPO / 'Client.html'
SYNC = REPO / 'RealtimeDailySync.js'
CLOUD_LIVE = Path.home() / 'nova-realtime' / 'cloud-run' / 'index.js'
CLOUD_SNAPSHOT = REPO / 'cloudrun' / 'index.js'


def fail(message):
    print(f'PATCH_ERROR: {message}')
    sys.exit(1)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)

for path in (BASE_PATCH, CLIENT, SYNC, CLOUD_LIVE, CLOUD_SNAPSHOT):
    if not path.exists():
        fail(f'file not found: {path}')

# Safety: the GitHub snapshot must still match the live Cloud Run source before patching.
if CLOUD_LIVE.read_bytes() != CLOUD_SNAPSHOT.read_bytes():
    fail('live Cloud Run index.js differs from the GitHub snapshot; stop before patching')

# The original patch was written for a one-line Express route. The actual production
# source is formatted across multiple lines. Execute the same reviewed patch body with
# route markers adapted to the exact production layout.
source = BASE_PATCH.read_text(encoding='utf-8')
source = replace_once(
    source,
    'route_start = cloud.find("app.post(\'/v1/rooms/:roomNo/action\', async (req, res, next) => {")\nroute_end = cloud.find("\\n\\n/**\\n * 하우스맨 오더 Realtime 선등록.", route_start)',
    'route_start = cloud.find("app.post(\\n  \'/v1/rooms/:roomNo/action\',")\nhouseman_route = cloud.find("app.post(\\n  \'/v1/houseman-orders\',", route_start)\nroute_end = cloud.rfind("/**", route_start, houseman_route) if houseman_route >= 0 else -1',
    'production Cloud Run route markers'
)

namespace = {
    '__file__': str(BASE_PATCH),
    '__name__': '__main__',
}
try:
    exec(compile(source, str(BASE_PATCH), 'exec'), namespace, namespace)
except SystemExit as error:
    if int(error.code or 0) != 0:
        raise

# Assignment is now DB-owned too, so broadcast / room-changes must be allowed to
# update assignment fields instead of only cleaning progress.
client = CLIENT.read_text(encoding='utf-8')
client = replace_once(
    client,
    "    'cleaningStatus', 'version', 'updatedAt'\n",
    "    'cleaningStatus', 'cleaningType', 'assignmentType',\n    'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo',\n    'version', 'updatedAt'\n",
    'Realtime assignment owned fields'
)

# When the DB has not yet received a newly-created roommaid user, JIT sync users/room
# and retry once, just like ROOM_NOT_FOUND / FORBIDDEN / INVALID_STATE.
client = replace_once(
    client,
    "      if (!['ROOM_NOT_FOUND', 'FORBIDDEN', 'INVALID_STATE'].includes(code)) throw error;",
    "      if (!['ROOM_NOT_FOUND', 'FORBIDDEN', 'INVALID_STATE', 'ROOMMAID_NOT_AVAILABLE'].includes(code)) throw error;",
    'assignment JIT retry code'
)

# Keep the displayed roommaid names aligned with the Realtime employee numbers on
# other ADMIN/ORDER clients without changing the UI structure.
merge_anchor = """    NOVA_REALTIME_ROOM_FIELDS_.forEach(key => {
      if (Object.prototype.hasOwnProperty.call(realtimeRoom, key)) merged[key] = realtimeRoom[key];
    });
    if (realtimeRoom.building) merged.building = realtimeRoom.building;
"""
merge_replacement = """    NOVA_REALTIME_ROOM_FIELDS_.forEach(key => {
      if (Object.prototype.hasOwnProperty.call(realtimeRoom, key)) merged[key] = realtimeRoom[key];
    });
    if (Object.prototype.hasOwnProperty.call(realtimeRoom, 'roommaidEmployeeNo')) {
      const roommaids = state.indicator.data?.staff?.roommaids || [];
      const primary = roommaids.find(user => String(user.employeeNo || '') === String(merged.roommaidEmployeeNo || ''));
      merged.roommaidName = primary?.name || String(merged.roommaidEmployeeNo || '');
    }
    if (Object.prototype.hasOwnProperty.call(realtimeRoom, 'secondaryRoommaidEmployeeNo')) {
      const roommaids = state.indicator.data?.staff?.roommaids || [];
      const secondary = roommaids.find(user => String(user.employeeNo || '') === String(merged.secondaryRoommaidEmployeeNo || ''));
      merged.secondaryRoommaidName = secondary?.name || String(merged.secondaryRoommaidEmployeeNo || '');
    }
    if (realtimeRoom.building) merged.building = realtimeRoom.building;
"""
client = replace_once(client, merge_anchor, merge_replacement, 'Realtime assignment display names')
CLIENT.write_text(client, encoding='utf-8')

# Remove local Apps Script backup copies created by the guarded patch. The live
# Cloud Run backup remains outside the clasp project for rollback.
for backup_path in (
    REPO / 'Client.html.backup_v19_before_assignment_realtime',
    REPO / 'RealtimeDailySync.js.backup_v19_before_assignment_realtime',
):
    if backup_path.exists():
        backup_path.unlink()

# Persist the exact patched Cloud Run source into GitHub too, so Cloud Run and GitHub
# have one auditable source of truth.
CLOUD_SNAPSHOT.write_bytes(CLOUD_LIVE.read_bytes())

# Final guard rails.
subprocess.run(['node', '--check', str(SYNC)], cwd=REPO, check=True)
subprocess.run(['node', '--check', str(CLOUD_LIVE)], cwd=CLOUD_LIVE.parent, check=True)
subprocess.run(['node', '--check', str(CLOUD_SNAPSHOT)], cwd=REPO, check=True)
subprocess.run(
    ['git', 'diff', '--check', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'],
    cwd=REPO,
    check=True,
)

print('PATCH_OK')
print('Changed: Client.html, RealtimeDailySync.js, cloudrun/index.js')
print('Live Cloud Run index.js patched and syntax checked')
print('Realtime added: ASSIGN_ROOMMAID')
print('Preserved: login, UI layout, existing START/COMPLETE, history, Telegram, permissions')
subprocess.run(
    ['git', 'diff', '--stat', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'],
    cwd=REPO,
    check=True,
)
