from pathlib import Path
import sys

MONTHLY = Path('11_Monthly.js')
CLIENT = Path('Client.html')
MARKER = 'MONTHLY_DAILY_DB_FIRST_CLIENT_V2'


def fail(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    raise SystemExit(95)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)

monthly = MONTHLY.read_text(encoding='utf-8')
if 'function readMonthlyHistoryRowsLegacy_' not in monthly:
    monthly = replace_once(
        monthly,
        "function readMonthlyHistoryRows_(request, allowedRecordTypesOverride) { // (업무이력 월·일 행 선별·행 인덱스 캐시)\n",
        "function readMonthlyHistoryRowsLegacy_(request, allowedRecordTypesOverride) { // (기존 Sheet 이력 fallback · NOVA_MONTHLY_DB_FIRST_V2)\n",
        'rename monthly legacy reader'
    )
    anchor = "function readMonthlyHistoryRowsLegacy_(request, allowedRecordTypesOverride) { // (기존 Sheet 이력 fallback · NOVA_MONTHLY_DB_FIRST_V2)\n"
    wrapper = "function readMonthlyHistoryRows_(request, allowedRecordTypesOverride) { // NOVA_MONTHLY_DB_FIRST_V2\n  const token = String(request && request.__dbFirstToken || '').trim();\n  return token\n    ? readMonthlyHistoryRowsDbFirst_(token, request, allowedRecordTypesOverride)\n    : readMonthlyHistoryRowsLegacy_(request, allowedRecordTypesOverride);\n}\n\n"
    monthly = monthly.replace(anchor, wrapper + anchor, 1)
    MONTHLY.write_text(monthly, encoding='utf-8')

client = CLIENT.read_text(encoding='utf-8')
if MARKER not in client:
    client = replace_once(
        client,
        "      const result = await callServer('getMonthlyHistory', state.token, filters);",
        "      const result = await callServer('getMonthlyHistoryDbFirst', state.token, filters); // MONTHLY_DAILY_DB_FIRST_CLIENT_V2",
        'monthly web read route'
    )
    client = replace_once(
        client,
        "      const result = await callServer('getMonthlyHistoryExport', state.token, collectMonthlyFilters_({ page: 1 }));",
        "      const result = await callServer('getMonthlyHistoryExportDbFirst', state.token, collectMonthlyFilters_({ page: 1 })); // MONTHLY_DAILY_DB_FIRST_CLIENT_V2",
        'monthly export route'
    )
    client = replace_once(
        client,
        "      const result = await callServer('writeMonthlyViewSheet', state.token, collectMonthlyFilters_({ page: 1 }));",
        "      const result = await callServer('writeMonthlyViewSheetDbFirst', state.token, collectMonthlyFilters_({ page: 1 })); // MONTHLY_DAILY_DB_FIRST_CLIENT_V2",
        'monthly sheet route'
    )
    client = replace_once(
        client,
        "      const result = await callServer('saveDailyCloseSnapshot', state.token, { businessDate, site });",
        "      const result = await callServer('saveDailyCloseSnapshotDbFirst', state.token, {\n        businessDate,\n        site,\n        requestId: novaRealtimeRequestId_('DAILY_CLOSE_V3', site || businessDate)\n      }); // MONTHLY_DAILY_DB_FIRST_CLIENT_V2",
        'daily close save route'
    )
    CLIENT.write_text(client, encoding='utf-8')

print(f'{MARKER} applied.')
