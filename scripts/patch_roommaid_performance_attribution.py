from pathlib import Path
import sys

realtime_path = Path('RealtimeDailySync.js')
performance_path = Path('17_RoommaidPerformance.js')
v1 = 'ROOMMAID_PERFORMANCE_ATTRIBUTION_V1'
v2 = 'ROOMMAID_PERFORMANCE_ATTRIBUTION_V2'

realtime = realtime_path.read_text(encoding='utf-8')
performance = performance_path.read_text(encoding='utf-8')

# V2는 명시적으로 저장된 과거 primaryEmployeeNo는 그대로 보존하고,
# primaryEmployeeNo가 비어 대상사번으로 fallback할 때만 현재 ROOMMAID 권한을 검증합니다.
if v1 in realtime and v2 in performance:
    print('Roommaid performance attribution patch V2 already applied.')
    sys.exit(0)

v1_helper = """function roommaidPerformanceEligibleEmployeeNo_(employeeNo, usersByEmployeeNo) { // (실적 귀속 가능 룸메이드 검증 · ROOMMAID_PERFORMANCE_ATTRIBUTION_V1)
  const no = String(employeeNo || '').trim();
  if (!no) return '';
  const user = usersByEmployeeNo && usersByEmployeeNo[no] || null;
  // 현재 사용자목록에 없는 과거 사번은 기존 이력 호환을 위해 보존합니다.
  // 현재 등록된 사용자라면 ROOMMAID 권한만 정비실적에 귀속합니다.
  if (!user) return no;
  return String(user.role || '').trim().toUpperCase() === 'ROOMMAID' ? no : '';
}
"""

v2_helper = """function roommaidPerformanceFallbackEmployeeNo_(employeeNo, usersByEmployeeNo) { // (대상사번 fallback 룸메이드 검증 · ROOMMAID_PERFORMANCE_ATTRIBUTION_V1 · ROOMMAID_PERFORMANCE_ATTRIBUTION_V2)
  const no = String(employeeNo || '').trim();
  if (!no) return '';
  const user = usersByEmployeeNo && usersByEmployeeNo[no] || null;
  // 사용자목록에 없는 과거 사번은 기존 이력 호환을 위해 보존합니다.
  // 현재 등록된 사번을 fallback으로 쓸 때는 ROOMMAID 권한만 허용해 ORDER/ADMIN/QM/HOUSEMAN 오귀속을 막습니다.
  if (!user) return no;
  return String(user.role || '').trim().toUpperCase() === 'ROOMMAID' ? no : '';
}
"""

v1_participants = """    const primaryNo = roommaidPerformanceEligibleEmployeeNo_(
      detail.primaryEmployeeNo || data['대상사번'] || '', users
    );
    const secondaryNo = roommaidPerformanceEligibleEmployeeNo_(detail.secondaryEmployeeNo || '', users);
"""

v2_participants = """    // 명시적으로 저장된 배정 스냅샷은 과거 직무변경과 무관하게 그대로 보존합니다.
    // 배정 스냅샷이 비어 있을 때만 대상사번을 fallback하며, 이 경우 현재 ROOMMAID 권한을 검증합니다.
    const explicitPrimaryNo = String(detail.primaryEmployeeNo || '').trim();
    const primaryNo = explicitPrimaryNo || roommaidPerformanceFallbackEmployeeNo_(data['대상사번'] || '', users);
    const secondaryNo = String(detail.secondaryEmployeeNo || '').trim();
"""

# 이미 V1이 배포된 운영소스는 성능집계 부분만 V2로 좁게 업그레이드합니다.
if v1 in realtime and v1 in performance and v2 not in performance:
    helper_count = performance.count(v1_helper)
    participant_count = performance.count(v1_participants)
    if helper_count != 1 or participant_count != 1:
        print(
            f'ERROR: Expected V1 upgrade anchors helper=1/participants=1, found {helper_count}/{participant_count}.',
            file=sys.stderr
        )
        sys.exit(70)
    performance = performance.replace(v1_helper, v2_helper, 1)
    performance = performance.replace(v1_participants, v2_participants, 1)
    performance_path.write_text(performance, encoding='utf-8')
    print('Upgraded Roommaid performance attribution protection to V2.')
    sys.exit(0)

# 최초 적용 경로: Realtime 미러 오귀속 차단 + 집계 fallback 검증을 한 번에 적용합니다.
if v1 in realtime or v1 in performance or v2 in performance:
    print('ERROR: Roommaid attribution patch is partially applied.', file=sys.stderr)
    sys.exit(71)

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
    sys.exit(72)
realtime = realtime.replace(old_realtime, new_realtime, 1)

old_helper_anchor = """function buildRoommaidPerformanceBundle_(historyRows, request) { // (개인별 실적·일자별·상세 집계)
"""
new_helper_anchor = v2_helper + "\n" + old_helper_anchor
count = performance.count(old_helper_anchor)
if count != 1:
    print(f'ERROR: Expected exactly one Roommaid bundle anchor, found {count}.', file=sys.stderr)
    sys.exit(73)
performance = performance.replace(old_helper_anchor, new_helper_anchor, 1)

old_performance = """    const primaryNo = String(detail.primaryEmployeeNo || data['대상사번'] || '').trim();
    const secondaryNo = String(detail.secondaryEmployeeNo || '').trim();
"""
count = performance.count(old_performance)
if count != 1:
    print(f'ERROR: Expected exactly one Roommaid participant anchor, found {count}.', file=sys.stderr)
    sys.exit(74)
performance = performance.replace(old_performance, v2_participants, 1)

realtime_path.write_text(realtime, encoding='utf-8')
performance_path.write_text(performance, encoding='utf-8')
print('Applied Roommaid performance attribution protection V2.')
