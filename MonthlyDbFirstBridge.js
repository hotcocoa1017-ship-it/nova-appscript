/** NOVA_MONTHLY_DB_FIRST_V2 */
function readMonthlyHistoryRowsDbFirst_(token, request, allowedRecordTypesOverride) {
  const startDate = request.period === 'DAILY'
    ? request.date
    : `${request.year}-${String(request.month).padStart(2, '0')}-01`;
  const endDate = request.period === 'DAILY'
    ? request.date
    : Utilities.formatDate(new Date(request.year, request.month, 0), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
  const db = novaDbFirstRpc_(token, 'nova_monthly_history_v1', {
    p_start_date: startDate,
    p_end_date: endDate,
    p_site: request.site
  }, { readOnly: true, allowLegacyFallback: true });
  if (db && db.legacyFallback) return readMonthlyHistoryRowsLegacy_(request, allowedRecordTypesOverride);

  const allowed = new Set((allowedRecordTypesOverride && allowedRecordTypesOverride.length
    ? allowedRecordTypesOverride
    : monthlyRecordTypesForType_(request.type)).map(value => String(value || '').trim()).filter(Boolean));
  const nativeKeys = new Set((Array.isArray(db && db.nativeKeys) ? db.nativeKeys : [])
    .map(item => `${String(item && item.businessDate || '').trim()}|${String(item && item.site || '').trim()}`));
  if (!nativeKeys.size) return readMonthlyHistoryRowsLegacy_(request, allowedRecordTypesOverride);

  const dbRows = (Array.isArray(db && db.items) ? db.items : [])
    .filter(data => allowed.has(String(data && data['기록구분'] || '').trim()))
    .map(data => ({ rowNumber: 0, data: data || {}, dbFirst: true }));
  const legacyRows = readMonthlyHistoryRowsLegacy_(request, allowedRecordTypesOverride)
    .filter(row => !nativeKeys.has(`${String(row.data && row.data['업무일자'] || '').trim()}|${String(row.data && row.data['사업장'] || '').trim()}`));
  return legacyRows.concat(dbRows);
}

// MONTHLY_QM_QUALITY_STATUS_V2
// 월별조회 > QM은 점검 시작/완료 타임라인보다 최종 체크리스트 판정(양호/불량)을 우선 표시합니다.
// 업무내용은 해당 점검 직전 최종정비자와 청소완료일을 표시하며 객실상태·QM 최종제출·재정비 로직은 변경하지 않습니다.
function monthlyQmQualityPeriod_(request) {
  const startDate = request.period === 'DAILY'
    ? request.date
    : `${request.year}-${String(request.month).padStart(2, '0')}-01`;
  const endDate = request.period === 'DAILY'
    ? request.date
    : Utilities.formatDate(new Date(request.year, request.month, 0), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
  return { startDate, endDate };
}

function novaMonthlyQmQualityRead_(token, period, site) { // MONTHLY_QM_QUALITY_DIRECT_READ_V2
  let auth;
  try {
    auth = novaDbFirstRealtimeAuth_(token);
  } catch (error) {
    console.warn('[NOVA MONTHLY QM] 품질조회 인증 준비 실패:', error && error.message ? error.message : error);
    return null;
  }
  const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_monthly_qm_quality_v1`;
  const bodyText = JSON.stringify({
    p_start_date: String(period && period.startDate || '').trim(),
    p_end_date: String(period && period.endDate || '').trim(),
    p_site: String(site || '').trim()
  });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    let response;
    try {
      response = UrlFetchApp.fetch(endpoint, {
        method: 'post',
        contentType: 'application/json; charset=utf-8',
        headers: {
          Authorization: `Bearer ${auth.token}`,
          apikey: String(auth.publishableKey || '')
        },
        payload: bodyText,
        muteHttpExceptions: true,
        followRedirects: true
      });
    } catch (networkError) {
      if (attempt < 2) {
        Utilities.sleep([140, 420, 900][attempt] || 900);
        continue;
      }
      console.warn('[NOVA MONTHLY QM] 품질조회 네트워크 실패:', networkError && networkError.message ? networkError.message : networkError);
      return null;
    }
    const status = Number(response.getResponseCode() || 0);
    let data = {};
    try { data = JSON.parse(response.getContentText('UTF-8') || '{}'); } catch (ignore) { data = {}; }
    if (status >= 200 && status < 300 && data && data.ok) return data;
    if (status === 401 && attempt < 2) {
      try { auth = novaDbFirstRealtimeAuth_(token); } catch (error) { return null; }
      Utilities.sleep(120);
      continue;
    }
    if ((status === 429 || status >= 500) && attempt < 2) {
      Utilities.sleep([160, 420, 900][attempt] || 900);
      continue;
    }
    console.warn('[NOVA MONTHLY QM] 품질조회 DB 응답 실패:', status, data && (data.message || data.error || data.hint || data.code) || '');
    return null;
  }
  return null;
}

function monthlyQmQualityFailureText_(inspection) {
  const direct = String(inspection && inspection.failSummary || '').trim();
  if (direct) return direct;
  const parts = [];
  const answers = Array.isArray(inspection && inspection.answers) ? inspection.answers : [];
  answers.forEach(answer => {
    if (String(answer && answer.result || '').trim().toUpperCase() !== 'FAIL') return;
    const label = String(answer && (answer.itemLabel || answer.label || answer.code) || '체크리스트 불량').trim();
    const note = String(answer && answer.note || '').trim();
    parts.push(note ? `${label}: ${note}` : label);
  });
  const defects = Array.isArray(inspection && inspection.defects) ? inspection.defects : [];
  defects.forEach(defect => {
    const label = String(defect && (defect.itemLabel || defect.placeLabel) || '추가 하자').trim();
    const note = String(defect && defect.note || '').trim();
    parts.push(note ? `${label}: ${note}` : label);
  });
  return Array.from(new Set(parts.filter(Boolean))).join(' / ');
}

function monthlyQmQualityRoomKey_(item) {
  return [
    String(item && item.businessDate || '').trim(),
    String(item && item.site || '').trim(),
    String(item && item.roomNo || '').trim()
  ].join('|');
}

function monthlyQmQualityItem_(inspection, users) { // MONTHLY_QM_STATUS_DISPLAY_V2
  const qmEmployeeNo = String(inspection && inspection.qmEmployeeNo || '').trim();
  const user = users[qmEmployeeNo];
  const result = String(inspection && inspection.resultStatus || '').trim().toUpperCase() === 'FAIL' ? 'FAIL' : 'PASS';
  const statusCode = result === 'FAIL' ? 'QM_QUALITY_FAIL' : 'QM_QUALITY_PASS';
  const statusLabel = result === 'FAIL' ? '불량' : '양호';
  const completedAt = String(inspection && inspection.completedAt || '').trim();
  const startedAt = String(inspection && inspection.startedAt || '').trim();
  const roommaidNames = [
    String(inspection && inspection.roommaidName || '').trim(),
    String(inspection && inspection.secondaryRoommaidName || '').trim()
  ].filter(Boolean);
  const roommaidEmployeeNos = [
    String(inspection && inspection.roommaidEmployeeNo || '').trim(),
    String(inspection && inspection.secondaryRoommaidEmployeeNo || '').trim()
  ].filter(Boolean);
  const finalCleanerText = roommaidNames.length
    ? roommaidNames.join(' · ')
    : (roommaidEmployeeNos.length ? roommaidEmployeeNos.join(' · ') : '-');
  const cleaningCompletedAt = String(inspection && inspection.cleaningCompletedAt || '').trim();
  const detailText = `최종정비자 ${finalCleanerText} · 청소완료 ${cleaningCompletedAt || '-'}`;
  return {
    rowNumber: 0,
    recordId: String(inspection && inspection.inspectionId || '').trim(),
    typeCode: 'QM',
    typeLabel: 'QM',
    businessDate: String(inspection && inspection.businessDate || '').trim(),
    site: String(inspection && inspection.site || '').trim(),
    roomNo: String(inspection && inspection.roomNo || '').trim(),
    employeeNos: qmEmployeeNo ? [qmEmployeeNo] : [],
    employeeNo: qmEmployeeNo,
    employeeName: user ? user.name : (qmEmployeeNo || '-'),
    employeeDisplay: user ? `${user.name} (${qmEmployeeNo})` : (qmEmployeeNo || '-'),
    registeredByEmployeeNo: qmEmployeeNo,
    registeredByName: user ? user.name : (qmEmployeeNo || '-'),
    acceptedByEmployeeNo: '',
    handlerEmployeeNo: qmEmployeeNo,
    handlerName: user ? user.name : (qmEmployeeNo || '-'),
    statusCode,
    statusLabel,
    qualityResult: result,
    requestSource: '',
    version: Number(inspection && inspection.sourceVersion || 0),
    assignedEmployeeNo: '',
    assignedName: '',
    items: [],
    note: '',
    canManage: false,
    canEdit: false,
    canAssign: false,
    canCancel: false,
    canDelete: false,
    detailText,
    registeredAt: completedAt,
    acceptedAt: '',
    startedAt,
    completedAt,
    eventAt: completedAt || startedAt,
    durationMinutes: Number.isFinite(Number(inspection && inspection.durationMinutes))
      ? Number(inspection.durationMinutes)
      : minutesBetween_(startedAt, completedAt),
    cleaningType: '',
    cleaningTypeLabel: '',
    creditUnit: 0,
    part: '',
    itemSummary: '',
    requester: '',
    photos: [],
    photoCount: 0,
    important: false,
    handover: false
  };
}

function monthlyQmQualityCompleted_(item) {
  return ['QM_QUALITY_PASS', 'QM_QUALITY_FAIL'].includes(String(item && item.statusCode || '').trim().toUpperCase())
    || monthlyItemCompleted_(item);
}

function monthlyQmQualityStatusMatches_(item, status) {
  const value = String(status || '').trim();
  if (!value || value === '전체') return true;
  if (value === '완료') return monthlyQmQualityCompleted_(item);
  if (value === '진행중') return !monthlyQmQualityCompleted_(item);
  if (value === '양호') return item.statusCode === 'QM_QUALITY_PASS';
  if (value === '불량') return item.statusCode === 'QM_QUALITY_FAIL';
  return item.statusCode === value || item.statusLabel === value;
}

function monthlyQmQualitySummary_(items) {
  const completed = items.filter(monthlyQmQualityCompleted_).length;
  const durations = items.map(item => item.durationMinutes).filter(value => Number.isFinite(value) && value >= 0);
  return {
    total: items.length,
    completed,
    active: Math.max(0, items.length - completed),
    unable: 0,
    uniqueRooms: new Set(items.map(item => `${item.site}|${item.roomNo}`).filter(value => !value.endsWith('|'))).size,
    uniqueStaff: new Set(items.flatMap(item => item.employeeNos || [])).size,
    recognizedUnits: 0,
    averageMinutes: durations.length
      ? Math.round((durations.reduce((sum, value) => sum + value, 0) / durations.length) * 10) / 10
      : null
  };
}

function monthlyQmQualityStaffSummary_(items, users) {
  const groups = {};
  items.forEach(item => {
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
        durations: []
      };
    }
    const group = groups[employeeNo];
    group.total += 1;
    if (monthlyQmQualityCompleted_(item)) group.completed += 1;
    if (Number.isFinite(item.durationMinutes) && item.durationMinutes >= 0) group.durations.push(item.durationMinutes);
  });
  return Object.values(groups).map(group => ({
    employeeNo: group.employeeNo,
    name: group.name,
    job: group.job,
    total: group.total,
    completed: group.completed,
    unable: 0,
    recognizedUnits: 0,
    averageMinutes: group.durations.length
      ? Math.round((group.durations.reduce((sum, value) => sum + value, 0) / group.durations.length) * 10) / 10
      : null
  })).sort((a, b) => b.total - a.total || a.name.localeCompare(b.name, 'ko'));
}

function applyMonthlyQmQualityStatus_(token, request, bundle) {
  if (String(request && request.type || '').trim().toUpperCase() !== 'QM') return bundle;
  const period = monthlyQmQualityPeriod_(request);
  const result = novaMonthlyQmQualityRead_(token, period, request.site);
  if (!result || result.ok === false || !Array.isArray(result.items)) return bundle;

  const users = getUserIndex_().byEmployeeNo;
  const inspections = result.items;
  const finalRoomKeys = new Set(inspections.map(monthlyQmQualityRoomKey_));
  const baseItems = (bundle.items || []).map(item => {
    if (item.typeCode !== 'QM') return item;
    const statusCode = String(item.statusCode || '').trim().toUpperCase();
    if (statusCode === 'QM_START' && !finalRoomKeys.has(monthlyQmQualityRoomKey_(item))) {
      return Object.assign({}, item, { statusCode: 'QM_CHECKING', statusLabel: '점검중', detailText: '점검중' });
    }
    if (statusCode === 'QM_COMPLETE' && !finalRoomKeys.has(monthlyQmQualityRoomKey_(item))) {
      return Object.assign({}, item, { statusLabel: '점검완료', detailText: '점검완료' });
    }
    return item;
  }).filter(item => {
    if (item.typeCode !== 'QM') return true;
    const statusCode = String(item.statusCode || '').trim().toUpperCase();
    return !(finalRoomKeys.has(monthlyQmQualityRoomKey_(item)) && ['QM_START', 'QM_COMPLETE'].includes(statusCode));
  });

  const qualityItems = inspections.map(item => monthlyQmQualityItem_(item, users));
  const candidates = baseItems.concat(qualityItems).sort(compareMonthlyItems_);
  const options = buildMonthlyOptions_(candidates, users);
  options.sites = Array.from(new Set([...(options.sites || []), ...getMonthlyConfiguredSites_()]))
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b, 'ko'));

  const filtered = candidates
    .filter(item => !request.site || item.site === request.site)
    .filter(item => !request.employeeNo || (item.employeeNos || []).includes(request.employeeNo))
    .filter(item => !request.search || monthlyItemSearchText_(item).includes(request.search))
    .filter(item => monthlyQmQualityStatusMatches_(item, request.status))
    .sort(compareMonthlyItems_);

  bundle.items = filtered;
  bundle.summary = monthlyQmQualitySummary_(filtered);
  bundle.staffSummary = monthlyQmQualityStaffSummary_(filtered, users);
  bundle.options = options;
  return bundle;
}

function buildMonthlyHistoryBundleDbFirst_(token, request) {
  if (String(request && request.type || '').trim().toUpperCase() !== 'QM') {
    return buildMonthlyHistoryBundle_(request);
  }
  // 품질상태가 기존 이벤트 필터에서 먼저 제거되지 않도록 QM은 원본 이력을 넓게 읽은 뒤 마지막에 필터합니다.
  const baseRequest = Object.assign({}, request, { employeeNo: '', status: '', search: '' });
  const bundle = buildMonthlyHistoryBundle_(baseRequest);
  return applyMonthlyQmQualityStatus_(token, request, bundle);
}

function getMonthlyHistoryDbFirst(token, filters) {
  return measureResponse_('getMonthlyHistoryDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(filters, user);
    request.__dbFirstToken = token;
    const bundle = buildMonthlyHistoryBundleDbFirst_(token, request);
    const pageCount = Math.max(1, Math.ceil(bundle.items.length / request.pageSize));
    const page = Math.min(request.page, pageCount);
    const start = (page - 1) * request.pageSize;
    return {
      ok: true,
      dbFirst: true,
      filters: Object.assign({}, request, { page, __dbFirstToken: undefined }),
      summary: bundle.summary,
      staffSummary: bundle.staffSummary,
      qmQuality: bundle.qmQuality,
      options: bundle.options,
      pagination: { page, pageSize: request.pageSize, total: bundle.items.length, pageCount },
      items: bundle.items.slice(start, start + request.pageSize),
      close: request.type === 'CLEANING' ? buildDailyCloseOverviewDbFirst_(token, request) : {},
      serverTime: nowText_()
    };
  });
}

function getMonthlyHistoryExportDbFirst(token, filters) {
  return measureResponse_('getMonthlyHistoryExportDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(Object.assign({}, filters, { page: 1, pageSize: 500 }), user);
    request.__dbFirstToken = token;
    const bundle = buildMonthlyHistoryBundleDbFirst_(token, request);
    if (bundle.items.length > 20000) throw new Error('조회 결과가 20,000건을 초과합니다. 사업장·직원·상태 조건을 추가해 범위를 줄여주세요.');
    return {
      ok: true, dbFirst: true,
      filename: buildMonthlyFilename_(request, 'xls'),
      headers: NOVA_MONTHLY_EXPORT_HEADERS,
      rows: bundle.items.map(monthlyExportRow_),
      summary: bundle.summary
    };
  });
}

function writeMonthlyViewSheetDbFirst(token, filters) {
  return measureResponse_('writeMonthlyViewSheetDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(Object.assign({}, filters, { page: 1, pageSize: 500 }), user);
    request.__dbFirstToken = token;
    const bundle = buildMonthlyHistoryBundleDbFirst_(token, request);
    if (bundle.items.length > 20000) throw new Error('월별조회 시트에 표시할 데이터가 20,000건을 초과합니다. 조회조건을 좁혀주세요.');
    writeMonthlyViewSheetData_(request, bundle);
    return { ok: true, dbFirst: true, message: `월별조회 시트에 ${bundle.items.length.toLocaleString('ko-KR')}건을 반영했습니다.`, count: bundle.items.length };
  });
}