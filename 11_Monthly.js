/**
 * 월별 룸메이드·QM·하우스맨 통합 이력조회
 * 신규 시트를 추가하지 않고 기존 업무이력·월별조회 시트만 사용합니다.
 */
const NOVA_MONTHLY_EXPORT_HEADERS = Object.freeze([
  '업무일자', '업무구분', '사업장', '객실번호', '담당자', '처리상태',
  '정비유형', '인정정비수', '업무내용', '등록일시', '시작일시', '완료일시', '소요시간(분)', '중요', '인수인계'
]);

function getMonthlyHistory(token, filters) { // (월별 이력 페이지 조회)
  return measureResponse_('getMonthlyHistory', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(filters, user);
    const bundle = buildMonthlyHistoryBundle_(request);
    const pageCount = Math.max(1, Math.ceil(bundle.items.length / request.pageSize));
    const page = Math.min(request.page, pageCount);
    const start = (page - 1) * request.pageSize;
    const pageItems = bundle.items.slice(start, start + request.pageSize);

    return {
      ok: true,
      filters: Object.assign({}, request, { page }),
      summary: bundle.summary,
      staffSummary: bundle.staffSummary,
      qmQuality: bundle.qmQuality,
      options: bundle.options,
      pagination: {
        page,
        pageSize: request.pageSize,
        total: bundle.items.length,
        pageCount
      },
      items: pageItems,
      close: request.type === 'CLEANING' ? buildDailyCloseOverviewForRequest_(request) : {},
      serverTime: nowText_()
    };
  });
}

