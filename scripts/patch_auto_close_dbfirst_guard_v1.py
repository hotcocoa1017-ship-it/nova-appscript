from pathlib import Path

p = Path('15_AdminSettings.js')
s = p.read_text(encoding='utf-8')

s = s.replace(
"""function runAutomaticDailyCloseNow(token) { // (관리자 자동마감 즉시 시험)\n  requireRole_(token, ['ADMIN']);\n  return processAutomaticDailyClose({ force: true, invokedBy: 'ADMIN_TEST' });\n}\n""",
"""function runAutomaticDailyCloseNow(token) { // (관리자 자동마감 즉시 시험 · AUTO_CLOSE_DB_FIRST_GUARD_V1)\n  requireRole_(token, ['ADMIN']);\n  return processAutomaticDailyClose({ force: true, invokedBy: 'ADMIN_TEST', dbToken: token });\n}\n"""
)

start = s.index("function processAutomaticDailyClose(options) {")
end = s.index("\nfunction ensureAutomaticDailyCloseTrigger_()", start)
new_fn = r'''function processAutomaticDailyClose(options) { // (설정시각 기준 미마감 사업장 자동 저장 · AUTO_CLOSE_DB_FIRST_GUARD_V1)
  const safe = options || {};
  const force = safe.force === true;
  const enabled = getOperationSetting_('AUTO_CLOSE_ENABLED', 'N') === 'Y';
  if (!enabled && !force) return { ok: true, skipped: true, reason: 'DISABLED' };
  const now = new Date();
  const businessDate = businessDateText_(); // 공통 09:00 업무일자 기준
  const currentTime = Utilities.formatDate(now, NOVA.TIMEZONE, 'HH:mm');
  const closeTime = getOperationSetting_('AUTO_CLOSE_TIME', '23:50');
  if (!force && currentTime < closeTime) return { ok: true, skipped: true, reason: 'BEFORE_TIME', businessDate, currentTime, closeTime };

  const dbFirstRequired = typeof novaDailyCloseDbFirstEnabled_ === 'function' && novaDailyCloseDbFirstEnabled_();
  const dbToken = String(safe.dbToken || '').trim();

  // DB-primary에서는 무인 시간트리거가 Sheet만 단독 마감해 split-brain을 만들지 못하게 합니다.
  // 관리자 즉시시험은 로그인 토큰을 전달하므로 DB source -> DB close -> Sheet mirror 경로를 그대로 사용합니다.
  if (dbFirstRequired && !dbToken) {
    const error = new Error('DB-primary 자동마감은 안전한 system DB endpoint가 연결되기 전까지 무인 실행을 차단합니다. 관리자 즉시시험 또는 수동 마감을 사용해 주세요.');
    notifyAutomaticCloseFailure_(businessDate, error);
    return { ok: false, skipped: true, reason: 'DB_SYSTEM_ENDPOINT_REQUIRED', businessDate, closeTime, message: error.message };
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return { ok: false, skipped: true, reason: 'LOCKED' };
  try {
    if (dbFirstRequired && dbToken) {
      const configuredSites = getSiteList_();
      const dbSources = {};
      configuredSites.forEach(site => {
        const source = tryNovaDailyCloseDbSource_(dbToken, businessDate, site);
        if (source && source.ready) dbSources[site] = source;
      });
      const sourceSites = Object.keys(dbSources);
      if (!sourceSites.length) throw new Error(`${businessDate} DB에 자동마감 가능한 사업장이 없습니다.`);

      const savedDb = readDailyCloseDbSnapshots_(dbToken, businessDate, businessDate, '');
      const closedSites = new Set(savedDb.map(item => String(item.site || '').trim()).filter(Boolean));
      const pendingSites = sourceSites.filter(site => !closedSites.has(site));
      if (!pendingSites.length) return { ok: true, skipped: true, reason: 'ALREADY_CLOSED', businessDate, sites: sourceSites, dbFirst: true };

      const systemUser = { employeeNo: 'SYSTEM', name: '자동마감', role: 'ADMIN' };
      const results = pendingSites.map(site => saveDailyCloseSnapshotForSite_(businessDate, site, systemUser, {
        currentRows: dbSources[site].currentRows,
        historyRows: dbSources[site].historyRows,
        dbToken,
        dbSource: true
      }));
      PropertiesService.getScriptProperties().deleteProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_KEY');
      PropertiesService.getScriptProperties().deleteProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_TEXT');
      return { ok: true, businessDate, closeTime, sites: results, dbFirst: true, message: `${businessDate} ${results.length}개 사업장을 DB-first로 자동 마감했습니다.` };
    }

    // Realtime/DB-first가 꺼진 레거시 모드에서만 기존 Sheet 자동마감을 유지합니다.
    const sites = getCurrentSitesForDate_(businessDate);
    if (!sites.length) throw new Error(`${businessDate} 현재객실현황에 자동마감할 사업장이 없습니다.`);
    const saved = readDailyCloseSummaries_(businessDate, '');
    const closedSites = new Set(saved.map(item => item.site));
    const pendingSites = sites.filter(site => !closedSites.has(site));
    if (!pendingSites.length) return { ok: true, skipped: true, reason: 'ALREADY_CLOSED', businessDate, sites };
    const allCurrentRows = readCurrentRowsForClose_(businessDate, '');
    const allHistoryRows = readHistoryRowsForClose_(businessDate, '');
    const systemUser = { employeeNo: 'SYSTEM', name: '자동마감', role: 'ADMIN' };
    const results = pendingSites.map(site => saveDailyCloseSnapshotForSite_(businessDate, site, systemUser, {
      currentRows: allCurrentRows.filter(data => String(data['사업장'] || '').trim() === site),
      historyRows: allHistoryRows.filter(data => String(data['사업장'] || '').trim() === site)
    }));
    PropertiesService.getScriptProperties().deleteProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_KEY');
    PropertiesService.getScriptProperties().deleteProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_TEXT');
    return { ok: true, businessDate, closeTime, sites: results, dbFirst: false, message: `${businessDate} ${results.length}개 사업장을 자동 마감했습니다.` };
  } catch (error) {
    notifyAutomaticCloseFailure_(businessDate, error);
    throw error;
  } finally {
    lock.releaseLock();
  }
}
'''
s = s[:start] + new_fn + s[end:]
p.write_text(s, encoding='utf-8')
print('patched automatic close DB-first guard')
