/**
 * 일일/룸메이드 마감 계산용 PostgreSQL source bridge.
 * DB 준비조건을 모두 통과한 업무일자/사업장만 DB current/history를 반환합니다.
 */
function novaDailyCloseSourceDbFirstEnabled_() { // DAILY_CLOSE_SOURCE_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_DAILY_CLOSE_SOURCE_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaDailyCloseDbSource_(token, businessDate, site) { // DAILY_CLOSE_SOURCE_DB_FIRST_V1
  if (!token || !novaDailyCloseSourceDbFirstEnabled_()) {
    return { ok: true, dbFirst: false, ready: false, reasons: ['DISABLED'] };
  }
  return novaRealtimeUserRpc_(token, 'nova_daily_close_source_v1', {
    p_business_date: String(businessDate || '').trim(),
    p_site: String(site || '').trim()
  });
}

function tryNovaDailyCloseDbSource_(token, businessDate, site) { // DAILY_CLOSE_SOURCE_DB_FIRST_V1
  try {
    const result = novaDailyCloseDbSource_(token, businessDate, site);
    if (!result || result.ready !== true) return null;
    const currentRows = Array.isArray(result.currentRows) ? result.currentRows : [];
    const historyRows = Array.isArray(result.historyRows) ? result.historyRows : [];
    if (!currentRows.length) return null;
    return {
      currentRows,
      historyRows,
      metrics: result.metrics && typeof result.metrics === 'object' ? result.metrics : {},
      dbFirst: true,
      ready: true
    };
  } catch (error) {
    console.warn('[NOVA DAILY CLOSE DB source fallback]', error && error.message ? error.message : error);
    return null;
  }
}
