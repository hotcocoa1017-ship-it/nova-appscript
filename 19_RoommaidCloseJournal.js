/**
 * NOVA v1.0 RC6.4.39: 오더테이커·관리자 전용 룸메이드 마감일지
 * 현재객실현황·업무이력·객실마스터를 기준으로 마감표와 개인별 타입 실적을 구성합니다.
 */
const NOVA_ROOMMAID_CLOSE = Object.freeze({
  SCHEMA_VERSION: 28,
  DEFAULT_MAINTENANCE_TYPES: Object.freeze(['F', 'T', 'R', 'G']),
  REPORT_MAINTENANCE_TYPES: Object.freeze(['F', 'T', 'R', 'G']),
  CONVERSION_GROUPS: Object.freeze({
    F: Object.freeze(['F', 'T']),
    R: Object.freeze(['R', 'G'])
  }),
  CONVERSION_WEIGHTS: Object.freeze({
    F: Object.freeze({ F: 1, T: 1.5 }),
    R: Object.freeze({ R: 1.5, G: 2 })
  }),
  REPORT_STAFF_BLOCKS: 5,
  REPORT_STAFF_ROWS_PER_BLOCK: 20,
  INITIAL_STOCK_STATUSES: Object.freeze(['STOCK', 'STOCK_RC', 'STOCK_HU']),
  DEPARTURE_STATUSES: Object.freeze(['DUE_OUT', 'CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU']),
  REENTRY_STATUSES: Object.freeze(['RECHECKIN']),
  DUPLICATE_COMPLETE_WINDOW_SECONDS: 600,
  DUPLICATE_COMPLETE_RESULT_LIMIT: 200,
  CURRENT_STOCK_STATUSES: Object.freeze(['STOCK', 'STOCK_RC', 'STOCK_HU', 'CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU']),
  TEMP_GROUPS: Object.freeze([
    Object.freeze({ code: 'DAILY_GUMGWANG', label: '일용(금광)', tokens: Object.freeze(['일용(금광)', '금광']) }),
    Object.freeze({ code: 'DAILY_HIVENET', label: '일용(하이브넷)', tokens: Object.freeze(['일용(하이브넷)', '하이브넷']) })
  ])
});

function getRoommaidCloseJournal(token, filters) { // (룸메이드 마감일지 조회)
  return measureResponse_('getRoommaidCloseJournal', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = filters || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const currentAll = readCurrentRowsForClose_(businessDate, '');
    const sites = Array.from(new Set(currentAll.map(row => String(row['사업장'] || '').trim()).filter(Boolean)))
      .sort((a, b) => a.localeCompare(b, 'ko'));
    const requestedSite = String(safe.site || '').trim();
    const preferredSite = requestedSite || (sites.includes(String(user.defaultSite || '').trim()) ? String(user.defaultSite || '').trim() : sites[0] || '');
    if (!preferredSite) throw new Error(`${businessDate} 현재객실현황에 조회할 사업장이 없습니다.`);
    if (!sites.includes(preferredSite)) throw new Error(`${businessDate} ${preferredSite} 현재객실현황이 없습니다.`);

    const currentRows = currentAll.filter(row => String(row['사업장'] || '').trim() === preferredSite);
    const historyRows = readHistoryRowsForClose_(businessDate, preferredSite);
    const users = getUserIndex_().byEmployeeNo;
    const employmentIndex = readRoommaidCloseEmploymentIndex_();
    const saved = readDailyCloseSummaries_(businessDate, preferredSite)[0] || null;
    const inferredAttendance = inferRoommaidCloseAttendance_(currentRows, historyRows);
    const savedAttendance = saved && Array.isArray(saved.attendanceEmployeeNos) ? saved.attendanceEmployeeNos : [];
    const hasAttendanceOverride = Array.isArray(safe.attendanceEmployeeNos);
    const requestedAttendance = hasAttendanceOverride ? safe.attendanceEmployeeNos : [];
    const attendanceEmployeeNos = uniqueEmployeeNos_(hasAttendanceOverride ? requestedAttendance : (savedAttendance.length ? savedAttendance : inferredAttendance));
    const liveSnapshot = buildDailyCloseSnapshot_(businessDate, preferredSite, {
      closedBy: saved ? saved.closedBy : '',
      closedByName: saved ? saved.closedByName : '',
      closedAt: saved ? saved.closedAt : '',
      includeRooms: false,
      currentRows,
      historyRows,
      attendanceEmployeeNos
    });
    const latestSourceAt = latestRoommaidCloseSourceAt_(currentRows, historyRows);
    const savedHasJournal = Boolean(saved && saved.roommaidCloseJournal);
    const savedJournalSchemaChanged = Boolean(
      savedHasJournal &&
      Number(saved.roommaidCloseJournal.schemaVersion || 0) !== NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION
    );
    const signatureChanged = Boolean(saved && saved.sourceSignature && saved.sourceSignature !== liveSnapshot.sourceSignature);
    const legacyTimestampChanged = Boolean(saved && !saved.sourceSignature && saved.closedAt && latestSourceAt && latestSourceAt > saved.closedAt);
    const isStale = Boolean(saved && (!savedHasJournal || savedJournalSchemaChanged || signatureChanged || legacyTimestampChanged));
    const useSaved = Boolean(saved && !isStale && savedHasJournal && !hasAttendanceOverride);
    const selected = useSaved ? saved : liveSnapshot;
    const journal = selected.roommaidCloseJournal || liveSnapshot.roommaidCloseJournal;
    const baseWarning = journal && journal.initialStatusDetailAvailable
      ? ''
      : '해당 업무일자의 객실현황 업로드가 RC6.4 이전에 적용되어 최초 재고·퇴실의 객실별 상세가 없습니다. 현재 상태를 기준으로 보정 표시됩니다.';

    return {
      ok: true,
      businessDate,
      site: preferredSite,
      sites,
      source: saved ? (isStale ? 'CLOSED_STALE' : 'CLOSED') : 'LIVE',
      isClosed: Boolean(saved),
      isStale,
      closedAt: saved ? String(saved.closedAt || '') : '',
      closedBy: saved ? String(saved.closedByName || saved.closedBy || '') : '',
      latestSourceAt,
      attendanceEmployeeNos: uniqueEmployeeNos_(journal && journal.attendanceEmployeeNos || attendanceEmployeeNos),
      attendanceOptions: buildRoommaidCloseAttendanceOptions_(users, preferredSite, inferredAttendance, journal && journal.attendanceEmployeeNos || attendanceEmployeeNos, employmentIndex),
      journal,
      warning: baseWarning,
      message: saved
        ? (isStale ? '마감 이후 객실 또는 정비실적이 수정되었습니다. 수정 후 재마감이 필요합니다.' : '저장된 마감자료입니다.')
        : '실시간 미마감 자료입니다.'
    };
  });
}