function cancelMonthlyManagedHousemanOrder(token, payload) { // (월별조회 하우스맨 오더취소 · 이력 보존)
  return measureResponse_('cancelMonthlyManagedHousemanOrder', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    if (!orderId) throw new Error('취소할 오더 번호가 없습니다.');

    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const found = findHousemanOrderRow_(sheet, orderId, Number(safe.rowNumber || 0));
      if (!found) throw new Error('하우스맨 오더를 찾을 수 없습니다.');
      if (String(found.data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.HOUSEMAN_ORDER) {
        throw new Error('하우스맨 오더만 취소할 수 있습니다.');
      }
      if (String(found.data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') {
        throw new Error('이미 삭제된 오더입니다.');
      }

      const statusCode = String(found.data['처리상태'] || '').trim().toUpperCase();
      if (statusCode === 'CANCELLED') {
        return { ok: true, orderId, alreadyCancelled: true, message: '이미 취소된 오더입니다.' };
      }
      if (!['REGISTERED', 'ASSIGNED'].includes(statusCode)
          || String(found.data['접수일시'] || '').trim()
          || String(found.data['처리시작일시'] || '').trim()
          || String(found.data['완료일시'] || '').trim()) {
        throw new Error('접수 또는 처리가 시작된 오더는 취소할 수 없습니다.');
      }

      let detail = {};
      try { detail = JSON.parse(String(found.data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
      const version = reserveDataVersion_({ lockHeld: true });
      const now = nowText_();
      detail = Object.assign({}, detail, {
        cancelled: true,
        cancelledAt: now,
        cancelledBy: user.employeeNo,
        cancelSource: 'MONTHLY_HISTORY'
      });

      updateRowByHeaders_(sheet, found.rowNumber, {
        '처리상태': 'CANCELLED',
        '세부내용JSON': JSON.stringify(detail),
        '수정일시': now,
        '변경버전': version
      });

      const users = getUserIndex_().byEmployeeNo;
      const statusCodeMap = {};
      getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
      statusCodeMap.CANCELLED = '오더취소';
      const updatedData = Object.assign({}, found.data, {
        '처리상태': 'CANCELLED',
        '세부내용JSON': JSON.stringify(detail),
        '수정일시': now,
        '변경버전': version
      });
      const order = housemanOrderObject_(updatedData, found.rowNumber, users, statusCodeMap);
      const auditRow = buildHousemanAuditRow_(sheet, order, 'CANCELLED', user.employeeNo, version, {
        source: 'MONTHLY_HISTORY',
        reason: 'ORDER_CANCELLED_BY_MANAGER'
      });
      const auditRowNumber = sheet.getLastRow() + 1;
      ensureSheetRowCapacity_(sheet, auditRowNumber);
      sheet.getRange(auditRowNumber, 1, 1, auditRow.length).setValues([auditRow]);
      SpreadsheetApp.flush();

      publishDataVersion_(version, {
        domains: ['ORDER'],
        businessDate: String(found.data['업무일자'] || '').trim(),
        site: String(found.data['사업장'] || '').trim(),
        lockHeld: true
      });

      return {
        ok: true,
        orderId,
        version,
        order,
        message: `${String(found.data['객실번호'] || '').trim()}호 오더를 취소했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function deleteMonthlyHousemanOrder(token, payload) { // (월별조회 하우스맨 오더 소프트삭제 · 감사이력 유지)
  return measureResponse_('deleteMonthlyHousemanOrder', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    if (!orderId) throw new Error('삭제할 오더 번호가 없습니다.');

    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const found = findHousemanOrderRow_(sheet, orderId, Number(safe.rowNumber || 0));
      if (!found) throw new Error('하우스맨 오더를 찾을 수 없습니다.');
      if (String(found.data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') {
        return { ok: true, orderId, alreadyDeleted: true, message: '이미 삭제된 오더입니다.' };
      }
      if (String(found.data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.HOUSEMAN_ORDER) {
        throw new Error('하우스맨 오더만 삭제할 수 있습니다.');
      }

      const statusCode = String(found.data['처리상태'] || '').trim().toUpperCase();
      if (!['REGISTERED', 'ASSIGNED', 'CANCELLED'].includes(statusCode)) {
        throw new Error('접수 또는 처리가 시작된 오더는 삭제할 수 없습니다.');
      }
      if (String(found.data['접수일시'] || '').trim()
          || String(found.data['처리시작일시'] || '').trim()
          || String(found.data['완료일시'] || '').trim()) {
        throw new Error('접수 또는 처리가 시작된 오더는 삭제할 수 없습니다.');
      }

      const users = getUserIndex_().byEmployeeNo;
      const statusCodeMap = {};
      getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
      statusCodeMap.CANCELLED = '오더취소';
      const current = housemanOrderObject_(found.data, found.rowNumber, users, statusCodeMap);
      const version = reserveDataVersion_({ lockHeld: true });
      const now = nowText_();

      updateRowByHeaders_(sheet, found.rowNumber, {
        '삭제여부': 'Y',
        '수정일시': now,
        '변경버전': version
      });

      const auditRow = buildHousemanAuditRow_(sheet, current, 'DELETED', user.employeeNo, version, {
        source: 'MONTHLY_HISTORY',
        reason: 'ORDER_DELETED_BY_MANAGER',
        previousStatus: statusCode
      });
      const auditRowNumber = sheet.getLastRow() + 1;
      ensureSheetRowCapacity_(sheet, auditRowNumber);
      sheet.getRange(auditRowNumber, 1, 1, auditRow.length).setValues([auditRow]);
      SpreadsheetApp.flush();

      publishDataVersion_(version, {
        domains: ['ORDER'],
        businessDate: String(found.data['업무일자'] || '').trim(),
        site: String(found.data['사업장'] || '').trim(),
        lockHeld: true
      });

      return {
        ok: true,
        orderId,
        version,
        message: `${String(found.data['객실번호'] || '').trim()}호 오더를 삭제했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}


function getMonthlyHousemanAutoAssignment(token, payload) { // (월별조회 자동배정 후보 사전확정)
  return measureResponse_('getMonthlyHousemanAutoAssignment', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!businessDate || !site || !roomNo) {
      throw new Error('자동배정 확인에 필요한 업무일자·사업장·객실번호가 없습니다.');
    }
    const assignment = resolveHousemanAutoAssignee_(businessDate, site, roomNo);
    return {
      ok: true,
      businessDate,
      site,
      roomNo,
      assignment
    };
  });
}

function getMonthlyHousemanOrderOptions(token) { // (월별조회 하우스맨 등록창 코드옵션 직접 조회)
  return measureResponse_('getMonthlyHousemanOrderOptions', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    let codeIndex = getCodeIndex_();
    let orderParts = Array.isArray(codeIndex['하우스맨파트']) ? codeIndex['하우스맨파트'] : [];
    let orderItems = Array.isArray(codeIndex['하우스맨품목']) ? codeIndex['하우스맨품목'] : [];

    if (!orderParts.length || !orderItems.length) {
      CacheService.getScriptCache().remove('NOVA_CODE_INDEX_V2');
      codeIndex = getCodeIndex_();
      orderParts = Array.isArray(codeIndex['하우스맨파트']) ? codeIndex['하우스맨파트'] : [];
      orderItems = Array.isArray(codeIndex['하우스맨품목']) ? codeIndex['하우스맨품목'] : [];
    }

    return {
      ok: true,
      orderParts,
      orderItems,
      housemen: getPublicStaffList_(['HOUSEMAN']), // MONTHLY_HOUSEMAN_MANAGEMENT_V1
      sites: getMonthlyConfiguredSites_()
    };
  });
}

function getMonthlyHistoryExport(token, filters) { // (월별 이력 엑셀용 전체 조회)
  return measureResponse_('getMonthlyHistoryExport', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(Object.assign({}, filters, { page: 1, pageSize: 500 }), user);
    const bundle = buildMonthlyHistoryBundle_(request);
    if (bundle.items.length > 20000) {
      throw new Error('조회 결과가 20,000건을 초과합니다. 사업장·직원·상태 조건을 추가해 범위를 줄여주세요.');
    }
    return {
      ok: true,
      filename: buildMonthlyFilename_(request, 'xls'),
      headers: NOVA_MONTHLY_EXPORT_HEADERS,
      rows: bundle.items.map(monthlyExportRow_),
      summary: bundle.summary
    };
  });
}

function writeMonthlyViewSheet(token, filters) { // (웹 조회조건을 월별조회 시트에 반영)
  return measureResponse_('writeMonthlyViewSheet', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(Object.assign({}, filters, { page: 1, pageSize: 500 }), user);
    const bundle = buildMonthlyHistoryBundle_(request);
    if (bundle.items.length > 20000) {
      throw new Error('월별조회 시트에 표시할 데이터가 20,000건을 초과합니다. 조회조건을 좁혀주세요.');
    }
    writeMonthlyViewSheetData_(request, bundle);
    return {
      ok: true,
      message: `월별조회 시트에 ${bundle.items.length.toLocaleString('ko-KR')}건을 반영했습니다.`,
      count: bundle.items.length
    };
  });
}

function refreshMonthlyViewSheet() { // (스프레드시트 메뉴에서 월별조회 새로고침)
  const request = readMonthlyViewSheetFilters_();
  const bundle = buildMonthlyHistoryBundle_(request);
  if (bundle.items.length > 20000) {
    throw new Error('월별조회 결과가 20,000건을 초과합니다. 사업장·직원·상태 조건을 추가해 주세요.');
  }
  writeMonthlyViewSheetData_(request, bundle);
  SpreadsheetApp.getActive().toast(
    `월별조회 ${bundle.items.length.toLocaleString('ko-KR')}건 반영 완료`,
    NOVA.APP_NAME,
    5
  );
  return { ok: true, count: bundle.items.length, summary: bundle.summary };
}

function onOpen() { // (스프레드시트 NOVA 메뉴 구성)
  SpreadsheetApp.getUi()
    .createMenu('NOVA')
    .addItem('월별조회 새로고침', 'refreshMonthlyViewSheet')
    .addSeparator()
    .addItem('사용자·코드 캐시 갱신', 'clearNovaCaches_')
    .addToUi();
}

function normalizeMonthlyFilters_(filters, user) { // (월별·일별 조회조건 정리)
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
  const allowedTypes = new Set(['ALL', 'CLEANING', 'QM', 'HOUSEMAN']);
  const type = String(safe.type || 'ALL').trim().toUpperCase();
  return {
    period,
    date,
    year,
    month,
    type: allowedTypes.has(type) ? type : 'ALL',
    site: String(safe.site || '').trim(),
    employeeNo: String(safe.employeeNo || '').trim(),
    status: String(safe.status || '').trim(),
    search: String(safe.search || '').trim().toLowerCase(),
    page: Math.max(1, Number(safe.page || 1)),
    pageSize: Math.max(20, Math.min(500, Number(safe.pageSize || 100))),
    requestedBy: user && user.employeeNo ? user.employeeNo : ''
  };
}

function normalizeMonthlyDate_(value, fallbackYear, fallbackMonth) { // (일별 조회일자 정규화)
  const text = String(value || '').trim();
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const probe = new Date(Date.UTC(year, month - 1, day));
    if (
      probe.getUTCFullYear() === year &&
      probe.getUTCMonth() + 1 === month &&
      probe.getUTCDate() === day
    ) return text;
  }
  const today = businessDateText_();
  if (
    Number(today.slice(0, 4)) === Number(fallbackYear) &&
    Number(today.slice(5, 7)) === Number(fallbackMonth)
  ) return today;
  return `${String(fallbackYear).padStart(4, '0')}-${String(fallbackMonth).padStart(2, '0')}-01`;
}

function monthlyRecordTypesForType_(type) { // (월별조회 소분류별 실제 조회 기록구분)
  const normalized = String(type || 'ALL').trim().toUpperCase();
  if (normalized === 'HOUSEMAN') return [NOVA.RECORD_TYPES.HOUSEMAN_ORDER];
  if (normalized === 'CLEANING') return [NOVA.RECORD_TYPES.CLEANING];
  if (normalized === 'QM') return [NOVA.RECORD_TYPES.QM, NOVA.RECORD_TYPES.QM_CHECKLIST];
  return [
    NOVA.RECORD_TYPES.CLEANING,
    NOVA.RECORD_TYPES.QM,
    NOVA.RECORD_TYPES.QM_CHECKLIST,
    NOVA.RECORD_TYPES.HOUSEMAN_ORDER
  ];
}

function buildMonthlyHistoryBundle_(request) { // (월별 이력 조회·필터·집계)
  const rawRows = readMonthlyHistoryRows_(request, monthlyRecordTypesForType_(request.type));
  const users = getUserIndex_().byEmployeeNo;
  const orderStatusMap = {};
  getCodes_('하우스맨상태').forEach(code => { orderStatusMap[code.code] = code.label; });

  const typedItems = rawRows
    .map(row => monthlyHistoryItem_(row.data, row.rowNumber, users, orderStatusMap))
    .filter(Boolean)
    .filter(item => request.type === 'ALL' || item.typeCode === request.type)
    .filter(item => !request.search || monthlyItemSearchText_(item).includes(request.search));

  const options = buildMonthlyOptions_(typedItems, users);
  options.sites = Array.from(new Set([...(options.sites || []), ...getMonthlyConfiguredSites_()]))
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b, 'ko'));
  if (request.type === 'HOUSEMAN') {
    options.orderParts = getCodes_('하우스맨파트');
    options.orderItems = getCodes_('하우스맨품목');
    options.housemen = getPublicStaffList_(['HOUSEMAN']); // MONTHLY_HOUSEMAN_MANAGEMENT_V1
  }
  const scopedItems = typedItems
    .filter(item => !request.site || item.site === request.site)
    .filter(item => !request.employeeNo || item.employeeNos.includes(request.employeeNo));
  const filtered = scopedItems
    .filter(item => monthlyStatusMatches_(item, request.status))
    .sort(compareMonthlyItems_);

  return {
    items: filtered,
    summary: buildMonthlySummary_(filtered),
    staffSummary: buildMonthlyStaffSummary_(filtered, users),
    qmQuality: request.type === 'QM'
      ? buildQmQualityAnalyticsFromHistoryRows_(rawRows.map(row => row.data), users, request)
      : {},
    options
  };
}

