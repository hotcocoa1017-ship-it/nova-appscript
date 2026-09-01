/**
 * NOVA 룸메이드 개인별 정비실적 · 정비유형 6종
 * 모든 고유 정비완료 기록을 각각 집계하고 정비유형별 실적과 인정정비수를 계산합니다.
 */
const NOVA_ROOMMAID_PERFORMANCE = Object.freeze({
  MAX_DETAIL_ROWS: 1500,
  MAINTENANCE_CREDIT: Object.freeze({ F: 1, T: 1.5, R: 1.5, G: 2 })
});

function getRoommaidPerformance(token, filters) { // (룸메이드 개인별 일·월 정비실적 조회)
  return measureResponse_('getRoommaidPerformance', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const role = String(auth.user.role || '').trim().toUpperCase();
    if (!['ADMIN', 'ORDER', 'ROOMMAID'].includes(role)) throw new Error('룸메이드 실적 조회 권한이 없습니다.');
    const request = normalizeRoommaidPerformanceFilters_(filters, auth.user);
    const rows = readMonthlyHistoryRows_(request, [NOVA.RECORD_TYPES.CLEANING]).map(row => row && row.data ? row.data : row);
    const result = buildRoommaidPerformanceBundle_(rows, request);
    return Object.assign({ ok: true, filters: request, serverTime: nowText_() }, result);
  });
}

function normalizeRoommaidPerformanceFilters_(filters, user) { // (룸메이드 실적 조회조건 정리)
  const safe = filters || {};
  const now = new Date();
  const currentYear = Number(Utilities.formatDate(now, NOVA.TIMEZONE, 'yyyy'));
  const currentMonth = Number(Utilities.formatDate(now, NOVA.TIMEZONE, 'M'));
  const period = String(safe.period || 'MONTHLY').trim().toUpperCase() === 'DAILY' ? 'DAILY' : 'MONTHLY';
  let year = Math.max(2020, Math.min(2100, Number(safe.year || currentYear)));
  let month = Math.max(1, Math.min(12, Number(safe.month || currentMonth)));
  const date = normalizeMonthlyDate_(safe.date, year, month);
  if (period === 'DAILY') {
    year = Number(date.slice(0, 4));
    month = Number(date.slice(5, 7));
  }
  const role = String(user.role || '').trim().toUpperCase();
  return {
    period, date, year, month,
    site: String(safe.site || '').trim(),
    employeeNo: role === 'ROOMMAID' ? String(user.employeeNo || '').trim() : String(safe.employeeNo || '').trim(),
    employeeSearch: role === 'ROOMMAID' ? '' : String(safe.employeeSearch || '').trim().toLowerCase(),
    employmentCategory: role === 'ROOMMAID' ? '' : String(safe.employmentCategory || '').trim(),
    employmentVendor: role === 'ROOMMAID' ? '' : String(safe.employmentVendor || '').trim(),
    requestedBy: String(user.employeeNo || '').trim(),
    requesterRole: role
  };
}

function readRoommaidPerformanceEmploymentIndex_() { // (사용자계정 채용구분 인덱스)
  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  const headerMap = getHeaderMap_(sheet);
  const result = {};
  if (sheet.getLastRow() < 2) return result;
  const values = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getDisplayValues();
  values.forEach(row => {
    const data = rowObjectFromValues_(row, headerMap);
    const employeeNo = String(data['사번'] || '').trim();
    if (!employeeNo) return;
    result[employeeNo] = parseRoommaidPerformanceEmployment_(data['채용구분'], data);
  });
  return result;
}

function parseRoommaidPerformanceEmployment_(value, fallback) { // (정규직·아르바이트·외주업체 구분)
  const raw = String(value || '').trim();
  if (raw === '정규직') return { category: '정규직', vendor: '', label: '정규직', sortRank: 1 };
  if (raw === '아르바이트') return { category: '아르바이트', vendor: '', label: '아르바이트', sortRank: 2 };
  const outsource = raw.match(/^외주업체\s*[:：\-]?\s*(.*)$/i);
  if (outsource) {
    const vendor = String(outsource[1] || '').trim() || '미지정';
    return { category: '외주업체', vendor, label: vendor, sortRank: 3 };
  }
  const text = [raw, fallback && fallback['직무'], fallback && fallback['비고']].map(String).join(' ');
  if (text.includes('아르바이트') || text.includes('알바')) return { category: '아르바이트', vendor: '', label: '아르바이트', sortRank: 2 };
  const vendorMatch = text.match(/(?:외주업체|외주|용역|일용)\s*[:：\-]?\s*([^,()\/]+)/i);
  if (vendorMatch) {
    const vendor = String(vendorMatch[1] || '').trim() || '미지정';
    return { category: '외주업체', vendor, label: vendor, sortRank: 3 };
  }
  return { category: '정규직', vendor: '', label: '정규직', sortRank: 1 };
}