function saveRoommaidCloseJournal(token, payload) { // (룸메이드 마감일지 저장·수정 후 재마감)
  return measureResponse_('saveRoommaidCloseJournal', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('마감할 사업장을 선택하세요.');
    const attendanceEmployeeNos = uniqueEmployeeNos_(safe.attendanceEmployeeNos || []);
    const lock = acquireWriteLock_(30000);
    try {
      const currentRows = readCurrentRowsForClose_(businessDate, site);
      if (!currentRows.length) throw new Error(`${businessDate} ${site} 현재객실현황이 없습니다.`);
      const historyRows = readHistoryRowsForClose_(businessDate, site);
      const result = saveDailyCloseSnapshotForSite_(businessDate, site, user, {
        currentRows,
        historyRows,
        attendanceEmployeeNos
      });
      return {
        ok: true,
        businessDate,
        site,
        closedAt: result.closedAt,
        message: `${businessDate} ${site} 룸메이드 마감일지를 저장했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function resetRoommaidCloseJournal(token, payload) { // (룸메이드 저장 마감자료 초기화)
  return measureResponse_('resetRoommaidCloseJournal', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('초기화할 사업장을 선택하세요.');

    const lock = acquireWriteLock_(30000);
    try {
      const resetAt = nowText_();
      const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const resetCount = markExistingDailyCloseDeleted_(historySheet, businessDate, site, resetAt);
      if (resetCount > 0) {
        const version = reserveDataVersion_({ lockHeld: true });
        publishDataVersion_(version, { domains: ['REPORT'], businessDate, site, lockHeld: true });
      }
      return {
        ok: true,
        businessDate,
        site,
        resetCount,
        resetBy: user.employeeNo,
        resetAt,
        message: resetCount > 0
          ? `${businessDate} ${site} 룸메이드 마감자료를 초기화했습니다. 현재 자료를 확인한 후 다시 마감하세요.`
          : `${businessDate} ${site}에 초기화할 저장 마감자료가 없습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}


function getRoommaidCloseMaintenanceHistory(token, filters) { // (객실·직원별 정비이력 검토 조회)
  return measureResponse_('getRoommaidCloseMaintenanceHistory', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = filters || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    const roomNo = safe.roomNo ? normalizeRoomNo_(safe.roomNo) : '';
    const employeeNo = String(safe.employeeNo || '').trim();
    const unassignedOnly = Boolean(safe.unassignedOnly);
    if (!site) throw new Error('사업장을 선택하세요.');
    if (!roomNo && !employeeNo && !unassignedOnly) throw new Error('객실번호 또는 룸메이드를 선택하거나 정비자 미지정 완료만 조회하세요.');

    const users = getUserIndex_().byEmployeeNo;
    const rawEvents = readRoommaidCloseMaintenanceHistoryRows_(businessDate, site, roomNo);
    let performanceCompletionKeys = new Set();
    let performanceWarning = '';
    try {
      const currentRows = readCurrentRowsForClose_(businessDate, site);
      const liveCurrentRows = latestRoommaidCloseCurrentRows_(currentRows, site);
      const activeHistoryRows = readHistoryRowsForClose_(businessDate, site);
      const master = readRoomMasterIndexForClose_(site);
      const upload = latestUploadSummaryForClose_(activeHistoryRows);
      const initialMap = buildInitialRoomStatusMapForClose_(upload, liveCurrentRows);
      const completionEvents = cleaningCompletionEventsForClose_(activeHistoryRows);
      const workloadHistoryRows = roommaidCloseHistoryAfterLatestUpload_(activeHistoryRows, upload);
      const workloadEvents = buildRoommaidCloseWorkloadEvents_(initialMap, workloadHistoryRows, completionEvents, master, liveCurrentRows, site);
      const maintenanceTypes = buildMaintenanceTypeListForClose_(master);
      const buildings = buildCloseBuildingList_(master, liveCurrentRows);
      const completionSnapshot = buildRoommaidCloseCompletionSnapshot_(
        completionEvents, workloadEvents, master, liveCurrentRows, site, buildings, maintenanceTypes
      );
      performanceCompletionKeys = new Set(completionSnapshot.performanceCompletionKeys || []);
    } catch (error) {
      performanceWarning = `개인실적 반영여부 계산 중 확인 필요: ${error && error.message || error}`;
    }

    const master = readRoomMasterIndexForClose_(site);
    let items = rawEvents
      .filter(event => !employeeNo || roommaidCloseMaintenanceHistoryEmployeeMatches_(event, employeeNo))
      .map(event => buildRoommaidCloseMaintenanceHistoryPublicItem_(event, users, master, performanceCompletionKeys))
      .filter(item => !unassignedOnly || (item.isCompletion && !item.primaryEmployeeNo));

    items.sort((a, b) => Number(a.version || 0) - Number(b.version || 0)
      || String(a.eventAt || '').localeCompare(String(b.eventAt || ''))
      || Number(a.rowNumber || 0) - Number(b.rowNumber || 0));

    const totalCount = items.length;
    const limit = 500;
    if (items.length > limit) items = items.slice(items.length - limit);
    const completionItems = items.filter(item => item.isCompletion);
    return {
      ok: true,
      businessDate,
      site,
      roomNo,
      employeeNo,
      unassignedOnly,
      totalCount,
      resultTruncated: totalCount > items.length,
      activeCompletionCount: completionItems.filter(item => !item.deleted).length,
      includedCompletionCount: completionItems.filter(item => item.performanceIncluded).length,
      canceledCompletionCount: completionItems.filter(item => item.deleted).length,
      unassignedCompletionCount: completionItems.filter(item => !item.primaryEmployeeNo).length,
      warning: performanceWarning,
      items
    };
  });
}

function readRoommaidCloseMaintenanceHistoryRows_(businessDate, site, roomNo) { // (삭제이력 포함 객실 정비 타임라인 읽기)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const dateColumn = headerMap['업무일자'];
  const siteColumn = headerMap['사업장'];
  const roomColumn = headerMap['객실번호'];
  const typeColumn = headerMap['기록구분'];
  if (!dateColumn || !siteColumn || !roomColumn || !typeColumn) {
    throw new Error('업무이력 시트의 업무일자·사업장·객실번호·기록구분 열을 확인하세요.');
  }
  const allowed = new Set([
    NOVA.RECORD_TYPES.CLEANING,
    NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE,
    NOVA.RECORD_TYPES.QM,
    NOVA.RECORD_TYPES.QM_CHECKLIST
  ]);
  const rowCount = lastRow - 1;
  const dates = sheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const sites = sheet.getRange(2, siteColumn, rowCount, 1).getDisplayValues();
  const rooms = sheet.getRange(2, roomColumn, rowCount, 1).getDisplayValues();
  const types = sheet.getRange(2, typeColumn, rowCount, 1).getDisplayValues();
  const rowNumbers = [];
  for (let index = 0; index < rowCount; index += 1) {
    if (String(dates[index][0] || '').trim() !== businessDate) continue;
    if (String(sites[index][0] || '').trim() !== site) continue;
    if (!allowed.has(String(types[index][0] || '').trim())) continue;
    const currentRoomNo = normalizeRoomNo_(rooms[index][0]);
    if (!currentRoomNo) continue;
    if (roomNo && currentRoomNo !== roomNo) continue;
    rowNumbers.push(index + 2);
  }
  if (!rowNumbers.length) return [];

  const result = [];
  const lastColumn = sheet.getLastColumn();
  roommaidCloseGroupConsecutiveRows_(rowNumbers).forEach(group => {
    const values = sheet.getRange(group.start, 1, group.count, lastColumn).getDisplayValues();
    values.forEach((row, offset) => {
      const data = rowObjectFromValues_(row, headerMap);
      const detail = parseHistoryDetailSafe_(data);
      result.push({
        data,
        detail,
        rowNumber: group.start + offset,
        recordId: String(data['기록ID'] || '').trim(),
        recordType: String(data['기록구분'] || '').trim(),
        status: String(data['처리상태'] || '').trim().toUpperCase(),
        action: String(detail.action || data['처리상태'] || '').trim().toUpperCase(),
        roomNo: normalizeRoomNo_(data['객실번호']),
        eventAt: closeHistoryEventAt_(data),
        version: Number(data['변경버전'] || 0),
        deleted: String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y'
      });
    });
  });
  return result;
}

function roommaidCloseMaintenanceHistoryEmployeeMatches_(event, employeeNo) { // (주·보조·초기화 대상 직원 검색)
  const target = String(employeeNo || '').trim();
  if (!target) return true;
  const data = event && event.data || {};
  const detail = event && event.detail || {};
  const values = [
    data['대상사번'], detail.primaryEmployeeNo, detail.secondaryEmployeeNo,
    detail.previousPrimaryEmployeeNo, detail.previousSecondaryEmployeeNo,
    detail.resetBy
  ];
  if (Array.isArray(detail.removedEmployeeNos)) values.push.apply(values, detail.removedEmployeeNos);
  return values.map(value => String(value || '').trim()).includes(target);
}

function buildRoommaidCloseMaintenanceHistoryPublicItem_(event, users, master, performanceCompletionKeys) { // (정비이력 화면 표시용 정리)
  const data = event && event.data || {};
  const detail = event && event.detail || {};
  const status = String(event && event.status || '').trim().toUpperCase();
  const action = String(event && event.action || status).trim().toUpperCase();
  const roomNo = normalizeRoomNo_(event && event.roomNo || data['객실번호']);
  const meta = roomCloseMeta_(master || { byRoomNo: {} }, [], String(data['사업장'] || '').trim(), roomNo);
  const primaryEmployeeNo = String(detail.primaryEmployeeNo || data['대상사번'] || '').trim();
  const secondaryEmployeeNo = String(detail.secondaryEmployeeNo || '').trim();
  const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
  const assignmentType = String(detail.assignmentType || '').trim().toUpperCase();
  const isCompletion = ['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(status);
  const deleted = Boolean(event && event.deleted);
  const recordId = String(event && event.recordId || '').trim();
  const stockReducing = isRoommaidStockReducingCleaningType_(cleaningType);
  let performanceIncluded = false;
  let performanceReason = '';
  if (isCompletion) {
    if (deleted) performanceReason = '청소초기화·보정으로 취소됨';
    else if (!primaryEmployeeNo) performanceReason = '정비자 미지정 · 개인실적 제외';
    else if (!stockReducing || performanceCompletionKeys.has(recordId)) {
      performanceIncluded = true;
      performanceReason = '개인실적 반영';
    } else performanceReason = '유효 정비주기 제외';
  } else if (action === 'CLEANING_RESET') {
    performanceReason = `청소완료 ${Number(detail.removedCompletionCount || 0)}건 초기화`;
  }

  const shares = primaryEmployeeNo
    ? roommaidCloseAssignmentCreditShares_(assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO, primaryEmployeeNo, secondaryEmployeeNo)
    : { primary: 0, secondary: 0 };
  const removedEmployeeNos = Array.isArray(detail.removedEmployeeNos)
    ? uniqueEmployeeNos_(detail.removedEmployeeNos) : [];
  return {
    rowNumber: Number(event && event.rowNumber || 0),
    recordId,
    recordType: String(event && event.recordType || ''),
    status,
    action,
    statusLabel: roommaidCloseMaintenanceHistoryStatusLabel_(action || status),
    eventAt: String(event && event.eventAt || ''),
    version: Number(event && event.version || 0),
    roomNo,
    building: String(meta && meta.building || ''),
    maintenanceType: String(meta && meta.maintenanceType || ''),
    deleted,
    isCompletion,
    primaryEmployeeNo,
    primaryName: roommaidCloseMaintenanceHistoryEmployeeName_(users, primaryEmployeeNo),
    secondaryEmployeeNo,
    secondaryName: roommaidCloseMaintenanceHistoryEmployeeName_(users, secondaryEmployeeNo),
    cleaningType,
    cleaningTypeLabel: roommaidCloseMaintenanceHistoryCleaningTypeLabel_(cleaningType),
    assignmentType,
    assignmentTypeLabel: roommaidCloseMaintenanceHistoryAssignmentTypeLabel_(assignmentType),
    roomStatus: String(detail.roomStatus || '').trim(),
    previousRoomStatus: String(detail.previousRoomStatus || '').trim(),
    sourceRoomStatus: String(detail.sourceRoomStatus || '').trim(),
    primaryCreditShare: Number(shares.primary || 0),
    secondaryCreditShare: Number(shares.secondary || 0),
    performanceIncluded,
    performanceReason,
    registeredBy: String(data['등록사번'] || '').trim(),
    registeredByName: roommaidCloseMaintenanceHistoryEmployeeName_(users, data['등록사번']),
    removedCompletionCount: Number(detail.removedCompletionCount || 0),
    removedEmployeeNos,
    removedEmployeeNames: removedEmployeeNos.map(employeeNo => roommaidCloseMaintenanceHistoryEmployeeName_(users, employeeNo) || employeeNo)
  };
}

function roommaidCloseMaintenanceHistoryEmployeeName_(users, employeeNo) { // (정비이력 직원명)
  const no = String(employeeNo || '').trim();
  if (!no) return '';
  const user = users && users[no];
  return String(user && user.name || no).trim();
}

function roommaidCloseMaintenanceHistoryCleaningTypeLabel_(cleaningType) { // (정비이력 정비유형명)
  const code = normalizeRoommaidCleaningType_(cleaningType || NOVA.CLEANING_TYPES.NORMAL);
  const definition = getRoommaidCleaningTypeDefinitions_().find(item => String(item.code || '').trim().toUpperCase() === code);
  return String(definition && definition.label || code || '-');
}

function roommaidCloseMaintenanceHistoryAssignmentTypeLabel_(assignmentType) { // (정비이력 배정유형명)
  const code = String(assignmentType || '').trim().toUpperCase();
  if (code === 'PAIR') return '2인1조';
  if (code === 'PAIR_TRAINING') return '교육배정';
  if (code === 'SOLO') return '단독';
  return code || '-';
}

function roommaidCloseMaintenanceHistoryStatusLabel_(status) { // (정비이력 처리상태 표시명)
  const code = String(status || '').trim().toUpperCase();
  const labels = {
    ASSIGN_ROOMMAID: '룸메이드 배정',
    AUTO_ASSIGN_ROOMMAID: '자동 배정',
    BULK_ASSIGN_ROOMMAID: '일괄 배정',
    CLEANING_START: '청소 시작',
    CLEANING_COMPLETE: '객실정비 완료',
    ROOMMAID_COMPLETE: '객실정비 완료',
    CLEANING_RESET: '청소 초기화',
    CLEAR_ASSIGNMENT: '배정 초기화',
    REWORK: '재정비',
    CHANGE_ROOM_STATUS: '객실상태 변경',
    QM_ASSIGN: 'QM 배정',
    QM_WAITING: 'QM 대기',
    QM_CHECKING: 'QM 점검중',
    QM_COMPLETED: 'QM 완료',
    PASS: 'QM 합격',
    FAIL: 'QM 불합격'
  };
  return labels[code] || code || '-';
}

function validateRoommaidCloseDuplicateCompletions(token, filters) { // (동일 정비주기 청소완료 중복 검증)
  return measureResponse_('validateRoommaidCloseDuplicateCompletions', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = filters || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('검증할 사업장을 선택하세요.');
    const result = scanRoommaidCloseDuplicateCompletions_(businessDate, site);
    return Object.assign({ ok: true, businessDate, site }, roommaidCloseDuplicateScanResponse_(result));
  });
}

function repairRoommaidCloseDuplicateCompletions(token, payload) { // (확정 중복 청소완료 이력 소프트삭제·보정이력 저장)
  return measureResponse_('repairRoommaidCloseDuplicateCompletions', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('정리할 사업장을 선택하세요.');

    const lock = acquireWriteLock_(30000);
    try {
      // 검증 결과를 클라이언트에서 그대로 신뢰하지 않고 잠금 안에서 다시 계산합니다.
      const scan = scanRoommaidCloseDuplicateCompletions_(businessDate, site);
      const exact = Array.isArray(scan.exact) ? scan.exact : [];
      if (!exact.length) {
        return Object.assign({
          ok: true,
          businessDate,
          site,
          repairedCount: 0,
          message: `${businessDate} ${site}에 자동 정리할 확정 중복 청소완료 이력이 없습니다.`
        }, roommaidCloseDuplicateScanResponse_(scan));
      }

      const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const headerMap = getHeaderMap_(sheet);
      const deletedColumn = headerMap['삭제여부'];
      const updatedColumn = headerMap['수정일시'];
      if (!deletedColumn || !updatedColumn) throw new Error('업무이력 시트의 삭제여부·수정일시 열을 확인하세요.');

      const repairAt = nowText_();
      const duplicateRows = Array.from(new Set(exact.map(item => Number(item.duplicateRowNumber || 0)).filter(value => value >= 2))).sort((a, b) => a - b);
      if (!duplicateRows.length) throw new Error('정리할 중복 업무이력 행을 확인하지 못했습니다.');

      const version = reserveDataVersion_({ lockHeld: true });
      sheet.getRangeList(duplicateRows.map(rowNumber => sheet.getRange(rowNumber, deletedColumn).getA1Notation())).setValue('Y');
      sheet.getRangeList(duplicateRows.map(rowNumber => sheet.getRange(rowNumber, updatedColumn).getA1Notation())).setValue(repairAt);

      const auditRows = exact.map(item => createRowByHeaders_(sheet, {
        '기록ID': `${NOVA.RECORD_TYPES.ROOMMAID_CLOSE_AUDIT}-${Utilities.getUuid()}`,
        '기록구분': NOVA.RECORD_TYPES.ROOMMAID_CLOSE_AUDIT,
        '업무일자': businessDate,
        '사업장': site,
        '객실번호': item.roomNo,
        '대상사번': item.employeeNo || '',
        '처리상태': 'DUPLICATE_CLEANING_COMPLETE_REMOVED',
        '세부내용JSON': JSON.stringify({
          action: 'ROOMMAID_CLOSE_DUPLICATE_REPAIR',
          keptRecordId: item.keptRecordId,
          removedRecordId: item.duplicateRecordId,
          keptRowNumber: item.keptRowNumber,
          removedRowNumber: item.duplicateRowNumber,
          firstCompletedAt: item.firstCompletedAt,
          duplicateCompletedAt: item.duplicateCompletedAt,
          gapSeconds: item.gapSeconds,
          sourceRoomStatus: item.sourceRoomStatus,
          cleaningType: item.cleaningType,
          assignmentType: item.assignmentType,
          primaryEmployeeNo: item.employeeNo,
          secondaryEmployeeNo: item.secondaryEmployeeNo,
          reason: item.reason,
          repairedBy: user.employeeNo,
          repairedAt: repairAt
        }),
        '등록사번': user.employeeNo,
        '등록일시': repairAt,
        '수정일시': repairAt,
        '완료일시': repairAt,
        '변경버전': version,
        '삭제여부': 'N'
      }));
      if (auditRows.length) {
        const startRow = sheet.getLastRow() + 1;
        ensureSheetRowCapacity_(sheet, startRow + auditRows.length - 1);
        sheet.getRange(startRow, 1, auditRows.length, auditRows[0].length).setValues(auditRows);
      }
      SpreadsheetApp.flush();
      publishDataVersion_(version, { domains: ['REPORT'], businessDate, site, lockHeld: true });

      const after = scanRoommaidCloseDuplicateCompletions_(businessDate, site);
      return Object.assign({
        ok: true,
        businessDate,
        site,
        repairedCount: duplicateRows.length,
        repairAt,
        repairBy: user.employeeNo,
        version,
        message: `${businessDate} ${site} 중복 청소완료 이력 ${duplicateRows.length}건을 소프트삭제하고 보정이력을 저장했습니다. 마감자료를 확인한 후 재마감하세요.`
      }, roommaidCloseDuplicateScanResponse_(after));
    } finally {
      lock.releaseLock();
    }
  });
}

function roommaidCloseDuplicateScanResponse_(scan) { // (중복검증 결과의 화면 전달값 제한)
  const safe = scan || {};
  const limit = Number(NOVA_ROOMMAID_CLOSE.DUPLICATE_COMPLETE_RESULT_LIMIT || 200);
  const exact = Array.isArray(safe.exact) ? safe.exact : [];
  const review = Array.isArray(safe.review) ? safe.review : [];
  return {
    exactCount: exact.length,
    reviewCount: review.length,
    exact: exact.slice(0, limit).map(roommaidCloseDuplicatePublicItem_),
    review: review.slice(0, limit).map(roommaidCloseDuplicatePublicItem_),
    resultTruncated: exact.length > limit || review.length > limit
  };
}

function roommaidCloseDuplicatePublicItem_(item) { // (중복검증 화면 표시용 항목)
  const safe = item || {};
  return {
    roomNo: String(safe.roomNo || ''),
    keptRecordId: String(safe.keptRecordId || ''),
    duplicateRecordId: String(safe.duplicateRecordId || ''),
    firstCompletedAt: String(safe.firstCompletedAt || ''),
    duplicateCompletedAt: String(safe.duplicateCompletedAt || ''),
    gapSeconds: Number(safe.gapSeconds || 0),
    employeeNo: String(safe.employeeNo || ''),
    secondaryEmployeeNo: String(safe.secondaryEmployeeNo || ''),
    sourceRoomStatus: String(safe.sourceRoomStatus || ''),
    cleaningType: String(safe.cleaningType || ''),
    assignmentType: String(safe.assignmentType || ''),
    reason: String(safe.reason || '')
  };
}

function scanRoommaidCloseDuplicateCompletions_(businessDate, site) { // (객실별 완료이력 사이 신규 정비주기 존재여부 검사)
  const events = readRoommaidCloseDuplicateScanEvents_(businessDate, site);
  const byRoom = {};
  events.forEach(event => {
    if (!event.roomNo) return;
    if (!byRoom[event.roomNo]) byRoom[event.roomNo] = [];
    byRoom[event.roomNo].push(event);
  });

  const exact = [];
  const review = [];
  Object.keys(byRoom).sort((a, b) => a.localeCompare(b, 'ko')).forEach(roomNo => {
    const roomEvents = byRoom[roomNo].sort(compareRoommaidCloseDuplicateEvents_);
    let keptCompletion = null;
    roomEvents.forEach(event => {
      if (isRoommaidCloseDuplicateCycleBoundary_(event)) {
        keptCompletion = null;
        return;
      }
      if (!isRoommaidCloseCompletionEvent_(event)) return;
      if (!keptCompletion) {
        keptCompletion = event;
        return;
      }

      const firstSignature = roommaidCloseDuplicateCompletionSignature_(keptCompletion);
      const nextSignature = roommaidCloseDuplicateCompletionSignature_(event);
      const sameSignature = firstSignature.key === nextSignature.key;
      const firstMs = roommaidCloseTimestampMs_(keptCompletion.eventAt);
      const duplicateMs = roommaidCloseTimestampMs_(event.eventAt);
      const gapSeconds = Number.isFinite(firstMs) && Number.isFinite(duplicateMs)
        ? Math.round((duplicateMs - firstMs) / 1000)
        : NaN;
      const item = {
        roomNo,
        keptRecordId: keptCompletion.recordId || `ROW-${keptCompletion.rowNumber}`,
        duplicateRecordId: event.recordId || `ROW-${event.rowNumber}`,
        keptRowNumber: keptCompletion.rowNumber,
        duplicateRowNumber: event.rowNumber,
        firstCompletedAt: keptCompletion.eventAt,
        duplicateCompletedAt: event.eventAt,
        gapSeconds: Number.isFinite(gapSeconds) ? gapSeconds : 0,
        employeeNo: nextSignature.primaryEmployeeNo,
        secondaryEmployeeNo: nextSignature.secondaryEmployeeNo,
        sourceRoomStatus: nextSignature.sourceRoomStatus,
        cleaningType: nextSignature.cleaningType,
        assignmentType: nextSignature.assignmentType,
        reason: ''
      };

      if (sameSignature && Number.isFinite(gapSeconds) && gapSeconds >= 0 && gapSeconds <= Number(NOVA_ROOMMAID_CLOSE.DUPLICATE_COMPLETE_WINDOW_SECONDS || 600)) {
        item.reason = `동일 정비주기·동일 담당·동일 정비정보로 ${gapSeconds}초 간격 중복 완료`;
        exact.push(item);
        // 확정 중복은 뒤 기록만 제외하고 최초 정상 완료를 계속 기준으로 유지합니다.
        return;
      }

      item.reason = sameSignature
        ? '동일 정비정보이나 완료 간격이 길거나 시각 확인이 어려워 자동정리 제외'
        : '신규 정비주기 이력 없이 완료정보가 달라 관리자 확인 필요';
      review.push(item);
      keptCompletion = event;
    });
  });
  return { exact, review };
}

function readRoommaidCloseDuplicateScanEvents_(businessDate, site) { // (검증 대상 업무이력 행번호 포함 고속 읽기)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const dateColumn = headerMap['업무일자'];
  const siteColumn = headerMap['사업장'];
  const roomColumn = headerMap['객실번호'];
  const deletedColumn = headerMap['삭제여부'];
  if (!dateColumn || !siteColumn || !roomColumn) throw new Error('업무이력 시트의 업무일자·사업장·객실번호 열을 확인하세요.');

  const rowCount = lastRow - 1;
  const dateValues = sheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const siteValues = sheet.getRange(2, siteColumn, rowCount, 1).getDisplayValues();
  const roomValues = sheet.getRange(2, roomColumn, rowCount, 1).getDisplayValues();
  const deletedValues = deletedColumn
    ? sheet.getRange(2, deletedColumn, rowCount, 1).getDisplayValues()
    : Array.from({ length: rowCount }, () => ['N']);
  const rowNumbers = [];
  for (let index = 0; index < rowCount; index += 1) {
    if (String(dateValues[index][0] || '').trim() !== businessDate) continue;
    if (String(siteValues[index][0] || '').trim() !== site) continue;
    if (!normalizeRoomNo_(roomValues[index][0])) continue;
    if (String(deletedValues[index][0] || 'N').trim().toUpperCase() === 'Y') continue;
    rowNumbers.push(index + 2);
  }
  if (!rowNumbers.length) return [];

  const result = [];
  const lastColumn = sheet.getLastColumn();
  roommaidCloseGroupConsecutiveRows_(rowNumbers).forEach(group => {
    const values = sheet.getRange(group.start, 1, group.count, lastColumn).getDisplayValues();
    values.forEach((row, offset) => {
      const data = rowObjectFromValues_(row, headerMap);
      const recordType = String(data['기록구분'] || '').trim();
      if (![NOVA.RECORD_TYPES.CLEANING, NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE, NOVA.RECORD_TYPES.QM, NOVA.RECORD_TYPES.QM_CHECKLIST].includes(recordType)) return;
      const detail = parseHistoryDetailSafe_(data);
      result.push({
        data,
        detail,
        rowNumber: group.start + offset,
        recordId: String(data['기록ID'] || '').trim(),
        recordType,
        status: String(data['처리상태'] || '').trim().toUpperCase(),
        action: String(detail.action || data['처리상태'] || '').trim().toUpperCase(),
        roomNo: normalizeRoomNo_(data['객실번호']),
        eventAt: closeHistoryEventAt_(data),
        version: Number(data['변경버전'] || 0)
      });
    });
  });
  return result;
}

function roommaidCloseGroupConsecutiveRows_(rowNumbers) { // (검증 대상 연속행 묶음)
  const groups = [];
  (rowNumbers || []).forEach(rowNumber => {
    const last = groups[groups.length - 1];
    if (last && last.start + last.count === rowNumber) last.count += 1;
    else groups.push({ start: rowNumber, count: 1 });
  });
  return groups;
}

function compareRoommaidCloseDuplicateEvents_(a, b) { // (변경버전 우선 업무이력 순서)
  if (a.version > 0 && b.version > 0 && a.version !== b.version) return a.version - b.version;
  return String(a.eventAt || '').localeCompare(String(b.eventAt || '')) || Number(a.rowNumber || 0) - Number(b.rowNumber || 0);
}

function isRoommaidCloseCompletionEvent_(event) { // (청소완료 업무이력 판정)
  return Boolean(event)
    && event.recordType === NOVA.RECORD_TYPES.CLEANING
    && ['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(String(event.status || '').trim().toUpperCase());
}

function isRoommaidCloseDuplicateCycleBoundary_(event) { // (정상 다회 정비를 구분하는 신규 주기 경계)
  if (!event) return false;
  const type = String(event.recordType || '').trim();
  const status = String(event.status || '').trim().toUpperCase();
  const action = String(event.action || '').trim().toUpperCase();
  if (type === NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE) return true;
  if (type === NOVA.RECORD_TYPES.CLEANING && !isRoommaidCloseCompletionEvent_(event)) {
    return ['ASSIGN_ROOMMAID', 'CLEANING_START', 'CLEAR_ASSIGNMENT', 'REWORK'].includes(action || status);
  }
  if (type === NOVA.RECORD_TYPES.QM && (status.includes('REWORK') || action.includes('REWORK'))) return true;
  if (type === NOVA.RECORD_TYPES.QM_CHECKLIST && (status === 'FAIL' || action.includes('REWORK'))) return true;
  return false;
}

function roommaidCloseDuplicateCompletionSignature_(event) { // (동일 완료요청 판정용 정비정보 서명)
  const safe = event || {};
  const detail = safe.detail || {};
  const normalizer = buildRoommaidCloseRoomStatusNormalizer_();
  const sourceRoomStatus = normalizeRoommaidCloseRoomStatus_(detail.sourceRoomStatus || detail.previousRoomStatus || detail.roomStatus, normalizer);
  const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
  const assignmentType = String(detail.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
  const primaryEmployeeNo = String(detail.primaryEmployeeNo || safe.data && safe.data['대상사번'] || '').trim();
  const secondaryEmployeeNo = String(detail.secondaryEmployeeNo || '').trim();
  const creditUnit = Number(detail.creditUnit || getRoommaidCleaningCreditUnit_(cleaningType) || 0);
  return {
    sourceRoomStatus,
    cleaningType,
    assignmentType,
    primaryEmployeeNo,
    secondaryEmployeeNo,
    creditUnit,
    key: [sourceRoomStatus, cleaningType, assignmentType, primaryEmployeeNo, secondaryEmployeeNo, creditUnit].join('|')
  };
}

function roommaidCloseTimestampMs_(value) { // (NOVA 일시 문자열 밀리초 변환)
  const text = String(value || '').trim();
  if (!text) return NaN;
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
  if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]), Number(match[6])).getTime();
  const parsed = new Date(text).getTime();
  return Number.isFinite(parsed) ? parsed : NaN;
}

