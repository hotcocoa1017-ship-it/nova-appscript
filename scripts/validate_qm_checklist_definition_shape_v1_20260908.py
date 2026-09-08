from pathlib import Path
import subprocess
import sys

errors=[]
checks=[]


def require(text, needle, label):
    ok = needle in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'MISSING: {label} :: {needle}')


bridge = Path('QmChecklistDbFirstBridge.js').read_text(encoding='utf-8')
canonical = Path('scripts/fix_patch_site_scope_v2.py').read_text(encoding='utf-8')

require(bridge, "const placeMap = {};", 'DB definition place map')
require(bridge, "placeLabel: place.label", 'legacy-compatible placeLabel')
require(bridge, "placeOrder: Number(place.order || 9999)", 'legacy-compatible placeOrder')
require(bridge, "a.placeOrder - b.placeOrder || a.order - b.order", 'legacy-compatible item sorting')
require(bridge, "revision: buildQmChecklistRevision_(items, places)", 'revision uses DB-shaped items')
require(canonical, 'patch_qm_checklist_definition_shape_v1_20260908.py', 'canonical shape patch registration')
require(canonical, 'validate_qm_checklist_definition_shape_v1_20260908.py', 'canonical shape validator registration')

r = subprocess.run(['node','--check','QmChecklistDbFirstBridge.js'], text=True, capture_output=True, check=False)
checks.append(('QmChecklistDbFirstBridge syntax', r.returncode == 0))
if r.returncode != 0:
    errors.append(f'SYNTAX: {(r.stderr or r.stdout).strip()}')

if errors:
    print(f'QM checklist DB definition shape gate FAILED: {len(errors)} issue(s), {len(checks)} checks.', file=sys.stderr)
    for error in errors:
        print(f' - {error}', file=sys.stderr)
    raise SystemExit(99)
print(f'QM checklist DB definition shape gate passed: {len(checks)} checks.')