function roommaidPerformanceEmploymentMatches_(employment, request) { // (근무구분·업체 필터 일치)
  const item = employment || { category: '정규직', vendor: '' };
  if (request.employmentCategory && item.category !== request.employmentCategory) return false;
  if (request.employmentCategory === '외주업체' && request.employmentVendor && item.vendor !== request.employmentVendor) return false;
  return true;
}

function roommaidPerformanceMonthlyEmployment_(employeeNo, employmentIndex) { // (월 합계 리스트 사용자계정 채용구분 적용)
  const key = String(employeeNo || '').trim();
  const employment = key && employmentIndex ? employmentIndex[key] : null;
  if (employment) {
    return {
      category: String(employment.category || '미확인'),
      vendor: String(employment.vendor || ''),
      label: String(employment.label || employment.category || '미확인'),
      sortRank: Number(employment.sortRank || 9)
    };
  }
  return { category: '미확인', vendor: '', label: '미확인', sortRank: 9 };
}

function roommaidPerformanceMonthDays_(year, month) { // (선택 월 일수)
  return new Date(Number(year), Number(month), 0).getDate();
}

function roommaidPerformanceEligibleEmployeeNo_(employeeNo, usersByEmployeeNo) { // (실적 귀속 가능 룸메이드 검증 · ROOMMAID_PERFORMANCE_ATTRIBUTION_V1)
  const no = String(employeeNo || '').trim();
  if (!no) return '';
  const user = usersByEmployeeNo && usersByEmployeeNo[no] || null;
  // 현재 사용자목록에 없는 과거 사번은 기존 이력 호환을 위해 보존합니다.
  // 현재 등록된 사용자라면 ROOMMAID 권한만 정비실적에 귀속합니다.
  if (!user) return no;
  return String(user.role || '').trim().toUpperCase() === 'ROOMMAID' ? no : '';
}

