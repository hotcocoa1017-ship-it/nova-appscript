/** ROOMMAID_CLOSE_READ_PERFORMANCE_V3
 * Read-only performance helpers for the roommaid close journal.
 * Business logic remains in 19_RoommaidCloseJournal.js.
 */
function readRoomMasterIndexForCloseCached_(site) { // ROOMMAID_CLOSE_MASTER_CACHE_V1
  const siteText = String(site || '').trim();
  const configVersion = getSyncVersion_(['CONFIG'], '', '');
  const cacheKey = buildDeltaCacheKey_('ROOMMAID_CLOSE_MASTER_V1', [
    NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION, siteText, configVersion
  ]);
  const cached = getCachedJson_(cacheKey);
  if (cached && cached.byRoomNo && cached.maintenanceTypes && cached.buildings) return cached;
  const master = readRoomMasterIndexForClose_(siteText);
  putCachedJson_(cacheKey, master, 300);
  return master;
}