function readMonthlyHistoryRows_(request, allowedRecordTypesOverride) { // (업무이력 월·일 행 선별·행 인덱스 캐시)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  const headerMap = getHeaderMap_(sheet);
  const allowedRecordTypes = new Set(
    (allowedRecordTypesOverride && allowedRecordTypesOverride.length
      ? allowedRecordTypesOverride
      : [
          NOVA.RECORD_TYPES.CLEANING,
          NOVA.RECORD_TYPES.QM,
          NOVA.RECORD_TYPES.QM_CHECKLIST,
          NOVA.RECORD_TYPES.HOUSEMAN_ORDER
        ])
      .map(value => String(value || '').trim())
      .filter(Boolean)
  );
  const rowNumbers = getMonthlyHistoryRowNumbers_(sheet, headerMap, request, allowedRecordTypes);
  if (!rowNumbers.length) return [];

  const groups = groupConsecutiveRows_(rowNumbers);
  const headerCount = sheet.getLastColumn();
  const result = [];
  if (groups.length > 40) {
    const startRow = rowNumbers[0];
    const endRow = rowNumbers[rowNumbers.length - 1];
    const allValues = sheet.getRange(startRow, 1, endRow - startRow + 1, headerCount).getDisplayValues();
    const wanted = new Set(rowNumbers);
    allValues.forEach((row, offset) => {
      const rowNumber = startRow + offset;
      if (wanted.has(rowNumber)) result.push({ rowNumber, data: rowObjectFromValues_(row, headerMap) });
    });
    return result;
  }

  groups.forEach(group => {
    const values = sheet.getRange(group.start, 1, group.count, headerCount).getDisplayValues();
    values.forEach((row, offset) => {
      result.push({ rowNumber: group.start + offset, data: rowObjectFromValues_(row, headerMap) });
    });
  });
  return result;
}

