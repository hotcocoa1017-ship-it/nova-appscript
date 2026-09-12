from pathlib import Path
import re
import subprocess
import sys

errors = []


def read(path):
    p = Path(path)
    if not p.exists():
        errors.append(f'MISSING FILE: {path}')
        return ''
    return p.read_text(encoding='utf-8')


def require(text, needle, label):
    if needle not in text:
        errors.append(f'MISSING {label}: {needle}')


def forbid(text, needle, label):
    if needle in text:
        errors.append(f'FORBIDDEN {label}: {needle}')


bridge = read('DbFirstBridge.js')
shift = read('12_Shifts.js')
migration = read('supabase/migrations/20260912_shift_management_site_scope_parity_v1.sql')
incident = read('docs/incidents/2026-09-12-shift-management-regression.md')

require(bridge, 'SHIFT_MANAGEMENT_READ_NONBLOCKING_V1', 'nonblocking read marker')
require(bridge, 'readNonBlocking: true', 'nonblocking response flag')
require(bridge, 'sheetMirrorPending: mirrorPending', 'pending mirror diagnostic only')

m = re.search(r'function getShiftManagementDataDbFirst\(.*?\n}\n\nfunction saveShiftAssignmentsDbFirst', bridge, flags=re.S)
if not m:
    errors.append('Could not isolate getShiftManagementDataDbFirst')
else:
    read_block = m.group(0)
    forbid(read_block, 'mirrorShiftZoneDbStateToSheets_(token, db)', 'Sheet mirror write inside shift read path')
    require(read_block, "'nova_houseman_shift_zone_get_v2'", 'DB authority read')

# Compatibility mirrors must still exist on write paths.
require(bridge, 'function mirrorShiftZoneDbStateToSheets_', 'legacy mirror helper preserved')
require(bridge, 'markShiftZoneMirrorPending_(businessDate, site)', 'write mirror retry marker preserved')

# Multiple shifts for the same employee are a valid operating rule.
require(shift, 'Object.keys(NOVA.SHIFTS).forEach', 'legacy per-shift iteration')
forbidden_cross_shift_phrases = [
    'duplicateAcrossShifts',
    '이미 다른 근무조에',
    '한 개 조만',
    'one shift only'
]
for phrase in forbidden_cross_shift_phrases:
    forbid(shift, phrase, 'cross-shift duplicate rejection')

# Shift-only site parity: use active confirmed site master and do not mutate nova_users permissions.
require(migration, 'SHIFT_MANAGEMENT_SITE_SCOPE_PARITY_V1', 'site parity migration marker')
require(migration, "c.group_code='사업장' and c.enabled=true and c.confirmed=true", 'active site master rule')
require(migration, "nova_houseman_shift_zone_get_v1", 'shift read RPC scoped patch')
require(migration, "nova_houseman_shift_save_v1", 'shift save RPC scoped patch')
require(migration, "nova_houseman_zone_save_v1", 'zone save RPC scoped patch')
require(migration, "nova_houseman_shift_zone_bootstrap_v3", 'bootstrap RPC scoped patch')
forbid(migration.lower(), 'update public.nova_users', 'global user permission mutation')
forbid(migration.lower(), 'alter table public.nova_users', 'global user schema mutation')

require(incident, 'DB 성공 조회 후 Sheet 쓰기 금지', 'durable incident invariant')
require(incident, '복수 근무조 배정은 정상', 'multi-shift operating rule record')

# Syntax check touched Apps Script server file.
result = subprocess.run(['node', '--check', 'DbFirstBridge.js'], text=True, capture_output=True)
if result.returncode != 0:
    errors.append('DbFirstBridge.js syntax error: ' + (result.stderr or result.stdout).strip())

if errors:
    print('\n'.join('ERROR: ' + e for e in errors), file=sys.stderr)
    raise SystemExit(92)

print('Shift-management regression guard: PASS')