function buildRoommaidCloseJournal_(businessDate, site, currentRows, historyRows, users, attendanceEmployeeNos) { // (현재객실현황 최신 1행·현재 분류 기준 마감일지 집계)
  const liveCurrentRows = latestRoommaidCloseCurrentRows_(currentRows, site);
  const master = readRoomMasterIndexForClose_(site);
  const upload = latestUploadSummaryForClose_(historyRows);
  const initialMap = buildInitialRoomStatusMapForClose_(upload, liveCurrentRows);
  const maintenanceTypes = buildMaintenanceTypeListForClose_(master);
  const cleaningTypes = getRoommaidCleaningTypeDefinitions_().map(item => ({ code: item.code, label: item.label, creditMultiplier: Number(item.creditMultiplier || 0), stockReducing: item.stockReducing !== false }));
  const employmentIndex = readRoommaidCloseEmploymentIndex_();
  const buildings = buildCloseBuildingList_(master, liveCurrentRows);
  const buildingColumns = buildRoommaidCloseBuildingColumns_(master, buildings, maintenanceTypes);
  const matrices = {
    initialStock: createCloseMatrixSeed_(buildings, maintenanceTypes),
    departures: createCloseMatrixSeed_(buildings, maintenanceTypes),
    completed: createCloseMatrixSeed_(buildings, maintenanceTypes),
    currentStock: createCloseMatrixSeed_(buildings, maintenanceTypes)
  };
  const specialMatrices = {
    initialStock: createRoommaidCloseSpecialSeed_(maintenanceTypes),
    departures: createRoommaidCloseSpecialSeed_(maintenanceTypes),
    completed: createRoommaidCloseSpecialSeed_(maintenanceTypes),
    currentStock: createRoommaidCloseSpecialSeed_(maintenanceTypes)
  };

  // 업로드 기준상태와 실제 객실상태 변경이력으로 정비주기를 구성한다.
  // 완료이력만으로 새 주기를 만들지 않고, 미완료 상태에서 일반↔R/C↔H/U로 바뀌면 같은 주기를 재분류한다.
  const completionEvents = cleaningCompletionEventsForClose_(historyRows);
  const workloadHistoryRows = roommaidCloseHistoryAfterLatestUpload_(historyRows, upload);
  const workloadEvents = buildRoommaidCloseWorkloadEvents_(initialMap, workloadHistoryRows, completionEvents, master, liveCurrentRows, site);

  // 금일퇴실은 현재 퇴실상태를 기준으로 하되, 청소완료 후 새 R/C·H/U가 발생한 정상 다회주기는 앞선 완료주기도 보존한다.
  // 미완료 상태에서 일반↔R/C↔H/U 전환은 기존 workload 1개를 재분류하므로 중복되지 않는다.
  const departureSnapshot = buildRoommaidCloseCurrentDepartureSnapshot_(
    liveCurrentRows, master, site, buildings, maintenanceTypes, workloadEvents
  );
  matrices.departures = departureSnapshot.matrix;
  specialMatrices.departures = departureSnapshot.specialMatrix;

  // 상단 청소완료는 전일재고 + 정상 다회 퇴실주기의 최초 완료를 주기당 최대 1회 집계한다.
  const completionSnapshot = buildRoommaidCloseCompletionSnapshot_(
    completionEvents, workloadEvents, master, liveCurrentRows, site, buildings, maintenanceTypes
  );
  matrices.completed = completionSnapshot.matrix;
  specialMatrices.completed = completionSnapshot.specialMatrix;

  // 개인별 정비실적은 정상적으로 생성된 모든 정비주기의 최초 완료를 인정한다.
  // 상단 객실 청소완료 집계와 분리하여 정상적인 추가 정비주기 실적이 사라지지 않게 한다.
  const validPerformanceCompletionKeys = new Set(completionSnapshot.performanceCompletionKeys || []);
  const performanceCompletionEvents = completionEvents.filter(item => {
    const detail = item && item.detail || {};
    const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
    if (!isRoommaidStockReducingCleaningType_(cleaningType)) return true; // D/S 등 비재고차감 실적은 기존대로 보존
    return validPerformanceCompletionKeys.has(String(item && item.uniqueKey || ''));
  });
  const completionByEmployee = {};
  performanceCompletionEvents.forEach(item => {
    const data = item.data;
    const detail = item.detail;
    const roomNo = String(data['객실번호'] || '').trim();
    const meta = roomCloseMeta_(master, liveCurrentRows, site, roomNo);
    const primaryNo = String(detail.primaryEmployeeNo || data['대상사번'] || '').trim();
    const secondaryNo = String(detail.secondaryEmployeeNo || '').trim();
    const assignmentType = String(detail.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
    const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
    // 정비자가 없는 완료이력은 원본 업무이력에는 보존하되 개인별 정비현황에는 가상 '미지정' 실적으로 만들지 않는다.
    if (!primaryNo) return;
    const shares = roommaidCloseAssignmentCreditShares_(assignmentType, primaryNo, secondaryNo);
    if (primaryNo) {
      if (!completionByEmployee[primaryNo]) completionByEmployee[primaryNo] = createEmployeeTypeSeed_(primaryNo, maintenanceTypes, cleaningTypes);
      incrementEmployeeTypeCount_(completionByEmployee[primaryNo], cleaningType, meta.maintenanceType, shares.primary);
      completionByEmployee[primaryNo].primaryCompleted += 1;
    }
    if (secondaryNo && secondaryNo !== primaryNo) {
      if (!completionByEmployee[secondaryNo]) completionByEmployee[secondaryNo] = createEmployeeTypeSeed_(secondaryNo, maintenanceTypes, cleaningTypes);
      incrementEmployeeTypeCount_(completionByEmployee[secondaryNo], cleaningType, meta.maintenanceType, shares.secondary);
      completionByEmployee[secondaryNo].secondaryParticipation += 1;
    }
  });

  workloadEvents.forEach(event => {
    const bucket = String(event.bucket || 'BUILDING').toUpperCase();
    const special = bucket === 'RC' || bucket === 'HU';
    const increment = (normalMatrix, specialMatrix) => {
      if (special) incrementRoommaidCloseSpecial_(specialMatrix, bucket, event.maintenanceType, 1);
      else incrementCloseMatrix_(normalMatrix, event.building, event.maintenanceType, 1);
    };
    if (event.initialStock && !event.canceled) increment(matrices.initialStock, specialMatrices.initialStock);
  });

  matrices.currentStock = calculateRoommaidCloseRemainingMatrix_(
    matrices.initialStock, matrices.departures, matrices.completed, buildings, maintenanceTypes
  );
  specialMatrices.currentStock = calculateRoommaidCloseRemainingSpecialMatrix_(
    specialMatrices.initialStock, specialMatrices.departures, specialMatrices.completed, maintenanceTypes
  );

  validateRoommaidCloseMatrixBalance_(matrices, specialMatrices, buildings, maintenanceTypes);

  const inferred = inferRoommaidCloseAttendance_(liveCurrentRows, historyRows);
  const attendance = uniqueEmployeeNos_((attendanceEmployeeNos || []).concat(inferred));
  const staffRows = buildRoommaidCloseStaffRows_(attendance, completionByEmployee, users, maintenanceTypes, cleaningTypes, employmentIndex);
  const rows = [
    closeMatrixRow_('INITIAL_STOCK', '전일재고', matrices.initialStock, specialMatrices.initialStock, buildings, maintenanceTypes),
    closeMatrixRow_('DEPARTURES', '금일퇴실', matrices.departures, specialMatrices.departures, buildings, maintenanceTypes),
    closeMatrixRow_('COMPLETED', '청소완료', matrices.completed, specialMatrices.completed, buildings, maintenanceTypes),
    closeMatrixRow_('CURRENT_STOCK', '금일재고', matrices.currentStock, specialMatrices.currentStock, buildings, maintenanceTypes)
  ];
  return {
    schemaVersion: NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION,
    businessDate,
    site,
    buildings,
    buildingColumns,
    maintenanceTypes,
    cleaningTypes,
    reportMaintenanceTypes: NOVA_ROOMMAID_CLOSE.REPORT_MAINTENANCE_TYPES.slice(),
    specialColumnOrder: ['HU', 'RC'],
    conversionGroups: {
      F: NOVA_ROOMMAID_CLOSE.CONVERSION_GROUPS.F.slice(),
      R: NOVA_ROOMMAID_CLOSE.CONVERSION_GROUPS.R.slice()
    },
    staffBlockCount: NOVA_ROOMMAID_CLOSE.REPORT_STAFF_BLOCKS,
    staffRowsPerBlock: NOVA_ROOMMAID_CLOSE.REPORT_STAFF_ROWS_PER_BLOCK,
    matrixRows: rows,
    attendanceEmployeeNos: attendance,
    attendanceCount: attendance.length,
    staffRows,
    temporaryGroups: staffRows.filter(row => row.rowType === 'GROUP'),
    initialStatusDetailAvailable: Boolean(upload.roomStatusDetailAvailable),
    uploadFileName: String(upload.fileName || ''),
    uploadAppliedAt: String(upload.uploadedAt || ''),
    generatedAt: nowText_()
  };
}

function latestRoommaidCloseCurrentRows_(currentRows, site) { // (인디게이터와 동일 기준 현재객실현황 최신 1행 선택)
  const latestByRoom = {};
  (currentRows || []).forEach((data, index) => {
    const roomNo = normalizeRoomNo_(data && data['객실번호']);
    const rowSite = String(data && data['사업장'] || site || '').trim();
    if (!roomNo || (site && rowSite && rowSite !== site)) return;
    const key = `${rowSite || site}|${roomNo}`;
    const candidate = { data, index };
    const current = latestByRoom[key];
    if (!current) {
      latestByRoom[key] = candidate;
      return;
    }
    const leftVersion = Number(candidate.data && candidate.data['마지막변경버전'] || 0);
    const rightVersion = Number(current.data && current.data['마지막변경버전'] || 0);
    if (leftVersion !== rightVersion) {
      if (leftVersion > rightVersion) latestByRoom[key] = candidate;
      return;
    }
    const leftUpdated = String(candidate.data && candidate.data['수정일시'] || '').trim();
    const rightUpdated = String(current.data && current.data['수정일시'] || '').trim();
    if (leftUpdated !== rightUpdated) {
      if (leftUpdated > rightUpdated) latestByRoom[key] = candidate;
      return;
    }
    // readCurrentRowsForClose_는 시트 행 순서대로 읽으므로 같은 버전·시각이면 뒤 행을 최신으로 본다.
    if (candidate.index > current.index) latestByRoom[key] = candidate;
  });
  return Object.values(latestByRoom)
    .sort((a, b) => a.index - b.index)
    .map(item => item.data);
}

function resolveRoommaidCloseVisibleDepartureEvents_(roomNo, currentStatus, workloadEvents) { // (완료 후 추가 R/C·H/U 등 정상 다회 퇴실주기 선별)
  const normalizedRoomNo = normalizeRoomNo_(roomNo);
  const status = String(currentStatus || '').trim().toUpperCase();
  if (!normalizedRoomNo || !NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(status)) {
    return { events: [], currentEvent: null, currentBucket: '' };
  }

  const currentBucket = roommaidCloseSpecialBucket_(status) || 'BUILDING';
  const candidates = (workloadEvents || []).filter(event =>
    event && event.departure && !event.canceled
    && normalizeRoomNo_(event.roomNo) === normalizedRoomNo
  ).sort(compareRoommaidCloseWorkloadEventOrder_);

  // 현재 상태와 같은 버킷의 마지막 주기가 현재 퇴실주기입니다.
  const currentEvent = [...candidates].reverse().find(event =>
    String(event.bucket || 'BUILDING').trim().toUpperCase() === currentBucket
  ) || null;

  const selected = [];
  const seen = new Set();
  const add = event => {
    if (!event || event.canceled) return;
    const key = roommaidCloseWorkloadEventKey_(event);
    if (!key || seen.has(key)) return;
    seen.add(key);
    selected.push(event);
  };

  // 이미 정상 완료된 앞선 퇴실주기는 실제 수행된 별도 정비이므로 보존합니다.
  // 예: 일반퇴실→완료→R/C퇴실이면 일반퇴실 완료주기 + 현재 R/C주기 = 2건입니다.
  candidates.forEach(event => {
    if (event.completed && event.completionItem) add(event);
  });
  add(currentEvent);

  selected.sort(compareRoommaidCloseWorkloadEventOrder_);
  return { events: selected, currentEvent, currentBucket };
}

function buildRoommaidCloseCurrentDepartureSnapshot_(currentRows, master, site, buildings, maintenanceTypes, workloadEvents) { // (현재 퇴실 + 완료 후 추가 특수퇴실의 독립 주기 집계)
  const matrix = createCloseMatrixSeed_(buildings, maintenanceTypes);
  const specialMatrix = createRoommaidCloseSpecialSeed_(maintenanceTypes);
  const statusNormalizer = buildRoommaidCloseRoomStatusNormalizer_();
  const seenRooms = new Set();
  const seenCycles = new Set();
  let departureCycleCount = 0;

  const incrementCycle = (event, fallback) => {
    const roomNo = normalizeRoomNo_(event && event.roomNo || fallback && fallback.roomNo);
    if (!roomNo) return;
    const meta = roomCloseMeta_(master, currentRows, site, roomNo);
    const bucket = String(event && event.bucket || fallback && fallback.bucket || 'BUILDING').trim().toUpperCase();
    const maintenanceType = event && event.maintenanceType || meta.maintenanceType;
    const cycleKey = event ? roommaidCloseWorkloadEventKey_(event) : `${roomNo}|CURRENT|${bucket}`;
    if (!cycleKey || seenCycles.has(cycleKey)) return;
    seenCycles.add(cycleKey);
    departureCycleCount += 1;
    if (bucket === 'RC' || bucket === 'HU') {
      incrementRoommaidCloseSpecial_(specialMatrix, bucket, maintenanceType, 1);
    } else {
      incrementCloseMatrix_(matrix, event && event.building || meta.building, maintenanceType, 1);
    }
  };

  (currentRows || []).forEach(data => {
    const roomNo = normalizeRoomNo_(data && data['객실번호']);
    const rowSite = String(data && data['사업장'] || site || '').trim();
    if (!roomNo || (site && rowSite && rowSite !== site)) return;
    const roomKey = `${rowSite || site}|${roomNo}`;
    if (seenRooms.has(roomKey)) return;

    const status = normalizeRoommaidCloseRoomStatus_(data && data['객실상태'], statusNormalizer);
    if (!NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(status)) return;
    seenRooms.add(roomKey);

    const visible = resolveRoommaidCloseVisibleDepartureEvents_(roomNo, status, workloadEvents);
    visible.events.forEach(event => incrementCycle(event));

    // 전일재고가 완료 전 퇴실상태로 재분류된 것이라면 같은 정비주기이므로 금일퇴실을 추가하지 않는다.
    const openingStockCycle = [...(workloadEvents || [])].reverse().find(event =>
      event && event.initialStock && !event.manualInitialStock && !event.canceled
      && normalizeRoomNo_(event.roomNo) === roomNo
      && String(event.openingStockReclassifiedTo || '').trim().toUpperCase() === status
    ) || null;

    // 이력 누락 등으로 현재 퇴실주기를 workloadEvents에서 찾지 못한 경우에만 현재 객실상태 1건을 보장한다.
    if (!visible.currentEvent && !openingStockCycle) {
      incrementCycle(null, { roomNo, bucket: visible.currentBucket || roommaidCloseSpecialBucket_(status) || 'BUILDING' });
    }
  });

  return {
    matrix,
    specialMatrix,
    roomCount: seenRooms.size,
    departureCycleCount
  };
}


function buildRoommaidCloseCompletionSnapshot_(completionEvents, workloadEvents, master, currentRows, site, buildings, maintenanceTypes) { // (전일재고 + 정상 다회 퇴실주기별 최초 완료 집계)
  const matrix = createCloseMatrixSeed_(buildings, maintenanceTypes);
  const specialMatrix = createRoommaidCloseSpecialSeed_(maintenanceTypes);
  const statusNormalizer = buildRoommaidCloseRoomStatusNormalizer_();
  const eligibleEvents = [];
  const eligibleKeys = new Set();
  const completionKeys = new Set();
  const performanceCompletionKeys = new Set();

  const addEligible = event => {
    if (!event || event.canceled) return;
    const key = roommaidCloseWorkloadEventKey_(event);
    if (!key || eligibleKeys.has(key)) return;
    eligibleKeys.add(key);
    eligibleEvents.push(event);
  };

  // 개인 실적은 정상적으로 생성된 정비주기별 최초 완료를 모두 보존한다.
  (workloadEvents || []).forEach(event => {
    if (!event || event.canceled || !event.completed || !event.completionItem) return;
    const detail = event.completionItem.detail || parseHistoryDetailSafe_(event.completionItem.data || {});
    const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
    if (!isRoommaidStockReducingCleaningType_(cleaningType)) return;
    const key = String(event.completionItem.uniqueKey || '').trim();
    if (key) performanceCompletionKeys.add(key);
  });

  // 전일재고 주기는 완료 여부와 관계없이 마감 상단의 유효 대상에 유지한다.
  (workloadEvents || []).forEach(event => {
    if (event && event.initialStock && !event.canceled) addEligible(event);
  });

  // 현재도 퇴실상태인 객실은 현재 주기뿐 아니라 그 전에 정상 완료된 별도 퇴실주기도 함께 보존한다.
  // 일반퇴실→완료→R/C퇴실→완료는 일반 1건 + R/C 1건의 청소완료로 각각 집계된다.
  (currentRows || []).forEach(data => {
    const roomNo = normalizeRoomNo_(data && data['객실번호']);
    const rowSite = String(data && data['사업장'] || site || '').trim();
    if (!roomNo || (site && rowSite && rowSite !== site)) return;
    const status = normalizeRoommaidCloseRoomStatus_(data && data['객실상태'], statusNormalizer);
    if (!NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(status)) return;

    const visible = resolveRoommaidCloseVisibleDepartureEvents_(roomNo, status, workloadEvents);
    visible.events.forEach(addEligible);
  });

  eligibleEvents.forEach(event => {
    if (!event.completed || !event.completionItem) return;
    const detail = event.completionItem.detail || parseHistoryDetailSafe_(event.completionItem.data || {});
    const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
    if (!isRoommaidStockReducingCleaningType_(cleaningType)) return;

    const bucket = String(event.bucket || 'BUILDING').trim().toUpperCase();
    const meta = roomCloseMeta_(master, currentRows, site, event.roomNo);
    const maintenanceType = event.maintenanceType || meta.maintenanceType;
    if (bucket === 'RC' || bucket === 'HU') {
      incrementRoommaidCloseSpecial_(specialMatrix, bucket, maintenanceType, 1);
    } else {
      incrementCloseMatrix_(matrix, event.building || meta.building, maintenanceType, 1);
    }

    const completionKey = String(event.completionItem.uniqueKey || '').trim();
    if (completionKey) completionKeys.add(completionKey);
  });

  return {
    matrix,
    specialMatrix,
    completionCount: completionKeys.size,
    completionKeys: Array.from(completionKeys),
    performanceCompletionKeys: Array.from(performanceCompletionKeys)
  };
}


function roommaidCloseWorkloadEventKey_(event) { // (정비주기 고유키)
  if (!event) return '';
  return String(event.id || '').trim()
    || [
      normalizeRoomNo_(event.roomNo),
      String(event.bucket || 'BUILDING').trim().toUpperCase(),
      event.initialStock ? 'STOCK' : event.departure ? 'DEPARTURE' : 'OTHER',
      Number(event.startedVersion || 0),
      String(event.startedAt || '')
    ].join('|');
}

function compareRoommaidCloseWorkloadEventOrder_(a, b) { // (정비주기 시작순 정렬)
  const versionDiff = Number(a && (a.startedVersion || a.completedVersion) || 0)
    - Number(b && (b.startedVersion || b.completedVersion) || 0);
  if (versionDiff) return versionDiff;
  const timeDiff = String(a && (a.startedAt || a.completedAt) || '').localeCompare(String(b && (b.startedAt || b.completedAt) || ''));
  if (timeDiff) return timeDiff;
  return String(roommaidCloseWorkloadEventKey_(a)).localeCompare(String(roommaidCloseWorkloadEventKey_(b)));
}

function resolveRoommaidCloseVisibleDepartureCycles_(data, normalizer) { // (인디게이터 현재 객실상태 기준 퇴실 1실 1회 판정)
  const current = normalizeRoommaidCloseRoomStatus_(data && data['객실상태'], normalizer);
  if (!NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(current)) return [];
  return [{ slot: 'CURRENT', status: current, source: 'ROOM_STATUS' }];
}

function buildRoommaidCloseRoomStatusNormalizer_() { // (객실상태 코드·표시명·R/C·H/U 변형 정규화표)
  const map = {};
  const add = (value, code) => {
    const key = roommaidCloseRoomStatusKey_(value);
    const normalizedCode = String(code || '').trim().toUpperCase();
    if (key && normalizedCode) map[key] = normalizedCode;
  };

  [
    'DUE_OUT', 'CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU',
    'STOCK', 'STOCK_RC', 'STOCK_HU', 'VACANT_CLEAN', 'RECHECKIN', 'STAY'
  ].forEach(code => add(code, code));

  const aliases = {
    '퇴실예정': 'DUE_OUT',
    '퇴실': 'CHECKED_OUT',
    '퇴실R/C': 'CHECKED_OUT_RC',
    '퇴실RC': 'CHECKED_OUT_RC',
    '퇴실 R/C': 'CHECKED_OUT_RC',
    '퇴실H/U': 'CHECKED_OUT_HU',
    '퇴실HU': 'CHECKED_OUT_HU',
    '퇴실 H/U': 'CHECKED_OUT_HU',
    '재고': 'STOCK',
    '재고R/C': 'STOCK_RC',
    '재고RC': 'STOCK_RC',
    '재고 R/C': 'STOCK_RC',
    '재고H/U': 'STOCK_HU',
    '재고HU': 'STOCK_HU',
    '재고 H/U': 'STOCK_HU',
    '공실': 'VACANT_CLEAN',
    '공실청소완료': 'VACANT_CLEAN',
    '공실.청소완료': 'VACANT_CLEAN',
    '재입실': 'RECHECKIN',
    '투숙': 'STAY'
  };
  Object.keys(aliases).forEach(label => add(label, aliases[label]));

  try {
    (getCodes_('객실상태') || []).forEach(item => {
      const code = String(item && item.code || '').trim().toUpperCase();
      if (!code) return;
      add(code, code);
      add(item && item.label, code);
      add(item && item.name, code);
      add(item && item.displayName, code);
    });
  } catch (error) {
    // 코드설정 조회 실패 시에도 기본 코드와 업무용 별칭으로 정상 집계한다.
  }
  return map;
}

function normalizeRoommaidCloseRoomStatus_(value, normalizer) { // (객실상태를 NOVA 코드로 변환)
  const raw = String(value || '').trim();
  if (!raw) return '';
  const map = normalizer || buildRoommaidCloseRoomStatusNormalizer_();
  const key = roommaidCloseRoomStatusKey_(raw);
  return String(map[key] || raw).trim().toUpperCase();
}

function roommaidCloseRoomStatusKey_(value) { // (객실상태 비교키 생성)
  let text = String(value || '').trim();
  if (!text) return '';
  try { text = text.normalize('NFKC'); } catch (error) {}
  return text.toUpperCase().replace(/[^0-9A-Z가-힣]/g, '');
}

function roommaidCloseHistoryAfterLatestUpload_(historyRows, upload) { // (최종 업로드 이후 상태변경만 변경버전 우선 선별)
  const rows = historyRows || [];
  const latestUploadRow = rows
    .filter(data => String(data['기록구분'] || '').trim() === NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD)
    .sort((a, b) => {
      const versionDiff = Number(b['변경버전'] || 0) - Number(a['변경버전'] || 0);
      return versionDiff || String(b['등록일시'] || '').localeCompare(String(a['등록일시'] || ''));
    })[0] || null;
  const baselineVersion = Number(latestUploadRow && latestUploadRow['변경버전'] || upload && upload.version || 0);
  const baselineAt = String(latestUploadRow && latestUploadRow['등록일시'] || upload && upload.uploadedAt || '').trim();
  return rows.filter(data => {
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE) return true;
    const version = Number(data['변경버전'] || 0);
    if (baselineVersion > 0 && version > 0) return version > baselineVersion;
    const eventAt = closeHistoryEventAt_(data);
    if (baselineAt && eventAt) return eventAt >= baselineAt;
    return true;
  });
}