function getMonthlyHistoryRowNumbers_(sheet, headerMap, request, allowedRecordTypes) { // (월·일 업무이력 대상행 캐시)
  const typeColumn = headerMap['기록구분'];
  const dateColumn = headerMap['업무일자'];
  const deletedColumn = headerMap['삭제여부'];
  if (!typeColumn || !dateColumn) return [];

  const typeKey = Array.from(allowedRecordTypes).sort().join(',');
  const periodKey = request.period === 'DAILY'
    ? String(request.date || '')
    : `${request.year}-${String(request.month).padStart(2, '0')}`;
  const cacheKey = `NOVA_HISTORY_ROWS_RC6:${getDataVersion_()}:${periodKey}:${Utilities.base64EncodeWebSafe(typeKey).slice(0, 48)}`;
  const cache = CacheService.getScriptCache();
  const cached = cache.get(cacheKey);
  if (cached) {
    try { return JSON.parse(cached); } catch (error) { /* 캐시 손상 시 재구성 */ }
  }

  const rowCount = sheet.getLastRow() - 1;
  const typeValues = sheet.getRange(2, typeColumn, rowCount, 1).getDisplayValues();
  const dateValues = sheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const deletedValues = deletedColumn
    ? sheet.getRange(2, deletedColumn, rowCount, 1).getDisplayValues()
    : Array.from({ length: rowCount }, () => ['N']);
  const prefix = `${request.year}-${String(request.month).padStart(2, '0')}-`;
  const exactDate = request.period === 'DAILY' ? request.date : '';
  const rowNumbers = [];

  for (let index = 0; index < rowCount; index += 1) {
    const recordType = String(typeValues[index][0] || '').trim();
    const businessDate = String(dateValues[index][0] || '').trim();
    const deleted = String(deletedValues[index][0] || 'N').trim().toUpperCase();
    const dateMatches = exactDate ? businessDate === exactDate : businessDate.startsWith(prefix);
    if (allowedRecordTypes.has(recordType) && dateMatches && deleted !== 'Y') {
      rowNumbers.push(index + 2);
    }
  }

  const serialized = JSON.stringify(rowNumbers);
  if (serialized.length <= Number(NOVA.CACHE_MAX_CHARS || 90000)) {
    cache.put(cacheKey, serialized, Number(NOVA.HISTORY_INDEX_CACHE_SECONDS || 300));
  }
  return rowNumbers;
}

function groupConsecutiveRows_(rowNumbers) { // (연속 행 구간 묶기)
  const groups = [];
  rowNumbers.forEach(rowNumber => {
    const last = groups[groups.length - 1];
    if (last && last.start + last.count === rowNumber) {
      last.count += 1;
    } else {
      groups.push({ start: rowNumber, count: 1 });
    }
  });
  return groups;
}

