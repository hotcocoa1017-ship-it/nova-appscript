from pathlib import Path
import sys

PERF = Path('17_RoommaidPerformance.js')
CLOSE = Path('19_RoommaidCloseJournal.js')
MARKER = 'ROOMMAID_REPORTING_DB_FIRST_APP_V2'


def fail(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    raise SystemExit(96)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)

perf = PERF.read_text(encoding='utf-8')
if MARKER not in perf:
    perf = replace_once(
        perf,
        "    const request = normalizeRoommaidPerformanceFilters_(filters, auth.user);\n    const rows = readMonthlyHistoryRows_(request, [NOVA.RECORD_TYPES.CLEANING]).map(row => row && row.data ? row.data : row);",
        "    const request = normalizeRoommaidPerformanceFilters_(filters, auth.user);\n    request.__dbFirstToken = token; // ROOMMAID_REPORTING_DB_FIRST_APP_V2\n    const rows = readMonthlyHistoryRows_(request, [NOVA.RECORD_TYPES.CLEANING]).map(row => row && row.data ? row.data : row);",
        'roommaid performance DB token'
    )
    PERF.write_text(perf, encoding='utf-8')

close = CLOSE.read_text(encoding='utf-8')
if MARKER not in close:
    close = replace_once(
        close,
        "    const historyBundle = readRoommaidCloseHistoryBundleFast_(businessDate, preferredSite);",
        "    const historyBundle = readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, preferredSite); // ROOMMAID_REPORTING_DB_FIRST_APP_V2",
        'roommaid close DB history'
    )
    CLOSE.write_text(close, encoding='utf-8')

print(f'{MARKER} applied.')