function buildRoommaidCloseWorkloadEvents_(initialMap, historyRows, completionEvents, master, currentRows, site) { // (객실별 실제 정비주기·상태재분류 구성)
  const events = [];
  const eventsByRoom = {};
  const activeByRoom = {};
  const stateByRoom = {};
  const statusNormalizer = buildRoommaidCloseRoomStatusNormalizer_();
  let sequenceNo = 0;

  const addEvent = (roomNo, options) => {
    const normalizedRoomNo = normalizeRoomNo_(roomNo);
    if (!normalizedRoomNo) return null;
    const meta = roomCloseMeta_(master, currentRows, site, normalizedRoomNo);
    const event = Object.assign({
      id: `RMC-${normalizedRoomNo}-${++sequenceNo}`,
      roomNo: normalizedRoomNo,
      bucket: 'BUILDING',
      building: meta.building,
      maintenanceType: meta.maintenanceType,
      initialStock: false,
      manualInitialStock: false,
      departure: false,
      completed: false,
      canceled: false,
      sourceStatus: '',
      startedVersion: 0,
      startedAt: ''
    }, options || {});
    events.push(event);
    if (!eventsByRoom[normalizedRoomNo]) eventsByRoom[normalizedRoomNo] = [];
    eventsByRoom[normalizedRoomNo].push(event);
    if (!event.completed && !event.canceled) activeByRoom[normalizedRoomNo] = event;
    return event;
  };

  Object.keys(initialMap || {}).forEach(roomNo => {
    const status = String(initialMap[roomNo] || '').trim().toUpperCase();
    const normalizedRoomNo = normalizeRoomNo_(roomNo);
    if (!normalizedRoomNo) return;
    stateByRoom[normalizedRoomNo] = status;
    const bucket = roommaidCloseSpecialBucket_(status) || 'BUILDING';
    if (NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(status)) {
      addEvent(normalizedRoomNo, { bucket, initialStock: true, sourceStatus: status });
    } else if (NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(status)) {
      addEvent(normalizedRoomNo, { bucket, departure: true, sourceStatus: status });
    }
  });

  const sequence = closeWorkloadHistorySequence_(historyRows, completionEvents);
  sequence.forEach(item => {
    const roomNo = normalizeRoomNo_(item.data && item.data['객실번호']);
    if (!roomNo) return;

    if (item.kind === 'STATUS') {
      const detail = item.detail || {};
      const nextStatus = normalizeRoommaidCloseRoomStatus_(detail.roomStatus, statusNormalizer);
      if (!nextStatus) return;
      const previousStatus = normalizeRoommaidCloseRoomStatus_(detail.previousRoomStatus || stateByRoom[roomNo], statusNormalizer);
      const active = activeByRoom[roomNo] || null;
      const nextBucket = roommaidCloseSpecialBucket_(nextStatus) || 'BUILDING';
      const isDeparture = NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(nextStatus);
      const isManualInitialStock = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(nextStatus)
        && previousStatus === 'VACANT_CLEAN';
      const isOpeningStockReturn = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(nextStatus)
        && ['STAY', 'RECHECKIN'].includes(previousStatus);

      if (isDeparture) {
        // 아직 청소완료되지 않은 재고/퇴실 정비대상에서 일반↔R/C↔H/U 또는 재고→퇴실로 바뀌면
        // 신규 작업을 더하지 않고 같은 정비주기의 최종 분류만 변경한다.
        if (active && !active.completed && !active.canceled && (active.initialStock || active.departure)) {
          const openingInitialStock = Boolean(active.initialStock && !active.manualInitialStock);
          if (openingInitialStock) {
            // 최종 업로드에서 시작한 전일재고는 같은 미완료 정비주기에서 퇴실상태로 바뀌어도
            // 전일재고의 원래 일반/RC/HU 분류를 그대로 유지한다.
            // 현재 퇴실상태는 같은 정비주기의 표시상태로만 기억하고 금일퇴실을 새로 1건 만들지 않는다.
            active.initialStock = true;
            active.departure = false;
            active.openingStockReclassifiedTo = nextStatus;
            active.openingStockReclassifiedVersion = item.version;
            active.openingStockReclassifiedAt = item.eventAt;
          } else {
            // 당일 수동 재고 또는 기존 퇴실주기는 기존 동작대로 최종 퇴실분류를 따른다.
            active.initialStock = false;
            active.manualInitialStock = false;
            active.departure = true;
            active.bucket = nextBucket;
            active.sourceStatus = nextStatus;
            active.reclassifiedVersion = item.version;
            active.reclassifiedAt = item.eventAt;
          }
        } else {
          // 업로드 당시 재고가 아니라 당일 VACANT_CLEAN → STOCK_* 로 생성된 임시 재고가
          // 청소완료 후 STOCK_* → CHECKED_OUT_* 로 전환되면 이전 재고주기를 전일재고에 남기지 않는다.
          // 실제 업로드 원본의 전일재고는 manualInitialStock=false 이므로 이 취소 대상이 아니다.
          if (NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(previousStatus)) {
            const priorManualStock = [...(eventsByRoom[roomNo] || [])].reverse().find(event =>
              event && event.manualInitialStock && event.initialStock && !event.canceled
              && normalizeRoommaidCloseRoomStatus_(event.sourceStatus, statusNormalizer) === previousStatus
            ) || null;
            if (priorManualStock) {
              priorManualStock.canceled = true;
              priorManualStock.cancelReason = 'MANUAL_STOCK_SUPERSEDED_BY_DEPARTURE';
              priorManualStock.supersededVersion = item.version;
              priorManualStock.supersededAt = item.eventAt;
            }
          }
          addEvent(roomNo, {
            bucket: nextBucket,
            departure: true,
            sourceStatus: nextStatus,
            startedVersion: item.version,
            startedAt: item.eventAt
          });
        }
      } else if (isOpeningStockReturn) {
        // 업로드 당시 전일재고가 STAY/RECHECKIN으로 잠시 취소된 뒤
        // 같은 STOCK/RC/HU 상태로 돌아오면 새 작업을 만들지 않고 원래 전일재고 주기를 복구한다.
        // 예: STOCK -> STAY -> STOCK -> 청소완료.
        const restoredOpeningStock = [...(eventsByRoom[roomNo] || [])].reverse().find(event =>
          event && event.initialStock && !event.manualInitialStock
          && !event.completed && event.canceled
          && ['STAY', 'RECHECKIN'].includes(String(event.cancelReason || '').trim().toUpperCase())
          && normalizeRoommaidCloseRoomStatus_(event.sourceStatus, statusNormalizer) === nextStatus
        ) || null;
        if (restoredOpeningStock) {
          restoredOpeningStock.canceled = false;
          restoredOpeningStock.cancelReason = '';
          restoredOpeningStock.restoredAfterStatus = previousStatus;
          restoredOpeningStock.restoredVersion = item.version;
          restoredOpeningStock.restoredAt = item.eventAt;
          activeByRoom[roomNo] = restoredOpeningStock;
        }
      } else if (isManualInitialStock) {
        if (active && !active.completed && !active.canceled && (active.initialStock || active.departure)) {
          active.initialStock = true;
          active.manualInitialStock = true;
          active.departure = false;
          active.bucket = nextBucket;
          active.sourceStatus = nextStatus;
          active.reclassifiedVersion = item.version;
          active.reclassifiedAt = item.eventAt;
        } else {
          addEvent(roomNo, {
            bucket: nextBucket,
            initialStock: true,
            manualInitialStock: true,
            sourceStatus: nextStatus,
            startedVersion: item.version,
            startedAt: item.eventAt
          });
        }
      } else if (nextStatus === 'VACANT_CLEAN') {
        if (active && (active.departure || active.initialStock) && !active.completed && !active.canceled) {
          active.canceled = true;
          active.cancelReason = 'VACANT_CORRECTION';
        }
        activeByRoom[roomNo] = null;
      } else if (['STAY', 'RECHECKIN'].includes(nextStatus)) {
        if (active && (active.departure || active.initialStock) && !active.completed && !active.canceled) {
          active.canceled = true;
          active.cancelReason = nextStatus;
        }
        activeByRoom[roomNo] = null;
      }
      stateByRoom[roomNo] = nextStatus || previousStatus;
      return;
    }

    if (item.kind === 'COMPLETE') {
      const detail = item.detail || {};
      const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
      if (!isRoommaidStockReducingCleaningType_(cleaningType)) return;

      const sourceStatus = normalizeRoommaidCloseRoomStatus_(
        detail.sourceRoomStatus || detail.previousRoomStatus || stateByRoom[roomNo] || '',
        statusNormalizer
      );
      const sourceRecognized = isNovaRoomCleaningTargetStatus_(sourceStatus);
      const desiredBucket = roommaidCloseSpecialBucket_(sourceStatus) || 'BUILDING';
      const roomEvents = eventsByRoom[roomNo] || [];

      // 최초 완료는 현재 열린 정비주기에만 연결한다. 이미 완료된 주기에 들어온 추가 완료이력은 중복으로 무시한다.
      let target = [...roomEvents].reverse().find(event =>
        !event.completed && !event.canceled
        && (!sourceRecognized || String(event.bucket || 'BUILDING').trim().toUpperCase() === desiredBucket)
      ) || null;
      // 전일재고가 완료 전 퇴실/RC/HU 상태로 바뀐 경우에도 같은 정비주기의 완료로 연결한다.
      // 이때 전일재고의 원래 분류는 유지하여 전일재고 숫자와 완료 차감 기준이 서로 어긋나지 않게 한다.
      if (!target && sourceRecognized) {
        target = [...roomEvents].reverse().find(event =>
          !event.completed && !event.canceled && event.initialStock && !event.manualInitialStock
          && String(event.openingStockReclassifiedTo || '').trim().toUpperCase() === sourceStatus
        ) || null;
      }
      if (!target && !sourceRecognized) {
        target = [...roomEvents].reverse().find(event => !event.completed && !event.canceled) || null;
      }

      if (target) {
        target.completed = true;
        target.completedVersion = item.version;
        target.completedAt = item.eventAt;
        target.completionRecordId = String(item.data['기록ID'] || '');
        target.completionItem = item;
        if (activeByRoom[roomNo] === target) activeByRoom[roomNo] = null;
      }
      stateByRoom[roomNo] = normalizeRoommaidCloseRoomStatus_(detail.roomStatus || stateByRoom[roomNo] || '', statusNormalizer);
    }
  });

  return events;
}

