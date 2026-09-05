#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def text(name):
    return (ROOT / name).read_text(encoding='utf-8')


def require(condition, message):
    if not condition:
        raise SystemExit(message)


index = text('Index.html')
client = text('Client.html')
helper = text('QmFastPathClient.html')
qm = text('16_QmChecklist.js')
mirror = text('RealtimeDailySync.js')

require("include_('QmFastPathClient')" in index, 'QmFastPathClient include missing')
require('QM_FAST_START_PHOTO_V1' in helper, 'QM helper marker missing')
require("nova-qm-photo-v1" in helper, 'QM Edge slug missing')
require("nova_qm_browse_start" in helper, 'QM browse RPC missing')
require('NOVA_QM_FAST.startBrowse' in client, 'QM browse fast path missing')
require('NOVA_QM_FAST.uploadPhoto' in client, 'QM direct photo upload missing')
require('NOVA_QM_FAST.deletePhoto' in client, 'QM Storage delete missing')
require('NOVA_QM_FAST.viewPhoto' in client, 'QM Storage viewer missing')
require('QM_REALTIME_STALE_SHEET_VERIFY_V1' in qm, 'QM stale Sheet DB verification missing')
require('QM_START_MIRROR_ASSIGNMENT_V1' in mirror, 'QM_START assignment mirror missing')

# Existing degraded paths must remain available.
require("callServer('startQmMobileBrowseInspection'" in client, 'QM browse legacy fallback removed')
require("callServer('uploadQmInspectionPhoto'" in client, 'QM Drive upload fallback removed')
require("callServer('deleteQmInspectionPhoto'" in client, 'QM Drive delete path removed')
require("callServer('getQmInspectionPhoto'" in client, 'QM Drive viewer path removed')
require("callServer('startQmInspection'" in client, 'QM legacy draft preparation removed')
require('novaQmScheduleLegacyDraftMirror_' in client, 'QM Sheet draft mirror removed')

# New private-Storage file IDs must never be sent to the legacy Drive delete path.
delete_start = client.find('async function deleteQmInspectionPhoto_')
delete_end = client.find('\n  async function openQmPhotoViewer_', delete_start)
require(delete_start >= 0 and delete_end > delete_start, 'QM delete function not found')
delete_seg = client[delete_start:delete_end]
require("/^sbqm:/i.test(fileId)" in delete_seg, 'Storage file-id routing missing')
require(delete_seg.find('NOVA_QM_FAST.deletePhoto') < delete_seg.find("callServer('deleteQmInspectionPhoto'"), 'Storage delete must route before Drive fallback')

# No privileged server secret may be shipped in browser code.
for forbidden in ['SUPABASE_SERVICE_ROLE_KEY', 'service_role', 'DB_PASSWORD', 'NOVA_TOKEN_SECRET']:
    require(forbidden not in helper, f'forbidden browser secret marker: {forbidden}')

# New helper must be JavaScript-syntax valid.
scripts = re.findall(r'<script[^>]*>(.*?)</script>', helper, flags=re.S | re.I)
require(bool(scripts), 'QmFastPathClient script block missing')
with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8', delete=False) as handle:
    handle.write('\n'.join(scripts))
    temp_path = handle.name
result = subprocess.run(['node', '--check', temp_path], capture_output=True, text=True)
require(result.returncode == 0, 'QmFastPathClient syntax error: ' + (result.stderr or result.stdout))

print('QM_FAST_START_PHOTO_VALIDATION=PASS')
