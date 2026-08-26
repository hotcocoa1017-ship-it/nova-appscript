from pathlib import Path
import re

path = Path('06_Indicator.js')
text = path.read_text(encoding='utf-8')

start_marker = 'function findIndicatorRoomActiveCleaningCompletions_('
end_marker = 'function markIndicatorRoomCleaningCompletionsDeleted_('

start = text.find(start_marker)
end = text.find(end_marker)
if start < 0 or end < 0 or end <= start:
    raise SystemExit('PATCH_ERROR: cleaning reset history lookup markers not found')

old = text[start:end]
if "sheet.getRange(2, 1, lastRow - 1, lastColumn).getDisplayValues()" not in old:
    raise SystemExit('PATCH_ERROR: expected full-history scan not found')

new = r'''function findIndicatorRoomActiveCleaningCompletions_(sheet, businessDate, site, roomNo) { // (객실 금일 활성 청소완료 이력 전체 조회·업무일자 우선검색)
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const requiredHeaders = ['기록ID', '기록구분', '업무일자', '사업장', '객실번호', '대상사번', '처리상태', '세부내용JSON', '삭제여부'];
  requiredHeaders.forEach(header => {
    if (!headerMap[header]) throw new Error(`업무이력 시트의 ${header} 열을 확인하세요.`);
  });

  // 기존에는 업무이력 전체 행×전체 열을 매번 읽어 청소초기화가 수 초~수십 초 걸렸다.
  // 먼저 업무일자 열에서 오늘 날짜 행만 서버측 TextFinder로 찾고,
  // 그 날짜가 존재하는 최소~최대 행 범위의 필요한 열 구간만 1회 읽는다.
  // 필터 조건과 결과 형식은 기존 로직과 동일하게 유지한다.
  const dateColumn = Number(headerMap['업무일자']);
  const dateMatches = sheet
    .getRange(2, dateColumn, lastRow - 1, 1)
    .createTextFinder(String(businessDate || '').trim())
    .matchEntireCell(true)
    .findAll();

  if (!dateMatches.length) return [];

  const matchedRows = Array.from(new Set(dateMatches.map(cell => cell.getRow())))
    .filter(rowNumber => rowNumber >= 2)
    .sort((a, b) => a - b);
  if (!matchedRows.length) return [];

  const matchedRowSet = new Set(matchedRows);
  const firstRow = matchedRows[0];
  const lastMatchedRow = matchedRows[matchedRows.length - 1];

  const requiredColumns = requiredHeaders.map(header => Number(headerMap[header]));
  const firstColumn = Math.min.apply(null, requiredColumns);
  const lastColumn = Math.max.apply(null, requiredColumns);
  const width = lastColumn - firstColumn + 1;
  const values = sheet
    .getRange(firstRow, firstColumn, lastMatchedRow - firstRow + 1, width)
    .getDisplayValues();

  const columnIndex = header => Number(headerMap[header] || 0) - firstColumn;
  const index = {
    recordId: columnIndex('기록ID'),
    type: columnIndex('기록구분'),
    date: columnIndex('업무일자'),
    site: columnIndex('사업장'),
    room: columnIndex('객실번호'),
    target: columnIndex('대상사번'),
    status: columnIndex('처리상태'),
    detail: columnIndex('세부내용JSON'),
    deleted: columnIndex('삭제여부')
  };
  const completionStatuses = new Set(['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE']);
  const normalizedRoomNo = normalizeRoomNo_(roomNo);
  const result = [];

  matchedRows.forEach(rowNumber => {
    if (!matchedRowSet.has(rowNumber)) return;
    const row = values[rowNumber - firstRow];
    if (!row) return;
    if (String(row[index.type] || '').trim() !== NOVA.RECORD_TYPES.CLEANING) return;
    if (String(row[index.date] || '').trim() !== businessDate) return;
    if (String(row[index.site] || '').trim() !== site) return;
    if (normalizeRoomNo_(row[index.room]) !== normalizedRoomNo) return;
    if (String(row[index.deleted] || 'N').trim().toUpperCase() === 'Y') return;
    const status = String(row[index.status] || '').trim().toUpperCase();
    if (!completionStatuses.has(status)) return;

    let detail = {};
    try { detail = JSON.parse(String(row[index.detail] || '{}')); } catch (error) { detail = {}; }
    result.push({
      rowNumber,
      recordId: String(row[index.recordId] || '').trim(),
      targetEmployeeNo: String(row[index.target] || '').trim(),
      status,
      primaryEmployeeNo: String(detail.primaryEmployeeNo || '').trim(),
      secondaryEmployeeNo: String(detail.secondaryEmployeeNo || '').trim()
    });
  });
  return result;
}

'''

patched = text[:start] + new + text[end:]
path.write_text(patched, encoding='utf-8')

# Verification: only the intended history lookup implementation should change.
check = path.read_text(encoding='utf-8')
if check.count(start_marker) != 1 or check.count(end_marker) != 1:
    raise SystemExit('VERIFY_ERROR: function markers changed unexpectedly')
if "createTextFinder(String(businessDate || '').trim())" not in check:
    raise SystemExit('VERIFY_ERROR: date TextFinder fast path missing')
if "sheet.getRange(2, 1, lastRow - 1, lastColumn).getDisplayValues()" in check[start:end + len(end_marker)]:
    raise SystemExit('VERIFY_ERROR: old full-history scan still present')

print('PATCH_OK')
print('Repository only; production Apps Script NOT changed yet')
print('Changed: 06_Indicator.js only')
print('Optimized: CLEANING_RESET active completion lookup searches business-date rows first instead of reading full history sheet')
print('Preserved: reset eligibility, completion soft-delete, room reset, unified history, data-version publish, permissions')
print('No Cloud Run change required')
print('VERIFY: PASS')
