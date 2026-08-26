from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
original = text

old = """  function renderShiftManagementShell_() { // (A·B·C 근무조 관리 화면 골격)\n    const businessDate = state.shifts.businessDate || state.bootstrap.app.businessDate;\n"""
new = """  function restoreShiftManagementContext_() { // (근무조 화면 새로고침 후 업무일자·사업장 복원)\n    try {\n      if (!state.shifts.businessDate) state.shifts.businessDate = String(sessionStorage.getItem('novaShiftBusinessDate') || '').trim();\n      if (!state.shifts.site) state.shifts.site = String(sessionStorage.getItem('novaShiftSite') || '').trim();\n    } catch (ignore) {}\n  }\n\n  function persistShiftManagementContext_() { // (근무조 조회조건 새로고침 유지)\n    try {\n      if (state.shifts.businessDate) sessionStorage.setItem('novaShiftBusinessDate', state.shifts.businessDate);\n      if (state.shifts.site) sessionStorage.setItem('novaShiftSite', state.shifts.site);\n      else sessionStorage.removeItem('novaShiftSite');\n    } catch (ignore) {}\n  }\n\n  function renderShiftManagementShell_() { // (A·B·C 근무조 관리 화면 골격)\n    restoreShiftManagementContext_();\n    const businessDate = state.shifts.businessDate || state.bootstrap.app.businessDate;\n"""
if text.count(old) != 1:
    raise SystemExit(f'render shell anchor count mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

old = """    $('shiftBusinessDate').addEventListener('change', () => {\n      state.shifts.businessDate = $('shiftBusinessDate').value;\n      state.shifts.zoneDraft = { employeeNo: '', buildings: [] };\n    });\n    $('shiftSite').addEventListener('change', () => {\n      state.shifts.site = $('shiftSite').value;\n      state.shifts.zoneDraft = { employeeNo: '', buildings: [] };\n    });\n"""
new = """    $('shiftBusinessDate').addEventListener('change', () => {\n      state.shifts.businessDate = $('shiftBusinessDate').value;\n      state.shifts.zoneDraft = { employeeNo: '', buildings: [] };\n      persistShiftManagementContext_();\n    });\n    $('shiftSite').addEventListener('change', () => {\n      state.shifts.site = $('shiftSite').value;\n      state.shifts.zoneDraft = { employeeNo: '', buildings: [] };\n      persistShiftManagementContext_();\n    });\n"""
if text.count(old) != 1:
    raise SystemExit(f'change listener anchor count mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

old = """      state.shifts.businessDate = result.businessDate;\n      state.shifts.site = result.site;\n      state.shifts.draft = {\n"""
new = """      state.shifts.businessDate = result.businessDate;\n      state.shifts.site = result.site;\n      persistShiftManagementContext_();\n      state.shifts.draft = {\n"""
if text.count(old) != 1:
    raise SystemExit(f'load result anchor count mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

if text == original:
    raise SystemExit('patch produced no changes')

required = [
    'function restoreShiftManagementContext_',
    'function persistShiftManagementContext_',
    "sessionStorage.getItem('novaShiftSite')",
    'persistShiftManagementContext_();'
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'missing marker after patch: {marker}')

path.write_text(text, encoding='utf-8')
print('Applied shift/zone refresh persistence patch to Client.html')
