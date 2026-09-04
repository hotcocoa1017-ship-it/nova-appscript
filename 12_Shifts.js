/**
 * NOVA 하우스맨 A·B·C 근무조 관리
 * 별도 시트 없이 업무이력의 SHIFT_ASSIGNMENT 기록을 사용합니다.
 */
function getShiftManagementData(token, options) { // (근무조 관리 화면 조회)
  return measureResponse_('getShiftManagementData', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const sites = getSiteList_();
    const site = String(safe.site || user.defaultSite || sites[0] || '').trim();
    const assignments = getShiftAssignmentsForDate_(businessDate, site);
    const zoneAssignments = getHousemanZoneAssignmentsForDate_(businessDate, site);
    const staff = getPublicStaffList_(['HOUSEMAN']);
    const staffByEmployeeNo = {};
    staff.forEach(item => { staffByEmployeeNo[item.employeeNo] = item; });
    const attendanceStaff = assignments.allEmployeeNos.map(employeeNo => {
      const item = staffByEmployeeNo[employeeNo] || { employeeNo, name: employeeNo };
      return Object.assign({}, item, {
        shiftCodes: assignments.byEmployeeNo[employeeNo] || [],
        shiftLabels: (assignments.byEmployeeNo[employeeNo] || []).map(code => NOVA.SHIFTS[code] ? NOVA.SHIFTS[code].label : code)
      });
    });
    return {
      ok: true,
      businessDate,
      site,
      sites,
      shifts: getShiftDefinitions_(),
      assignments: assignments.byShift,
      zoneAssignments: zoneAssignments.byEmployeeNo,
      zoneAssignmentsByBuilding: zoneAssignments.byBuilding,
      buildings: getHousemanBuildingCards_(),
      attendanceStaff,
      staff,
      maxStaff: NOVA.MAX_SHIFT_STAFF,
      currentShift: resolveCurrentShiftCode_(new Date()),
      serverTime: nowText_()
    };
  });
}

