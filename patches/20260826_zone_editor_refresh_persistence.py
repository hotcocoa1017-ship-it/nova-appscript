from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
original = text

old = """  function restoreShiftManagementContext_() { // (근무조 화면 새로고침 후 업무일자·사업장 복원)\n    try {\n      if (!state.shifts.businessDate) state.shifts.businessDate = String(sessionStorage.getItem('novaShiftBusinessDate') || '').trim();\n      if (!state.shifts.site) state.shifts.site = String(sessionStorage.getItem('novaShiftSite') || '').trim();\n    } catch (ignore) {}\n  }\n\n  function persistShiftManagementContext_() { // (근무조 조회조건 새로고침 유지)\n    try {\n      if (state.shifts.businessDate) sessionStorage.setItem('novaShiftBusinessDate', state.shifts.businessDate);\n      if (state.shifts.site) sessionStorage.setItem('novaShiftSite', state.shifts.site);\n      else sessionStorage.removeItem('novaShiftSite');\n    } catch (ignore) {}\n  }\n"""
new = """  function restoreShiftManagementContext_() { // (근무조 화면 새로고침 후 업무일자·사업장·담당동 편집대상 복원)\n    try {\n      if (!state.shifts.businessDate) state.shifts.businessDate = String(sessionStorage.getItem('novaShiftBusinessDate') || '').trim();\n      if (!state.shifts.site) state.shifts.site = String(sessionStorage.getItem('novaShiftSite') || '').trim();\n      const zoneEmployeeNo = String(sessionStorage.getItem('novaShiftZoneEmployeeNo') || '').trim();\n      const zoneBuildings = String(sessionStorage.getItem('novaShiftZoneBuildings') || '')\n        .split(',').map(value => value.trim()).filter(Boolean);\n      if (!String(state.shifts.zoneDraft?.employeeNo || '').trim() && zoneEmployeeNo) {\n        state.shifts.zoneDraft = { employeeNo: zoneEmployeeNo, buildings: zoneBuildings };\n      }\n    } catch (ignore) {}\n  }\n\n  function persistShiftManagementContext_() { // (근무조 조회조건·담당동 편집대상 새로고침 유지)\n    try {\n      if (state.shifts.businessDate) sessionStorage.setItem('novaShiftBusinessDate', state.shifts.businessDate);\n      if (state.shifts.site) sessionStorage.setItem('novaShiftSite', state.shifts.site);\n      else sessionStorage.removeItem('novaShiftSite');\n      const zoneEmployeeNo = String(state.shifts.zoneDraft?.employeeNo || '').trim();\n      const zoneBuildings = Array.isArray(state.shifts.zoneDraft?.buildings) ? state.shifts.zoneDraft.buildings.filter(Boolean) : [];\n      if (zoneEmployeeNo) sessionStorage.setItem('novaShiftZoneEmployeeNo', zoneEmployeeNo);\n      else sessionStorage.removeItem('novaShiftZoneEmployeeNo');\n      if (zoneEmployeeNo && zoneBuildings.length) sessionStorage.setItem('novaShiftZoneBuildings', zoneBuildings.join(','));\n      else sessionStorage.removeItem('novaShiftZoneBuildings');\n    } catch (ignore) {}\n  }\n"""
if text.count(old) != 1:
    raise SystemExit(f'context function anchor mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

old = """      state.shifts.zoneDraft = {\n        employeeNo: selectedZoneEmployee && (result.attendanceStaff || []).some(item => item.employeeNo === selectedZoneEmployee) ? selectedZoneEmployee : '',\n        buildings: selectedZone ? [...(selectedZone.buildings || [])] : []\n      };\n      if (state.activeMenu === 'shifts') renderShiftManagementData_();\n"""
new = """      state.shifts.zoneDraft = {\n        employeeNo: selectedZoneEmployee && (result.attendanceStaff || []).some(item => item.employeeNo === selectedZoneEmployee) ? selectedZoneEmployee : '',\n        buildings: selectedZone ? [...(selectedZone.buildings || [])] : []\n      };\n      persistShiftManagementContext_();\n      if (state.activeMenu === 'shifts') renderShiftManagementData_();\n"""
if text.count(old) != 1:
    raise SystemExit(f'load zoneDraft anchor mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

old = """      state.shifts.zoneDraft = {\n        employeeNo,\n        buildings: existing ? [...(existing.buildings || [])] : []\n      };\n      renderZoneAssignmentManagement_();\n"""
new = """      state.shifts.zoneDraft = {\n        employeeNo,\n        buildings: existing ? [...(existing.buildings || [])] : []\n      };\n      persistShiftManagementContext_();\n      renderZoneAssignmentManagement_();\n"""
if text.count(old) != 1:
    raise SystemExit(f'zone employee change anchor mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

old = """      state.shifts.zoneDraft.buildings = Array.from(draft).sort((a, b) => Number(a.replace(/\\D/g, '')) - Number(b.replace(/\\D/g, '')));\n      renderZoneAssignmentManagement_();\n"""
new = """      state.shifts.zoneDraft.buildings = Array.from(draft).sort((a, b) => Number(a.replace(/\\D/g, '')) - Number(b.replace(/\\D/g, '')));\n      persistShiftManagementContext_();\n      renderZoneAssignmentManagement_();\n"""
if text.count(old) != 1:
    raise SystemExit(f'zone building toggle anchor mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

old = """      const employeeNo = button.dataset.zoneLoad;\n      const existing = data.zoneAssignments?.[employeeNo];\n      state.shifts.zoneDraft = { employeeNo, buildings: [...(existing?.buildings || [])] };\n      renderZoneAssignmentManagement_();\n"""
new = """      const employeeNo = button.dataset.zoneLoad;\n      const existing = data.zoneAssignments?.[employeeNo];\n      state.shifts.zoneDraft = { employeeNo, buildings: [...(existing?.buildings || [])] };\n      persistShiftManagementContext_();\n      renderZoneAssignmentManagement_();\n"""
if text.count(old) != 1:
    raise SystemExit(f'zone summary select anchor mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

old = """      state.shifts.zoneDraft = { employeeNo: action === 'CANCEL' ? '' : employeeNo, buildings: action === 'CANCEL' ? [] : [...(result.buildings || [])] };\n      await loadShiftManagement_({ force: true });\n"""
new = """      state.shifts.zoneDraft = { employeeNo: action === 'CANCEL' ? '' : employeeNo, buildings: action === 'CANCEL' ? [] : [...(result.buildings || [])] };\n      persistShiftManagementContext_();\n      await loadShiftManagement_({ force: true });\n"""
if text.count(old) != 1:
    raise SystemExit(f'zone save anchor mismatch: {text.count(old)}')
text = text.replace(old, new, 1)

if text == original:
    raise SystemExit('patch produced no changes')

required = [
    "sessionStorage.getItem('novaShiftZoneEmployeeNo')",
    "sessionStorage.setItem('novaShiftZoneEmployeeNo'",
    "sessionStorage.setItem('novaShiftZoneBuildings'",
    "persistShiftManagementContext_();\n      renderZoneAssignmentManagement_();",
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'missing marker after patch: {marker}')

path.write_text(text, encoding='utf-8')
print('Applied houseman zone editor refresh persistence fix to Client.html')