function closeWorkloadHistorySequence_(historyRows, completionEvents) { // (객실상태변경·정비완료 시간순 배열)
  const sequence = [];
  (historyRows || []).forEach((data, index) => {
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE) return;
    const detail = parseHistoryDetailSafe_(data);
    const roomStatus = String(detail.roomStatus || '').trim().toUpperCase();
    if (!roomStatus) return;
    sequence.push({
      kind: 'STATUS', data, detail, index,
      version: Number(data['변경버전'] || 0),
      eventAt: closeHistoryEventAt_(data)
    });
  });
  (completionEvents || []).forEach((item, index) => {
    sequence.push({
      kind: 'COMPLETE', data: item.data, detail: item.detail, index: 1000000 + index,
      version: item.version,
      eventAt: item.eventAt,
      uniqueKey: item.uniqueKey
    });
  });
  return sequence.sort((a, b) => {
    if (a.version > 0 && b.version > 0 && a.version !== b.version) return a.version - b.version;
    const timeCompare = String(a.eventAt || '').localeCompare(String(b.eventAt || ''));
    return timeCompare || a.index - b.index;
  });
}

function closeHistoryEventAt_(data) { // (마감 집계용 이력시각)
  return String(data && (data['완료일시'] || data['처리시작일시'] || data['수정일시'] || data['등록일시']) || '').trim();
}


function readRoomMasterIndexForClose_(site) { // (사업장 객실마스터 동별 정비타입 인덱스)
  const sheet = getRequiredSheet_(NOVA.SHEETS.ROOMS);
  const headerMap = getHeaderMap_(sheet);
  const byRoomNo = {};
  const maintenanceTypes = new Set();
  const buildings = new Set();
  const buildingTypes = {};
  if (sheet.getLastRow() >= 2) {
    const values = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getDisplayValues();
    values.forEach(row => {
      const data = rowObjectFromValues_(row, headerMap);
      const roomSite = String(data['사업장'] || '').trim();
      const enabled = String(data['사용여부'] || 'Y').trim().toUpperCase();
      if (roomSite !== site || ['N', '미사용', '사용안함'].includes(enabled)) return;
      const roomNo = normalizeRoomNo_(data['객실번호']);
      if (!roomNo) return;
      const maintenanceType = normalizeMaintenanceTypeForClose_(data['정비타입']);
      const building = normalizeRoomBuilding_(data['동'], roomNo) || '미지정';
      byRoomNo[roomNo] = { roomNo, site: roomSite, building, maintenanceType };
      maintenanceTypes.add(maintenanceType);
      buildings.add(building);
      if (!buildingTypes[building]) buildingTypes[building] = new Set();
      buildingTypes[building].add(maintenanceType);
    });
  }
  const normalizedBuildingTypes = {};
  Object.keys(buildingTypes).forEach(building => {
    normalizedBuildingTypes[building] = Array.from(buildingTypes[building]);
  });
  return {
    byRoomNo,
    maintenanceTypes: Array.from(maintenanceTypes),
    buildings: Array.from(buildings),
    buildingTypes: normalizedBuildingTypes
  };
}

function buildInitialRoomStatusMapForClose_(upload, currentRows) { // (최초 업로드 객실상태 상세·자동 공실 객실 복원)
  const result = {};
  const normalizer = buildRoommaidCloseRoomStatusNormalizer_();
  const roomsByStatus = upload && upload.roomsByStatus && typeof upload.roomsByStatus === 'object' ? upload.roomsByStatus : {};
  Object.keys(roomsByStatus).forEach(status => {
    const normalizedStatus = normalizeRoommaidCloseRoomStatus_(status, normalizer);
    (Array.isArray(roomsByStatus[status]) ? roomsByStatus[status] : []).forEach(roomNo => {
      const normalized = normalizeRoomNo_(roomNo);
      if (normalized) result[normalized] = normalizedStatus;
    });
  });
  if (Object.keys(result).length) {
    // 객실업로드는 원본 상태 시트에 없는 객실을 VACANT_CLEAN으로 생성합니다.
    // roomsByStatus에는 원본에 직접 등장한 객실만 있으므로 누락 객실을 업로드 당시 공실로 복원합니다.
    (currentRows || []).forEach(data => {
      const roomNo = normalizeRoomNo_(data['객실번호']);
      if (roomNo && !Object.prototype.hasOwnProperty.call(result, roomNo)) result[roomNo] = 'VACANT_CLEAN';
    });
    return result;
  }
  // RC6.4 이전 업로드는 객실별 원본 상태가 없으므로 현재 객실상태로 보정합니다.
  (currentRows || []).forEach(data => {
    const roomNo = normalizeRoomNo_(data['객실번호']);
    if (roomNo) result[roomNo] = normalizeRoommaidCloseRoomStatus_(data['객실상태'], normalizer);
  });
  return result;
}

