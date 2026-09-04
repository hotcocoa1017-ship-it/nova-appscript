from pathlib import Path

MARKER = 'PUBLIC_HOUSEMAN_REQUEST_FAST_V2'
client_path = Path('Client.html')
mobile_path = Path('10_Mobile.js')
shifts_path = Path('12_Shifts.js')

client = client_path.read_text(encoding='utf-8')
mobile = mobile_path.read_text(encoding='utf-8')
shifts = shifts_path.read_text(encoding='utf-8')

if MARKER in client and MARKER in mobile and MARKER in shifts:
    print(f'{MARKER} already applied.')
    raise SystemExit(0)


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


# 1) 12_Shifts.js: 객실퍼블릭 공동전달은 전체 오더 미처리건수 스캔 없이
#    근무조 + 담당동만으로 후보를 계산한다.
fast_resolver = r'''function resolveHousemanPublicFastAssignee_(businessDate, site, roomNo) { // (객실퍼블릭 공동전달 담당동 경량 자동배정) // PUBLIC_HOUSEMAN_REQUEST_FAST_V2
  const date = normalizeBusinessDate_(businessDate);
  const normalizedSite = String(site || '').trim();
  const building = normalizeRoomBuilding_('', roomNo);
  if (!/^([1-9])동$/.test(building)) throw new Error('자동배정은 4자리 객실번호로 등록해야 합니다.');

  const shiftAssignments = getShiftAssignmentsForDate_(date, normalizedSite);
  const zoneAssignments = getHousemanZoneAssignmentsForDate_(date, normalizedSite);
  const isToday = date === businessDateText_();
  const activeShiftCodes = isToday ? resolveActiveShiftCodes_(new Date()) : Object.keys(NOVA.SHIFTS);
  const eligibleEmployeeNos = isToday
    ? Array.from(new Set(activeShiftCodes.flatMap(code => shiftAssignments.byShift[code] || [])))
    : shiftAssignments.allEmployeeNos;
  const eligibleSet = new Set(eligibleEmployeeNos);
  const users = getUserIndex_().byEmployeeNo;

  // 객실퍼블릭 오더는 담당동 후보 전체에 공동 전달되므로,
  // 대표 배정자를 고르기 위해 기존 오더 전체의 미처리 건수를 다시 셀 필요가 없습니다.
  const candidates = (zoneAssignments.byBuilding[building] || [])
    .filter(employeeNo => eligibleSet.has(employeeNo))
    .map(employeeNo => users[employeeNo])
    .filter(user => user && user.enabled && user.role === 'HOUSEMAN')
    .map(user => ({
      employeeNo: user.employeeNo,
      name: user.name,
      shiftCodes: shiftAssignments.byEmployeeNo[user.employeeNo] || [],
      pendingCount: 0
    }))
    .sort((a, b) => String(a.employeeNo).localeCompare(String(b.employeeNo)));

  if (!candidates.length) {
    const shiftCodes = isToday ? activeShiftCodes : [];
    const shiftLabel = shiftCodes.length ? `${shiftCodes.join('·')}조 ` : '';
    throw new Error(`${building} ${shiftLabel}담당 하우스맨이 없습니다. 근무조와 담당동을 먼저 등록하세요.`);
  }

  const selected = candidates[0];
  return {
    building,
    employeeNo: selected.employeeNo,
    name: selected.name,
    employeeNos: candidates.map(candidate => candidate.employeeNo),
    names: candidates.map(candidate => candidate.name),
    candidates: candidates.map(candidate => Object.assign({}, candidate)),
    shiftCodes: selected.shiftCodes,
    pendingCount: 0,
    currentShift: resolveCurrentShiftCode_(new Date()),
    activeShiftCodes
  };
}

'''

if MARKER not in shifts:
    anchor = 'function buildHistoryRowWithMap_(columnCount, headerMap, valuesByHeader) {'
    if anchor not in shifts:
        raise SystemExit('shifts fast resolver insertion anchor not found')
    shifts = shifts.replace(anchor, fast_resolver + anchor, 1)

# 2) 10_Mobile.js: PUBLIC 사전배정/legacy fallback 모두 경량 resolver 사용.
if MARKER not in mobile:
    mobile = replace_once(
        mobile,
        "    const assignment = resolveHousemanAutoAssignee_(businessDate, site, roomNo);",
        "    const assignment = resolveHousemanPublicFastAssignee_(businessDate, site, roomNo); // PUBLIC_HOUSEMAN_REQUEST_FAST_V2",
        'mobile public assignment resolver'
    )
    mobile = replace_once(
        mobile,
        "        : resolveHousemanAutoAssignee_(safe.businessDate, safe.site, safe.roomNo);",
        "        : resolveHousemanPublicFastAssignee_(safe.businessDate, safe.site, safe.roomNo); // PUBLIC_HOUSEMAN_REQUEST_FAST_V2",
        'mobile public fallback resolver'
    )

