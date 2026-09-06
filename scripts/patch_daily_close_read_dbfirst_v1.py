from pathlib import Path

MARKER = 'DAILY_CLOSE_READ_DB_FIRST_V1'

close_path = Path('14_DailyClose.js')
monthly_path = Path('11_Monthly.js')
roommaid_path = Path('19_RoommaidCloseJournal.js')

close = close_path.read_text(encoding='utf-8')
monthly = monthly_path.read_text(encoding='utf-8')
roommaid = roommaid_path.read_text(encoding='utf-8')


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)

if MARKER not in close:
    close = replace_once(
        close,
        "return Object.assign({ ok: true }, buildDailyCloseOverviewForRequest_(request));",
        "return Object.assign({ ok: true }, buildDailyCloseOverviewForRequest_(request, token)); // DAILY_CLOSE_READ_DB_FIRST_V1",
        'getDailyCloseOverview token'
    )

    close = replace_once(
        close,
        """function buildDailyCloseOverviewForRequest_(request) { // (조회방식별 마감통계 묶음 구성)
  if (request.period === 'DAILY') return buildDailyCloseDailyOverview_(request);
  return buildDailyCloseMonthlyOverview_(request);
}

function buildDailyCloseDailyOverview_(request) { // (일별 저장자료 또는 실시간 마감통계 조회)
  const allCurrentRows = readCurrentRowsForClose_(request.date, request.site);
""",
        """function buildDailyCloseOverviewForRequest_(request, dbToken) { // (조회방식별 마감통계 묶음 구성 · DAILY_CLOSE_READ_DB_FIRST_V1)
  if (request.period === 'DAILY') return buildDailyCloseDailyOverview_(request, dbToken);
  return buildDailyCloseMonthlyOverview_(request, dbToken);
}

function buildDailyCloseDailyOverview_(request, dbToken) { // (일별 저장자료 또는 실시간 마감통계 조회)
  const dbSavedSites = readDailyCloseDbSnapshots_(dbToken, request.date, request.date, request.site);
  // 사업장이 명시됐고 DB 확정본이 있으면 Sheet 전체 조회 없이 즉시 반환합니다.
  if (request.site && dbSavedSites.length) {
    const items = dbSavedSites.map(item => Object.assign({ source: 'CLOSED', dbFirst: true }, item));
    return {
      period: 'DAILY',
      businessDate: request.date,
      site: request.site,
      source: 'CLOSED',
      isClosed: true,
      closedAt: latestText_(items.map(item => item.closedAt)),
      closedBy: items.length === 1 ? String(items[0].closedByName || items[0].closedBy || '') : '',
      summary: aggregateDailyCloseSummaries_(items),
      sites: items,
      dbFirst: true,
      message: ''
    };
  }

  const allCurrentRows = readCurrentRowsForClose_(request.date, request.site);
""",
        'daily overview DB shortcut'
    )

    close = replace_once(
        close,
        """  const savedSites = readDailyCloseSummaries_(request.date, request.site);
  const savedBySite = {};
  savedSites.forEach(item => { savedBySite[item.site] = item; });
""",
        """  const savedSites = mergeDailyCloseSnapshots_(
    readDailyCloseSummaries_(request.date, request.site),
    dbSavedSites
  );
  const savedBySite = {};
  savedSites.forEach(item => { savedBySite[item.site] = item; });
""",
        'daily saved merge'
    )

    close = replace_once(
        close,
        """function buildDailyCloseMonthlyOverview_(request) { // (월별 저장 마감자료 합산)
  const prefix = `${request.year}-${String(request.month).padStart(2, '0')}-`;
  const summaries = readDailyCloseSummaryRows_()
    .filter(item => item.businessDate.startsWith(prefix))
    .filter(item => !request.site || item.site === request.site)
    .sort((a, b) => a.businessDate.localeCompare(b.businessDate) || a.site.localeCompare(b.site, 'ko'));
""",
        """function buildDailyCloseMonthlyOverview_(request, dbToken) { // (월별 저장 마감자료 합산 · DAILY_CLOSE_READ_DB_FIRST_V1)
  const monthText = String(request.month).padStart(2, '0');
  const prefix = `${request.year}-${monthText}-`;
  const startDate = `${request.year}-${monthText}-01`;
  const endDate = Utilities.formatDate(new Date(Number(request.year), Number(request.month), 0), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
  const sheetSummaries = readDailyCloseSummaryRows_()
    .filter(item => item.businessDate.startsWith(prefix))
    .filter(item => !request.site || item.site === request.site);
  const dbSummaries = readDailyCloseDbSnapshots_(dbToken, startDate, endDate, request.site);
  const summaries = mergeDailyCloseSnapshots_(sheetSummaries, dbSummaries)
    .sort((a, b) => a.businessDate.localeCompare(b.businessDate) || a.site.localeCompare(b.site, 'ko'));
""",
        'monthly DB merge'
    )

    insert_anchor = "\nfunction readDailyCloseSummaries_(businessDate, site)"
    helper = r'''

function readDailyCloseDbSnapshots_(token, startDate, endDate, site) { // DAILY_CLOSE_READ_DB_FIRST_V1
  if (!token || typeof novaDailyCloseDbRead_ !== 'function') return [];
  if (typeof novaDailyCloseDbFirstEnabled_ === 'function' && !novaDailyCloseDbFirstEnabled_()) return [];
  try {
    const result = novaDailyCloseDbRead_(token, {
      startDate: String(startDate || '').trim(),
      endDate: String(endDate || startDate || '').trim(),
      site: String(site || '').trim()
    });
    return (Array.isArray(result && result.items) ? result.items : []).map(item => {
      const detail = item && item.snapshot && typeof item.snapshot === 'object'
        ? Object.assign({}, item.snapshot)
        : {};
      if (detail.roommaidCloseJournal) {
        detail.roommaidCloseJournal = expandRoommaidCloseJournalFromStorage_(detail.roommaidCloseJournal);
      }
      return Object.assign({}, detail, {
        businessDate: String(item && item.businessDate || detail.businessDate || '').trim(),
        site: String(item && item.site || detail.site || '').trim(),
        closedAt: String(item && item.closedAt || detail.closedAt || '').trim(),
        closedBy: String(item && item.closedBy || detail.closedBy || '').trim(),
        closedByName: String(item && item.closedByName || detail.closedByName || '').trim(),
        dbFirst: true,
        dbCloseVersion: Number(item && item.version || 0),
        dbRequestId: String(item && item.requestId || '').trim()
      });
    }).filter(item => item.businessDate && item.site);
  } catch (error) {
    console.warn('[NOVA DAILY CLOSE DB read fallback]', error && error.message ? error.message : error);
    return [];
  }
}

function mergeDailyCloseSnapshots_(sheetItems, dbItems) { // DAILY_CLOSE_READ_DB_FIRST_V1
  const byKey = {};
  (Array.isArray(sheetItems) ? sheetItems : []).forEach(item => {
    const key = `${String(item && item.businessDate || '').trim()}|${String(item && item.site || '').trim()}`;
    if (key !== '|') byKey[key] = item;
  });
  // PostgreSQL 확정본이 동일 업무일자·사업장 Sheet 미러보다 우선합니다.
  (Array.isArray(dbItems) ? dbItems : []).forEach(item => {
    const key = `${String(item && item.businessDate || '').trim()}|${String(item && item.site || '').trim()}`;
    if (key !== '|') byKey[key] = item;
  });
  return Object.values(byKey);
}
'''
    if insert_anchor not in close:
        raise SystemExit('daily close helper insertion anchor not found')
    close = close.replace(insert_anchor, helper + insert_anchor, 1)