function cleaningCompletionEventsForClose_(historyRows) { // (같은 객실 다회 정비완료 기록 보존)
  const result = [];
  const seen = new Set();
  (historyRows || []).forEach((data, index) => {
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.CLEANING) return;
    const status = String(data['처리상태'] || '').trim().toUpperCase();
    if (!['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(status)) return;
    const roomNo = normalizeRoomNo_(data['객실번호']);
    if (!roomNo) return;
    const recordId = String(data['기록ID'] || '').trim();
    const eventAt = closeHistoryEventAt_(data);
    const uniqueKey = recordId || `${String(data['사업장'] || '').trim()}|${roomNo}|${status}|${eventAt}|${index}`;
    if (seen.has(uniqueKey)) return;
    seen.add(uniqueKey);
    result.push({
      data,
      detail: parseHistoryDetailSafe_(data),
      eventAt,
      version: Number(data['변경버전'] || 0),
      index,
      uniqueKey
    });
  });
  return result.sort((a, b) => {
    if (a.version > 0 && b.version > 0 && a.version !== b.version) return a.version - b.version;
    return String(a.eventAt || '').localeCompare(String(b.eventAt || '')) || a.index - b.index;
  });
}

function latestCleaningCompletionsForClose_(historyRows) { // (호환용: 모든 고유 정비완료 기록 인덱스)
  const result = {};
  cleaningCompletionEventsForClose_(historyRows).forEach((item, index) => {
    result[item.uniqueKey || `COMPLETE-${index}`] = item;
  });
  return result;
}


function inferRoommaidCloseAttendance_(currentRows, historyRows) { // (배정·완료기록 기반 출근인원 자동선택)
  const result = [];
  (currentRows || []).forEach(data => {
    result.push(String(data['룸메이드사번'] || '').trim());
    result.push(String(data['보조룸메이드사번'] || '').trim());
  });
  Object.values(latestCleaningCompletionsForClose_(historyRows)).forEach(item => {
    const detail = parseHistoryDetailSafe_(item.data);
    result.push(String(detail.primaryEmployeeNo || item.data['대상사번'] || '').trim());
    result.push(String(detail.secondaryEmployeeNo || '').trim());
  });
  return uniqueEmployeeNos_(result);
}

function buildRoommaidCloseAttendanceOptions_(users, site, inferred, selected, employmentIndex) { // (출근인원 선택 목록·채용구분 표시)
  const inferredSet = new Set(uniqueEmployeeNos_(inferred));
  const selectedSet = new Set(uniqueEmployeeNos_(selected));
  const employment = employmentIndex || readRoommaidCloseEmploymentIndex_();
  return Object.values(users || {})
    .filter(user => user && user.enabled && String(user.role || '').trim().toUpperCase() === 'ROOMMAID')
    .filter(user => !site || !user.defaultSite || user.defaultSite === site || inferredSet.has(user.employeeNo) || selectedSet.has(user.employeeNo))
    .map(user => ({
      employeeNo: user.employeeNo,
      name: user.name,
      job: user.job,
      site: user.defaultSite,
      groupLabel: resolveRoommaidCloseWorkerGroup_(user, employment[user.employeeNo]).displayLabel,
      inferred: inferredSet.has(user.employeeNo),
      selected: selectedSet.has(user.employeeNo)
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'ko') || a.employeeNo.localeCompare(b.employeeNo));
}

function buildRoommaidCloseStaffRows_(attendance, completionByEmployee, users, maintenanceTypes, cleaningTypes, employmentIndex) { // (정규직 개인·아르바이트 통합·외주업체별 집계)
  const individualRows = [];
  const groups = {};
  const definitions = cleaningTypes || getRoommaidCleaningTypeDefinitions_();
  const employment = employmentIndex || readRoommaidCloseEmploymentIndex_();
  uniqueEmployeeNos_((attendance || []).concat(Object.keys(completionByEmployee || {}))).forEach(employeeNo => {
    const user = users[employeeNo] || { employeeNo, name: employeeNo, job: '', note: '' };
    const stats = completionByEmployee[employeeNo] || createEmployeeTypeSeed_(employeeNo, maintenanceTypes, definitions);
    const group = resolveRoommaidCloseWorkerGroup_(user, employment[employeeNo]);
    if (group.code) {
      if (!groups[group.code]) groups[group.code] = {
        rowType: 'GROUP', groupCode: group.code, employeeNo: '', name: group.label, job: group.jobLabel,
        memberEmployeeNos: [], memberNames: [],
        cleaningTypeCounts: createRoommaidCloseCleaningTypeSeed_(maintenanceTypes, definitions),
        primaryCompleted: 0, secondaryParticipation: 0
      };
      const row = groups[group.code];
      row.memberEmployeeNos.push(employeeNo);
      row.memberNames.push(user.name || employeeNo);
      addRoommaidCloseCleaningTypeCounts_(row.cleaningTypeCounts, stats.cleaningTypeCounts, maintenanceTypes, definitions);
      row.primaryCompleted += Number(stats.primaryCompleted || 0);
      row.secondaryParticipation += Number(stats.secondaryParticipation || 0);
      return;
    }
    const cleaningTypeCounts = cloneRoommaidCloseCleaningTypeCounts_(stats.cleaningTypeCounts, maintenanceTypes, definitions);
    individualRows.push({
      rowType: 'PERSON', groupCode: '', employeeNo,
      name: user.name || employeeNo, job: user.job || '',
      memberEmployeeNos: [employeeNo], memberNames: [user.name || employeeNo],
      cleaningTypeCounts,
      primaryCompleted: Number(stats.primaryCompleted || 0),
      secondaryParticipation: Number(stats.secondaryParticipation || 0)
    });
  });
  return individualRows.sort((a, b) => a.name.localeCompare(b.name, 'ko'))
    .concat(Object.values(groups).sort(compareRoommaidCloseEmploymentGroups_))
    .map((row, index) => {
      const cleaningTypeCounts = cloneRoommaidCloseCleaningTypeCounts_(row.cleaningTypeCounts, maintenanceTypes, definitions);
      const cleaningTypeTotals = {};
      definitions.forEach(definition => {
        cleaningTypeTotals[definition.code] = sumTypeCounts_(cleaningTypeCounts[definition.code], maintenanceTypes);
      });
      const stockReducingCounts = buildRoommaidCloseStockReducingTypeCounts_(cleaningTypeCounts, maintenanceTypes, definitions);
      return Object.assign({ sequence: index + 1 }, row, {
        cleaningTypeCounts,
        cleaningTypeTotals,
        normal: stockReducingCounts,
        ds: cleaningTypeCounts[NOVA.CLEANING_TYPES.DS],
        normalTotal: sumTypeCounts_(stockReducingCounts, maintenanceTypes),
        dsTotal: Number(cleaningTypeTotals[NOVA.CLEANING_TYPES.DS] || 0)
      });
    });
}

function buildRoommaidCloseStockReducingTypeCounts_(cleaningTypeCounts, maintenanceTypes, cleaningTypes) { // (개인표 정비열: 재고차감 정비유형 통합)
  const result = zeroTypeCounts_(maintenanceTypes);
  (cleaningTypes || getRoommaidCleaningTypeDefinitions_()).forEach(definition => {
    if (definition.stockReducing === false) return;
    addTypeCounts_(result, cleaningTypeCounts && cleaningTypeCounts[definition.code], maintenanceTypes);
  });
  return result;
}

function compareRoommaidCloseEmploymentGroups_(a, b) { // (아르바이트 후 외주업체명 순서)
  const aPartTime = String(a && a.groupCode || '') === 'EMPLOYMENT_PART_TIME';
  const bPartTime = String(b && b.groupCode || '') === 'EMPLOYMENT_PART_TIME';
  if (aPartTime !== bPartTime) return aPartTime ? -1 : 1;
  return String(a && a.name || '').localeCompare(String(b && b.name || ''), 'ko');
}

function resolveRoommaidCloseWorkerGroup_(user, storedEmploymentType) { // (채용구분 기준 마감일지 집계행 분류)
  const employment = parseRoommaidCloseEmploymentType_(storedEmploymentType, user);
  if (employment.category === '아르바이트') {
    return { code: 'EMPLOYMENT_PART_TIME', label: '아르바이트', jobLabel: '아르바이트', displayLabel: '아르바이트' };
  }
  if (employment.category === '외주업체' && employment.vendor) {
    return {
      code: `EMPLOYMENT_OUTSOURCE:${employment.vendor}`,
      label: employment.vendor,
      jobLabel: '외주업체',
      displayLabel: `외주업체: ${employment.vendor}`
    };
  }
  return { code: '', label: '', jobLabel: '', displayLabel: '정규직' };
}

function readRoommaidCloseEmploymentIndex_() { // (사용자계정 채용구분 인덱스)
  const result = {};
  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  const headerMap = getHeaderMap_(sheet);
  const employeeNoColumn = headerMap['사번'];
  const employmentColumn = headerMap['채용구분'];
  if (!employeeNoColumn || sheet.getLastRow() < 2) return result;
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getDisplayValues();
  rows.forEach(row => {
    const employeeNo = String(row[employeeNoColumn - 1] || '').trim();
    if (!employeeNo) return;
    result[employeeNo] = employmentColumn ? String(row[employmentColumn - 1] || '').trim() : '';
  });
  return result;
}

function parseRoommaidCloseEmploymentType_(value, user) { // (채용구분 해석·기존 일용표기 호환)
  const raw = String(value || '').trim();
  if (raw === '아르바이트') return { category: '아르바이트', vendor: '' };
  if (raw === '정규직') return { category: '정규직', vendor: '' };
  const outsource = raw.match(/^외주업체\s*[:：\-]?\s*(.*)$/i);
  if (outsource) return { category: '외주업체', vendor: String(outsource[1] || '').trim() };

  const text = [user && user.name, user && user.job, user && user.note].map(item => String(item || '').trim()).join(' ').toLowerCase();
  if (text.includes('아르바이트') || text.includes('알바')) return { category: '아르바이트', vendor: '' };
  const legacy = NOVA_ROOMMAID_CLOSE.TEMP_GROUPS.find(group => group.tokens.some(token => text.includes(String(token).toLowerCase())));
  if (legacy) {
    const vendorMatch = String(legacy.label || '').match(/\(([^)]+)\)/);
    return { category: '외주업체', vendor: vendorMatch ? vendorMatch[1] : String(legacy.label || '').replace(/^일용\s*/, '') };
  }
  return { category: '정규직', vendor: '' };
}

function roomCloseMeta_(master, currentRows, site, roomNo) { // (객실 동·정비타입 조회)
  const normalized = normalizeRoomNo_(roomNo);
  if (master.byRoomNo[normalized]) return master.byRoomNo[normalized];
  const current = (currentRows || []).find(row => normalizeRoomNo_(row['객실번호']) === normalized) || {};
  return {
    roomNo: normalized,
    site,
    building: normalizeRoomBuilding_(current['동'], normalized) || '미지정',
    maintenanceType: '미지정'
  };
}

function buildMaintenanceTypeListForClose_(master) { // (F/T/R/G 우선 정비타입 목록)
  const values = Array.from(new Set((master.maintenanceTypes || []).map(normalizeMaintenanceTypeForClose_).filter(Boolean)));
  const defaults = NOVA_ROOMMAID_CLOSE.DEFAULT_MAINTENANCE_TYPES.slice();
  const extras = values.filter(code => !NOVA_ROOMMAID_CLOSE.DEFAULT_MAINTENANCE_TYPES.includes(code)).sort((a, b) => a.localeCompare(b, 'ko'));
  return defaults.concat(extras);
}

function buildCloseBuildingList_(master, currentRows) { // (1~9동 우선 동 목록 정렬)
  const values = new Set(master.buildings || []);
  (currentRows || []).forEach(row => values.add(normalizeRoomBuilding_(row['동'], row['객실번호']) || '미지정'));
  const hasNumericBuilding = Array.from(values).some(value => /^[1-9]동$/.test(String(value || '').trim()));
  if (hasNumericBuilding) {
    for (let buildingNo = 1; buildingNo <= 9; buildingNo += 1) values.add(`${buildingNo}동`);
  }
  return Array.from(values).filter(Boolean).sort(compareDailyCloseBuilding_);
}

function buildRoommaidCloseBuildingColumns_(master, buildings, maintenanceTypes) { // (첨부 양식형 동별 실제 타입 열)
  const typeOrder = maintenanceTypes || NOVA_ROOMMAID_CLOSE.DEFAULT_MAINTENANCE_TYPES;
  return (buildings || []).map(building => {
    const actual = Array.from(new Set((master.buildingTypes && master.buildingTypes[building] || [])
      .map(normalizeMaintenanceTypeForClose_).filter(Boolean)));
    actual.sort((a, b) => {
      const ai = typeOrder.indexOf(a);
      const bi = typeOrder.indexOf(b);
      if (ai !== bi) return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi);
      return a.localeCompare(b, 'ko');
    });
    return { building, types: actual.length ? actual : [''] };
  });
}

function createRoommaidCloseSpecialSeed_(maintenanceTypes) { // (R/C·H/U 타입별 초기값)
  return {
    RC: zeroTypeCounts_(maintenanceTypes),
    HU: zeroTypeCounts_(maintenanceTypes)
  };
}

function roommaidCloseSpecialBucket_(roomStatus) { // (객실상태 R/C·H/U 분류)
  const status = String(roomStatus || '').trim().toUpperCase();
  if (['STOCK_RC', 'CHECKED_OUT_RC'].includes(status)) return 'RC';
  if (['STOCK_HU', 'CHECKED_OUT_HU'].includes(status)) return 'HU';
  return '';
}

function incrementRoommaidCloseSpecial_(specialMatrix, bucket, maintenanceType, amount) { // (H/U·R/C 수량 증가)
  if (!specialMatrix || !specialMatrix[bucket]) return;
  const type = normalizeMaintenanceTypeForClose_(maintenanceType);
  specialMatrix[bucket][type] = Number(specialMatrix[bucket][type] || 0) + Number(amount || 0);
}

function normalizeMaintenanceTypeForClose_(value) { // (객실 정비타입 표기 정리)
  const text = String(value || '').trim().toUpperCase();
  return text || '미지정';
}

function createCloseMatrixSeed_(buildings, maintenanceTypes) { // (동×정비타입 행렬 초기화)
  const cells = {};
  (buildings || []).forEach(building => { cells[building] = zeroTypeCounts_(maintenanceTypes); });
  return { cells };
}

function calculateRoommaidCloseRemainingMatrix_(initialMatrix, departureMatrix, completedMatrix, buildings, maintenanceTypes) { // (동별 금일재고 산식 계산)
  const result = createCloseMatrixSeed_(buildings, maintenanceTypes);
  (buildings || []).forEach(building => {
    (maintenanceTypes || []).forEach(type => {
      const initial = Number(initialMatrix && initialMatrix.cells && initialMatrix.cells[building] && initialMatrix.cells[building][type] || 0);
      const departures = Number(departureMatrix && departureMatrix.cells && departureMatrix.cells[building] && departureMatrix.cells[building][type] || 0);
      const completed = Number(completedMatrix && completedMatrix.cells && completedMatrix.cells[building] && completedMatrix.cells[building][type] || 0);
      // 음수를 0으로 숨기지 않는다. 바로 아래 자체검증에서 초과 완료를 오류로 차단한다.
      result.cells[building][type] = initial + departures - completed;
    });
  });
  return result;
}

function calculateRoommaidCloseRemainingSpecialMatrix_(initialMatrix, departureMatrix, completedMatrix, maintenanceTypes) { // (R/C·H/U 금일재고 산식 계산)
  const result = createRoommaidCloseSpecialSeed_(maintenanceTypes);
  ['RC', 'HU'].forEach(bucket => {
    (maintenanceTypes || []).forEach(type => {
      const initial = Number(initialMatrix && initialMatrix[bucket] && initialMatrix[bucket][type] || 0);
      const departures = Number(departureMatrix && departureMatrix[bucket] && departureMatrix[bucket][type] || 0);
      const completed = Number(completedMatrix && completedMatrix[bucket] && completedMatrix[bucket][type] || 0);
      // 음수를 0으로 숨기지 않는다. 초과 완료는 마감 오류로 처리한다.
      result[bucket][type] = initial + departures - completed;
    });
  });
  return result;
}

