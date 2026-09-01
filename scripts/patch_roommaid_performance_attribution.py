from pathlib import Path
import sys

realtime_path = Path('RealtimeDailySync.js')
performance_path = Path('17_RoommaidPerformance.js')
marker = 'ROOMMAID_PERFORMANCE_ATTRIBUTION_V1'

realtime = realtime_path.read_text(encoding='utf-8')
performance = performance_path.read_text(encoding='utf-8')

realtime_done = marker in realtime
performance_done = marker in performance
if realtime_done and performance_done:
    print('Roommaid performance attribution patch already applied.')
    sys.exit(0)
if realtime_done != performance_done:
    print('ERROR: Roommaid attribution patch is partially applied.', file=sys.stderr)
    sys.exit(70)

old_realtime = """      historyPayloads.push({
        recordType: NOVA.RECORD_TYPES.CLEANING,
        businessDate: eventBusinessDate,
        site: eventSite,
        roomNo: eventRoomNo,
        targetEmployeeNo: employeeNo,
        status: action === 'CLEANING_START' ? 'ROOMMAID_START' : 'ROOMMAID_COMPLETE',
        detail: {
          requestId,
          realtime: true,
          action: action === 'CLEANING_START' ? 'START' : 'COMPLETE',
          role: 'ROOMMAID',
          beforeCleaningStatus: beforeStatus,
          previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
          sourceRoomStatus: action === 'CLEANING_COMPLETE' ? String(rowInfo.data['객실상태'] || '').trim().toUpperCase() : '',
          roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
          cleaningStatus: afterStatus,
          cleaningType,
          assignmentType,
          primaryEmployeeNo: roommaidNo,
          secondaryEmployeeNo: secondaryRoommaidNo,
"""
new_realtime = """      const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
      const eventRole = String(
        eventDetail.role || (usersByEmployeeNo[employeeNo] && usersByEmployeeNo[employeeNo].role) || ''
      ).trim().toUpperCase();
      // ROOMMAID_PERFORMANCE_ATTRIBUTION_V1
      // 관리자·오더테이커가 대신 START/COMPLETE를 눌러도 처리자를 정비실적 대상자로 기록하지 않습니다.
      // Sheet 배정정보가 일시적으로 비어 있으면 실제 ROOMMAID 본인이 처리한 경우에만 본인 사번을 안전하게 보완합니다.
      const performancePrimaryEmployeeNo = roommaidNo || (eventRole === 'ROOMMAID' ? employeeNo : '');
      const performanceSecondaryEmployeeNo = performancePrimaryEmployeeNo ? secondaryRoommaidNo : '';

      historyPayloads.push({
        recordType: NOVA.RECORD_TYPES.CLEANING,
        businessDate: eventBusinessDate,
        site: eventSite,
        roomNo: eventRoomNo,
        targetEmployeeNo: performancePrimaryEmployeeNo,
        status: action === 'CLEANING_START' ? 'ROOMMAID_START' : 'ROOMMAID_COMPLETE',
        detail: {
          requestId,
          realtime: true,
          action: action === 'CLEANING_START' ? 'START' : 'COMPLETE',
          role: eventRole || 'UNKNOWN',
          beforeCleaningStatus: beforeStatus,
          previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
          sourceRoomStatus: action === 'CLEANING_COMPLETE' ? String(rowInfo.data['객실상태'] || '').trim().toUpperCase() : '',
          roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
          cleaningStatus: afterStatus,
          cleaningType,
          assignmentType,
          primaryEmployeeNo: performancePrimaryEmployeeNo,
          secondaryEmployeeNo: performanceSecondaryEmployeeNo,
"""

count = realtime.count(old_realtime)
if count != 1:
    print(f'ERROR: Expected exactly one Realtime attribution anchor, found {count}.', file=sys.stderr)
    sys.exit(71)
realtime = realtime.replace(old_realtime, new_realtime, 1)

old_helper_anchor = """function buildRoommaidPerformanceBundle_(historyRows, request) { // (개인별 실적·일자별·상세 집계)
"""
new_helper_anchor = """function roommaidPerformanceEligibleEmployeeNo_(employeeNo, usersByEmployeeNo) { // (실적 귀속 가능 룸메이드 검증 · ROOMMAID_PERFORMANCE_ATTRIBUTION_V1)
  const no = String(employeeNo || '').trim();
  if (!no) return '';
  const user = usersByEmployeeNo && usersByEmployeeNo[no] || null;
  // 현재 사용자목록에 없는 과거 사번은 기존 이력 호환을 위해 보존합니다.
  // 현재 등록된 사용자라면 ROOMMAID 권한만 정비실적에 귀속합니다.
  if (!user) return no;
  return String(user.role || '').trim().toUpperCase() === 'ROOMMAID' ? no : '';
}

function buildRoommaidPerformanceBundle_(historyRows, request) { // (개인별 실적·일자별·상세 집계)
"""
count = performance.count(old_helper_anchor)
if count != 1:
    print(f'ERROR: Expected exactly one Roommaid bundle anchor, found {count}.', file=sys.stderr)
    sys.exit(72)
performance = performance.replace(old_helper_anchor, new_helper_anchor, 1)

old_performance = """    const primaryNo = String(detail.primaryEmployeeNo || data['대상사번'] || '').trim();
    const secondaryNo = String(detail.secondaryEmployeeNo || '').trim();
"""
new_performance = """    const primaryNo = roommaidPerformanceEligibleEmployeeNo_(
      detail.primaryEmployeeNo || data['대상사번'] || '', users
    );
    const secondaryNo = roommaidPerformanceEligibleEmployeeNo_(detail.secondaryEmployeeNo || '', users);
"""
count = performance.count(old_performance)
if count != 1:
    print(f'ERROR: Expected exactly one Roommaid participant anchor, found {count}.', file=sys.stderr)
    sys.exit(73)
performance = performance.replace(old_performance, new_performance, 1)

realtime_path.write_text(realtime, encoding='utf-8')
performance_path.write_text(performance, encoding='utf-8')
print('Applied Roommaid performance attribution protection patch.')