function saveShiftAssignments(token, payload) { // (업무일자별 근무조 저장)
  return measureResponse_('saveShiftAssignments', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('사업장을 선택하세요.');

    const userIndex = getUserIndex_();
    const normalized = {};
    Object.keys(NOVA.SHIFTS).forEach(shiftCode => {
      const raw = Array.isArray(safe.assignments && safe.assignments[shiftCode])
        ? safe.assignments[shiftCode]
        : [];
      const unique = Array.from(new Set(raw.map(value => String(value || '').trim()).filter(Boolean)));
      if (unique.length > NOVA.MAX_SHIFT_STAFF) {
        throw new Error(`${NOVA.SHIFTS[shiftCode].label}은 최대 ${NOVA.MAX_SHIFT_STAFF}명까지 배정할 수 있습니다.`);
      }
      unique.forEach(employeeNo => {
        const staff = userIndex.byEmployeeNo[employeeNo];
        if (!staff || !staff.enabled || staff.role !== 'HOUSEMAN') {
          throw new Error(`${employeeNo} 사번은 사용 가능한 하우스맨 계정이 아닙니다.`);
        }
      });
      normalized[shiftCode] = unique;
    });

    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const headerMap = getHeaderMap_(sheet);
    let version = 0;
    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      version = reserveDataVersion_({ lockHeld: true });
      const existing = getShiftAssignmentRows_(businessDate, site);
      const deletedColumn = headerMap['삭제여부'];
      const statusColumn = headerMap['처리상태'];
      const updatedColumn = headerMap['수정일시'];
      const oldRows = existing.rows.map(item => item.rowNumber);
      if (oldRows.length) {
        if (deletedColumn) sheet.getRangeList(oldRows.map(rowNumber => `${columnLetter_(deletedColumn)}${rowNumber}`)).setValue('Y');
        if (statusColumn) sheet.getRangeList(oldRows.map(rowNumber => `${columnLetter_(statusColumn)}${rowNumber}`)).setValue('REPLACED');
        if (updatedColumn) sheet.getRangeList(oldRows.map(rowNumber => `${columnLetter_(updatedColumn)}${rowNumber}`)).setValue(nowText_());
      }

      const columnCount = sheet.getLastColumn();
      const rows = [];
      Object.keys(NOVA.SHIFTS).forEach(shiftCode => {
        const shift = NOVA.SHIFTS[shiftCode];
        normalized[shiftCode].forEach((employeeNo, index) => {
          rows.push(buildHistoryRowWithMap_(columnCount, headerMap, {
            '기록ID': `SHIFT-${businessDate.replaceAll('-', '')}-${shiftCode}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`,
            '기록구분': NOVA.RECORD_TYPES.SHIFT_ASSIGNMENT,
            '업무일자': businessDate,
            '사업장': site,
            '대상사번': employeeNo,
            '처리상태': 'ACTIVE',
            '세부내용JSON': JSON.stringify({
              shiftCode,
              shiftLabel: shift.label,
              startTime: shift.start,
              endTime: shift.end,
              position: index + 1
            }),
            '등록사번': user.employeeNo,
            '등록일시': nowText_(),
            '수정일시': nowText_(),
            '변경버전': version,
            '삭제여부': 'N'
          }));
        });
      });
      if (rows.length) {
        const startRow = sheet.getLastRow() + 1;
        ensureSheetRowCapacity_(sheet, startRow + rows.length - 1);
        sheet.getRange(startRow, 1, rows.length, sheet.getLastColumn()).setValues(rows);
      }
      publishDataVersion_(version, { domains: ['SHIFT'], businessDate, site, lockHeld: true });
      clearShiftCaches_(businessDate, site);
      clearHousemanZoneCaches_(businessDate, site);
      return {
        ok: true,
        businessDate,
        site,
        assignments: normalized,
        version,
        message: `${businessDate} ${site} 근무조를 저장했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function getShiftDefinitions_() { // (근무조 표시정보)
  return Object.keys(NOVA.SHIFTS).map(code => ({
    code,
    label: NOVA.SHIFTS[code].label,
    start: NOVA.SHIFTS[code].start,
    end: NOVA.SHIFTS[code].end,
    order: NOVA.SHIFTS[code].order
  })).sort((a, b) => a.order - b.order);
}

function getShiftAssignmentsForDate_(businessDate, site) { // (업무일자·사업장 근무조 인덱스)
  const date = normalizeBusinessDate_(businessDate);
  const normalizedSite = String(site || '').trim();
  const cacheKey = buildShiftCacheKey_(date, normalizedSite);
  const cache = CacheService.getScriptCache();
  const cached = cache.get(cacheKey);
  if (cached) return JSON.parse(cached);

  const rowData = getShiftAssignmentRows_(date, normalizedSite);
  const result = {
    businessDate: date,
    site: normalizedSite,
    byShift: { A: [], B: [], C: [] },
    byEmployeeNo: {},
    allEmployeeNos: []
  };
  rowData.rows.forEach(item => {
    const employeeNo = String(item.data['대상사번'] || '').trim();
    const shiftCode = String(item.detail.shiftCode || '').trim().toUpperCase();
    if (!employeeNo || !result.byShift[shiftCode]) return;
    if (!result.byShift[shiftCode].includes(employeeNo)) result.byShift[shiftCode].push(employeeNo);
    if (!result.byEmployeeNo[employeeNo]) result.byEmployeeNo[employeeNo] = [];
    if (!result.byEmployeeNo[employeeNo].includes(shiftCode)) result.byEmployeeNo[employeeNo].push(shiftCode);
  });
  Object.keys(result.byShift).forEach(code => {
    result.byShift[code].sort((a, b) => {
      const left = rowData.positions[`${code}|${a}`] || 999;
      const right = rowData.positions[`${code}|${b}`] || 999;
      return left - right;
    });
  });
  result.allEmployeeNos = Array.from(new Set(Object.values(result.byShift).flat()));
  const serialized = JSON.stringify(result);
  if (serialized.length < 95000) cache.put(cacheKey, serialized, NOVA.CACHE_SECONDS);
  return result;
}

function getShiftAssignmentRows_(businessDate, site) { // (근무조 원본행 조회)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const result = { rows: [], positions: {} };
  if (sheet.getLastRow() < 2) return result;
  const headerMap = getHeaderMap_(sheet);
  const scanLimit = 10000;
  const startRow = Math.max(2, sheet.getLastRow() - scanLimit + 1);
  const rowCount = sheet.getLastRow() - startRow + 1;
  const values = sheet.getRange(startRow, 1, rowCount, sheet.getLastColumn()).getDisplayValues();
  values.forEach((row, offset) => {
    const data = rowObjectFromValues_(row, headerMap);
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.SHIFT_ASSIGNMENT) return;
    if (String(data['업무일자'] || '').trim() !== businessDate) return;
    if (site && String(data['사업장'] || '').trim() !== site) return;
    if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') return;
    let detail = {};
    try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    const shiftCode = String(detail.shiftCode || '').trim().toUpperCase();
    const employeeNo = String(data['대상사번'] || '').trim();
    result.rows.push({ rowNumber: startRow + offset, data, detail });
    result.positions[`${shiftCode}|${employeeNo}`] = Number(detail.position || 999);
  });
  return result;
}

function buildShiftCacheKey_(businessDate, site) { // (근무조 캐시키)
  const digest = Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, `${businessDate}|${site}`)
  ).replace(/=+$/g, '').slice(0, 20);
  return `NOVA_SHIFT_${digest}`;
}

function clearShiftCaches_(businessDate, site) { // (근무조 캐시 초기화)
  CacheService.getScriptCache().remove(buildShiftCacheKey_(businessDate, site));
}

function resolveActiveShiftCodes_(dateValue) { // (현재 시각 실제 근무 중인 조·A/B 중첩 포함)
  const date = dateValue instanceof Date ? dateValue : new Date();
  const hour = Number(Utilities.formatDate(date, NOVA.TIMEZONE, 'H'));
  const minute = Number(Utilities.formatDate(date, NOVA.TIMEZONE, 'm'));
  const minutes = hour * 60 + minute;
  if (minutes >= 14 * 60 + 30 && minutes < 17 * 60 + 30) return ['A', 'B'];
  if (minutes >= 8 * 60 + 30 && minutes < 14 * 60 + 30) return ['A'];
  if (minutes >= 17 * 60 + 30 && minutes < 23 * 60 + 30) return ['B'];
  return ['C'];
}

function resolveCurrentShiftCode_(dateValue) { // (현재 대표 근무조·중첩시간은 B조 표시)
  const activeShiftCodes = resolveActiveShiftCodes_(dateValue);
  return activeShiftCodes.includes('B') ? 'B' : (activeShiftCodes[0] || 'C');
}

function resolveNextShiftCode_(currentShiftCode) { // (다음 근무조)
  const code = String(currentShiftCode || '').trim().toUpperCase();
  return code === 'A' ? 'B' : code === 'B' ? 'C' : 'A';
}

function resolveHandoverTargetShift_(registeredAt) { // (인수인계 대상 근무조)
  let date = new Date();
  const text = String(registeredAt || '').trim();
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) {
    const parsed = new Date(text.replace(' ', 'T') + '+09:00');
    if (!Number.isNaN(parsed.getTime())) date = parsed;
  }
  return resolveNextShiftCode_(resolveCurrentShiftCode_(date));
}

function getOrderShiftRecipients_(order) { // (중요·인수인계 근무조 대상 사번)
  const assignments = getShiftAssignmentsForDate_(order.businessDate, order.site);
  const result = new Set();
  if (order.important) assignments.allEmployeeNos.forEach(employeeNo => result.add(employeeNo));
  if (order.handover) {
    const targetShift = order.handoverTargetShift || resolveHandoverTargetShift_(order.registeredAt);
    (assignments.byShift[targetShift] || []).forEach(employeeNo => result.add(employeeNo));
  }
  return { employeeNos: Array.from(result), assignments };
}

function isHousemanOrderRouteCandidate_(order, employeeNo) { // (공동 전달 오더 접수 가능 직원 확인)
  const target = String(employeeNo || '').trim();
  if (!target || !order) return false;
  if (String(order.statusCode || '').trim().toUpperCase() !== 'ASSIGNED') return false;
  if (order.routeLocked === true) return false;
  const candidates = Array.isArray(order.routeCandidateEmployeeNos) ? order.routeCandidateEmployeeNos : [];
  return candidates.map(String).map(value => value.trim()).includes(target);
}

function isHousemanOrderVisibleForUser_(order, user, request) { // (근무조·공동 전달 기준 하우스맨 모바일 표시)
  if (order.assignedEmployeeNo === user.employeeNo) return true;
  if (isHousemanOrderRouteCandidate_(order, user.employeeNo)) return true;
  if (!order.important && !order.handover) return false;
  const site = order.site || request.site || user.defaultSite || '';
  const shiftRecipients = getOrderShiftRecipients_(Object.assign({}, order, { site }));
  if (shiftRecipients.assignments.allEmployeeNos.length) {
    return shiftRecipients.employeeNos.includes(user.employeeNo);
  }
  // 근무조가 아직 저장되지 않은 경우 중요·인수인계 누락 방지를 위해 해당 사업장 하우스맨에게 표시
  return user.role === 'HOUSEMAN' && (!site || !user.defaultSite || user.defaultSite === site);
}

function buildHousemanShiftContext_(businessDate, site, employeeNo) { // (하우스맨 본인 근무조 정보)
  const assignments = getShiftAssignmentsForDate_(businessDate, site);
  const shiftCodes = assignments.byEmployeeNo[String(employeeNo || '').trim()] || [];
  const activeShiftCodes = resolveActiveShiftCodes_(new Date());
  return {
    shiftCodes,
    shifts: shiftCodes.map(code => NOVA.SHIFTS[code]).filter(Boolean),
    currentShift: resolveCurrentShiftCode_(new Date()),
    activeShiftCodes,
    currentShiftAssigned: activeShiftCodes.some(code => shiftCodes.includes(code))
  };
}


function saveHousemanZoneAssignment(token, payload) { // (하우스맨 담당동 저장·변경·취소)
  return measureResponse_('saveHousemanZoneAssignment', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const employeeNo = String(safe.employeeNo || '').trim();
    const action = String(safe.action || 'SAVE').trim().toUpperCase();
    if (!site) throw new Error('사업장을 선택하세요.');
    if (!employeeNo) throw new Error('출근 직원을 선택하세요.');
    if (!['SAVE', 'UPDATE', 'CANCEL'].includes(action)) throw new Error('지원하지 않는 담당동 작업입니다.');

    const shiftAssignments = getShiftAssignmentsForDate_(businessDate, site);
    if (!shiftAssignments.allEmployeeNos.includes(employeeNo)) {
      throw new Error('선택한 직원은 해당 업무일자의 A·B·C 근무조에 등록되어 있지 않습니다.');
    }
    const employee = getActiveUserByEmployeeNo_(employeeNo);
    if (!employee || employee.role !== 'HOUSEMAN') throw new Error('사용 가능한 하우스맨 계정이 아닙니다.');

    const buildings = normalizeHousemanBuildings_(safe.buildings);
    if (action !== 'CANCEL' && !buildings.length) throw new Error('담당동을 한 개 이상 선택하세요.');

    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const headerMap = getHeaderMap_(sheet);
    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      const current = getHousemanZoneAssignmentRows_(businessDate, site, employeeNo);
      if (action === 'SAVE' && current.rows.length) throw new Error('이미 담당동이 등록되어 있습니다. 변경 버튼을 사용하세요.');
      if (action === 'UPDATE' && !current.rows.length) throw new Error('기존 담당동 배정이 없습니다. 저장 버튼을 사용하세요.');
      if (action === 'CANCEL' && !current.rows.length) throw new Error('취소할 담당동 배정이 없습니다.');

      const now = nowText_();
      const oldRows = current.rows.map(item => item.rowNumber);
      if (oldRows.length) {
        const updates = {};
        if (headerMap['삭제여부']) updates['삭제여부'] = 'Y';
        if (headerMap['처리상태']) updates['처리상태'] = action === 'CANCEL' ? 'CANCELLED' : 'REPLACED';
        if (headerMap['수정일시']) updates['수정일시'] = now;
        oldRows.forEach(rowNumber => updateRowByHeaders_(sheet, rowNumber, updates));
      }

      const version = reserveDataVersion_({ lockHeld: true });
      if (action !== 'CANCEL') {
        const row = createRowByHeaders_(sheet, {
          '기록ID': `ZONE-${businessDate.replaceAll('-', '')}-${employeeNo}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`,
          '기록구분': NOVA.RECORD_TYPES.HOUSEMAN_ZONE_ASSIGNMENT,
          '업무일자': businessDate,
          '사업장': site,
          '대상사번': employeeNo,
          '처리상태': 'ACTIVE',
          '세부내용JSON': JSON.stringify({
            buildings,
            shiftCodes: shiftAssignments.byEmployeeNo[employeeNo] || []
          }),
          '등록사번': user.employeeNo,
          '등록일시': now,
          '수정일시': now,
          '변경버전': version,
          '삭제여부': 'N'
        });
        const rowNumber = sheet.getLastRow() + 1;
        ensureSheetRowCapacity_(sheet, rowNumber);
        sheet.getRange(rowNumber, 1, 1, row.length).setValues([row]);
      }

      publishDataVersion_(version, { domains: ['SHIFT'], businessDate, site, lockHeld: true });
      clearHousemanZoneCaches_(businessDate, site);
      clearShiftCaches_(businessDate, site);
      return {
        ok: true,
        businessDate,
        site,
        employeeNo,
        action,
        buildings: action === 'CANCEL' ? [] : buildings,
        version,
        message: action === 'CANCEL'
          ? `${employee.name}님의 담당동 배정을 취소했습니다.`
          : action === 'UPDATE'
            ? `${employee.name}님의 담당동을 변경했습니다.`
            : `${employee.name}님의 담당동을 저장했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function getHousemanZoneAssignmentsForDate_(businessDate, site) { // (업무일자·사업장 담당동 인덱스)
  const date = normalizeBusinessDate_(businessDate);
  const normalizedSite = String(site || '').trim();
  const cacheKey = buildHousemanZoneCacheKey_(date, normalizedSite);
  const cache = CacheService.getScriptCache();
  const cached = cache.get(cacheKey);
  if (cached) return JSON.parse(cached);

  const rowData = getHousemanZoneAssignmentRows_(date, normalizedSite, '');
  const result = {
    businessDate: date,
    site: normalizedSite,
    byEmployeeNo: {},
    byBuilding: {}
  };
  getHousemanBuildingCards_().forEach(building => { result.byBuilding[building] = []; });
  rowData.rows.forEach(item => {
    const employeeNo = String(item.data['대상사번'] || '').trim();
    if (!employeeNo) return;
    const buildings = normalizeHousemanBuildings_(item.detail.buildings);
    result.byEmployeeNo[employeeNo] = {
      employeeNo,
      buildings,
      shiftCodes: Array.isArray(item.detail.shiftCodes) ? item.detail.shiftCodes : [],
      registeredAt: String(item.data['등록일시'] || '').trim(),
      updatedAt: String(item.data['수정일시'] || item.data['등록일시'] || '').trim()
    };
    buildings.forEach(building => {
      if (!result.byBuilding[building]) result.byBuilding[building] = [];
      if (!result.byBuilding[building].includes(employeeNo)) result.byBuilding[building].push(employeeNo);
    });
  });
  Object.keys(result.byBuilding).forEach(building => result.byBuilding[building].sort());
  const serialized = JSON.stringify(result);
  if (serialized.length < 95000) cache.put(cacheKey, serialized, NOVA.CACHE_SECONDS);
  return result;
}

function getHousemanZoneAssignmentRows_(businessDate, site, employeeNo) { // (담당동 원본행 조회)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const result = { rows: [] };
  if (sheet.getLastRow() < 2) return result;
  const headerMap = getHeaderMap_(sheet);
  const scanLimit = 15000;
  const startRow = Math.max(2, sheet.getLastRow() - scanLimit + 1);
  const rowCount = sheet.getLastRow() - startRow + 1;
  const values = sheet.getRange(startRow, 1, rowCount, sheet.getLastColumn()).getDisplayValues();
  values.forEach((row, offset) => {
    const data = rowObjectFromValues_(row, headerMap);
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.HOUSEMAN_ZONE_ASSIGNMENT) return;
    if (String(data['업무일자'] || '').trim() !== businessDate) return;
    if (site && String(data['사업장'] || '').trim() !== site) return;
    if (employeeNo && String(data['대상사번'] || '').trim() !== employeeNo) return;
    if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') return;
    let detail = {};
    try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    result.rows.push({ rowNumber: startRow + offset, data, detail });
  });
  return result;
}

function getHousemanBuildingCards_() { // (하우스맨 담당동 1~9동 카드)
  return Array.from({ length: 9 }, (_, index) => `${index + 1}동`);
}

function normalizeHousemanBuildings_(values) { // (담당동 값 정리)
  const raw = Array.isArray(values) ? values : String(values || '').split(',');
  const normalized = raw.map(value => {
    const match = String(value || '').trim().match(/^0?([1-9])(?:\s*동)?$/);
    return match ? `${Number(match[1])}동` : '';
  }).filter(Boolean);
  return Array.from(new Set(normalized)).sort((a, b) => Number(a.replace(/\D/g, '')) - Number(b.replace(/\D/g, '')));
}

function buildHousemanZoneCacheKey_(businessDate, site) { // (담당동 캐시키)
  const digest = Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, `${businessDate}|${site}`)
  ).replace(/=+$/g, '').slice(0, 20);
  return `NOVA_ZONE_${digest}`;
}

