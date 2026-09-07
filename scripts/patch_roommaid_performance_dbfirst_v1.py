from pathlib import Path

path = Path('17_RoommaidPerformance.js')
text = path.read_text(encoding='utf-8')
old = "    const rows = readMonthlyHistoryRows_(request, [NOVA.RECORD_TYPES.CLEANING]).map(row => row && row.data ? row.data : row);"
new = "    const rows = readMonthlyHistoryRowsDbFirst_(request, [NOVA.RECORD_TYPES.CLEANING], token).map(row => row && row.data ? row.data : row); // ROOMMAID_PERFORMANCE_DB_FIRST_V1"
if 'ROOMMAID_PERFORMANCE_DB_FIRST_V1' not in text:
    if old not in text:
        raise SystemExit('17_RoommaidPerformance.js patch anchor not found')
    text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')

if 'readMonthlyHistoryRows_(request, [NOVA.RECORD_TYPES.CLEANING])' in path.read_text(encoding='utf-8'):
    raise SystemExit('legacy direct monthly history read remains in getRoommaidPerformance')

print('roommaid performance DB-first patch OK')
