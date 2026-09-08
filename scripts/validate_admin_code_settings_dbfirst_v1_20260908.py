from pathlib import Path
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


def order(text, left, right, label):
    li = text.find(left)
    ri = text.find(right)
    ok = li >= 0 and ri >= 0 and li < ri
    checks.append((label, ok))
    if not ok:
        errors.append(f'ORDER: {label} :: {left} -> {right}')


def node_check(path, label):
    result = subprocess.run(['node', '--check', path], text=True, capture_output=True, check=False)
    ok = result.returncode == 0
    checks.append((label, ok))
    if not ok:
        errors.append(f'SYNTAX: {label} :: {(result.stderr or result.stdout).strip()}')


def html_check(path, label):
    text = read(path)
    blocks = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
    if not blocks:
        checks.append((label, False))
        errors.append(f'SYNTAX: {label} :: no script block')
        return
    result = subprocess.run(['node', '--check', '-'], input='\n'.join(blocks), text=True, capture_output=True, check=False)
    ok = result.returncode == 0
    checks.append((label, ok))
    if not ok:
        errors.append(f'SYNTAX: {label} :: {(result.stderr or result.stdout).strip()}')


bridge = read('AdminCodeSettingsDbFirstBridge.js')
admin_bridge = read('AdminSettingsDbFirstBridge.js')
db_bridge = read('DbFirstBridge.js')
client = read('Client.html')
legacy = read('15_AdminSettings.js')
patcher = read('scripts/patch_admin_code_settings_dbfirst_v1_20260908.py')
canonical = read('scripts/fix_patch_site_scope_v2.py')
schema_sql = read('supabase/migrations/20260908_admin_code_settings_db_first_v1.sql')
scope_sql = read('supabase/migrations/20260908_admin_code_settings_scope_v3.sql')

# Runtime bridge and exact authority boundary.
require(bridge, 'NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1', 'admin-code DB-first marker')
require(bridge, "GROUPS: Object.freeze(['동','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목'])", 'stable 8-group authority boundary')
for excluded in ['사업장', '객실타입', '직무', '운영설정', '텔레그램알림대상', 'QM체크리스트', 'QM점검장소']:
    forbid(bridge.split('GROUPS: Object.freeze(', 1)[1].split(')', 1)[0], f"'{excluded}'", f'excluded group {excluded}')
require(bridge, 'if (!novaAdminCodeSettingsIsDbGroup_(group)) return saveAdminCodeRow(token, payload);', 'non-DB save legacy preservation')
require(bridge, 'if (!novaAdminCodeSettingsIsDbGroup_(group)) return disableAdminCodeRow(token, payload);', 'non-DB disable legacy preservation')
require(bridge, "error.code = 'ADMIN_CODE_DB_UNAVAILABLE'", 'DB group write fail-closed')
require(bridge, 'novaAdminCodeMarkMirrorPending_', 'Sheet mirror pending marker')
require(bridge, 'novaAdminCodeRetryPendingMirrors_', 'Sheet mirror retry')
require(bridge, 'novaAdminCodeOverlayGroups_', 'DB group overlay')
order(bridge, "const db = novaDbFirstRpc_(token, 'nova_admin_code_settings_save_v1'", "novaAdminCodeMarkMirrorPending_('SAVE'", 'DB save precedes Sheet mirror pending')
order(bridge, "const db = novaDbFirstRpc_(token, 'nova_admin_code_settings_disable_v1'", "novaAdminCodeMarkMirrorPending_('DISABLE'", 'DB disable precedes Sheet mirror pending')

# Admin settings read overlays only confirmed DB groups while operation settings remains independent.
require(admin_bridge, 'novaAdminCodeSettingsDbRead_(token)', 'admin settings DB code read')
require(admin_bridge, 'novaAdminCodeRetryPendingMirrors_(token)', 'admin settings pending mirror retry')
require(admin_bridge, 'novaAdminCodeOverlayGroups_(legacy.groups, codeDb)', 'admin settings DB group overlay')
require(admin_bridge, 'result.adminCodeSettingsDbFirst = true', 'admin settings DB status flag')
require(admin_bridge, 'result.operationSettingsDbFirst = true', 'operation settings DB-first preserved')

