/**
 * 룸메이드 개인실적 PostgreSQL 우선 조회 브리지.
 * ADMIN/ORDER는 기존 월별 DB-first 경로를 재사용하고,
 * ROOMMAID는 본인 청소이력만 반환하는 전용 RPC를 사용합니다.
 */
function novaRoommaidPerformanceDbFirstEnabled_() { // ROOMMAID_PERFORMANCE_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_ROOMMAID_PERFORMANCE_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaRoommaidPerformanceDbRead_(token, payload) { // ROOMMAID_PERFORMANCE_DB_FIRST_V1
  const safe = payload || {};
  return novaRealtimeUserRpc_(token, 'nova_roommaid_performance_history_v1', {
    p_start_date: String(safe.startDate || '').trim(),
    p_end_date: String(safe.endDate || safe.startDate || '').trim(),
    p_site: String(safe.site || '').trim(),
    p_employee_no: String(safe.employeeNo || '').trim()
  });
}

function readRoommaidPerformanceHistoryDbFirst_(request, token) { // ROOMMAID_PERFORMANCE_DB_FIRST_V1
  const role = String(request && request.requesterRole || '').trim().toUpperCase();
  if (role !== 'ROOMMAID') {
    if (typeof readMonthlyHistoryRowsDbFirst_ === 'function') {
      return readMonthlyHistoryRowsDbFirst_(request, [NOVA.RECORD_TYPES.CLEANING], token);
    }
    return readMonthlyHistoryRows_(request, [NOVA.RECORD_TYPES.CLEANING]);
  }

  const sheetRows = readMonthlyHistoryRows_(request, [NOVA.RECORD_TYPES.CLEANING]);
  if (!token || !novaRoommaidPerformanceDbFirstEnabled_()) return sheetRows;
  if (typeof novaRoommaidPerformanceDbRead_ !== 'function') return sheetRows;

  const range = monthlyHistoryDbDateRange_(request);
  try {
    const result = novaRoommaidPerformanceDbRead_(token, {
      startDate: range.startDate,
      endDate: range.endDate,
      site: String(request.site || '').trim(),
      employeeNo: String(request.employeeNo || '').trim()
    });
    const nativeKeys = new Set((Array.isArray(result && result.nativeKeys) ? result.nativeKeys : [])
      .map(item => `${String(item && item.businessDate || '').trim()}|${String(item && item.site || '').trim()}`)
      .filter(key => key !== '|'));
    if (!nativeKeys.size) return sheetRows;

    const keptSheet = sheetRows.filter(row => {
      const data = row && row.data ? row.data : {};
      const key = `${String(data['업무일자'] || '').trim()}|${String(data['사업장'] || '').trim()}`;
      return !nativeKeys.has(key);
    });
    const dbRows = (Array.isArray(result && result.items) ? result.items : [])
      .filter(data => String(data && data['기록구분'] || '').trim() === NOVA.RECORD_TYPES.CLEANING)
      .map((data, index) => ({
        rowNumber: -(index + 1),
        data: Object.assign({}, data, { __NOVA_DB_FIRST: 'Y' })
      }));
    return keptSheet.concat(dbRows);
  } catch (error) {
    console.warn('[NOVA ROOMMAID PERFORMANCE DB read fallback]', error && error.message ? error.message : error);
    return sheetRows;
  }
}