function clearHousemanZoneCaches_(businessDate, site) { // (담당동 캐시 초기화)
  CacheService.getScriptCache().remove(buildHousemanZoneCacheKey_(businessDate, site));
}

function buildHousemanRoutingData_(businessDate, site, orders) { // (담당동 공동 전달 자동배정 화면정보)
  const shiftAssignments = getShiftAssignmentsForDate_(businessDate, site);
  const zoneAssignments = getHousemanZoneAssignmentsForDate_(businessDate, site);
  const currentShift = resolveCurrentShiftCode_(new Date());
  const isToday = normalizeBusinessDate_(businessDate) === businessDateText_();
  const activeShiftCodes = isToday ? resolveActiveShiftCodes_(new Date()) : Object.keys(NOVA.SHIFTS);
  const eligibleEmployeeNos = isToday
    ? Array.from(new Set(activeShiftCodes.flatMap(code => shiftAssignments.byShift[code] || [])))
    : shiftAssignments.allEmployeeNos;
  const eligibleSet = new Set(eligibleEmployeeNos);
  const users = getUserIndex_().byEmployeeNo;
  const pendingCounts = {};
  (orders || []).filter(order => !['COMPLETED', 'UNABLE'].includes(String(order.statusCode || '').toUpperCase())).forEach(order => {
    const sharedCandidates = String(order.statusCode || '').toUpperCase() === 'ASSIGNED' && order.routeLocked !== true
      ? (Array.isArray(order.routeCandidateEmployeeNos) ? order.routeCandidateEmployeeNos : [])
      : [];
    const targets = sharedCandidates.length ? sharedCandidates : [order.assignedEmployeeNo].filter(Boolean);
    Array.from(new Set(targets)).forEach(employeeNo => {
      pendingCounts[employeeNo] = (pendingCounts[employeeNo] || 0) + 1;
    });
  });
  const byBuilding = {};
  getHousemanBuildingCards_().forEach(building => {
    byBuilding[building] = (zoneAssignments.byBuilding[building] || [])
      .filter(employeeNo => eligibleSet.has(employeeNo))
      .map(employeeNo => users[employeeNo])
      .filter(user => user && user.enabled && user.role === 'HOUSEMAN')
      .map(user => ({
        employeeNo: user.employeeNo,
        name: user.name,
        shiftCodes: shiftAssignments.byEmployeeNo[user.employeeNo] || [],
        pendingCount: pendingCounts[user.employeeNo] || 0
      }))
      .sort((a, b) => a.pendingCount - b.pendingCount || String(a.employeeNo).localeCompare(String(b.employeeNo)));
  });
  return {
    businessDate: normalizeBusinessDate_(businessDate),
    site: String(site || '').trim(),
    currentShift,
    activeShiftCodes,
    isToday,
    byBuilding
  };
}

