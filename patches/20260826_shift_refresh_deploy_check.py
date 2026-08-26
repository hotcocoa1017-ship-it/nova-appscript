from pathlib import Path

text = Path('Client.html').read_text(encoding='utf-8')
required = [
    'function restoreShiftManagementContext_',
    'function persistShiftManagementContext_',
    "sessionStorage.getItem('novaShiftSite')",
    "sessionStorage.setItem('novaShiftBusinessDate'",
    "sessionStorage.setItem('novaShiftSite'"
]
missing = [marker for marker in required if marker not in text]
if missing:
    raise SystemExit('shift refresh persistence markers missing: ' + ', '.join(missing))
print('Shift refresh persistence source markers verified; deploy current branch head.')