function buildRoommaidPerformanceBundle_(historyRows, request) { // (개인별 실적·일자별·상세 집계)
  const users = getUserIndex_().byEmployeeNo;
  const employmentIndex = readRoommaidPerformanceEmploymentIndex_();
  const cleaningTypes = getRoommaidCleaningTypeDefinitions_().map(item => ({
    code: item.code,
    label: item.label,
    creditMultiplier: Number(item.creditMultiplier || 0)
  }));
  const roommaidOptions = Object.values(users)
    .filter(user => String(user.role || '').trim().toUpperCase() === 'ROOMMAID' && Boolean(user.enabled))
    .map(user => {
      const employeeNo = String(user.employeeNo || '').trim();
      const employment = employmentIndex[employeeNo] || parseRoommaidPerformanceEmployment_('', user);
      return {
        employeeNo,
        name: String(user.name || '').trim(),
        job: String(user.job || '').trim(),
        site: String(user.defaultSite || '').trim(),
        employmentCategory: employment.category,
        employmentVendor: employment.vendor,
        employmentLabel: employment.label,
        employmentSortRank: employment.sortRank
      };
    })
    .filter(user => user.employeeNo)
    .sort((a, b) => a.employmentSortRank - b.employmentSortRank || a.employmentLabel.localeCompare(b.employmentLabel, 'ko') || a.name.localeCompare(b.name, 'ko') || a.employeeNo.localeCompare(b.employeeNo, 'ko', { numeric: true }));

  const completions = {}; // (정비완료 기록ID별 고유 작업 보존)
  (historyRows || []).forEach((data, index) => {
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.CLEANING) return;
    if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') return;
    const status = String(data['처리상태'] || '').trim().toUpperCase();
    if (!['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(status)) return;
    const businessDate = String(data['업무일자'] || '').trim();
    const site = String(data['사업장'] || '').trim();
    const roomNo = String(data['객실번호'] || '').trim();
    if (!businessDate || !roomNo) return;

    const recordId = String(data['기록ID'] || '').trim();
    const eventAt = String(data['완료일시'] || data['수정일시'] || data['등록일시'] || '').trim();
    // 기록ID가 있으면 동일 ID만 중복 제거합니다. 기록ID가 없는 과거 자료는 각 행을 독립 작업으로 보존합니다.
    const key = recordId
      ? `RECORD|${recordId}`
      : `ROW|${businessDate}|${site}|${roomNo}|${status}|${eventAt}|${index}`;
    if (!completions[key] || eventAt >= completions[key].eventAt) {
      completions[key] = { data, eventAt, recordId, uniqueKey: key };
    }
  });

  const roomMasterIndex = buildRoommaidPerformanceRoomMasterIndex_();
  const staff = {};
  const daily = {};
  const details = [];
  const sites = new Set();
  Object.values(completions).forEach(entry => {
    const data = entry.data;
    let detail = {};
    try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    const businessDate = String(data['업무일자'] || '').trim();
    const site = String(data['사업장'] || '').trim();
    const roomNo = String(data['객실번호'] || '').trim();
    if (request.site && site !== request.site) return;
    sites.add(site);
    const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
    const assignmentType = String(detail.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
    const maintenanceType = resolveRoommaidPerformanceMaintenanceType_(roomMasterIndex, site, roomNo, detail, data);
    const maintenanceCredit = roommaidPerformanceMaintenanceCredit_(maintenanceType);
    const cleaningCredit = getRoommaidCleaningCreditUnit_(cleaningType);
    const unit = maintenanceCredit * cleaningCredit;
    const primaryNo = roommaidPerformanceEligibleEmployeeNo_(
      detail.primaryEmployeeNo || data['대상사번'] || '', users
    );
    const secondaryNo = roommaidPerformanceEligibleEmployeeNo_(detail.secondaryEmployeeNo || '', users);
    const shares = roommaidPerformanceAssignmentCreditShares_(assignmentType, primaryNo, secondaryNo);
    const participants = [];
    if (primaryNo) participants.push({
      employeeNo: primaryNo,
      participationRole: 'PRIMARY',
      recognizedUnits: unit * shares.primary
    });
    if (secondaryNo && secondaryNo !== primaryNo) participants.push({
      employeeNo: secondaryNo,
      participationRole: 'SECONDARY',
      recognizedUnits: unit * shares.secondary
    });

    participants.forEach(participant => {
      const user = users[participant.employeeNo] || {};
      const name = String(user.name || participant.employeeNo).trim();
      const searchText = `${name} ${participant.employeeNo}`.toLowerCase();
      const employment = employmentIndex[participant.employeeNo] || parseRoommaidPerformanceEmployment_('', user);
      if (request.employeeNo && participant.employeeNo !== request.employeeNo) return;
      if (!request.employeeNo && request.employeeSearch && !searchText.includes(request.employeeSearch)) return;
      if (!request.employeeNo && !roommaidPerformanceEmploymentMatches_(employment, request)) return;

      const group = roommaidPerformanceSeed_(staff, participant.employeeNo, users, '', '', cleaningTypes, employment);
      applyRoommaidPerformanceCount_(group, participant.participationRole, cleaningType, assignmentType, participant.recognizedUnits);
      const dailyKey = `${businessDate}|${participant.employeeNo}`;
      const day = roommaidPerformanceSeed_(daily, dailyKey, users, participant.employeeNo, businessDate, cleaningTypes, employment);
      applyRoommaidPerformanceCount_(day, participant.participationRole, cleaningType, assignmentType, participant.recognizedUnits);
      details.push({
        businessDate, site, roomNo,
        employeeNo: participant.employeeNo,
        name,
        participationRole: participant.participationRole,
        participationLabel: participant.participationRole === 'PRIMARY' ? '주담당' : '보조담당',
        cleaningType,
        cleaningTypeLabel: getRoommaidCleaningTypeLabel_(cleaningType),
        cleaningCredit,
        maintenanceType,
        maintenanceCredit,
        assignmentType,
        assignmentTypeLabel: roommaidPerformanceAssignmentTypeLabel_(assignmentType),
        recognizedUnits: roundRoommaidPerformance_(participant.recognizedUnits),
        completedAt: String(data['완료일시'] || data['수정일시'] || data['등록일시'] || '').trim()
      });
    });
  });

  // 등록된 활성 룸메이드도 실적이 없어도 월간 표에 0으로 표시합니다.
  roommaidOptions.forEach(option => {
    if (request.employeeNo && option.employeeNo !== request.employeeNo) return;
    if (!request.employeeNo && request.employeeSearch && !`${option.name} ${option.employeeNo}`.toLowerCase().includes(request.employeeSearch)) return;
    if (!request.employeeNo && !roommaidPerformanceEmploymentMatches_(option, request)) return;
    if (request.site && option.site && option.site !== request.site && !staff[option.employeeNo]) return;
    roommaidPerformanceSeed_(staff, option.employeeNo, users, '', '', cleaningTypes, option);
  });

  const staffRows = Object.values(staff).map(finalizeRoommaidPerformanceRow_)
    .sort((a, b) => Number(a.employmentSortRank || 9) - Number(b.employmentSortRank || 9) || String(a.employmentLabel || '').localeCompare(String(b.employmentLabel || ''), 'ko') || a.name.localeCompare(b.name, 'ko'));
  const dailyRows = Object.values(daily).map(finalizeRoommaidPerformanceRow_)
    .sort((a, b) => String(b.businessDate || '').localeCompare(String(a.businessDate || '')) || b.recognizedUnits - a.recognizedUnits || a.name.localeCompare(b.name, 'ko'));
  const daysInMonth = roommaidPerformanceMonthDays_(request.year, request.month);
  const dailyUnitsByEmployee = {};
  dailyRows.forEach(row => {
    const day = Number(String(row.businessDate || '').slice(8, 10));
    if (!dailyUnitsByEmployee[row.employeeNo]) dailyUnitsByEmployee[row.employeeNo] = {};
    if (day >= 1 && day <= daysInMonth) dailyUnitsByEmployee[row.employeeNo][day] = roundRoommaidPerformance_(row.recognizedUnits);
  });
  const monthlyGridRows = staffRows.map(row => {
    const employment = roommaidPerformanceMonthlyEmployment_(row.employeeNo, employmentIndex);
    return Object.assign({}, row, {
      employmentCategory: employment.category,
      employmentVendor: employment.vendor,
      employmentLabel: employment.label,
      employmentSortRank: employment.sortRank,
      dailyUnits: dailyUnitsByEmployee[row.employeeNo] || {},
      monthlyTotal: roundRoommaidPerformance_(row.recognizedUnits)
    });
  });
  details.sort((a, b) => String(b.businessDate).localeCompare(String(a.businessDate)) || String(b.completedAt).localeCompare(String(a.completedAt)) || String(a.roomNo).localeCompare(String(b.roomNo), 'ko', { numeric: true }));

  const summary = roommaidPerformanceSummarySeed_(cleaningTypes);
  staffRows.forEach(row => {
    ['totalParticipation', 'primaryCompleted', 'secondaryParticipation', 'pairCount', 'trainingCount', 'recognizedUnits'].forEach(key => {
      summary[key] += Number(row[key] || 0);
    });
    cleaningTypes.forEach(type => {
      summary.cleaningTypeCounts[type.code] += Number(row.cleaningTypeCounts && row.cleaningTypeCounts[type.code] || 0);
    });
  });
  summary.normalCount = Number(summary.cleaningTypeCounts[NOVA.CLEANING_TYPES.NORMAL] || 0);
  summary.dsCount = Number(summary.cleaningTypeCounts[NOVA.CLEANING_TYPES.DS] || 0);
  summary.recognizedUnits = roundRoommaidPerformance_(summary.recognizedUnits);
  summary.roommaidCount = staffRows.length;

  return {
    summary,
    staffRows,
    monthlyGridRows,
    daysInMonth,
    dailyRows,
    details: details.slice(0, NOVA_ROOMMAID_PERFORMANCE.MAX_DETAIL_ROWS),
    detailTotal: details.length,
    cleaningTypes,
    options: {
      roommaids: roommaidOptions,
      sites: Array.from(sites).filter(Boolean).sort((a, b) => a.localeCompare(b, 'ko')),
      employmentCategories: ['정규직', '아르바이트', '외주업체'],
      employmentVendors: Array.from(new Set(roommaidOptions.filter(item => item.employmentCategory === '외주업체').map(item => item.employmentVendor).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'ko'))
    },
    recognitionRule: {
      cleaningTypes,
      normal: getRoommaidCleaningCreditUnit_(NOVA.CLEANING_TYPES.NORMAL),
      ds: getRoommaidCleaningCreditUnit_(NOVA.CLEANING_TYPES.DS),
      special: 1.5,
      maintenanceTypeWeights: Object.assign({}, NOVA_ROOMMAID_PERFORMANCE.MAINTENANCE_CREDIT),
      maintenanceTypeText: 'F 1 · T 1.5 · R 1.5 · G 2',
      pairPrimary: '2인1조는 주담당·보조 50%씩, 교육배정은 주담당 100%',
      pairSecondary: '교육 보조는 참여실적만 반영'
    }
  };
}

function buildRoommaidPerformanceRoomMasterIndex_() { // (객실별 정비타입 인덱스)
  const sheet = getRequiredSheet_(NOVA.SHEETS.ROOMS);
  const headerMap = getHeaderMap_(sheet);
  const bySiteRoom = {};
  const byRoomNo = {};
  if (sheet.getLastRow() < 2) return { bySiteRoom, byRoomNo };
  const values = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getDisplayValues();
  values.forEach(row => {
    const data = rowObjectFromValues_(row, headerMap);
    const enabled = String(data['사용여부'] || 'Y').trim().toUpperCase();
    if (['N', '미사용', '사용안함'].includes(enabled)) return;
    const roomNo = normalizeRoomNo_(data['객실번호']);
    if (!roomNo) return;
    const site = String(data['사업장'] || '').trim();
    const maintenanceType = normalizeRoommaidPerformanceMaintenanceType_(data['정비타입']);
    const item = { roomNo, site, maintenanceType };
    bySiteRoom[`${site}|${roomNo}`] = item;
    if (!byRoomNo[roomNo]) byRoomNo[roomNo] = item;
  });
  return { bySiteRoom, byRoomNo };
}

function resolveRoommaidPerformanceMaintenanceType_(roomMasterIndex, site, roomNo, detail, historyData) { // (완료 객실 정비타입 확인)
  const direct = normalizeRoommaidPerformanceMaintenanceType_(
    detail && (detail.maintenanceType || detail.maintenanceTypeCode) || historyData && historyData['정비타입'] || ''
  );
  if (direct) return direct;
  const normalizedRoomNo = normalizeRoomNo_(roomNo);
  const normalizedSite = String(site || '').trim();
  const index = roomMasterIndex || { bySiteRoom: {}, byRoomNo: {} };
  const item = index.bySiteRoom[`${normalizedSite}|${normalizedRoomNo}`] || index.byRoomNo[normalizedRoomNo] || null;
  return item && item.maintenanceType ? item.maintenanceType : 'F';
}

function normalizeRoommaidPerformanceMaintenanceType_(value) { // (F/T/R/G 정비타입 정규화)
  const type = String(value || '').trim().toUpperCase();
  return Object.prototype.hasOwnProperty.call(NOVA_ROOMMAID_PERFORMANCE.MAINTENANCE_CREDIT, type) ? type : '';
}

function roommaidPerformanceMaintenanceCredit_(maintenanceType) { // (정비타입별 기본 인정정비수)
  const type = normalizeRoommaidPerformanceMaintenanceType_(maintenanceType);
  return Number(NOVA_ROOMMAID_PERFORMANCE.MAINTENANCE_CREDIT[type] || 1);
}

function roommaidPerformanceCleaningCountSeed_(cleaningTypes) { // (정비유형별 참여수 초기값)
  const result = {};
  (cleaningTypes || getRoommaidCleaningTypeDefinitions_()).forEach(type => { result[type.code] = 0; });
  return result;
}

function roommaidPerformanceSummarySeed_(cleaningTypes) { // (전체 실적 초기값)
  return {
    roommaidCount: 0,
    totalParticipation: 0,
    primaryCompleted: 0,
    secondaryParticipation: 0,
    pairCount: 0,
    trainingCount: 0,
    recognizedUnits: 0,
    cleaningTypeCounts: roommaidPerformanceCleaningCountSeed_(cleaningTypes),
    normalCount: 0,
    dsCount: 0
  };
}

function roommaidPerformanceSeed_(map, key, users, employeeNoOverride, businessDate, cleaningTypes, employmentInfo) { // (룸메이드 실적 초기값)
  if (!map[key]) {
    const employeeNo = String(employeeNoOverride || key || '').trim();
    const user = users[employeeNo] || {};
    const employment = employmentInfo || parseRoommaidPerformanceEmployment_('', user);
    map[key] = {
      businessDate: businessDate || '',
      employeeNo,
      name: String(user.name || employeeNo).trim(),
      job: String(user.job || '').trim(),
      employmentCategory: String(employment.category || '정규직'),
      employmentVendor: String(employment.vendor || ''),
      employmentLabel: String(employment.label || employment.category || '정규직'),
      employmentSortRank: Number(employment.sortRank || 9),
      totalParticipation: 0,
      primaryCompleted: 0,
      secondaryParticipation: 0,
      cleaningTypeCounts: roommaidPerformanceCleaningCountSeed_(cleaningTypes),
      normalCount: 0,
      dsCount: 0,
      pairCount: 0,
      trainingCount: 0,
      recognizedUnits: 0
    };
  }
  return map[key];
}

function applyRoommaidPerformanceCount_(row, participationRole, cleaningType, assignmentType, recognizedUnits) { // (개인 실적 정비유형별 1실 반영)
  row.totalParticipation += 1;
  if (participationRole === 'PRIMARY') row.primaryCompleted += 1;
  else row.secondaryParticipation += 1;
  const normalizedCleaningType = normalizeRoommaidCleaningType_(cleaningType);
  if (!row.cleaningTypeCounts) row.cleaningTypeCounts = roommaidPerformanceCleaningCountSeed_();
  if (!Object.prototype.hasOwnProperty.call(row.cleaningTypeCounts, normalizedCleaningType)) row.cleaningTypeCounts[normalizedCleaningType] = 0;
  row.cleaningTypeCounts[normalizedCleaningType] += 1;
  row.normalCount = Number(row.cleaningTypeCounts[NOVA.CLEANING_TYPES.NORMAL] || 0);
  row.dsCount = Number(row.cleaningTypeCounts[NOVA.CLEANING_TYPES.DS] || 0);
  if (assignmentType === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR) row.pairCount += 1;
  if (assignmentType === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING) row.trainingCount += 1;
  row.recognizedUnits += Number(recognizedUnits || 0);
}

function finalizeRoommaidPerformanceRow_(row) { // (개인 실적 소수점·호환값 정리)
  const cleaningTypeCounts = Object.assign(roommaidPerformanceCleaningCountSeed_(), row.cleaningTypeCounts || {});
  return Object.assign({}, row, {
    cleaningTypeCounts,
    normalCount: Number(cleaningTypeCounts[NOVA.CLEANING_TYPES.NORMAL] || 0),
    dsCount: Number(cleaningTypeCounts[NOVA.CLEANING_TYPES.DS] || 0),
    recognizedUnits: roundRoommaidPerformance_(row.recognizedUnits)
  });
}

function roommaidPerformanceAssignmentCreditShares_(assignmentType, primaryEmployeeNo, secondaryEmployeeNo) { // (배정유형별 인정 정비수 배분)
  const type = String(assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
  const primaryNo = String(primaryEmployeeNo || '').trim();
  const secondaryNo = String(secondaryEmployeeNo || '').trim();
  const validPair = Boolean(primaryNo && secondaryNo && primaryNo !== secondaryNo);
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR && validPair) {
    return { primary: 0.5, secondary: 0.5 };
  }
  // 교육배정은 교육생 참여만 기록하고 인정 정비수는 주담당에게 100% 반영합니다.
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING && validPair) {
    return { primary: 1, secondary: 0 };
  }
  return { primary: 1, secondary: 0 };
}

function roommaidPerformanceAssignmentTypeLabel_(assignmentType) { // (개인실적 배정유형 표시명)
  return {
    [NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO]: '1인 배정',
    [NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR]: '2인1조',
    [NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING]: '2인1조(교육)'
  }[assignmentType] || assignmentType || '-';
}

function roundRoommaidPerformance_(value) { // (정비 인정수 소수점 정리)
  return Math.round(Number(value || 0) * 1000) / 1000;
}