if MARKER not in monthly:
    monthly = replace_once(
        monthly,
        "close: request.type === 'CLEANING' ? buildDailyCloseOverviewForRequest_(request) : {},",
        "close: request.type === 'CLEANING' ? buildDailyCloseOverviewForRequest_(request, token) : {}, // DAILY_CLOSE_READ_DB_FIRST_V1",
        'monthly close token'
    )

if MARKER not in roommaid:
    roommaid = replace_once(
        roommaid,
        """    const historyBundle = readRoommaidCloseHistoryBundleFast_(businessDate, preferredSite);
    const historyRows = historyBundle.historyRows;
    const saved = historyBundle.saved;
""",
        """    let dbSaved = null; // DAILY_CLOSE_READ_DB_FIRST_V1
    try {
      dbSaved = readDailyCloseDbSnapshots_(token, businessDate, businessDate, preferredSite)[0] || null;
    } catch (error) {
      dbSaved = null;
    }
    const historyBundle = readRoommaidCloseHistoryBundleFast_(businessDate, preferredSite);
    const historyRows = historyBundle.historyRows;
    const saved = dbSaved || historyBundle.saved;
""",
        'roommaid saved DB first'
    )
    roommaid = replace_once(
        roommaid,
        """        currentSource,
        currentRowCount: currentRows.length,
""",
        """        currentSource,
        savedSource: dbSaved ? 'REALTIME_DB' : (historyBundle.saved ? 'SHEET' : 'NONE'), // DAILY_CLOSE_READ_DB_FIRST_V1
        currentRowCount: currentRows.length,
""",
        'roommaid optimization saved source'
    )

for label, body, required in [
    ('14_DailyClose.js', close, [MARKER, 'readDailyCloseDbSnapshots_', 'mergeDailyCloseSnapshots_', 'buildDailyCloseOverviewForRequest_(request, token)']),
    ('11_Monthly.js', monthly, [MARKER, 'buildDailyCloseOverviewForRequest_(request, token)']),
    ('19_RoommaidCloseJournal.js', roommaid, [MARKER, 'const saved = dbSaved || historyBundle.saved', "savedSource: dbSaved ? 'REALTIME_DB'"])
]:
    missing = [value for value in required if value not in body]
    if missing:
        raise SystemExit(f'{label} validation failed: {missing}')

close_path.write_text(close, encoding='utf-8')
monthly_path.write_text(monthly, encoding='utf-8')
roommaid_path.write_text(roommaid, encoding='utf-8')
print('Applied DAILY_CLOSE_READ_DB_FIRST_V1: DB saved close preferred with Sheet historical fallback.')