function resolveHousemanAutoAssignee_(businessDate, site, roomNo) { // (객실번호 담당동 근무자 전체 공동 전달)
  const building = normalizeRoomBuilding_('', roomNo);
  if (!/^([1-9])동$/.test(building)) throw new Error('자동배정은 4자리 객실번호로 등록해야 합니다.');
  const userIndex = getUserIndex_();
  const statusMap = {};
  getCodes_('하우스맨상태').forEach(code => { statusMap[code.code] = code.label; });
  const orders = getHousemanOrdersForDate_(normalizeBusinessDate_(businessDate), String(site || '').trim(), userIndex.byEmployeeNo, statusMap);
  const routing = buildHousemanRoutingData_(businessDate, site, orders);
  const candidates = routing.byBuilding[building] || [];
  if (!candidates.length) {
    const shiftCodes = routing.isToday ? routing.activeShiftCodes : [];
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
    pendingCount: selected.pendingCount,
    currentShift: routing.currentShift,
    activeShiftCodes: routing.activeShiftCodes || [routing.currentShift]
  };
}


function resolveHousemanPublicFastAssignee_(businessDate, site, roomNo) { // (객실퍼블릭 공동전달 담당동 경량 자동배정) // PUBLIC_HOUSEMAN_REQUEST_FAST_V2
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

function buildHistoryRowWithMap_(columnCount, headerMap, valuesByHeader) { // (근무조 일괄행 생성)
  const row = new Array(columnCount).fill('');
  Object.keys(valuesByHeader).forEach(header => {
    if (headerMap[header]) row[headerMap[header] - 1] = valuesByHeader[header];
  });
  return row;
}

function columnLetter_(columnNumber) { // (열번호 A1 문자 변환)
  let number = Number(columnNumber || 0);
  let result = '';
  while (number > 0) {
    number -= 1;
    result = String.fromCharCode(65 + (number % 26)) + result;
    number = Math.floor(number / 26);
  }
  return result;
}
