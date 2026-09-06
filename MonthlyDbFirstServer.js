/**
 * 월별조회 PostgreSQL 우선 조회 브리지.
 * native_complete=true인 업무일자/사업장만 DB가 원본이 되고,
 * 나머지는 기존 Sheet 업무이력을 그대로 사용합니다.
 */
function novaMonthlyHistoryDbFirstEnabled_() { // MONTHLY_HISTORY_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_MONTHLY_HISTORY_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaMonthlyHistoryDbRead_(token, payload) { // MONTHLY_HISTORY_DB_FIRST_V1
  const safe = payload || {};
  return novaRealtimeUserRpc_(token, 'nova_monthly_history_v1', {
    p_start_date: String(safe.startDate || '').trim(),
    p_end_date: String(safe.endDate || safe.startDate || '').trim(),
    p_site: String(safe.site || '').trim()
  });
}
