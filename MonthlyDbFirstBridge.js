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

function getMonthlyHistoryDbFirst(token, filters) {
  return measureResponse_('getMonthlyHistoryDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(filters, user);
    request.__dbFirstToken = token;
    const bundle = buildMonthlyHistoryBundle_(request);
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
    const bundle = buildMonthlyHistoryBundle_(request);
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
    const bundle = buildMonthlyHistoryBundle_(request);
    if (bundle.items.length > 20000) throw new Error('월별조회 시트에 표시할 데이터가 20,000건을 초과합니다. 조회조건을 좁혀주세요.');
    writeMonthlyViewSheetData_(request, bundle);
    return { ok: true, dbFirst: true, message: `월별조회 시트에 ${bundle.items.length.toLocaleString('ko-KR')}건을 반영했습니다.`, count: bundle.items.length };
  });
}
