/** NOVA_ROOMMAID_REPORTING_DB_FIRST_V2 */
function readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, site) {
  const db = novaDbFirstRpc_(token, 'nova_roommaid_close_history_v1', {
    p_business_date: normalizeBusinessDate_(businessDate),
    p_site: String(site || '').trim()
  }, { readOnly: true, allowLegacyFallback: true });
  if (db && db.legacyFallback) return readRoommaidCloseHistoryBundleFast_(businessDate, site);
  if (!db || db.nativeComplete !== true) return readRoommaidCloseHistoryBundleFast_(businessDate, site);

  const close = novaDbFirstRpc_(token, 'nova_daily_close_read_v1', {
    p_start_date: normalizeBusinessDate_(businessDate),
    p_end_date: normalizeBusinessDate_(businessDate),
    p_site: String(site || '').trim()
  }, { readOnly: true, allowLegacyFallback: true });
  const savedItem = close && !close.legacyFallback && Array.isArray(close.items)
    ? close.items.find(item => String(item && item.site || '').trim() === String(site || '').trim())
    : null;
  return {
    historyRows: Array.isArray(db.items) ? db.items : [],
    saved: savedItem ? novaDailyCloseDbSummary_(savedItem) : null,
    dbFirst: true,
    nativeComplete: true,
    stateVersion: Number(db.stateVersion || 0)
  };
}
