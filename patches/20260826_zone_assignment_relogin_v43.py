from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

old = """      const selectedZoneEmployee = state.shifts.zoneDraft.employeeNo;
      const selectedZone = selectedZoneEmployee ? result.zoneAssignments?.[selectedZoneEmployee] : null;
      state.shifts.zoneDraft = {
        employeeNo: selectedZoneEmployee && (result.attendanceStaff || []).some(item => item.employeeNo === selectedZoneEmployee) ? selectedZoneEmployee : '',
        buildings: selectedZone ? [...(selectedZone.buildings || [])] : []
      };
"""

new = """      // 담당동 저장값은 브라우저 세션이 아니라 서버 저장자료를 원본으로 복원합니다.
      // 재로그인처럼 sessionStorage 편집대상이 사라진 경우에도 저장된 담당동이 있는
      // 출근직원을 자동 선택해 카드가 즉시 실제 저장상태(검정색)로 표시되게 합니다.
      const attendanceStaff = result.attendanceStaff || [];
      const requestedZoneEmployee = String(state.shifts.zoneDraft.employeeNo || '').trim();
      const selectedZoneEmployee = requestedZoneEmployee && attendanceStaff.some(item => item.employeeNo === requestedZoneEmployee)
        ? requestedZoneEmployee
        : String(attendanceStaff.find(item => result.zoneAssignments?.[item.employeeNo])?.employeeNo || '').trim();
      const selectedZone = selectedZoneEmployee ? result.zoneAssignments?.[selectedZoneEmployee] : null;
      state.shifts.zoneDraft = {
        employeeNo: selectedZoneEmployee,
        buildings: selectedZone ? [...(selectedZone.buildings || [])] : []
      };
"""

if new in text:
    print('Zone assignment relogin restore patch already applied')
    raise SystemExit(0)

if old not in text:
    raise SystemExit('Expected shift zone restore block not found; refusing to patch')

text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('Applied server-backed zone assignment relogin restore')