function validateRoommaidCloseMatrixBalance_(matrices, specialMatrices, buildings, maintenanceTypes) { // (정비대상·청소완료·금일재고 강제정합 검증)
  const issues = [];
  const inspect = (label, initial, departures, completed, current) => {
    const available = initial + departures;
    const expected = available - completed;
    if (completed > available) {
      issues.push(`${label}: 정비대상 ${available}(${initial}+${departures}) < 청소완료 ${completed}`);
      return;
    }
    if (expected < 0) {
      issues.push(`${label}: 금일재고 음수 ${expected}`);
      return;
    }
    if (current !== expected) issues.push(`${label}: ${initial}+${departures}-${completed}=${expected}, 표시값 ${current}`);
  };

  (buildings || []).forEach(building => {
    (maintenanceTypes || []).forEach(type => {
      const initial = Number(matrices.initialStock && matrices.initialStock.cells && matrices.initialStock.cells[building] && matrices.initialStock.cells[building][type] || 0);
      const departures = Number(matrices.departures && matrices.departures.cells && matrices.departures.cells[building] && matrices.departures.cells[building][type] || 0);
      const completed = Number(matrices.completed && matrices.completed.cells && matrices.completed.cells[building] && matrices.completed.cells[building][type] || 0);
      const current = Number(matrices.currentStock && matrices.currentStock.cells && matrices.currentStock.cells[building] && matrices.currentStock.cells[building][type] || 0);
      inspect(`${building}/${type}`, initial, departures, completed, current);
    });
  });

  ['RC', 'HU'].forEach(bucket => {
    (maintenanceTypes || []).forEach(type => {
      const initial = Number(specialMatrices.initialStock && specialMatrices.initialStock[bucket] && specialMatrices.initialStock[bucket][type] || 0);
      const departures = Number(specialMatrices.departures && specialMatrices.departures[bucket] && specialMatrices.departures[bucket][type] || 0);
      const completed = Number(specialMatrices.completed && specialMatrices.completed[bucket] && specialMatrices.completed[bucket][type] || 0);
      const current = Number(specialMatrices.currentStock && specialMatrices.currentStock[bucket] && specialMatrices.currentStock[bucket][type] || 0);
      inspect(`${bucket}/${type}`, initial, departures, completed, current);
    });
  });

  if (issues.length) {
    throw new Error(`룸메이드 마감 정비현황 정합 검증 실패: ${issues.slice(0, 8).join(' / ')}`);
  }
  return true;
}

function incrementCloseMatrix_(matrix, building, maintenanceType, amount) { // (행렬 수량 증가)
  const b = String(building || '미지정');
  const t = normalizeMaintenanceTypeForClose_(maintenanceType);
  if (!matrix.cells[b]) matrix.cells[b] = {};
  matrix.cells[b][t] = Number(matrix.cells[b][t] || 0) + Number(amount || 0);
}

function closeMatrixRow_(code, label, matrix, specialMatrix, buildings, maintenanceTypes) { // (첨부 양식형 정비현황 행)
  const totals = zeroTypeCounts_(maintenanceTypes);
  const specialCells = {
    RC: cloneTypeCounts_(specialMatrix && specialMatrix.RC, maintenanceTypes),
    HU: cloneTypeCounts_(specialMatrix && specialMatrix.HU, maintenanceTypes)
  };
  let grandTotal = 0;
  (buildings || []).forEach(building => {
    (maintenanceTypes || []).forEach(type => {
      const value = Number(matrix.cells[building] && matrix.cells[building][type] || 0);
      totals[type] += value;
      grandTotal += value;
    });
  });
  ['RC', 'HU'].forEach(bucket => {
    (maintenanceTypes || []).forEach(type => {
      const value = Number(specialCells[bucket] && specialCells[bucket][type] || 0);
      totals[type] += value;
      grandTotal += value;
    });
  });
  const conversion = {};
  Object.keys(NOVA_ROOMMAID_CLOSE.CONVERSION_WEIGHTS).forEach(target => {
    const weights = NOVA_ROOMMAID_CLOSE.CONVERSION_WEIGHTS[target] || {};
    conversion[target] = Object.keys(weights)
      .reduce((sum, sourceType) => sum + Number(totals[sourceType] || 0) * Number(weights[sourceType] || 0), 0);
  });
  return { code, label, cells: matrix.cells, specialCells, totals, conversion, grandTotal, note: '' };
}

function createEmployeeTypeSeed_(employeeNo, maintenanceTypes, cleaningTypes) { // (개인 정비유형·객실타입 실적 초기값)
  const cleaningTypeCounts = createRoommaidCloseCleaningTypeSeed_(maintenanceTypes, cleaningTypes);
  return {
    employeeNo,
    cleaningTypeCounts,
    normal: cleaningTypeCounts[NOVA.CLEANING_TYPES.NORMAL],
    ds: cleaningTypeCounts[NOVA.CLEANING_TYPES.DS],
    primaryCompleted: 0,
    secondaryParticipation: 0
  };
}

function roommaidCloseAssignmentCreditShares_(assignmentType, primaryEmployeeNo, secondaryEmployeeNo) { // (마감일지 배정유형별 개인 정비수 배분)
  const type = String(assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
  const primaryNo = String(primaryEmployeeNo || '').trim();
  const secondaryNo = String(secondaryEmployeeNo || '').trim();
  const validPair = Boolean(primaryNo && secondaryNo && primaryNo !== secondaryNo);
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR && validPair) {
    return { primary: 0.5, secondary: 0.5 };
  }
  // 교육배정은 교육생 참여만 기록하고 개인 정비수는 주담당에게 100% 반영합니다.
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING && validPair) {
    return { primary: 1, secondary: 0 };
  }
  return { primary: 1, secondary: 0 };
}

function incrementEmployeeTypeCount_(row, cleaningType, maintenanceType, amount) { // (개인 정비유형별 인정 정비수 증가)
  const code = normalizeRoommaidCleaningType_(cleaningType);
  if (!row.cleaningTypeCounts) row.cleaningTypeCounts = createRoommaidCloseCleaningTypeSeed_([], getRoommaidCleaningTypeDefinitions_());
  if (!row.cleaningTypeCounts[code]) row.cleaningTypeCounts[code] = {};
  const type = normalizeMaintenanceTypeForClose_(maintenanceType);
  row.cleaningTypeCounts[code][type] = Number(row.cleaningTypeCounts[code][type] || 0) + Number(amount == null ? 1 : amount);
  row.normal = row.cleaningTypeCounts[NOVA.CLEANING_TYPES.NORMAL] || row.normal || {};
  row.ds = row.cleaningTypeCounts[NOVA.CLEANING_TYPES.DS] || row.ds || {};
}

function createRoommaidCloseCleaningTypeSeed_(maintenanceTypes, cleaningTypes) { // (정비유형×객실 정비타입 0 초기화)
  const result = {};
  (cleaningTypes || getRoommaidCleaningTypeDefinitions_()).forEach(definition => {
    result[definition.code] = zeroTypeCounts_(maintenanceTypes);
  });
  return result;
}

function cloneRoommaidCloseCleaningTypeCounts_(source, maintenanceTypes, cleaningTypes) { // (정비유형별 실적 복사)
  const result = createRoommaidCloseCleaningTypeSeed_(maintenanceTypes, cleaningTypes);
  Object.keys(source || {}).forEach(code => {
    if (!result[code]) result[code] = zeroTypeCounts_(maintenanceTypes);
    result[code] = cloneTypeCounts_(source[code], maintenanceTypes);
  });
  return result;
}

function addRoommaidCloseCleaningTypeCounts_(target, source, maintenanceTypes, cleaningTypes) { // (정비유형별 실적 합산)
  (cleaningTypes || getRoommaidCleaningTypeDefinitions_()).forEach(definition => {
    if (!target[definition.code]) target[definition.code] = zeroTypeCounts_(maintenanceTypes);
    addTypeCounts_(target[definition.code], source && source[definition.code], maintenanceTypes);
  });
}

function zeroTypeCounts_(maintenanceTypes) { // (타입별 0 초기화)
  const result = {};
  (maintenanceTypes || []).forEach(type => { result[type] = 0; });
  return result;
}

function cloneTypeCounts_(source, maintenanceTypes) { // (타입집계 복사)
  const result = zeroTypeCounts_(maintenanceTypes);
  (maintenanceTypes || []).forEach(type => { result[type] = Number(source && source[type] || 0); });
  return result;
}

function addTypeCounts_(target, source, maintenanceTypes) { // (타입집계 합산)
  (maintenanceTypes || []).forEach(type => { target[type] = Number(target[type] || 0) + Number(source && source[type] || 0); });
}

function sumTypeCounts_(source, maintenanceTypes) { // (타입집계 합계)
  return (maintenanceTypes || []).reduce((sum, type) => sum + Number(source && source[type] || 0), 0);
}

function parseHistoryDetailSafe_(data) { // (업무이력 JSON 안전 파싱)
  try { return JSON.parse(String(data && data['세부내용JSON'] || '{}')); } catch (error) { return {}; }
}

function uniqueEmployeeNos_(items) { // (사번 중복 제거)
  return Array.from(new Set((Array.isArray(items) ? items : []).map(value => String(value || '').trim()).filter(Boolean)));
}

function validateRoommaidCloseIntegrityForSave_(businessDate, site, currentRows, historyRows) { // (마감 저장 직전 원천자료 무결성 검증)
  const issues = [];
  const liveCurrentRows = latestRoommaidCloseCurrentRows_(currentRows, site);
  const ambiguous = findRoommaidCloseAmbiguousCurrentRows_(currentRows, site);
  ambiguous.forEach(item => {
    issues.push(`${item.roomNo}호 — 현재객실현황 최신행이 같은 버전·시각으로 중복되어 내용이 서로 다릅니다.`);
  });

  const master = readRoomMasterIndexForClose_(site);
  const upload = latestUploadSummaryForClose_(historyRows || []);
  const initialMap = buildInitialRoomStatusMapForClose_(upload, liveCurrentRows);
  const completionEvents = cleaningCompletionEventsForClose_(historyRows || []);
  const workloadHistoryRows = roommaidCloseHistoryAfterLatestUpload_(historyRows || [], upload);
  const workloadEvents = buildRoommaidCloseWorkloadEvents_(initialMap, workloadHistoryRows, completionEvents, master, liveCurrentRows, site);
  const statusNormalizer = buildRoommaidCloseRoomStatusNormalizer_();

  findRoommaidCloseReuploadRisks_(historyRows || [], upload, statusNormalizer).forEach(item => {
    issues.push(`${item.roomNo}호 — 당일 재업로드 이전 정비완료(${item.sourceStatus})와 최종 업로드 분류(${item.latestStatus})가 달라 정비주기를 확정할 수 없습니다.`);
  });

  liveCurrentRows.forEach(data => {
    const roomNo = normalizeRoomNo_(data && data['객실번호']);
    if (!roomNo) return;
    const status = normalizeRoommaidCloseRoomStatus_(data && data['객실상태'], statusNormalizer);
    const isInitialStock = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(status);
    const isDeparture = NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(status);
    if (!isInitialStock && !isDeparture) return;

    const desiredBucket = roommaidCloseSpecialBucket_(status) || 'BUILDING';
    const matched = (workloadEvents || []).some(event => {
      if (!event || event.canceled || normalizeRoomNo_(event.roomNo) !== roomNo) return false;
      if (isInitialStock) {
        if (String(event.bucket || 'BUILDING').trim().toUpperCase() !== desiredBucket) return false;
        if (normalizeRoommaidCloseRoomStatus_(event.sourceStatus, statusNormalizer) !== status) return false;
        return Boolean(event.initialStock);
      }
      if (isDeparture) {
        const normalDeparture = Boolean(event.departure)
          && String(event.bucket || 'BUILDING').trim().toUpperCase() === desiredBucket
          && normalizeRoommaidCloseRoomStatus_(event.sourceStatus, statusNormalizer) === status;
        const openingStockReclassification = Boolean(event.initialStock && !event.manualInitialStock)
          && String(event.openingStockReclassifiedTo || '').trim().toUpperCase() === status;
        return normalDeparture || openingStockReclassification;
      }
      return false;
    });
    if (!matched) {
      issues.push(`${roomNo}호 — 현재 ${status} 상태에 대응하는 정비주기 이력이 없습니다. 직접 시트 수정 또는 누락된 상태변경 이력을 확인하세요.`);
    }
  });

  if (issues.length) throwRoommaidCloseIntegrityError_(businessDate, site, issues);
  return { ok: true, businessDate, site, checkedRooms: liveCurrentRows.length, issueCount: 0 };
}

function findRoommaidCloseReuploadRisks_(historyRows, latestUpload, statusNormalizer) { // (당일 재업로드 이전 완료주기 분류변경 위험 검출)
  const rows = historyRows || [];
  const uploads = rows.filter(data => String(data['기록구분'] || '').trim() === NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD)
    .sort((a, b) => {
      const versionDiff = Number(b['변경버전'] || 0) - Number(a['변경버전'] || 0);
      return versionDiff || String(b['등록일시'] || '').localeCompare(String(a['등록일시'] || ''));
    });
  if (uploads.length <= 1) return [];

  const latestRow = uploads[0];
  const latestVersion = Number(latestRow && latestRow['변경버전'] || 0);
  const latestAt = String(latestRow && latestRow['등록일시'] || '').trim();
  const detailAvailable = Boolean(latestUpload && latestUpload.roomStatusDetailAvailable);
  const latestMap = {};
  const roomsByStatus = latestUpload && latestUpload.roomsByStatus && typeof latestUpload.roomsByStatus === 'object'
    ? latestUpload.roomsByStatus : {};
  Object.keys(roomsByStatus).forEach(status => {
    const normalizedStatus = normalizeRoommaidCloseRoomStatus_(status, statusNormalizer);
    (Array.isArray(roomsByStatus[status]) ? roomsByStatus[status] : []).forEach(roomNo => {
      const normalizedRoomNo = normalizeRoomNo_(roomNo);
      if (normalizedRoomNo) latestMap[normalizedRoomNo] = normalizedStatus;
    });
  });

  const risks = [];
  cleaningCompletionEventsForClose_(rows).forEach(item => {
    const detail = item && item.detail || {};
    const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
    if (!isRoommaidStockReducingCleaningType_(cleaningType)) return;
    const beforeLatest = latestVersion > 0 && Number(item.version || 0) > 0
      ? Number(item.version || 0) < latestVersion
      : Boolean(latestAt && item.eventAt && String(item.eventAt) < latestAt);
    if (!beforeLatest) return;

    const roomNo = normalizeRoomNo_(item.data && item.data['객실번호']);
    if (!roomNo) return;
    const sourceStatus = normalizeRoommaidCloseRoomStatus_(
      detail.sourceRoomStatus || detail.previousRoomStatus || '', statusNormalizer
    );
    if (!sourceStatus || !isNovaRoomCleaningTargetStatus_(sourceStatus)) return;
    const latestStatus = detailAvailable
      ? (latestMap[roomNo] || 'VACANT_CLEAN')
      : '';
    if (!latestStatus || !sameRoommaidCloseWorkloadClassification_(sourceStatus, latestStatus)) {
      risks.push({ roomNo, sourceStatus, latestStatus: latestStatus || '상세없음', completionAt: item.eventAt, completionVersion: item.version });
    }
  });
  return risks;
}

function sameRoommaidCloseWorkloadClassification_(leftStatus, rightStatus) { // (재고/퇴실·일반/HU/RC 분류 동등성 판정)
  const left = String(leftStatus || '').trim().toUpperCase();
  const right = String(rightStatus || '').trim().toUpperCase();
  const leftClass = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(left) ? 'STOCK'
    : NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(left) ? 'DEPARTURE' : '';
  const rightClass = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(right) ? 'STOCK'
    : NOVA_ROOMMAID_CLOSE.DEPARTURE_STATUSES.includes(right) ? 'DEPARTURE' : '';
  if (!leftClass || leftClass !== rightClass) return false;
  return (roommaidCloseSpecialBucket_(left) || 'BUILDING') === (roommaidCloseSpecialBucket_(right) || 'BUILDING');
}