function monthlyHistoryItem_(data, rowNumber, users, orderStatusMap) { // (업무이력 행을 월별조회 객체로 변환) // MONTHLY_HOUSEMAN_COLUMNS_V1
  const recordType = String(data['기록구분'] || '').trim();
  const typeCodeMap = {
    [NOVA.RECORD_TYPES.CLEANING]: 'CLEANING',
    [NOVA.RECORD_TYPES.QM]: 'QM',
    [NOVA.RECORD_TYPES.HOUSEMAN_ORDER]: 'HOUSEMAN'
  };
  const typeCode = typeCodeMap[recordType];
  if (!typeCode) return null;

  let detail = {};
  try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
  const photos = typeCode === 'HOUSEMAN' && Array.isArray(detail.photos)
    ? detail.photos
        .filter(photo => photo && photo.fileId)
        .slice(0, NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER)
        .map(photo => ({
          fileId: String(photo.fileId || ''),
          name: String(photo.name || ''),
          mimeType: String(photo.mimeType || 'image/jpeg'),
          size: Number(photo.size || 0),
          uploadedAt: String(photo.uploadedAt || '')
        }))
    : [];
  const targetEmployeeNo = String(data['대상사번'] || '').trim();
  const assignedEmployeeNo = String(data['배정사번'] || '').trim();
  const processorEmployeeNo = String(data['처리자사번'] || '').trim();
  const registeredEmployeeNo = String(data['등록사번'] || detail.registeredBy || detail.registeredEmployeeNo || '').trim();
  const qmReceiverEmployeeNo = typeCode === 'QM' && !processorEmployeeNo && !assignedEmployeeNo && !targetEmployeeNo
    ? registeredEmployeeNo
    : '';
  const employeeNos = Array.from(new Set([targetEmployeeNo, assignedEmployeeNo, processorEmployeeNo, qmReceiverEmployeeNo].filter(Boolean)));
  const primaryEmployeeNo = processorEmployeeNo || assignedEmployeeNo || targetEmployeeNo || qmReceiverEmployeeNo;
  const primaryUser = users[primaryEmployeeNo];
  const acceptedByEmployeeNo = String(detail.acceptedByEmployeeNo || '').trim(); // MONTHLY_HOUSEMAN_COLUMNS_V1
  const handlerEmployeeNo = processorEmployeeNo || acceptedByEmployeeNo;
  const registeredByUser = users[registeredEmployeeNo];
  const handlerUser = users[handlerEmployeeNo];
  const statusCode = String(data['처리상태'] || '').trim().toUpperCase();
  const statusLabel = monthlyStatusLabel_(typeCode, statusCode, orderStatusMap);
  const registeredAt = String(data['등록일시'] || '').trim();
  const acceptedAt = String(data['접수일시'] || '').trim();
  const startedAt = String(data['처리시작일시'] || '').trim();
  const completedAt = String(data['완료일시'] || '').trim();
  const durationMinutes = typeCode === 'HOUSEMAN'
    ? minutesBetween_(startedAt || acceptedAt || registeredAt, completedAt)
    : typeCode === 'QM'
      ? (Number.isFinite(Number(detail.durationMinutes)) ? Number(detail.durationMinutes) : minutesBetween_(startedAt || registeredAt, completedAt || String(data['수정일시'] || '').trim()))
      : null;
  const cleaningType = typeCode === 'CLEANING'
    ? String(detail.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase()
    : '';
  const cleaningTypeLabel = cleaningType ? getRoommaidCleaningTypeLabel_(cleaningType) : '';
  const creditUnit = typeCode === 'CLEANING' && ['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(statusCode)
    ? getRoommaidCleaningCreditUnit_(cleaningType)
    : 0;
  const housemanItems = typeCode === 'HOUSEMAN'
    ? (Array.isArray(detail.items) && detail.items.length
        ? detail.items.map(item => ({ name: String(item && item.name || '').trim(), quantity: Math.max(1, Number(item && item.quantity || 1)) })).filter(item => item.name)
        : (String(data['품목'] || '').trim() ? [{ name: String(data['품목'] || '').trim(), quantity: Math.max(1, Number(data['수량'] || 1)) }] : []))
    : [];
  const housemanPreStart = typeCode === 'HOUSEMAN'
    && ['REGISTERED', 'ASSIGNED'].includes(statusCode)
    && !acceptedAt && !startedAt && !completedAt;
  const canEdit = typeCode === 'HOUSEMAN' && ['REGISTERED', 'ASSIGNED', 'ACCEPTED'].includes(statusCode) && !startedAt && !completedAt;
  const canAssign = housemanPreStart;
  const canCancel = housemanPreStart;
  const canDelete = typeCode === 'HOUSEMAN'
    && (housemanPreStart || (statusCode === 'CANCELLED' && !acceptedAt && !startedAt && !completedAt));

  return {
    rowNumber,
    recordId: String(data['기록ID'] || '').trim(),
    typeCode,
    typeLabel: monthlyTypeLabel_(typeCode),
    businessDate: String(data['업무일자'] || '').trim(),
    site: String(data['사업장'] || '').trim(),
    roomNo: String(data['객실번호'] || '').trim(),
    employeeNos,
    employeeNo: primaryEmployeeNo,
    employeeName: primaryUser ? primaryUser.name : (primaryEmployeeNo || '-'),
    employeeDisplay: primaryUser ? `${primaryUser.name} (${primaryEmployeeNo})` : (primaryEmployeeNo || '-'),
    registeredByEmployeeNo: registeredEmployeeNo, // MONTHLY_HOUSEMAN_COLUMNS_V1
    registeredByName: registeredByUser ? registeredByUser.name : (registeredEmployeeNo || '-'),
    acceptedByEmployeeNo,
    handlerEmployeeNo,
    handlerName: handlerUser ? handlerUser.name : (handlerEmployeeNo || '-'),
    statusCode,
    statusLabel,
    requestSource: String(detail.requestSource || '').trim(),
    version: Number(data['변경버전'] || 0), // MONTHLY_HOUSEMAN_MANAGEMENT_V1
    assignedEmployeeNo,
    assignedName: assignedEmployeeNo && users[assignedEmployeeNo] ? users[assignedEmployeeNo].name : (assignedEmployeeNo || ''),
    items: housemanItems,
    note: String(data['추가내용'] || '').trim(),
    canManage: typeCode === 'HOUSEMAN',
    canEdit,
    canAssign,
    canCancel,
    canDelete,
    detailText: monthlyDetailText_(typeCode, data, detail, statusLabel),
    registeredAt,
    acceptedAt,
    startedAt,
    completedAt,
    eventAt: completedAt || startedAt || acceptedAt || String(data['수정일시'] || registeredAt).trim(),
    durationMinutes,
    cleaningType,
    cleaningTypeLabel,
    creditUnit,
    part: String(data['파트'] || '').trim(),
    itemSummary: String(data['품목'] || '').trim(),
    requester: String(data['요청자'] || detail.requester || '').trim(),
    photos,
    photoCount: photos.length,
    important: String(data['중요여부'] || '').trim().toUpperCase() === 'Y',
    handover: String(data['인수인계여부'] || '').trim().toUpperCase() === 'Y'
  };
}

function monthlyStatusLabel_(typeCode, statusCode, orderStatusMap) { // (월별 상태 표시명)
  if (typeCode === 'HOUSEMAN') {
    if (statusCode === 'CANCELLED') return '오더취소'; // MONTHLY_HOUSEMAN_MANAGEMENT_V1
    return orderStatusMap[statusCode] || statusCode || '-';
  }
  const labels = {
    ASSIGN_ROOMMAID: '룸메이드 배정', CLEANING_START: '청소 시작', CLEANING_COMPLETE: '청소 완료',
    ROOMMAID_START: '청소 시작', ROOMMAID_COMPLETE: '청소 완료', CLEAR_ASSIGNMENT: '배정 초기화',
    QM_ASSIGN: 'QM 배정', QM_WAITING: 'QM 대기', QM_CLEAR: 'QM 배정 취소', QM_START: 'QM 점검 시작',
    QM_COMPLETE: 'QM 완료', QM_REWORK: '재정비 요청'
  };
  return labels[statusCode] || statusCode || '-';
}

function monthlyTypeLabel_(typeCode) { // (월별 업무구분 표시명)
  return { CLEANING: '룸메이드', QM: 'QM', HOUSEMAN: '하우스맨' }[typeCode] || typeCode;
}

function monthlyDetailText_(typeCode, data, detail, statusLabel) { // (월별 리스트 업무내용)
  if (typeCode === 'HOUSEMAN') {
    return [String(data['파트'] || '').trim(), String(data['품목'] || '').trim(), String(data['추가내용'] || '').trim()]
      .filter(Boolean).join(' · ') || statusLabel;
  }
  const reason = String(detail.reason || '').trim();
  const cleaningStatus = String(detail.cleaningStatus || '').trim();
  return [detail.cleaningType ? getRoommaidCleaningTypeLabel_(detail.cleaningType) : '', statusLabel, cleaningStatus, reason].filter(Boolean).join(' · ');
}

function monthlyItemSearchText_(item) { // (월별 검색 문자열)
  return [
    item.businessDate, item.typeLabel, item.site, item.roomNo, item.employeeDisplay,
    item.statusLabel, item.cleaningTypeLabel, item.detailText, item.part, item.itemSummary, item.requester
  ].join(' ').toLowerCase();
}

function getMonthlyConfiguredSites_() { // (이력 유무와 무관한 객실 사업장 목록)
  const cache = CacheService.getScriptCache();
  const cacheKey = 'NOVA_MONTHLY_CONFIGURED_SITES_V79';
  const cached = cache.get(cacheKey);
  if (cached) {
    try {
      const parsed = JSON.parse(cached);
      if (Array.isArray(parsed)) return parsed;
    } catch (error) { /* 캐시 손상 시 재구성 */ }
  }

  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const siteColumn = headerMap['사업장'];
  if (!siteColumn) return [];

  const sites = Array.from(new Set(
    sheet.getRange(2, siteColumn, lastRow - 1, 1)
      .getDisplayValues()
      .map(row => String(row[0] || '').trim())
      .filter(Boolean)
  )).sort((a, b) => a.localeCompare(b, 'ko'));

  try { cache.put(cacheKey, JSON.stringify(sites), 300); } catch (error) { /* 캐시 저장 실패 무시 */ }
  return sites;
}

function buildMonthlyOptions_(items, users) { // (월별 필터 선택 목록)
  const sites = Array.from(new Set(items.map(item => item.site).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'ko'));
  const statuses = Array.from(new Map(items.map(item => [item.statusCode, { code: item.statusCode, label: item.statusLabel }])).values())
    .sort((a, b) => a.label.localeCompare(b.label, 'ko'));
  const employeeNumbers = new Set();
  items.forEach(item => item.employeeNos.forEach(employeeNo => employeeNumbers.add(employeeNo)));
  const employees = Array.from(employeeNumbers)
    .map(employeeNo => {
      const user = users[employeeNo];
      return { employeeNo, name: user ? user.name : employeeNo, job: user ? user.job : '' };
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  return { sites, statuses, employees };
}

function buildMonthlyStaffSummary_(items, users) { // (직원별 처리건수·평균시간 집계)
  const groups = {};
  items.forEach(item => {
    if (item.typeCode === 'HOUSEMAN' && item.statusCode === 'CANCELLED') return; // MONTHLY_HOUSEMAN_MANAGEMENT_V1
    const employeeNo = String(item.employeeNo || '').trim();
    if (!employeeNo) return;
    if (!groups[employeeNo]) {
      const user = users[employeeNo];
      groups[employeeNo] = {
        employeeNo,
        name: user ? user.name : employeeNo,
        job: user ? user.job : '',
        total: 0,
        completed: 0,
        unable: 0,
        durations: [],
        recognizedUnits: 0
      };
    }
    const group = groups[employeeNo];
    group.total += 1;
    group.recognizedUnits += Number(item.creditUnit || 0);
    if (monthlyItemCompleted_(item)) group.completed += 1;
    if (item.typeCode === 'HOUSEMAN' && item.statusCode === 'UNABLE') group.unable += 1;
    if (Number.isFinite(item.durationMinutes) && item.durationMinutes >= 0) group.durations.push(item.durationMinutes);
  });
  return Object.values(groups).map(group => ({
    employeeNo: group.employeeNo,
    name: group.name,
    job: group.job,
    total: group.total,
    completed: group.completed,
    unable: group.unable,
    recognizedUnits: Math.round(group.recognizedUnits * 10) / 10,
    averageMinutes: group.durations.length
      ? Math.round((group.durations.reduce((sum, value) => sum + value, 0) / group.durations.length) * 10) / 10
      : null
  })).sort((a, b) => b.total - a.total || a.name.localeCompare(b.name, 'ko'));
}

function monthlyStatusMatches_(item, status) { // (정확 상태·요약 상태 필터)
  const value = String(status || '').trim();
  if (!value || value === '전체') return true;
  if (value === '완료') return monthlyItemCompleted_(item);
  if (value === '진행중') return !monthlyItemCompleted_(item);
  if (value === '처리불가') return item.typeCode === 'HOUSEMAN' && item.statusCode === 'UNABLE';
  return item.statusCode === value || item.statusLabel === value;
}

function buildMonthlySummary_(items) { // (월별 조회 요약 집계)
  const completed = items.filter(monthlyItemCompleted_).length;
  const unable = items.filter(item => item.typeCode === 'HOUSEMAN' && item.statusCode === 'UNABLE').length;
  const durations = items.map(item => item.durationMinutes).filter(value => Number.isFinite(value) && value >= 0);
  const recognizedUnits = Math.round(items.reduce((sum, item) => sum + Number(item.creditUnit || 0), 0) * 10) / 10;
  const averageMinutes = durations.length
    ? Math.round((durations.reduce((sum, value) => sum + value, 0) / durations.length) * 10) / 10
    : null;
  return {
    total: items.length,
    completed,
    active: Math.max(0, items.filter(item => !monthlyItemCompleted_(item) && !(item.typeCode === 'HOUSEMAN' && item.statusCode === 'CANCELLED')).length), // MONTHLY_HOUSEMAN_MANAGEMENT_V1
    unable,
    uniqueRooms: new Set(items.map(item => `${item.site}|${item.roomNo}`).filter(value => !value.endsWith('|'))).size,
    uniqueStaff: new Set(items.flatMap(item => item.employeeNos)).size,
    recognizedUnits,
    averageMinutes
  };
}

function monthlyItemCompleted_(item) { // (월별 완료 여부 판단)
  if (item.typeCode === 'HOUSEMAN') return ['COMPLETED', 'UNABLE'].includes(item.statusCode);
  return ['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE', 'QM_COMPLETE'].includes(item.statusCode);
}

function compareMonthlyItems_(a, b) { // (월별 최신순 정렬)
  return String(b.businessDate).localeCompare(String(a.businessDate))
    || String(b.eventAt).localeCompare(String(a.eventAt))
    || String(a.roomNo).localeCompare(String(b.roomNo), 'ko', { numeric: true });
}

function minutesBetween_(startText, endText) { // (문자열 시각 간 분 계산)
  const start = parseNovaDateTime_(startText);
  const end = parseNovaDateTime_(endText);
  if (!start || !end || end < start) return null;
  return Math.round(((end.getTime() - start.getTime()) / 60000) * 10) / 10;
}

function parseNovaDateTime_(value) { // (NOVA 일시 문자열 Date 변환)
  const text = String(value || '').trim();
  if (!text) return null;
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/);
  if (!match) return null;
  return new Date(Date.UTC(
    Number(match[1]), Number(match[2]) - 1, Number(match[3]),
    Number(match[4]) - 9, Number(match[5]), Number(match[6])
  ));
}

function monthlyExportRow_(item) { // (엑셀·시트 공통 출력 행)
  return [
    item.businessDate,
    item.typeLabel,
    item.site,
    item.roomNo,
    item.employeeDisplay,
    item.statusLabel,
    item.cleaningTypeLabel || '',
    Number(item.creditUnit || 0) || '',
    item.detailText,
    item.registeredAt,
    item.startedAt || item.acceptedAt,
    item.completedAt,
    Number.isFinite(item.durationMinutes) ? item.durationMinutes : '',
    item.important ? 'Y' : '',
    item.handover ? 'Y' : ''
  ];
}

function buildMonthlyFilename_(request, extension) { // (월별·일별 다운로드 파일명)
  const typeLabel = { ALL: '전체', CLEANING: '룸메이드', QM: 'QM', HOUSEMAN: '하우스맨' }[request.type] || '전체';
  const site = request.site || '전체사업장';
  const periodText = request.period === 'DAILY'
    ? request.date
    : `${request.year}-${String(request.month).padStart(2, '0')}`;
  return `NOVA_${periodText}_${site}_${typeLabel}.${extension}`;
}

function configureMonthlyViewV2_() { // (이전 버전 호환용 월별조회 구성)
  return configureMonthlyViewV3_();
}

function configureMonthlyViewV3_() { // (월별조회 시트 월별·일별 선택영역 구성)
  const sheet = getRequiredSheet_(NOVA.SHEETS.MONTHLY);
  const headers = ['조회방식', '조회연도', '조회월', '조회일자', '조회구분', '사업장', '직원', '상태', '검색어'];
  const readColumnCount = Math.max(headers.length, sheet.getLastColumn(), 1);
  const previousHeaders = sheet.getRange(1, 1, 1, readColumnCount).getDisplayValues()[0];
  const previousValues = sheet.getRange(2, 1, 1, readColumnCount).getDisplayValues()[0];

  const now = new Date();
  const today = Utilities.formatDate(now, NOVA.TIMEZONE, NOVA.DATE_FORMAT);
  const defaultYear = Number(Utilities.formatDate(now, NOVA.TIMEZONE, 'yyyy'));
  const defaultMonth = Number(Utilities.formatDate(now, NOVA.TIMEZONE, 'M'));
  let values;

  if (String(previousHeaders[0] || '').trim() === '조회방식') {
    values = [
      previousValues[0] || '월별',
      previousValues[1] || defaultYear,
      previousValues[2] || defaultMonth,
      monthlySheetDateObject_(previousValues[3] || today),
      previousValues[4] || '전체',
      previousValues[5] || '전체',
      previousValues[6] || '전체',
      previousValues[7] || '전체',
      previousValues[8] || ''
    ];
  } else if (String(previousHeaders[0] || '').trim() === '조회연도') {
    // Sprint 5~8.5 시트: 연도/월/조회구분/사업장/직원/상태/검색어
    values = [
      '월별',
      previousValues[0] || defaultYear,
      previousValues[1] || defaultMonth,
      monthlySheetDateObject_(today),
      previousValues[2] || '전체',
      previousValues[3] || '전체',
      previousValues[4] || '전체',
      previousValues[5] || '전체',
      previousValues[6] || ''
    ];
  } else {
    values = [
      '월별',
      defaultYear,
      defaultMonth,
      monthlySheetDateObject_(today),
      '전체',
      '전체',
      '전체',
      '전체',
      ''
    ];
  }

  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(2, 1, 1, headers.length).setValues([values]);
  sheet.getRange('D2').setNumberFormat('yyyy-mm-dd');

  const years = Array.from({ length: 8 }, (_, index) => defaultYear - 6 + index);
  const sites = ['전체'].concat(getSiteList_());
  const employees = ['전체'].concat(
    getPublicStaffList_(['ROOMMAID', 'QM', 'HOUSEMAN']).map(user => `${user.name} (${user.employeeNo})`)
  );
  sheet.getRange('A2').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(['월별', '일별'], true).build());
  sheet.getRange('B2').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(years.map(String), true).build());
  sheet.getRange('C2').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(Array.from({ length: 12 }, (_, index) => String(index + 1)), true).build());
  sheet.getRange('D2').setDataValidation(SpreadsheetApp.newDataValidation().requireDate().setAllowInvalid(false).build());
  sheet.getRange('E2').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(['전체', '룸메이드', 'QM', '하우스맨'], true).build());
  sheet.getRange('F2').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(sites, true).build());
  sheet.getRange('G2').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(employees, true).build());
  sheet.getRange('H2').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(['전체', '완료', '진행중', '처리불가'], true).build());

  const outputHeaders = NOVA_MONTHLY_EXPORT_HEADERS;
  sheet.getRange(4, 1, 1, outputHeaders.length).setValues([outputHeaders]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold').setBackground('#e5e7eb').setHorizontalAlignment('center');
  sheet.getRange(4, 1, 1, outputHeaders.length).setFontWeight('bold').setBackground('#171717').setFontColor('#ffffff').setHorizontalAlignment('center');
  sheet.setFrozenRows(4);
  sheet.setFrozenColumns(4);
  sheet.getRange('K1').setValue('사용방법');
  sheet.getRange('K2').setValue('A2에서 월별/일별 선택 → 조건 입력 → NOVA 메뉴 → 월별조회 새로고침');
  sheet.getRange('K1').setFontWeight('bold');
  sheet.autoResizeColumns(1, Math.min(outputHeaders.length, 13));
}

