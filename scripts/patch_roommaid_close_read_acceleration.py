from pathlib import Path
import sys

path = Path('19_RoommaidCloseJournal.js')
marker = 'ROOMMAID_CLOSE_READ_ACCEL_V1'
text = path.read_text(encoding='utf-8')

if marker in text:
    print('Roommaid close read acceleration patch already applied.')
    sys.exit(0)

start = text.find("function getRoommaidCloseJournal(token, filters) { // (룸메이드 마감일지 조회)")
end = text.find("function saveRoommaidCloseJournal(token, payload) { // (룸메이드 마감일지 저장·수정 후 재마감)")
if start < 0 or end < 0 or end <= start:
    print('ERROR: Roommaid close journal anchors not found.', file=sys.stderr)
    sys.exit(70)

replacement = r'''function getRoommaidCloseJournal(token, filters) { // (룸메이드 마감일지 조회 · ROOMMAID_CLOSE_READ_ACCEL_V1)
  return measureResponse_('getRoommaidCloseJournal', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = filters || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const requestedSite = String(safe.site || '').trim();
    const hasAttendanceOverride = Array.isArray(safe.attendanceEmployeeNos);
    const requestedAttendance = hasAttendanceOverride ? uniqueEmployeeNos_(safe.attendanceEmployeeNos) : [];

    // 같은 변경버전의 같은 조회는 짧게 재사용하여 반복 탭 이동/재조회에서 Sheets 접근 자체를 생략합니다.
    // ROOM/ORDER/REPORT와 CONFIG/SYSTEM 버전이 바뀌면 캐시키가 달라져 즉시 새 원천자료를 읽습니다.
    const cacheSiteHint = requestedSite || String(user.defaultSite || '').trim();
    const sourceVersion = getSyncVersion_(['ROOM', 'ORDER', 'REPORT'], businessDate, cacheSiteHint);
    const cacheKey = buildDeltaCacheKey_('ROOMMAID_CLOSE_READ_V1', [
      NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION,
      businessDate,
      cacheSiteHint || '*',
      String(user.employeeNo || ''),
      sourceVersion,
      hasAttendanceOverride ? requestedAttendance.slice().sort().join(',') : 'AUTO'
    ]);
    const cached = getCachedJson_(cacheKey);
    if (cached && cached.ok) {
      return Object.assign({}, cached, {
        optimization: Object.assign({}, cached.optimization || {}, { cacheHit: true })
      });
    }

    // 기존에는 전체 사업장의 현재객실 전체행을 읽은 뒤 선택 사업장만 필터링했습니다.
    // 이제 날짜/사업장 2개 열만 먼저 훑고, 실제 전체행은 선택 사업장만 읽습니다.
    const currentSelection = readRoommaidCloseCurrentSelection_(
      businessDate,
      requestedSite,
      String(user.defaultSite || '').trim()
    );
    const sites = currentSelection.sites;
    const preferredSite = currentSelection.site;
    const currentRows = currentSelection.currentRows;

    if (!preferredSite) throw new Error(`${businessDate} 현재객실현황에 조회할 사업장이 없습니다.`);
    if (!sites.includes(preferredSite)) throw new Error(`${businessDate} ${preferredSite} 현재객실현황이 없습니다.`);

    // 업무이력과 저장된 DAILY_CLOSE 요약을 같은 전체열 스캔에서 함께 선별합니다.
    // 기존 readHistoryRowsForClose_ + readDailyCloseSummaries_의 중복 전체스캔을 제거합니다.
    const historyBundle = readRoommaidCloseHistoryBundle_(businessDate, preferredSite);
    const historyRows = historyBundle.historyRows;
    const saved = historyBundle.saved;
    const users = getUserIndex_().byEmployeeNo;
    const employmentIndex = readRoommaidCloseEmploymentIndex_();
    const inferredAttendance = inferRoommaidCloseAttendance_(currentRows, historyRows);
    const savedAttendance = saved && Array.isArray(saved.attendanceEmployeeNos) ? saved.attendanceEmployeeNos : [];
    const attendanceEmployeeNos = uniqueEmployeeNos_(
      hasAttendanceOverride ? requestedAttendance : (savedAttendance.length ? savedAttendance : inferredAttendance)
    );

    const liveSnapshot = buildDailyCloseSnapshot_(businessDate, preferredSite, {
      closedBy: saved ? saved.closedBy : '',
      closedByName: saved ? saved.closedByName : '',
      closedAt: saved ? saved.closedAt : '',
      includeRooms: false,
      currentRows,
      historyRows,
      attendanceEmployeeNos
    });
    const latestSourceAt = latestRoommaidCloseSourceAt_(currentRows, historyRows);
    const savedHasJournal = Boolean(saved && saved.roommaidCloseJournal);
    const savedJournalSchemaChanged = Boolean(
      savedHasJournal &&
      Number(saved.roommaidCloseJournal.schemaVersion || 0) !== NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION
    );
    const signatureChanged = Boolean(saved && saved.sourceSignature && saved.sourceSignature !== liveSnapshot.sourceSignature);
    const legacyTimestampChanged = Boolean(saved && !saved.sourceSignature && saved.closedAt && latestSourceAt && latestSourceAt > saved.closedAt);
    const isStale = Boolean(saved && (!savedHasJournal || savedJournalSchemaChanged || signatureChanged || legacyTimestampChanged));
    const useSaved = Boolean(saved && !isStale && savedHasJournal && !hasAttendanceOverride);
    const selected = useSaved ? saved : liveSnapshot;
    const journal = selected.roommaidCloseJournal || liveSnapshot.roommaidCloseJournal;
    const baseWarning = journal && journal.initialStatusDetailAvailable
      ? ''
      : '해당 업무일자의 객실현황 업로드가 RC6.4 이전에 적용되어 최초 재고·퇴실의 객실별 상세가 없습니다. 현재 상태를 기준으로 보정 표시됩니다.';

    const result = {
      ok: true,
      businessDate,
      site: preferredSite,
      sites,
      source: saved ? (isStale ? 'CLOSED_STALE' : 'CLOSED') : 'LIVE',
      isClosed: Boolean(saved),
      isStale,
      closedAt: saved ? String(saved.closedAt || '') : '',
      closedBy: saved ? String(saved.closedByName || saved.closedBy || '') : '',
      latestSourceAt,
      attendanceEmployeeNos: uniqueEmployeeNos_(journal && journal.attendanceEmployeeNos || attendanceEmployeeNos),
      attendanceOptions: buildRoommaidCloseAttendanceOptions_(users, preferredSite, inferredAttendance, journal && journal.attendanceEmployeeNos || attendanceEmployeeNos, employmentIndex),
      journal,
      warning: baseWarning,
      message: saved
        ? (isStale ? '마감 이후 객실 또는 정비실적이 수정되었습니다. 수정 후 재마감이 필요합니다.' : '저장된 마감자료입니다.')
        : '실시간 미마감 자료입니다.',
      optimization: {
        marker: 'ROOMMAID_CLOSE_READ_ACCEL_V1',
        cacheHit: false,
        sourceVersion,
        currentRowCount: currentRows.length,
        historyRowCount: historyRows.length
      }
    };

    // CacheService 항목 제한을 넘는 큰 응답은 putCachedJson_이 자동으로 저장을 건너뜁니다.
    putCachedJson_(cacheKey, result, Math.min(30, Number(NOVA.SNAPSHOT_CACHE_SECONDS || 45)));
    return result;
  });
}

function readRoommaidCloseCurrentSelection_(businessDate, requestedSite, defaultSite) { // (선택 사업장 현재객실만 전체행 읽기 · ROOMMAID_CLOSE_READ_ACCEL_V1)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { sites: [], site: '', currentRows: [] };
  const headerMap = getHeaderMap_(sheet);
  const dateColumn = headerMap['업무일자'];
  const siteColumn = headerMap['사업장'];
  if (!dateColumn || !siteColumn) return { sites: [], site: '', currentRows: [] };

  const rowCount = lastRow - 1;
  const dateValues = sheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const siteValues = sheet.getRange(2, siteColumn, rowCount, 1).getDisplayValues();
  const rowsBySite = {};
  const siteSet = new Set();

  for (let index = 0; index < rowCount; index += 1) {
    if (String(dateValues[index][0] || '').trim() !== businessDate) continue;
    const site = String(siteValues[index][0] || '').trim();
    if (!site) continue;
    siteSet.add(site);
    if (!rowsBySite[site]) rowsBySite[site] = [];
    rowsBySite[site].push(index + 2);
  }

  const sites = Array.from(siteSet).sort((a, b) => a.localeCompare(b, 'ko'));
  const requested = String(requestedSite || '').trim();
  const preferredDefault = String(defaultSite || '').trim();
  const site = requested || (sites.includes(preferredDefault) ? preferredDefault : sites[0] || '');
  const currentRows = site && rowsBySite[site]
    ? readRowsByNumbersForClose_(sheet, headerMap, rowsBySite[site])
    : [];
  return { sites, site, currentRows };
}

function readRoommaidCloseHistoryBundle_(businessDate, site) { // (실시간 업무이력 + 저장 마감요약 1회 스캔 · ROOMMAID_CLOSE_READ_ACCEL_V1)
  const liveTypes = new Set([
    NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD,
    NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE,
    NOVA.RECORD_TYPES.CLEANING,
    NOVA.RECORD_TYPES.QM,
    NOVA.RECORD_TYPES.QM_CHECKLIST,
    NOVA.RECORD_TYPES.HOUSEMAN_ORDER,
    NOVA.RECORD_TYPES.DEPARTURE_DELAY
  ]);
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { historyRows: [], saved: null };
  const headerMap = getHeaderMap_(sheet);
  const typeColumn = headerMap['기록구분'];
  const dateColumn = headerMap['업무일자'];
  const siteColumn = headerMap['사업장'];
  const statusColumn = headerMap['처리상태'];
  const deletedColumn = headerMap['삭제여부'];
  if (!typeColumn || !dateColumn || !siteColumn || !statusColumn) return { historyRows: [], saved: null };

  const rowCount = lastRow - 1;
  const typeValues = sheet.getRange(2, typeColumn, rowCount, 1).getDisplayValues();
  const dateValues = sheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const siteValues = sheet.getRange(2, siteColumn, rowCount, 1).getDisplayValues();
  const statusValues = sheet.getRange(2, statusColumn, rowCount, 1).getDisplayValues();
  const deletedValues = deletedColumn
    ? sheet.getRange(2, deletedColumn, rowCount, 1).getDisplayValues()
    : Array.from({ length: rowCount }, () => ['N']);
  const selected = [];

  for (let index = 0; index < rowCount; index += 1) {
    if (String(dateValues[index][0] || '').trim() !== businessDate) continue;
    if (site && String(siteValues[index][0] || '').trim() !== site) continue;
    if (String(deletedValues[index][0] || 'N').trim().toUpperCase() === 'Y') continue;
    const type = String(typeValues[index][0] || '').trim();
    const status = String(statusValues[index][0] || '').trim();
    const live = liveTypes.has(type);
    const closeSummary = type === NOVA.RECORD_TYPES.DAILY_CLOSE && status === NOVA_DAILY_CLOSE.SUMMARY_STATUS;
    if (live || closeSummary) selected.push(index + 2);
  }

  if (!selected.length) return { historyRows: [], saved: null };
  const rows = readRowsByNumbersForClose_(sheet, headerMap, selected);
  const historyRows = [];
  let saved = null;
  rows.forEach(data => {
    const type = String(data['기록구분'] || '').trim();
    if (type !== NOVA.RECORD_TYPES.DAILY_CLOSE) {
      historyRows.push(data);
      return;
    }
    if (saved || String(data['처리상태'] || '').trim() !== NOVA_DAILY_CLOSE.SUMMARY_STATUS) return;
    let detail = {};
    try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    if (detail.roommaidCloseJournal) {
      detail.roommaidCloseJournal = expandRoommaidCloseJournalFromStorage_(detail.roommaidCloseJournal);
    }
    saved = Object.assign({}, detail, {
      businessDate: String(data['업무일자'] || detail.businessDate || '').trim(),
      site: String(data['사업장'] || detail.site || '').trim(),
      closedAt: String(detail.closedAt || data['등록일시'] || '').trim(),
      closedBy: String(detail.closedBy || data['등록사번'] || '').trim()
    });
  });
  return { historyRows, saved };
}

'''

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding='utf-8')
print('Applied Roommaid close journal read acceleration V1.')