# RPC allowlist and client routes.
for rpc in ['nova_admin_code_settings_read_v1', 'nova_admin_code_settings_save_v1', 'nova_admin_code_settings_disable_v1']:
    require(db_bridge, f"'{rpc}'", f'RPC allowlist {rpc}')
require(client, "callServer('saveAdminCodeRowDbFirst'", 'client admin-code save DB route')
require(client, "callServer('disableAdminCodeRowDbFirst'", 'client admin-code disable DB route')
require(client, "novaRealtimeRequestId_('ADMIN_CODE_SAVE_V1'", 'admin-code save request id')
require(client, "novaRealtimeRequestId_('ADMIN_CODE_DISABLE_V1'", 'admin-code disable request id')
forbid(client, "callServer('saveAdminCodeRow', state.token, payload)", 'direct Sheet admin-code save removed from client')
forbid(client, "callServer('disableAdminCodeRow', state.token, { group: state.settings.selectedGroup, code })", 'direct Sheet admin-code disable removed from client')

# Legacy writers stay as compatibility mirrors.
require(legacy, 'function saveAdminCodeRow(token, payload)', 'legacy admin-code save writer preserved')
require(legacy, 'function disableAdminCodeRow(token, payload)', 'legacy admin-code disable writer preserved')
require(legacy, 'function seedAdminSettingsCodes_()', 'automatic seed behavior preserved')

# Database schema/security and scope migration.
require(schema_sql, 'NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1', 'admin-code schema migration marker')
require(schema_sql, 'alter table public.nova_code_settings enable row level security', 'admin-code table RLS')
require(schema_sql, 'nova_admin_code_settings_read_v1', 'admin-code read RPC migration')
require(schema_sql, 'nova_admin_code_settings_save_v1', 'admin-code save RPC migration')
require(schema_sql, 'nova_admin_code_settings_disable_v1', 'admin-code disable RPC migration')
require(schema_sql, 'revoke all on table public.nova_code_settings', 'direct table privileges revoked')
require(scope_sql, 'NOVA_ADMIN_CODE_SETTINGS_SCOPE_V3', 'stable scope migration marker')
require(scope_sql, 'baseline_count=48', 'stable 8-group baseline')
require(scope_sql, "array['동','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목']", 'scope RPC exact stable groups')
for excluded in ["'사업장'", "'객실타입'", "'직무'"]:
    forbid(scope_sql.split("where group_code = any", 1)[1].split(';', 1)[0], excluded, f'scope read excludes {excluded}')

# Canonical patch ownership.
require(patcher, "'nova_admin_code_settings_read_v1'", 'patcher RPC allowlist ownership')
require(patcher, "callServer('saveAdminCodeRowDbFirst'", 'patcher client save route ownership')
require(patcher, "callServer('disableAdminCodeRowDbFirst'", 'patcher client disable route ownership')
require(canonical, 'patch_admin_code_settings_dbfirst_v1_20260908.py', 'canonical admin-code patch registration')
require(canonical, 'validate_admin_code_settings_dbfirst_v1_20260908.py', 'canonical admin-code validator registration')

node_check('AdminCodeSettingsDbFirstBridge.js', 'AdminCode bridge JavaScript syntax')
node_check('AdminSettingsDbFirstBridge.js', 'AdminSettings bridge JavaScript syntax')
node_check('DbFirstBridge.js', 'DB bridge JavaScript syntax')
html_check('Client.html', 'Client script syntax')

if errors:
    print(f'Admin code settings DB-first gate FAILED: {len(errors)} issue(s), {len(checks)} checks.', file=sys.stderr)
    for error in errors:
        print(f' - {error}', file=sys.stderr)
    raise SystemExit(97)

print(f'Admin code settings DB-first gate passed: {len(checks)} checks.')