function monthlySheetDateObject_(value) { // (월별조회 시트 날짜 셀용 Date 변환)
  const normalized = normalizeMonthlyDate_(value, Number(businessDateText_().slice(0, 4)), Number(businessDateText_().slice(5, 7)));
  const parts = normalized.split('-').map(Number);
  return new Date(parts[0], parts[1] - 1, parts[2], 12, 0, 0);
}

function readMonthlyViewSheetFilters_() { // (월별조회 시트의 월별·일별 선택조건 읽기)
  const sheet = getRequiredSheet_(NOVA.SHEETS.MONTHLY);
  configureMonthlyViewV3_();
  const values = sheet.getRange(2, 1, 1, 9).getDisplayValues()[0];
  const typeMap = { '전체': 'ALL', '룸메이드': 'CLEANING', 'QM': 'QM', '하우스맨': 'HOUSEMAN' };
  const employeeMatch = String(values[6] || '').match(/\(([^()]+)\)$/);
  let status = String(values[7] || '').trim();
  if (status === '전체') status = '';
  return normalizeMonthlyFilters_({
    period: String(values[0] || '').trim() === '일별' ? 'DAILY' : 'MONTHLY',
    year: values[1],
    month: values[2],
    date: values[3],
    type: typeMap[String(values[4] || '').trim()] || 'ALL',
    site: String(values[5] || '').trim() === '전체' ? '' : values[5],
    employeeNo: employeeMatch ? employeeMatch[1] : '',
    status,
    search: values[8],
    page: 1,
    pageSize: 500
  }, null);
}

