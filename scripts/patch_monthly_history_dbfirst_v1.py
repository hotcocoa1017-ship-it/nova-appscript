from pathlib import Path

MARKER = 'MONTHLY_HISTORY_DB_FIRST_V1'
path = Path('11_Monthly.js')
text = path.read_text(encoding='utf-8')


def replace_once(src, old, new, label):
    if old not in src:
        raise SystemExit(f'{label} anchor not found')
    return src.replace(old, new, 1)

# Top-level web paths carry the authenticated Apps Script token into the hybrid reader.
if "buildMonthlyHistoryBundle_(request, token)" not in text:
    text = replace_once(
        text,
        "const bundle = buildMonthlyHistoryBundle_(request);",
        "const bundle = buildMonthlyHistoryBundle_(request, token); // MONTHLY_HISTORY_DB_FIRST_V1",
        'getMonthlyHistory bundle token'
    )

# Export has the same source expression; replace its first remaining occurrence.
if text.count("const bundle = buildMonthlyHistoryBundle_(request, token);") < 2:
    text = replace_once(
        text,
        "const bundle = buildMonthlyHistoryBundle_(request);",
        "const bundle = buildMonthlyHistoryBundle_(request, token); // MONTHLY_HISTORY_DB_FIRST_V1",
        'getMonthlyHistoryExport bundle token'
    )

# writeMonthlyViewSheet also has a user token. Spreadsheet onOpen refresh intentionally remains Sheet fallback.
if text.count("const bundle = buildMonthlyHistoryBundle_(request, token);") < 3:
    text = replace_once(
        text,
        "const bundle = buildMonthlyHistoryBundle_(request);",
        "const bundle = buildMonthlyHistoryBundle_(request, token); // MONTHLY_HISTORY_DB_FIRST_V1",
        'writeMonthlyViewSheet bundle token'
    )

old_bundle = """function buildMonthlyHistoryBundle_(request) { // (월별 이력 조회·필터·집계)
  const rawRows = readMonthlyHistoryRows_(request, monthlyRecordTypesForType_(request.type));
"""
new_bundle = """function buildMonthlyHistoryBundle_(request, dbToken) { // (월별 이력 조회·필터·집계 · MONTHLY_HISTORY_DB_FIRST_V1)
  const rawRows = readMonthlyHistoryRowsDbFirst_(request, monthlyRecordTypesForType_(request.type), dbToken);
"""
if old_bundle in text:
    text = text.replace(old_bundle, new_bundle, 1)

if 'function readMonthlyHistoryRowsDbFirst_' not in text:
    anchor = "\nfunction readMonthlyHistoryRows_(request, allowedRecordTypesOverride)"
    helper = r'''

function readMonthlyHistoryRowsDbFirst_(request, allowedRecordTypesOverride, token) { // MONTHLY_HISTORY_DB_FIRST_V1
  const allowed = (allowedRecordTypesOverride && allowedRecordTypesOverride.length
    ? allowedRecordTypesOverride
    : monthlyRecordTypesForType_(request.type))
    .map(value => String(value || '').trim())
    .filter(Boolean);
  const sheetRows = readMonthlyHistoryRows_(request, allowed);

  // Houseman 관리(수정·취소·삭제)는 아직 Sheet rowNumber를 사용하므로
  // 이번 단계에서는 HOUSEMAN_ORDER를 DB 목록으로 대체하지 않습니다.
  const dbReplaceTypes = new Set([
    String(NOVA.RECORD_TYPES.CLEANING || '').trim(),
    String(NOVA.RECORD_TYPES.QM || '').trim(),
    String(NOVA.RECORD_TYPES.QM_CHECKLIST || '').trim()
  ]);
  if (!token || !allowed.some(type => dbReplaceTypes.has(type))) return sheetRows;
  if (typeof novaMonthlyHistoryDbFirstEnabled_ !== 'function' || !novaMonthlyHistoryDbFirstEnabled_()) return sheetRows;
  if (typeof novaMonthlyHistoryDbRead_ !== 'function') return sheetRows;

  const range = monthlyHistoryDbDateRange_(request);
  try {
    const result = novaMonthlyHistoryDbRead_(token, {
      startDate: range.startDate,
      endDate: range.endDate,
      site: String(request.site || '').trim()
    });
    const nativeKeys = new Set((Array.isArray(result && result.nativeKeys) ? result.nativeKeys : [])
      .map(item => `${String(item && item.businessDate || '').trim()}|${String(item && item.site || '').trim()}`)
      .filter(key => key !== '|'));
    if (!nativeKeys.size) return sheetRows;

    const keptSheet = sheetRows.filter(row => {
      const data = row && row.data ? row.data : {};
      const type = String(data['기록구분'] || '').trim();
      if (!dbReplaceTypes.has(type)) return true;
      const key = `${String(data['업무일자'] || '').trim()}|${String(data['사업장'] || '').trim()}`;
      return !nativeKeys.has(key);
    });

    const allowedSet = new Set(allowed);
    const dbRows = (Array.isArray(result && result.items) ? result.items : [])
      .filter(data => allowedSet.has(String(data && data['기록구분'] || '').trim()))
      .filter(data => dbReplaceTypes.has(String(data && data['기록구분'] || '').trim()))
      .map((data, index) => ({
        rowNumber: -(index + 1),
        data: Object.assign({}, data, { __NOVA_DB_FIRST: 'Y' })
      }));

    return keptSheet.concat(dbRows);
  } catch (error) {
    console.warn('[NOVA MONTHLY DB read fallback]', error && error.message ? error.message : error);
    return sheetRows;
  }
}

function monthlyHistoryDbDateRange_(request) { // MONTHLY_HISTORY_DB_FIRST_V1
  if (String(request && request.period || '').trim().toUpperCase() === 'DAILY') {
    const date = String(request && request.date || '').trim();
    return { startDate: date, endDate: date };
  }
  const year = Number(request && request.year || 0);
  const month = Number(request && request.month || 0);
  const monthText = String(month).padStart(2, '0');
  const startDate = `${year}-${monthText}-01`;
  const endDate = Utilities.formatDate(new Date(year, month, 0), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
  return { startDate, endDate };
}
'''
    if anchor not in text:
        raise SystemExit('readMonthlyHistoryRows_ anchor not found')
    text = text.replace(anchor, helper + anchor, 1)

required = [
    MARKER,
    'readMonthlyHistoryRowsDbFirst_',
    'monthlyHistoryDbDateRange_',
    'novaMonthlyHistoryDbRead_',
    '__NOVA_DB_FIRST',
    'buildMonthlyHistoryBundle_(request, dbToken)'
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit(f'monthly DB-first validation failed: {missing}')

path.write_text(text, encoding='utf-8')
print('Applied MONTHLY_HISTORY_DB_FIRST_V1: DB-native CLEANING/QM slices with Sheet fallback and Houseman row management preserved.')