function findRoommaidCloseAmbiguousCurrentRows_(currentRows, site) { // (같은 최신버전·시각의 상충 현재객실행 검출)
  const grouped = {};
  (currentRows || []).forEach((data, index) => {
    const roomNo = normalizeRoomNo_(data && data['객실번호']);
    const rowSite = String(data && data['사업장'] || site || '').trim();
    if (!roomNo || (site && rowSite && rowSite !== site)) return;
    const key = `${rowSite || site}|${roomNo}`;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push({ data, index, roomNo });
  });

  const result = [];
  Object.keys(grouped).forEach(key => {
    const rows = grouped[key];
    if (rows.length < 2) return;
    const maxVersion = Math.max.apply(null, rows.map(item => Number(item.data && item.data['마지막변경버전'] || 0)));
    const versionRows = rows.filter(item => Number(item.data && item.data['마지막변경버전'] || 0) === maxVersion);
    const maxUpdated = versionRows.reduce((latest, item) => {
      const value = String(item.data && item.data['수정일시'] || '').trim();
      return value > latest ? value : latest;
    }, '');
    const finalists = versionRows.filter(item => String(item.data && item.data['수정일시'] || '').trim() === maxUpdated);
    if (finalists.length < 2) return;
    const signatures = new Set(finalists.map(item => roommaidCloseCurrentConflictSignature_(item.data)));
    if (signatures.size > 1) result.push({ roomNo: finalists[0].roomNo, count: finalists.length, version: maxVersion, updatedAt: maxUpdated });
  });
  return result;
}

function roommaidCloseCurrentConflictSignature_(data) { // (마감에 영향 주는 현재객실행 비교값)
  return [
    String(data && data['객실상태'] || '').trim().toUpperCase(),
    String(data && data['청소상태'] || '').trim().toUpperCase(),
    String(data && data['정비유형'] || '').trim().toUpperCase(),
    String(data && data['배정유형'] || '').trim().toUpperCase(),
    String(data && data['룸메이드사번'] || '').trim(),
    String(data && data['보조룸메이드사번'] || '').trim(),
    String(data && data['QM사번'] || '').trim()
  ].join('|');
}

function throwRoommaidCloseIntegrityError_(businessDate, site, issues) { // (마감 차단 오류메시지 구성)
  const list = Array.isArray(issues) ? issues.filter(Boolean) : [];
  const limit = 20;
  const lines = list.slice(0, limit).map((text, index) => `${index + 1}. ${text}`);
  if (list.length > limit) lines.push(`외 ${list.length - limit}건`);
  throw new Error([
    `마감 무결성 검증에 실패했습니다. ${businessDate} ${site} 마감은 저장하지 않았습니다.`,
    ...lines,
    '현재객실현황과 업무이력을 확인한 후 다시 마감하세요.'
  ].join('\n'));
}

function roommaidCloseMasterSignatureText_(site) { // (객실마스터의 마감영향 항목 서명 원문)
  const normalizedSite = String(site || '').trim();
  if (!normalizedSite) return '';
  const master = readRoomMasterIndexForClose_(normalizedSite);
  return Object.keys(master.byRoomNo || {}).sort().map(roomNo => {
    const item = master.byRoomNo[roomNo] || {};
    return [
      normalizedSite,
      roomNo,
      String(item.building || '').trim(),
      String(item.maintenanceType || '').trim().toUpperCase(),
      'Y'
    ].join('|');
  }).join('\n');
}

function roommaidCloseSourceSignature_(currentRows, historyRows, site) { // (현재객실·업무이력·객실마스터 변경 서명)
  const currentText = (currentRows || []).map(row => [
    String(row['사업장'] || '').trim(),
    String(row['객실번호'] || '').trim(),
    String(row['동'] || '').trim(),
    String(row['객실상태'] || '').trim(),
    String(row['청소상태'] || '').trim(),
    String(row['정비유형'] || '').trim(),
    String(row['배정유형'] || '').trim(),
    String(row['룸메이드사번'] || '').trim(),
    String(row['보조룸메이드사번'] || '').trim(),
    String(row['QM사번'] || '').trim(),
    String(row['수정일시'] || '').trim()
  ].join('|')).sort().join('\n');
  const historyText = (historyRows || []).map(row => [
    String(row['기록ID'] || '').trim(),
    String(row['기록구분'] || '').trim(),
    String(row['객실번호'] || '').trim(),
    String(row['대상사번'] || '').trim(),
    String(row['처리상태'] || '').trim(),
    String(row['세부내용JSON'] || '').trim(),
    String(row['수정일시'] || row['등록일시'] || '').trim()
  ].join('|')).sort().join('\n');
  const involvedEmployeeNos = uniqueEmployeeNos_([].concat(
    (currentRows || []).flatMap(row => [row['룸메이드사번'], row['보조룸메이드사번']]),
    (historyRows || []).flatMap(row => {
      const detail = parseHistoryDetailSafe_(row);
      return [row['대상사번'], detail.primaryEmployeeNo, detail.secondaryEmployeeNo];
    })
  ));
  const employmentIndex = readRoommaidCloseEmploymentIndex_();
  const employmentText = involvedEmployeeNos.map(employeeNo => `${employeeNo}|${String(employmentIndex[employeeNo] || '').trim()}`).sort().join('\n');
  const resolvedSite = String(site || ((currentRows || []).find(row => String(row && row['사업장'] || '').trim()) || {})['사업장'] || '').trim();
  const masterText = roommaidCloseMasterSignatureText_(resolvedSite);
  return Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(
      Utilities.DigestAlgorithm.SHA_256,
      currentText + '\n---\n' + historyText + '\n---EMPLOYMENT---\n' + employmentText + '\n---ROOMMASTER---\n' + masterText
    )
  ).replace(/=+$/g, '');
}

function latestRoommaidCloseSourceAt_(currentRows, historyRows) { // (마감 이후 원천자료 최종 수정시각)
  const values = [];
  (currentRows || []).forEach(row => values.push(String(row['수정일시'] || '').trim()));
  (historyRows || []).forEach(row => values.push(String(row['수정일시'] || row['등록일시'] || '').trim()));
  return latestText_(values);
}

function compactRoommaidCloseJournalForStorage_(journal) { // (룸메이드 마감일지 압축 저장)
  if (!journal) return null;
  const buildings = journal.buildings || [];
  const types = journal.maintenanceTypes || [];
  const reportTypes = journal.reportMaintenanceTypes || NOVA_ROOMMAID_CLOSE.REPORT_MAINTENANCE_TYPES;
  const cleaningTypes = journal.cleaningTypes || getRoommaidCleaningTypeDefinitions_();
  return {
    compactVersion: 3,
    schemaVersion: Number(journal.schemaVersion || NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION),
    d: String(journal.businessDate || ''),
    x: String(journal.site || ''),
    b: buildings,
    bc: journal.buildingColumns || [],
    t: types,
    rt: reportTypes,
    ct: cleaningTypes.map(item => [item.code, item.label, Number(item.creditMultiplier || 0), item.stockReducing === false ? 0 : 1]),
    cg: journal.conversionGroups || {
      F: NOVA_ROOMMAID_CLOSE.CONVERSION_GROUPS.F.slice(),
      R: NOVA_ROOMMAID_CLOSE.CONVERSION_GROUPS.R.slice()
    },
    sb: Number(journal.staffBlockCount || NOVA_ROOMMAID_CLOSE.REPORT_STAFF_BLOCKS),
    sr: Number(journal.staffRowsPerBlock || NOVA_ROOMMAID_CLOSE.REPORT_STAFF_ROWS_PER_BLOCK),
    m: (journal.matrixRows || []).map(row => [
      row.code, row.label,
      buildings.flatMap(building => types.map(type => Number(row.cells && row.cells[building] && row.cells[building][type] || 0))),
      ['HU', 'RC'].flatMap(bucket => types.map(type => Number(row.specialCells && row.specialCells[bucket] && row.specialCells[bucket][type] || 0))),
      types.map(type => Number(row.totals && row.totals[type] || 0)),
      [Number(row.conversion && row.conversion.F || 0), Number(row.conversion && row.conversion.R || 0)],
      Number(row.grandTotal || 0),
      String(row.note || '')
    ]),
    a: journal.attendanceEmployeeNos || [],
    s: (journal.staffRows || []).map(row => [
      row.rowType, row.groupCode || '', row.employeeNo || '', row.name || '', row.job || '',
      row.memberEmployeeNos || [], row.memberNames || [],
      cleaningTypes.map(definition => types.map(type => Number(row.cleaningTypeCounts && row.cleaningTypeCounts[definition.code] && row.cleaningTypeCounts[definition.code][type] || 0))),
      Number(row.primaryCompleted || 0), Number(row.secondaryParticipation || 0)
    ]),
    i: journal.initialStatusDetailAvailable ? 1 : 0,
    f: String(journal.uploadFileName || ''),
    u: String(journal.uploadAppliedAt || ''),
    g: String(journal.generatedAt || '')
  };
}

function expandRoommaidCloseJournalFromStorage_(stored) { // (압축 마감일지 복원·이전 버전 호환)
  if (!stored) return null;
  const compactVersion = Number(stored.compactVersion || 0);
  if (![1, 2, 3].includes(compactVersion)) return stored || null;
  const buildings = Array.isArray(stored.b) ? stored.b : [];
  const types = Array.isArray(stored.t) ? stored.t : [];
  const reportTypes = compactVersion >= 2 && Array.isArray(stored.rt) && stored.rt.length
    ? stored.rt : NOVA_ROOMMAID_CLOSE.REPORT_MAINTENANCE_TYPES.slice();
  const cleaningTypes = compactVersion >= 3 && Array.isArray(stored.ct) && stored.ct.length
    ? stored.ct.map(row => ({ code: row[0], label: row[1], creditMultiplier: Number(row[2] || 0), stockReducing: Number(row[3] || 0) === 1 }))
    : getRoommaidCleaningTypeDefinitions_().map(item => ({ code: item.code, label: item.label, creditMultiplier: Number(item.creditMultiplier || 0), stockReducing: item.stockReducing !== false }));
  const buildingColumns = compactVersion >= 2 && Array.isArray(stored.bc) && stored.bc.length
    ? stored.bc : buildings.map(building => ({ building, types: types.length ? types.slice() : [''] }));
  const matrixRows = (Array.isArray(stored.m) ? stored.m : []).map(row => {
    const values = Array.isArray(row[2]) ? row[2] : [];
    const cells = {};
    let index = 0;
    buildings.forEach(building => {
      cells[building] = {};
      types.forEach(type => { cells[building][type] = Number(values[index++] || 0); });
    });
    if (compactVersion === 1) {
      const totalsArray = Array.isArray(row[3]) ? row[3] : [];
      const totals = {};
      types.forEach((type, typeIndex) => { totals[type] = Number(totalsArray[typeIndex] || 0); });
      return {
        code: row[0], label: row[1], cells,
        specialCells: { HU: zeroTypeCounts_(types), RC: zeroTypeCounts_(types) }, totals,
        conversion: { F: Number(totals.F || 0) + Number(totals.T || 0), R: Number(totals.R || 0) + Number(totals.G || 0) },
        grandTotal: Number(row[4] || 0), note: ''
      };
    }
    const specialValues = Array.isArray(row[3]) ? row[3] : [];
    const specialCells = { HU: {}, RC: {} };
    let specialIndex = 0;
    ['HU', 'RC'].forEach(bucket => {
      types.forEach(type => { specialCells[bucket][type] = Number(specialValues[specialIndex++] || 0); });
    });
    const totalsArray = Array.isArray(row[4]) ? row[4] : [];
    const totals = {};
    types.forEach((type, typeIndex) => { totals[type] = Number(totalsArray[typeIndex] || 0); });
    const conversionArray = Array.isArray(row[5]) ? row[5] : [];
    return {
      code: row[0], label: row[1], cells, specialCells, totals,
      conversion: { F: Number(conversionArray[0] || 0), R: Number(conversionArray[1] || 0) },
      grandTotal: Number(row[6] || 0), note: String(row[7] || '')
    };
  });
  const staffRows = (Array.isArray(stored.s) ? stored.s : []).map((row, index) => {
    const cleaningTypeCounts = createRoommaidCloseCleaningTypeSeed_(types, cleaningTypes);
    let primaryCompleted = 0;
    let secondaryParticipation = 0;
    if (compactVersion >= 3) {
      const storedCounts = Array.isArray(row[7]) ? row[7] : [];
      cleaningTypes.forEach((definition, cleaningIndex) => {
        const values = Array.isArray(storedCounts[cleaningIndex]) ? storedCounts[cleaningIndex] : [];
        types.forEach((type, typeIndex) => { cleaningTypeCounts[definition.code][type] = Number(values[typeIndex] || 0); });
      });
      primaryCompleted = Number(row[8] || 0);
      secondaryParticipation = Number(row[9] || 0);
    } else {
      const normalArray = Array.isArray(row[7]) ? row[7] : [];
      const dsArray = Array.isArray(row[8]) ? row[8] : [];
      types.forEach((type, typeIndex) => {
        cleaningTypeCounts[NOVA.CLEANING_TYPES.NORMAL][type] = Number(normalArray[typeIndex] || 0);
        cleaningTypeCounts[NOVA.CLEANING_TYPES.DS][type] = Number(dsArray[typeIndex] || 0);
      });
      primaryCompleted = Number(row[9] || 0);
      secondaryParticipation = Number(row[10] || 0);
    }
    const cleaningTypeTotals = {};
    cleaningTypes.forEach(definition => { cleaningTypeTotals[definition.code] = sumTypeCounts_(cleaningTypeCounts[definition.code], types); });
    const stockReducingCounts = buildRoommaidCloseStockReducingTypeCounts_(cleaningTypeCounts, types, cleaningTypes);
    return {
      sequence: index + 1,
      rowType: row[0] || 'PERSON', groupCode: row[1] || '', employeeNo: row[2] || '',
      name: row[3] || '', job: row[4] || '', memberEmployeeNos: row[5] || [], memberNames: row[6] || [],
      cleaningTypeCounts, cleaningTypeTotals,
      normal: stockReducingCounts, ds: cleaningTypeCounts[NOVA.CLEANING_TYPES.DS],
      primaryCompleted, secondaryParticipation,
      normalTotal: sumTypeCounts_(stockReducingCounts, types),
      dsTotal: Number(cleaningTypeTotals[NOVA.CLEANING_TYPES.DS] || 0)
    };
  });
  const attendance = uniqueEmployeeNos_(stored.a || []);
  return {
    schemaVersion: Number(stored.schemaVersion || NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION),
    businessDate: String(stored.d || ''), site: String(stored.x || ''),
    buildings, buildingColumns, maintenanceTypes: types, cleaningTypes, reportMaintenanceTypes: reportTypes,
    conversionGroups: compactVersion >= 2 && stored.cg ? stored.cg : {
      F: NOVA_ROOMMAID_CLOSE.CONVERSION_GROUPS.F.slice(), R: NOVA_ROOMMAID_CLOSE.CONVERSION_GROUPS.R.slice()
    },
    staffBlockCount: compactVersion >= 2 ? Number(stored.sb || NOVA_ROOMMAID_CLOSE.REPORT_STAFF_BLOCKS) : NOVA_ROOMMAID_CLOSE.REPORT_STAFF_BLOCKS,
    staffRowsPerBlock: compactVersion >= 2 ? Number(stored.sr || NOVA_ROOMMAID_CLOSE.REPORT_STAFF_ROWS_PER_BLOCK) : NOVA_ROOMMAID_CLOSE.REPORT_STAFF_ROWS_PER_BLOCK,
    matrixRows, attendanceEmployeeNos: attendance, attendanceCount: attendance.length,
    staffRows, temporaryGroups: staffRows.filter(row => row.rowType === 'GROUP'),
    initialStatusDetailAvailable: Number(stored.i || 0) === 1,
    uploadFileName: String(stored.f || ''), uploadAppliedAt: String(stored.u || ''), generatedAt: String(stored.g || '')
  };
}

