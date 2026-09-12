from pathlib import Path

client = Path('Client.html').read_text(encoding='utf-8')
index = Path('Index.html').read_text(encoding='utf-8')
guard = Path('QmChecklistInteractionGuard.html').read_text(encoding='utf-8')

required_client = [
    "root.addEventListener('input', scheduleQmInspectionAutosave_);",
    "root.addEventListener('change', event => {",
    "if (active) active.localDirty = true;",
    "if (modalOpen && !active.localDirty) openQmInspectionModal_();",
]
for marker in required_client:
    if marker not in client:
        raise SystemExit(f'Missing QM interaction invariant: {marker}')

required_guard = [
    'QM_CHECKLIST_SELECT_STABILITY_V1',
    ".qm-checklist-modal [data-qm-result]",
    "new Event('input', { bubbles: true })",
    "document.addEventListener('pointerdown', primeResultSelect_, true);",
]
for marker in required_guard:
    if marker not in guard:
        raise SystemExit(f'Missing QM select stability guard: {marker}')

if "include_('QmChecklistInteractionGuard')" not in index:
    raise SystemExit('QmChecklistInteractionGuard is not included in Index.html')

for forbidden in ('preventDefault(', 'stopPropagation(', 'stopImmediatePropagation('):
    if forbidden in guard:
        raise SystemExit(f'QM select guard must not intercept native selection: {forbidden}')

for forbidden in ('nova_qm_inspection_finalize_v2', 'QM_REWORK', 'updateMobileRoomOperation'):
    if forbidden in guard:
        raise SystemExit(f'QM select guard must not mutate finalize/rework policy: {forbidden}')

print('QM checklist interaction stability invariants: OK')