# 3) Client.html: 요청창을 여는 순간 담당동 조회를 선행하고,
#    같은 모달 저장에서는 동일 in-flight/result를 재사용한다.
if MARKER not in client:
    helper = r'''  let novaPublicHousemanAssignmentPrefetch_ = null; // PUBLIC_HOUSEMAN_REQUEST_FAST_V2

  function publicHousemanAssignmentContext_(payload) { // (객실퍼블릭 담당동 사전조회 키)
    const selection = state.mobile.data?.selection || {};
    const roomNo = String(payload?.roomNo || '').trim();
    const businessDate = String(payload?.businessDate || selection.businessDate || '').trim();
    const site = String(payload?.site || selection.site || '').trim();
    const building = roomNo ? roomNo.charAt(0) : '';
    return { businessDate, site, roomNo, key: `${businessDate}|${site}|${building}` };
  }

  function getPublicHousemanAssignmentFast_(payload) { // (모달 사전조회 결과 재사용)
    const context = publicHousemanAssignmentContext_(payload);
    if (!context.businessDate || !context.site || !context.roomNo) {
      return Promise.reject(new Error('자동배정 확인에 업무일자·사업장·객실번호가 필요합니다.'));
    }
    const now = Date.now();
    if (novaPublicHousemanAssignmentPrefetch_
      && novaPublicHousemanAssignmentPrefetch_.key === context.key
      && now - novaPublicHousemanAssignmentPrefetch_.startedAt <= 30000
      && novaPublicHousemanAssignmentPrefetch_.promise) {
      return novaPublicHousemanAssignmentPrefetch_.promise;
    }

    const request = callServer('getMobilePublicHousemanAutoAssignment', state.token, {
      businessDate: context.businessDate,
      site: context.site,
      roomNo: context.roomNo
    }).then(result => {
      const assignment = result?.assignment || null;
      if (!assignment?.employeeNo) throw new Error('해당 동에 자동배정 가능한 하우스맨이 없습니다.');
      return assignment;
    });

    novaPublicHousemanAssignmentPrefetch_ = {
      key: context.key,
      startedAt: now,
      promise: request
    };
    request.catch(() => {
      if (novaPublicHousemanAssignmentPrefetch_?.promise === request) novaPublicHousemanAssignmentPrefetch_ = null;
    });
    return request;
  }

  function prefetchPublicHousemanAssignment_(roomNo) { // (요청창 진입 즉시 담당동 조회 시작)
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (role !== 'PUBLIC') return;
    const selection = state.mobile.data?.selection || {};
    void getPublicHousemanAssignmentFast_({
      businessDate: selection.businessDate,
      site: selection.site,
      roomNo
    }).catch(() => null);
  }

'''
    anchor = "  async function createRoommaidHousemanRequestFast_(payload) { // (ROOMMAID·QM·PUBLIC 하우스맨 요청 PostgreSQL 선확정·Sheet 후행) // QM_HOUSEMAN_REQUEST_PARITY_V1 · PUBLIC_HOUSEMAN_REQUEST_V1"
    if anchor not in client:
        raise SystemExit('client fast-create insertion anchor not found')
    client = client.replace(anchor, helper + anchor, 1)

    old_assignment = """    let publicAssignment = null; // PUBLIC_HOUSEMAN_REQUEST_V1
    if (role === 'PUBLIC') {
      const assignmentResult = await callServer('getMobilePublicHousemanAutoAssignment', state.token, {
        businessDate: payload?.businessDate, site: payload?.site, roomNo: payload?.roomNo
      });
      publicAssignment = assignmentResult?.assignment || null;
      if (!publicAssignment?.employeeNo) throw new Error('해당 동에 자동배정 가능한 하우스맨이 없습니다.');
    }
"""
    new_assignment = """    let publicAssignment = null; // PUBLIC_HOUSEMAN_REQUEST_V1
    if (role === 'PUBLIC') {
      publicAssignment = await getPublicHousemanAssignmentFast_(payload); // PUBLIC_HOUSEMAN_REQUEST_FAST_V2
    }
"""
    client = replace_once(client, old_assignment, new_assignment, 'client public assignment reuse')

    open_anchor = """  function openMobileHousemanRequest_(roomNo) { // (모바일 하우스맨 요청 등록창) // PUBLIC_HOUSEMAN_REQUEST_V1
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    const rawParts = state.mobile.data?.codes?.orderParts || [];
"""
    open_replacement = """  function openMobileHousemanRequest_(roomNo) { // (모바일 하우스맨 요청 등록창) // PUBLIC_HOUSEMAN_REQUEST_V1
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    const rawParts = state.mobile.data?.codes?.orderParts || [];
    if (role === 'PUBLIC') prefetchPublicHousemanAssignment_(roomNo); // PUBLIC_HOUSEMAN_REQUEST_FAST_V2
"""
    client = replace_once(client, open_anchor, open_replacement, 'client public prefetch')

client_path.write_text(client, encoding='utf-8')
mobile_path.write_text(mobile, encoding='utf-8')
shifts_path.write_text(shifts, encoding='utf-8')
print(f'{MARKER} applied.')
