/** NOVA_ROOMMAID_REPORTING_DB_FIRST_V4 */
function readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, site) {
  const dateText = normalizeBusinessDate_(businessDate);
  const siteText = String(site || '').trim();
  const db = novaDbFirstRpc_(token, 'nova_roommaid_close_history_v1', {
    p_business_date: dateText,
    p_site: siteText
  }, { readOnly: true, allowLegacyFallback: true });

  if (db && db.legacyFallback) {
    const fast = readRoommaidCloseHistoryBundleFast_(dateText, siteText);
    return Object.assign({}, fast, {
      dbFirst: false,
      nativeComplete: false,
      readPath: String(fast && fast.readPath || 'SHEET_FALLBACK')
    });
  }

  if (!db || db.nativeComplete !== true) {
    const fast = readRoommaidCloseHistoryBundleFast_(dateText, siteText);
    return Object.assign({}, fast, {
      dbFirst: false,
      nativeComplete: false,
      readPath: String(fast && fast.readPath || 'SHEET_INCOMPLETE_FALLBACK'),
      cacheComplete: Boolean(db && db.cacheComplete),
      cacheRows: Number(db && db.cacheRows || 0)
    });
  }

  return {
    historyRows: Array.isArray(db.items) ? db.items : [],
    saved: db.saved ? novaDailyCloseDbSummary_(db.saved) : null,
    dbFirst: true,
    nativeComplete: true,
    stateVersion: Number(db.stateVersion || 0),
    liveNativeReady: Boolean(db.liveNativeReady),
    cacheComplete: Boolean(db.cacheComplete),
    cacheRows: Number(db.cacheRows || 0),
    readPath: 'DB_NATIVE_BUNDLE_V4'
  };
}
