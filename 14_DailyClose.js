/**
 * Sprint 9.2: 업무일자별 공식 마감통계 및 객실 스냅샷
 * 별도 시트 없이 업무이력의 DAILY_CLOSE 기록으로 저장합니다.
 */
const NOVA_DAILY_CLOSE = Object.freeze({
  SCHEMA_VERSION: 3,
  ROOM_CHUNK_SIZE: 120,
  SUMMARY_STATUS: 'SUMMARY',
  ROOM_STATUS_PREFIX: 'ROOMS_',
  MAX_JSON_LENGTH: 45000
});

function getDailyCloseOverview(token, filters) { // (일일·월별 마감통계 조회)
  return measureResponse_('getDailyCloseOverview', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(filters || {}, user);
    return Object.assign({ ok: true }, buildDailyCloseOverviewForRequest_(request));
  });
}

function saveDailyCloseSnapshot(token, payload) { // (업무일자 공식 마감 저장·갱신)
  return measureResponse_('saveDailyCloseSnapshot', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const requestedSite = String(safe.site || '').trim();
    const sites = requestedSite ? [requestedSite] : getCurrentSitesForDate_(businessDate);
    if (!sites.length) throw new Error(`${businessDate} 현재객실현황에 마감할 사업장이 없습니다.`);

    const lock = acquireWriteLock_(30000);
    try {
      const allCurrentRows = readCurrentRowsForClose_(businessDate, requestedSite);
      const allHistoryRows = readHistoryRowsForClose_(businessDate, requestedSite);
      const results = sites.map(site => saveDailyCloseSnapshotForSite_(businessDate, site, user, {
        currentRows: allCurrentRows.filter(data => String(data['사업장'] || '').trim() === site),
        historyRows: allHistoryRows.filter(data => String(data['사업장'] || '').trim() === site),
        attendanceEmployeeNos: Array.isArray(safe.attendanceEmployeeNos) ? safe.attendanceEmployeeNos : []
      }));
      return {
        ok: true,
        businessDate,
        sites: results,
        message: `${businessDate} ${results.length}개 사업장의 마감자료를 저장했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function buildDailyCloseOverviewForRequest_(request) { // (조회방식별 마감통계 묶음 구성)
  if (request.period === 'DAILY') return buildDailyCloseDailyOverview_(request);
  return buildDailyCloseMonthlyOverview_(request);
}

function buildDailyCloseDailyOverview_(request) { // (일별 저장자료 또는 실시간 마감통계 조회)
  const allCurrentRows = readCurrentRowsForClose_(request.date, request.site);
  const allHistoryRows = readHistoryRowsForClose_(request.date, request.site);
  const availableSites = request.site
    ? (allCurrentRows.length ? [request.site] : [])
    : Array.from(new Set(allCurrentRows.map(data => String(data['사업장'] || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'ko'));
  const savedSites = readDailyCloseSummaries_(request.date, request.site);
  const savedBySite = {};
  savedSites.forEach(item => { savedBySite[item.site] = item; });

  const sites = Array.from(new Set(availableSites.concat(savedSites.map(item => item.site)))).filter(Boolean)
    .sort((a, b) => a.localeCompare(b, 'ko'));
  const items = sites.map(site => {
    if (savedBySite[site]) return Object.assign({ source: 'CLOSED' }, savedBySite[site]);
    const live = buildDailyCloseSnapshot_(request.date, site, {
      closedBy: '',
      closedAt: '',
      includeRooms: false,
      currentRows: allCurrentRows.filter(data => String(data['사업장'] || '').trim() === site),
      historyRows: allHistoryRows.filter(data => String(data['사업장'] || '').trim() === site)
    });
    return Object.assign({ source: 'LIVE' }, live);
  });

  return {
    period: 'DAILY',
    businessDate: request.date,
    site: request.site,
    source: dailyCloseSourceLabel_(items),
    isClosed: Boolean(items.length && items.every(item => item.source === 'CLOSED')),
    closedAt: latestText_(items.map(item => item.closedAt)),
    closedBy: items.length === 1 ? String(items[0].closedByName || items[0].closedBy || '') : '',
    summary: aggregateDailyCloseSummaries_(items),
    sites: items,
    message: items.length ? '' : `${request.date} 마감통계 자료가 없습니다.`
  };
}

function buildDailyCloseMonthlyOverview_(request) { // (월별 저장 마감자료 합산)
  const prefix = `${request.year}-${String(request.month).padStart(2, '0')}-`;
  const summaries = readDailyCloseSummaryRows_()
    .filter(item => item.businessDate.startsWith(prefix))
    .filter(item => !request.site || item.site === request.site)
    .sort((a, b) => a.businessDate.localeCompare(b.businessDate) || a.site.localeCompare(b.site, 'ko'));
  return {
    period: 'MONTHLY',
    year: request.year,
    month: request.month,
    site: request.site,
    source: summaries.length ? 'CLOSED' : 'NONE',
    isClosed: Boolean(summaries.length),
    closedDays: new Set(summaries.map(item => item.businessDate)).size,
    summary: aggregateDailyCloseSummaries_(summaries),
    sites: summaries,
    message: summaries.length ? '' : '선택한 월에 저장된 공식 마감자료가 없습니다.'
  };
}

function saveDailyCloseSnapshotForSite_(businessDate, site, user, preloaded) { // (사업장별 마감 스냅샷 저장)
  const closedAt = nowText_();
  const preload = preloaded || {};
  const snapshot = buildDailyCloseSnapshot_(businessDate, site, {
    closedBy: user.employeeNo,
    closedByName: user.name,
    closedAt,
    includeRooms: true,
    currentRows: preload.currentRows,
    historyRows: preload.historyRows,
    attendanceEmployeeNos: preload.attendanceEmployeeNos
  });
  if (!snapshot.totalRooms) throw new Error(`${businessDate} ${site} 현재객실현황이 없습니다.`);

  const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  markExistingDailyCloseDeleted_(historySheet, businessDate, site, closedAt);
  const version = reserveDataVersion_({ lockHeld: true });
  const batchId = `DC-${businessDate.replaceAll('-', '')}-${dailyCloseSafeId_(site)}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;
  const summaryDetail = Object.assign({}, snapshot);
  delete summaryDetail.rooms;
  summaryDetail.roommaidCloseJournal = compactRoommaidCloseJournalForStorage_(snapshot.roommaidCloseJournal);
  const summaryJson = JSON.stringify(summaryDetail);
  if (summaryJson.length > NOVA_DAILY_CLOSE.MAX_JSON_LENGTH) {
    throw new Error(`${site} 마감 요약 데이터가 너무 큽니다. 직원별 집계 항목을 확인하세요.`);
  }

  const rows = [createRowByHeaders_(historySheet, {
    '기록ID': `${batchId}-SUMMARY`,
    '기록구분': NOVA.RECORD_TYPES.DAILY_CLOSE,
    '업무일자': businessDate,
    '사업장': site,
    '처리상태': NOVA_DAILY_CLOSE.SUMMARY_STATUS,
    '세부내용JSON': summaryJson,
    '등록사번': user.employeeNo,
    '등록일시': closedAt,
    '수정일시': closedAt,
    '변경버전': version,
    '삭제여부': 'N'
  })];

  chunkArray_(snapshot.rooms || [], NOVA_DAILY_CLOSE.ROOM_CHUNK_SIZE).forEach((chunk, index) => {
    const status = `${NOVA_DAILY_CLOSE.ROOM_STATUS_PREFIX}${String(index + 1).padStart(3, '0')}`;
    const detail = JSON.stringify({
      schemaVersion: NOVA_DAILY_CLOSE.SCHEMA_VERSION,
      batchId,
      chunkIndex: index + 1,
      rooms: chunk
    });
    if (detail.length > NOVA_DAILY_CLOSE.MAX_JSON_LENGTH) throw new Error(`${site} 객실 스냅샷 ${index + 1}번 묶음이 너무 큽니다.`);
    rows.push(createRowByHeaders_(historySheet, {
      '기록ID': `${batchId}-${status}`,
      '기록구분': NOVA.RECORD_TYPES.DAILY_CLOSE,
      '업무일자': businessDate,
      '사업장': site,
      '처리상태': status,
      '세부내용JSON': detail,
      '등록사번': user.employeeNo,
      '등록일시': closedAt,
      '수정일시': closedAt,
      '변경버전': version,
      '삭제여부': 'N'
    }));
  });

  const startRow = historySheet.getLastRow() + 1;
  ensureSheetRowCapacity_(historySheet, startRow + rows.length - 1);
  historySheet.getRange(startRow, 1, rows.length, rows[0].length).setValues(rows);
  SpreadsheetApp.flush();
  publishDataVersion_(version, { domains: ['REPORT'], businessDate, site, lockHeld: true });
  return Object.assign({ source: 'CLOSED', chunkCount: rows.length - 1 }, summaryDetail);
}

function buildDailyCloseSnapshot_(businessDate, site, options) { // (현재 객실·업무이력 기반 마감통계 계산)
  const safe = options || {};
  const currentRows = Array.isArray(safe.currentRows) ? safe.currentRows : readCurrentRowsForClose_(businessDate, site);
  const historyRows = Array.isArray(safe.historyRows) ? safe.historyRows : readHistoryRowsForClose_(businessDate, site);
  const users = getUserIndex_().byEmployeeNo;
  const upload = latestUploadSummaryForClose_(historyRows);
  const roomsByKey = {};
  const byBuilding = {};
  const roomStatusCounts = {};
  const cleaningStatusCounts = {};
  const roomSnapshots = [];

  currentRows.forEach(data => {
    const roomNo = String(data['객실번호'] || '').trim();
    const roomSite = String(data['사업장'] || site || '').trim();
    const building = normalizeRoomBuilding_(data['동'], roomNo);
    const roomStatus = String(data['객실상태'] || '').trim().toUpperCase();
    const cleaningStatus = String(data['청소상태'] || '').trim().toUpperCase();
    const cleaningType = String(data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
    const key = `${roomSite}|${roomNo}`;
    roomsByKey[key] = { roomNo, site: roomSite, building, roomStatus, cleaningStatus, cleaningType };
    roomStatusCounts[roomStatus || 'BLANK'] = (roomStatusCounts[roomStatus || 'BLANK'] || 0) + 1;
    cleaningStatusCounts[cleaningStatus || 'BLANK'] = (cleaningStatusCounts[cleaningStatus || 'BLANK'] || 0) + 1;
    if (!byBuilding[building]) byBuilding[building] = dailyCloseBuildingSeed_(building);
    const group = byBuilding[building];
    group.total += 1;
    if (['STOCK', 'STOCK_RC', 'STOCK_HU'].includes(roomStatus) && !isCleaningCompletedStatus_(cleaningStatus)) group.stockRemaining += 1;
    if (roomStatus === 'DUE_OUT') group.dueOutRemaining += 1;
    if (['CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU'].includes(roomStatus) && !isCleaningCompletedStatus_(cleaningStatus)) group.checkedOutWaiting += 1;
    if (roomStatus === 'VACANT_CLEAN' && isCleaningCompletedStatus_(cleaningStatus)) group.vacantClean += 1;
    if (safe.includeRooms !== false) {
      roomSnapshots.push({
        n: roomNo,
        b: building,
        s: roomStatus,
        c: cleaningStatus,
        t: cleaningType,
        a: String(data['배정유형'] || '').trim(),
        p: String(data['룸메이드사번'] || '').trim(),
        r: String(data['보조룸메이드사번'] || '').trim(),
        q: String(data['QM사번'] || '').trim(),
        h: String(data['하우스맨상태'] || '').trim(),
        u: String(data['수정일시'] || '').trim()
      });
    }
  });

  const cleaning = buildDailyCloseCleaningStats_(historyRows, roomsByKey, users, currentRows);
  Object.keys(cleaning.completedByBuilding).forEach(building => {
    if (!byBuilding[building]) byBuilding[building] = dailyCloseBuildingSeed_(building);
    byBuilding[building].cleaningCompleted = cleaning.completedByBuilding[building];
  });
  const qm = buildDailyCloseQmStats_(historyRows, users);
  const houseman = buildDailyCloseHousemanStats_(historyRows, users);
  const departureDelay = buildDailyCloseDepartureDelayStats_(historyRows);
  const validation = buildDailyCloseValidation_(currentRows);
  const attendanceEmployeeNos = uniqueEmployeeNos_(safe.attendanceEmployeeNos || []);
  const roommaidCloseJournal = buildRoommaidCloseJournal_(businessDate, site, currentRows, historyRows, users, attendanceEmployeeNos);
  const sourceUpdatedAt = latestRoommaidCloseSourceAt_(currentRows, historyRows);
  const sourceSignature = roommaidCloseSourceSignature_(currentRows, historyRows);
  const uploadCounts = upload.counts || {};
  const previousStock = Number(uploadCounts.STOCK || 0) + Number(uploadCounts.STOCK_RC || 0) + Number(uploadCounts.STOCK_HU || 0);
  const scheduledDepartures = Number(uploadCounts.DUE_OUT || 0) + Number(uploadCounts.CHECKED_OUT || 0);

  return {
    schemaVersion: NOVA_DAILY_CLOSE.SCHEMA_VERSION,
    businessDate,
    site,
    closedAt: String(safe.closedAt || '').trim(),
    closedBy: String(safe.closedBy || '').trim(),
    closedByName: String(safe.closedByName || '').trim(),
    generatedAt: nowText_(),
    sourceUpdatedAt,
    sourceSignature,
    attendanceEmployeeNos: roommaidCloseJournal.attendanceEmployeeNos,
    roommaidCloseJournal,
    totalRooms: currentRows.length,
    previousStock,
    scheduledDepartures,
    recheckin: Number(uploadCounts.RECHECKIN || 0),
    cleaningCompleted: cleaning.totalCompleted,
    recognizedUnits: cleaning.recognizedUnits,
    normalCompleted: cleaning.normalCompleted,
    dsCompleted: cleaning.dsCompleted,
    stockRemaining: Object.values(byBuilding).reduce((sum, item) => sum + Number(item.stockRemaining || 0), 0),
    dueOutRemaining: Object.values(byBuilding).reduce((sum, item) => sum + Number(item.dueOutRemaining || 0), 0),
    checkedOutWaiting: Object.values(byBuilding).reduce((sum, item) => sum + Number(item.checkedOutWaiting || 0), 0),
    vacantClean: Object.values(byBuilding).reduce((sum, item) => sum + Number(item.vacantClean || 0), 0),
    qmCompleted: qm.completed,
    qmRework: qm.rework,
    qmAverageMinutes: qm.averageMinutes,
    qmDefectCount: qm.defectCount,
    housemanCompleted: houseman.completed,
    housemanUnable: houseman.unable,
    housemanAverageMinutes: houseman.averageMinutes,
    departureDelayCount: departureDelay.count,
    roomStatusCounts,
    cleaningStatusCounts,
    uploadSummary: upload,
    byBuilding: Object.values(byBuilding).sort((a, b) => compareDailyCloseBuilding_(a.building, b.building)),
    cleaningTypes: cleaning.cleaningTypes,
    roommaidSummary: cleaning.staffSummary,
    qmSummary: qm.staffSummary,
    roommaidQualitySummary: qm.roommaidSummary,
    qmLocationSummary: qm.locationSummary,
    housemanSummary: houseman.staffSummary,
    validation,
    rooms: roomSnapshots.sort((a, b) => compareDepartureRoomNos_(a.n, b.n))
  };
}

function readCurrentRowsForClose_(businessDate, site) { // (마감 대상 현재객실현황 고속 읽기)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const dateColumn = headerMap['업무일자'];
  const siteColumn = headerMap['사업장'];
  if (!dateColumn || !siteColumn) return [];
  const rowCount = lastRow - 1;
  const dateValues = sheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const siteValues = sheet.getRange(2, siteColumn, rowCount, 1).getDisplayValues();
  const rowNumbers = [];
  for (let index = 0; index < rowCount; index += 1) {
    if (String(dateValues[index][0] || '').trim() !== businessDate) continue;
    if (site && String(siteValues[index][0] || '').trim() !== site) continue;
    rowNumbers.push(index + 2);
  }
  return readRowsByNumbersForClose_(sheet, headerMap, rowNumbers);
}

function getCurrentSitesForDate_(businessDate) { // (업무일자 현재 사업장 목록)
  return Array.from(new Set(readCurrentRowsForClose_(businessDate, '').map(data => String(data['사업장'] || '').trim()).filter(Boolean)))
    .sort((a, b) => a.localeCompare(b, 'ko'));
}

function readHistoryRowsForClose_(businessDate, site) { // (마감 집계용 당일 업무이력 고속 읽기)
  const allowed = new Set([
    NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD,
    NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE,
    NOVA.RECORD_TYPES.CLEANING,
    NOVA.RECORD_TYPES.QM,
    NOVA.RECORD_TYPES.QM_CHECKLIST,
    NOVA.RECORD_TYPES.HOUSEMAN_ORDER,
    NOVA.RECORD_TYPES.DEPARTURE_DELAY
  ]);
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const typeColumn = headerMap['기록구분'];
  const dateColumn = headerMap['업무일자'];
  const siteColumn = headerMap['사업장'];
  const deletedColumn = headerMap['삭제여부'];
  if (!typeColumn || !dateColumn || !siteColumn) return [];
  const rowCount = lastRow - 1;
  const typeValues = sheet.getRange(2, typeColumn, rowCount, 1).getDisplayValues();
  const dateValues = sheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const siteValues = sheet.getRange(2, siteColumn, rowCount, 1).getDisplayValues();
  const deletedValues = deletedColumn
    ? sheet.getRange(2, deletedColumn, rowCount, 1).getDisplayValues()
    : Array.from({ length: rowCount }, () => ['N']);
  const rowNumbers = [];
  for (let index = 0; index < rowCount; index += 1) {
    if (!allowed.has(String(typeValues[index][0] || '').trim())) continue;
    if (String(dateValues[index][0] || '').trim() !== businessDate) continue;
    if (site && String(siteValues[index][0] || '').trim() !== site) continue;
    if (String(deletedValues[index][0] || 'N').trim().toUpperCase() === 'Y') continue;
    rowNumbers.push(index + 2);
  }
  return readRowsByNumbersForClose_(sheet, headerMap, rowNumbers);
}

function readRowsByNumbersForClose_(sheet, headerMap, rowNumbers) { // (선택 행 구간 읽기)
  if (!rowNumbers.length) return [];
  const groups = groupConsecutiveRows_(rowNumbers);
  const lastColumn = sheet.getLastColumn();
  const result = [];
  groups.forEach(group => {
    const values = sheet.getRange(group.start, 1, group.count, lastColumn).getDisplayValues();
    values.forEach(row => result.push(rowObjectFromValues_(row, headerMap)));
  });
  return result;
}

function latestUploadSummaryForClose_(historyRows) { // (최종 객실현황 업로드: 변경버전 우선·등록일시 보조 선택)
  const uploads = (historyRows || []).filter(data => String(data['기록구분'] || '').trim() === NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD)
    .sort((a, b) => {
      const versionDiff = Number(b['변경버전'] || 0) - Number(a['변경버전'] || 0);
      return versionDiff || String(b['등록일시'] || '').localeCompare(String(a['등록일시'] || ''));
    });
  if (!uploads.length) return { counts: {}, totalRooms: 0, fileName: '', uploadedAt: '', version: 0, roomsByStatus: {}, roomStatusDetailAvailable: false };
  const row = uploads[0];
  let detail = {};
  try { detail = JSON.parse(String(row['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
  return {
    counts: detail.counts || {},
    totalRooms: Number(detail.totalRooms || 0),
    fileName: String(detail.fileName || '').trim(),
    uploadedAt: String(row['등록일시'] || '').trim(),
    version: Number(row['변경버전'] || 0),
    roomsByStatus: detail.roomsByStatus && typeof detail.roomsByStatus === 'object' ? detail.roomsByStatus : {},
    roomStatusDetailAvailable: Boolean(detail.roomsByStatus && Object.keys(detail.roomsByStatus).length)
  };
}

function buildDailyCloseCleaningStats_(historyRows, roomsByKey, users, currentRows) { // (다회 정비완료 포함 룸메이드 실적 집계)
  const completionEvents = cleaningCompletionEventsForClose_(historyRows);
  const staff = {};
  const completedByBuilding = {};
  let recognizedUnits = 0;
  let normalCompleted = 0;
  let dsCompleted = 0;

  completionEvents.forEach(item => {
    const data = item.data || {};
    const detail = item.detail || {};
    const roomNo = String(data['객실번호'] || '').trim();
    const site = String(data['사업장'] || '').trim();
    const room = roomsByKey[`${site}|${roomNo}`] || {};
    const building = room.building || normalizeRoomBuilding_('', roomNo);
    const cleaningType = normalizeRoommaidCleaningType_(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL);
    const unit = Number(detail.creditUnit != null
      ? detail.creditUnit
      : getRoommaidCleaningCreditUnit_(cleaningType));
    const assignmentType = String(detail.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
    const primaryNo = String(detail.primaryEmployeeNo || data['대상사번'] || '').trim();
    const secondaryNo = String(detail.secondaryEmployeeNo || '').trim();
    const creditShares = dailyCloseAssignmentCreditShares_(assignmentType, primaryNo, secondaryNo);

    recognizedUnits += Number.isFinite(unit) ? unit : 0;
    if (cleaningType === NOVA.CLEANING_TYPES.DS) dsCompleted += 1;
    else normalCompleted += 1;
    completedByBuilding[building] = (completedByBuilding[building] || 0) + 1;

    if (primaryNo) {
      const group = dailyCloseStaffSeed_(staff, primaryNo, users);
      group.completedPrimary += 1;
      group.recognizedUnits += Number.isFinite(unit) ? unit * creditShares.primary : 0;
      if (assignmentType === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR) group.pairRooms += 1;
      if (assignmentType === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING) group.trainingRooms += 1;
    }
    if (secondaryNo && secondaryNo !== primaryNo) {
      const group = dailyCloseStaffSeed_(staff, secondaryNo, users);
      group.completedSecondary += 1;
      group.pairParticipation += 1;
      group.recognizedUnits += Number.isFinite(unit) ? unit * creditShares.secondary : 0;
      if (assignmentType === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR) group.pairRooms += 1;
      if (assignmentType === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING) group.trainingRooms += 1;
    }
  });

  currentRows.forEach(data => {
    const primaryNo = String(data['룸메이드사번'] || '').trim();
    const secondaryNo = String(data['보조룸메이드사번'] || '').trim();
    if (primaryNo) dailyCloseStaffSeed_(staff, primaryNo, users).assigned += 1;
    if (secondaryNo && secondaryNo !== primaryNo) dailyCloseStaffSeed_(staff, secondaryNo, users).assigned += 1;
  });

  return {
    totalCompleted: completionEvents.length,
    recognizedUnits: roundDailyCloseNumber_(recognizedUnits),
    normalCompleted,
    dsCompleted,
    cleaningTypes: [
      { code: NOVA.CLEANING_TYPES.NORMAL, label: '일반정비', completed: normalCompleted, recognizedUnits: normalCompleted },
      { code: NOVA.CLEANING_TYPES.DS, label: 'D/S', completed: dsCompleted, recognizedUnits: roundDailyCloseNumber_(dsCompleted * getRoommaidCleaningCreditUnit_(NOVA.CLEANING_TYPES.DS)) }
    ],
    completedByBuilding,
    staffSummary: Object.values(staff).map(group => Object.assign({}, group, {
      recognizedUnits: roundDailyCloseCredit_(group.recognizedUnits)
    })).sort((a, b) => b.recognizedUnits - a.recognizedUnits || b.completedPrimary - a.completedPrimary || a.name.localeCompare(b.name, 'ko'))
  };
}

function buildDailyCloseQmStats_(historyRows, users) { // (QM 시간·점검수·장소하자·룸메이드 품질 집계)
  const quality = buildQmQualityAnalyticsFromHistoryRows_(historyRows, users, {});
  if (quality.summary.inspections) {
    return {
      completed: quality.summary.inspections,
      rework: quality.summary.failed,
      defectCount: quality.summary.defectCount,
      averageMinutes: quality.summary.averageMinutes,
      staffSummary: quality.qmManagers.map(item => ({
        employeeNo: item.employeeNo,
        name: item.name,
        job: users[item.employeeNo] ? users[item.employeeNo].job : '',
        completed: item.inspections,
        rework: item.failedInspections,
        defectCount: item.defectCount,
        averageMinutes: item.averageMinutes
      })),
      roommaidSummary: quality.roommaids,
      locationSummary: quality.locations
    };
  }

  // RC2 이전 이력 호환: 최종 체크리스트 기록이 없을 때 기존 QM 이력으로 집계합니다.
  const completedByRoom = {};
  const rework = {};
  historyRows.forEach(data => {
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.QM) return;
    const status = String(data['처리상태'] || '').trim().toUpperCase();
    const roomNo = String(data['객실번호'] || '').trim();
    const site = String(data['사업장'] || '').trim();
    const employeeNo = String(data['대상사번'] || '').trim();
    const key = `${site}|${roomNo}`;
    const eventAt = String(data['수정일시'] || data['등록일시'] || '').trim();
    if (status === 'QM_COMPLETE' && (!completedByRoom[key] || eventAt >= completedByRoom[key].eventAt)) completedByRoom[key] = { employeeNo, eventAt };
    if (status === 'QM_REWORK') rework[employeeNo] = (rework[employeeNo] || 0) + 1;
  });
  const staff = {};
  Object.values(completedByRoom).forEach(item => {
    if (!item.employeeNo) return;
    const group = dailyCloseStaffSeed_(staff, item.employeeNo, users);
    group.completed = (group.completed || 0) + 1;
  });
  Object.keys(rework).forEach(employeeNo => { dailyCloseStaffSeed_(staff, employeeNo, users).rework = rework[employeeNo]; });
  return {
    completed: Object.keys(completedByRoom).length,
    rework: Object.values(rework).reduce((sum, value) => sum + value, 0),
    defectCount: 0,
    averageMinutes: null,
    staffSummary: Object.values(staff).map(group => ({
      employeeNo: group.employeeNo, name: group.name, job: group.job,
      completed: Number(group.completed || 0), rework: Number(group.rework || 0),
      defectCount: 0, averageMinutes: null
    })).sort((a, b) => b.completed - a.completed || b.rework - a.rework || a.name.localeCompare(b.name, 'ko')),
    roommaidSummary: [],
    locationSummary: []
  };
}

function buildDailyCloseHousemanStats_(historyRows, users) { // (하우스맨 처리건수·평균시간 집계)
  const rows = historyRows.filter(data => String(data['기록구분'] || '').trim() === NOVA.RECORD_TYPES.HOUSEMAN_ORDER);
  const staff = {};
  const durations = [];
  let completed = 0;
  let unable = 0;
  rows.forEach(data => {
    const status = String(data['처리상태'] || '').trim().toUpperCase();
    const employeeNo = String(data['처리자사번'] || data['배정사번'] || data['대상사번'] || '').trim();
    const group = employeeNo ? dailyCloseStaffSeed_(staff, employeeNo, users) : null;
    if (group) group.total = Number(group.total || 0) + 1;
    if (status === 'COMPLETED') {
      completed += 1;
      if (group) group.completed = Number(group.completed || 0) + 1;
    }
    if (status === 'UNABLE') {
      unable += 1;
      if (group) group.unable = Number(group.unable || 0) + 1;
    }
    const duration = minutesBetween_(
      String(data['처리시작일시'] || data['접수일시'] || data['등록일시'] || '').trim(),
      String(data['완료일시'] || '').trim()
    );
    if (Number.isFinite(duration)) {
      durations.push(duration);
      if (group) {
        if (!group.durations) group.durations = [];
        group.durations.push(duration);
      }
    }
  });
  return {
    total: rows.length,
    completed,
    unable,
    averageMinutes: durations.length ? roundDailyCloseNumber_(durations.reduce((sum, value) => sum + value, 0) / durations.length) : null,
    staffSummary: Object.values(staff).map(group => ({
      employeeNo: group.employeeNo,
      name: group.name,
      job: group.job,
      total: Number(group.total || 0),
      completed: Number(group.completed || 0),
      unable: Number(group.unable || 0),
      averageMinutes: group.durations && group.durations.length
        ? roundDailyCloseNumber_(group.durations.reduce((sum, value) => sum + value, 0) / group.durations.length)
        : null
    })).sort((a, b) => b.total - a.total || a.name.localeCompare(b.name, 'ko'))
  };
}

function buildDailyCloseDepartureDelayStats_(historyRows) { // (퇴실지연 고유 객실 집계)
  const keys = new Set();
  historyRows.forEach(data => {
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.DEPARTURE_DELAY) return;
    keys.add(`${String(data['사업장'] || '').trim()}|${String(data['객실번호'] || '').trim()}`);
  });
  return { count: keys.size };
}

function buildDailyCloseValidation_(currentRows) { // (마감 전 상태 정합성 검사)
  const issues = [];
  currentRows.forEach(data => {
    const roomNo = String(data['객실번호'] || '').trim();
    const roomStatus = String(data['객실상태'] || '').trim().toUpperCase();
    const cleaningStatus = String(data['청소상태'] || '').trim().toUpperCase();
    if (roomStatus === 'RECHECKIN' && !isCleaningCompletedStatus_(cleaningStatus)) {
      issues.push({ roomNo, code: 'RECHECKIN_NOT_COMPLETED', message: '재입실 객실이 청소완료가 아닙니다.' });
    }
    if (isNovaRoomCleaningTargetStatus_(roomStatus) && isCleaningCompletedStatus_(cleaningStatus)) {
      issues.push({ roomNo, code: 'TARGET_ALREADY_COMPLETED', message: '정비완료 객실이 공실로 전환되지 않았습니다.' });
    }
  });
  return { ok: issues.length === 0, issueCount: issues.length, issues: issues.slice(0, 200) };
}

function readDailyCloseSummaries_(businessDate, site) { // (업무일자 저장 마감요약 조회)
  return readDailyCloseSummaryRows_().filter(item => item.businessDate === businessDate && (!site || item.site === site));
}

function readDailyCloseSummaryRows_() { // (전체 저장 마감요약 읽기)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  if (sheet.getLastRow() < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const rowCount = sheet.getLastRow() - 1;
  const typeColumn = headerMap['기록구분'];
  const statusColumn = headerMap['처리상태'];
  const deletedColumn = headerMap['삭제여부'];
  if (!typeColumn || !statusColumn) return [];
  const typeValues = sheet.getRange(2, typeColumn, rowCount, 1).getDisplayValues();
  const statusValues = sheet.getRange(2, statusColumn, rowCount, 1).getDisplayValues();
  const deletedValues = deletedColumn ? sheet.getRange(2, deletedColumn, rowCount, 1).getDisplayValues() : [];
  const selected = [];
  for (let index = 0; index < rowCount; index += 1) {
    if (String(typeValues[index][0] || '').trim() !== NOVA.RECORD_TYPES.DAILY_CLOSE) continue;
    if (String(statusValues[index][0] || '').trim() !== NOVA_DAILY_CLOSE.SUMMARY_STATUS) continue;
    if (deletedValues.length && String(deletedValues[index][0] || 'N').trim().toUpperCase() === 'Y') continue;
    selected.push(index + 2);
  }
  if (!selected.length) return [];
  return readRowsByNumbersForClose_(sheet, headerMap, selected).map(data => {
    let detail = {};
    try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    if (detail.roommaidCloseJournal) detail.roommaidCloseJournal = expandRoommaidCloseJournalFromStorage_(detail.roommaidCloseJournal);
    return Object.assign({}, detail, {
      businessDate: String(data['업무일자'] || detail.businessDate || '').trim(),
      site: String(data['사업장'] || detail.site || '').trim(),
      closedAt: String(detail.closedAt || data['등록일시'] || '').trim(),
      closedBy: String(detail.closedBy || data['등록사번'] || '').trim()
    });
  });
}

function markExistingDailyCloseDeleted_(sheet, businessDate, site, updatedAt) { // (기존 마감 스냅샷 소프트삭제)
  if (sheet.getLastRow() < 2) return 0;
  const headerMap = getHeaderMap_(sheet);
  const rowCount = sheet.getLastRow() - 1;
  const values = sheet.getRange(2, 1, rowCount, sheet.getLastColumn()).getDisplayValues();
  const deletedColumn = headerMap['삭제여부'];
  const updatedColumn = headerMap['수정일시'];
  const matched = [];
  values.forEach((row, index) => {
    const data = rowObjectFromValues_(row, headerMap);
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.DAILY_CLOSE) return;
    if (String(data['업무일자'] || '').trim() !== businessDate) return;
    if (String(data['사업장'] || '').trim() !== site) return;
    if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') return;
    matched.push(index + 2);
  });
  matched.forEach(rowNumber => {
    if (deletedColumn) sheet.getRange(rowNumber, deletedColumn).setValue('Y');
    if (updatedColumn) sheet.getRange(rowNumber, updatedColumn).setValue(updatedAt);
  });
  return matched.length;
}

function aggregateDailyCloseSummaries_(items) { // (다수 사업장·날짜 마감요약 합산)
  const summaries = (items || []).filter(Boolean);
  const totals = {
    siteCount: new Set(summaries.map(item => item.site).filter(Boolean)).size,
    recordCount: summaries.length,
    totalRooms: 0,
    previousStock: 0,
    scheduledDepartures: 0,
    recheckin: 0,
    cleaningCompleted: 0,
    recognizedUnits: 0,
    normalCompleted: 0,
    dsCompleted: 0,
    stockRemaining: 0,
    dueOutRemaining: 0,
    checkedOutWaiting: 0,
    vacantClean: 0,
    qmCompleted: 0,
    qmRework: 0,
    qmDefectCount: 0,
    housemanCompleted: 0,
    housemanUnable: 0,
    departureDelayCount: 0,
    validationIssues: 0
  };
  summaries.forEach(item => {
    Object.keys(totals).forEach(key => {
      if (['siteCount', 'recordCount'].includes(key)) return;
      if (key === 'validationIssues') {
        totals.validationIssues += Number(item.validation && item.validation.issueCount || 0);
      } else {
        totals[key] += Number(item[key] || 0);
      }
    });
  });
  totals.recognizedUnits = roundDailyCloseNumber_(totals.recognizedUnits);
  return totals;
}

function dailyCloseBuildingSeed_(building) { // (동별 마감집계 초기값)
  return { building: building || '미지정', total: 0, stockRemaining: 0, dueOutRemaining: 0, checkedOutWaiting: 0, vacantClean: 0, cleaningCompleted: 0 };
}

function dailyCloseStaffSeed_(map, employeeNo, users) { // (직원별 마감집계 초기값)
  const key = String(employeeNo || '').trim();
  if (!map[key]) {
    const user = users[key];
    map[key] = {
      employeeNo: key,
      name: user ? user.name : key,
      job: user ? user.job : '',
      assigned: 0,
      completedPrimary: 0,
      completedSecondary: 0,
      pairParticipation: 0,
      pairRooms: 0,
      trainingRooms: 0,
      recognizedUnits: 0
    };
  }
  return map[key];
}

function chunkArray_(items, size) { // (배열 고정크기 분할)
  const result = [];
  for (let index = 0; index < items.length; index += size) result.push(items.slice(index, index + size));
  return result;
}

function dailyCloseSafeId_(value) { // (기록ID 안전문자 변환)
  return String(value || '').replace(/[^0-9A-Za-z가-힣]/g, '').slice(0, 20) || 'SITE';
}

function dailyCloseAssignmentCreditShares_(assignmentType, primaryEmployeeNo, secondaryEmployeeNo) { // (마감통계 배정유형별 개인 인정 정비수 배분)
  const type = String(assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
  const primaryNo = String(primaryEmployeeNo || '').trim();
  const secondaryNo = String(secondaryEmployeeNo || '').trim();
  const validPair = Boolean(primaryNo && secondaryNo && primaryNo !== secondaryNo);
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR && validPair) {
    return { primary: 0.5, secondary: 0.5 };
  }
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING && validPair) {
    return { primary: 1, secondary: 0 };
  }
  return { primary: 1, secondary: 0 };
}

function roundDailyCloseCredit_(value) { // (개인 인정 정비수 0.001 단위 보존)
  return Math.round(Number(value || 0) * 1000) / 1000;
}

function roundDailyCloseNumber_(value) { // (마감 소수점 한 자리 정리)
  return Math.round(Number(value || 0) * 10) / 10;
}

function compareDailyCloseBuilding_(a, b) { // (동 번호 정렬)
  const an = Number(String(a || '').replace(/\D/g, ''));
  const bn = Number(String(b || '').replace(/\D/g, ''));
  if (Number.isFinite(an) && Number.isFinite(bn) && an !== bn) return an - bn;
  return String(a || '').localeCompare(String(b || ''), 'ko');
}

function latestText_(values) { // (문자열 시각 최신값)
  return (values || []).map(value => String(value || '').trim()).filter(Boolean).sort().slice(-1)[0] || '';
}

function dailyCloseSourceLabel_(items) { // (일별 마감자료 출처 판정)
  if (!items.length) return 'NONE';
  if (items.every(item => item.source === 'CLOSED')) return 'CLOSED';
  if (items.every(item => item.source === 'LIVE')) return 'LIVE';
  return 'MIXED';
}

function writeDailyCloseOverviewToMonthlySheet_(sheet, close) { // (월별조회 시트 마감요약 출력)
  const summary = close && close.summary ? close.summary : {};
  sheet.getRange('K10:R20').clearContent().clearFormat();
  sheet.getRange('K10:R10').setValues([[
    '마감상태', '전일재고', '당일퇴실', '청소완료', '인정정비수', '미완료재고', '하우스맨완료', '퇴실지연'
  ]]);
  const status = close && close.source === 'CLOSED'
    ? '마감완료'
    : close && close.source === 'MIXED'
      ? '일부마감'
      : close && close.source === 'LIVE'
        ? '실시간'
        : '자료없음';
  sheet.getRange('K11:R11').setValues([[
    status,
    Number(summary.previousStock || 0),
    Number(summary.scheduledDepartures || 0),
    Number(summary.cleaningCompleted || 0),
    Number(summary.recognizedUnits || 0),
    Number(summary.stockRemaining || 0),
    Number(summary.housemanCompleted || 0),
    Number(summary.departureDelayCount || 0)
  ]]);
  sheet.getRange('K10:R10').setFontWeight('bold').setBackground('#dbeafe').setHorizontalAlignment('center');
  sheet.getRange('K11:R11').setFontWeight('bold').setHorizontalAlignment('center');
  sheet.getRange('K13').setValue(close && close.period === 'DAILY' ? `마감업무일자: ${close.businessDate || ''}` : `마감저장일수: ${Number(close && close.closedDays || 0)}일`);
  if (close && close.closedAt) sheet.getRange('K14').setValue(`마감저장시각: ${close.closedAt}`);
  if (close && close.message) sheet.getRange('K15').setValue(close.message);
}