function writeMonthlyViewSheetData_(request, bundle) { // (월별조회 시트 월별·일별 목록·요약 쓰기)
  const sheet = getRequiredSheet_(NOVA.SHEETS.MONTHLY);
  configureMonthlyViewV3_();
  const typeLabel = { ALL: '전체', CLEANING: '룸메이드', QM: 'QM', HOUSEMAN: '하우스맨' }[request.type] || '전체';
  const employee = request.employeeNo
    ? (getUserIndex_().byEmployeeNo[request.employeeNo]
      ? `${getUserIndex_().byEmployeeNo[request.employeeNo].name} (${request.employeeNo})`
      : request.employeeNo)
    : '전체';
  sheet.getRange(2, 1, 1, 9).setValues([[
    request.period === 'DAILY' ? '일별' : '월별',
    request.year,
    request.month,
    monthlySheetDateObject_(request.date),
    typeLabel,
    request.site || '전체',
    employee,
    request.status || '전체',
    request.search || ''
  ]]);
  sheet.getRange('D2').setNumberFormat('yyyy-mm-dd');

  const lastRow = Math.max(sheet.getLastRow(), 5);
  if (lastRow >= 5) {
    sheet.getRange(
      5,
      1,
      lastRow - 4,
      Math.max(sheet.getLastColumn(), NOVA_MONTHLY_EXPORT_HEADERS.length)
    ).clearContent();
  }
  const rows = bundle.items.map(monthlyExportRow_);
  if (rows.length) {
    ensureSheetRowCapacity_(sheet, rows.length + 4);
    sheet.getRange(5, 1, rows.length, NOVA_MONTHLY_EXPORT_HEADERS.length).setValues(rows);
  }
  sheet.getRange('K4:P4').setValues([['전체', '완료', '진행', '처리불가', '객실수', '평균(분)']]);
  sheet.getRange('K5:P5').setValues([[
    bundle.summary.total,
    bundle.summary.completed,
    bundle.summary.active,
    bundle.summary.unable,
    bundle.summary.uniqueRooms,
    bundle.summary.averageMinutes === null ? '' : bundle.summary.averageMinutes
  ]]);
  sheet.getRange('K4:P4').setFontWeight('bold').setBackground('#e5e7eb').setHorizontalAlignment('center');
  sheet.getRange('K5:P5').setFontWeight('bold').setHorizontalAlignment('center');
  sheet.getRange('K7').setValue(`조회범위: ${request.period === 'DAILY' ? request.date : `${request.year}-${String(request.month).padStart(2, '0')}`}`);
  sheet.getRange('K8').setValue(`최종 조회: ${nowText_()}`);
  writeDailyCloseOverviewToMonthlySheet_(sheet, buildDailyCloseOverviewForRequest_(request));
  sheet.autoResizeColumns(1, NOVA_MONTHLY_EXPORT_HEADERS.length);
}
