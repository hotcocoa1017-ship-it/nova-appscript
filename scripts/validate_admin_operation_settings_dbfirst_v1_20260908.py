from pathlib import Path
import hashlib
import re
import subprocess
import sys

errors = []
checks = []


def read(path):
    p = Path(path)
    if not p.exists():
        errors.append(f'MISSING FILE: {path}')
        return ''
    return p.read_text(encoding='utf-8')


def require(text, needle, label):
    ok = needle in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'MISSING: {label} :: {needle}')


def forbid(text, needle, label):
    ok = needle not in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'FORBIDDEN: {label} :: {needle}')


def digest(paths):
    h = hashlib.sha256()
    for path in paths:
        p = Path(path)
        h.update(path.encode('utf-8'))
        h.update(b'\0')
        h.update(p.read_bytes() if p.exists() else b'<missing>')
        h.update(b'\0')
    return h.hexdigest()


def node_check(path, label):
    result = subprocess.run(['node', '--check', path], text=True, capture_output=True, check=False)
    ok = result.returncode == 0
    checks.append((label, ok))
    if not ok:
        errors.append(f'SYNTAX: {label} :: {(result.stderr or result.stdout).strip()}')


bridge = read('DbFirstBridge.js')
admin_bridge = read('AdminSettingsDbFirstBridge.js')
client = read('Client.html')
canonical = read('scripts/fix_patch_site_scope_v2.py')

require(admin_bridge, 'NOVA_OPERATION_SETTINGS_DB_FIRST_V1', 'operation settings bridge marker')
require(admin_bridge, 'function getAdminSettingsDataDbFirst(', 'DB-first admin settings read wrapper')
require(admin_bridge, 'function saveAdminOperationSettingsDbFirst(', 'DB-first admin settings save wrapper')
require(admin_bridge, "novaDbFirstRpc_(token, 'nova_operation_settings_save_v1'", 'DB operation settings save RPC')
require(admin_bridge, "error.code = 'OPERATION_SETTINGS_DB_UNAVAILABLE'", 'DB write fail-closed on unavailable read')
forbid(admin_bridge, "return saveAdminOperationSettings(token, payload);", 'no Sheet-only write fallback after cutover')
require(bridge, "'nova_operation_settings_read_v1'", 'operation settings read RPC allowlist')
require(bridge, "'nova_operation_settings_save_v1'", 'operation settings save RPC allowlist')
require(client, "callServer('getAdminSettingsDataDbFirst', state.token)", 'client admin settings DB-first read')
require(client, "callServer('saveAdminOperationSettingsDbFirst', state.token", 'client admin settings DB-first save')
require(client, "novaRealtimeRequestId_('OPERATION_SETTINGS_V1', 'ADMIN')", 'client operation settings request id')
forbid(client, "callServer('getAdminSettingsData', state.token)", 'legacy direct admin settings read route removed')
forbid(client, "callServer('saveAdminOperationSettings', state.token, { values })", 'legacy direct admin settings save route removed')
require(canonical, 'patch_admin_operation_settings_dbfirst_v1_20260908.py', 'canonical operation settings patch')
require(canonical, 'validate_admin_operation_settings_dbfirst_v1_20260908.py', 'canonical operation settings validator')

node_check('DbFirstBridge.js', 'DbFirstBridge.js')
node_check('AdminSettingsDbFirstBridge.js', 'AdminSettingsDbFirstBridge.js')
blocks = re.findall(r'<script[^>]*>(.*?)</script>', client, flags=re.S | re.I)
if not blocks:
    errors.append('SYNTAX: Client.html script block missing')
else:
    result = subprocess.run(['node', '--check', '-'], input='\n'.join(blocks), text=True, capture_output=True, check=False)
    ok = result.returncode == 0
    checks.append(('Client.html scripts', ok))
    if not ok:
        errors.append(f'SYNTAX: Client.html :: {(result.stderr or result.stdout).strip()}')

tracked = ['DbFirstBridge.js', 'Client.html', 'scripts/fix_patch_site_scope_v2.py']
before = digest(tracked)
result = subprocess.run([sys.executable, 'scripts/patch_admin_operation_settings_dbfirst_v1_20260908.py'], text=True, capture_output=True, check=False)
if result.returncode != 0:
    errors.append(f'IDEMPOTENCE PATCH FAILED: {(result.stderr or result.stdout).strip()}')
after = digest(tracked)
idempotent = before == after
checks.append(('operation settings patch idempotent', idempotent))
if not idempotent:
    errors.append('IDEMPOTENCE: operation settings patch changed sources on second run')

if errors:
    print(f'Admin operation settings DB-first gate FAILED: {len(errors)} issue(s), {len(checks)} checks.', file=sys.stderr)
    for error in errors:
        print(f' - {error}', file=sys.stderr)
    raise SystemExit(98)

print(f'Admin operation settings DB-first gate passed: {len(checks)} checks.')
