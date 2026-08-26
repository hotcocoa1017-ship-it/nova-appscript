from pathlib import Path
import re

path = Path('19_RoommaidCloseJournal.js')
text = path.read_text(encoding='utf-8')
original = text

# 1) Remove the temporary diagnostic call/result while preserving the original warning behavior.
call_line = "    const stockDiagnostic = buildRoommaidCloseStockDiagnostic_(businessDate, preferredSite, currentRows, historyRows);\n"
if call_line not in text:
    raise SystemExit('PATCH_ERROR: stock diagnostic call not found')
text = text.replace(call_line, '', 1)

old_warning = "      warning: [baseWarning, stockDiagnostic.message].filter(Boolean).join(' / '),\n      stockDiagnostic,\n"
new_warning = "      warning: baseWarning,\n"
if old_warning not in text:
    raise SystemExit('PATCH_ERROR: stock diagnostic response block not found')
text = text.replace(old_warning, new_warning, 1)

# 2) Remove only the temporary read-only diagnostic helper.
pattern = re.compile(
    r"\nfunction buildRoommaidCloseStockDiagnostic_\(businessDate, site, currentRows, historyRows\) \{.*?\n\}\n\n(?=function buildRoommaidCloseJournal_)",
    re.S,
)
text, count = pattern.subn('\n', text, count=1)
if count != 1:
    raise SystemExit(f'PATCH_ERROR: expected 1 diagnostic helper, removed {count}')

# 3) Guard rails: the real fix and all production logic must remain.
required_markers = [
    'SCHEMA_VERSION: 28',
    'const isOpeningStockReturn = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(nextStatus)',
    "&& ['STAY', 'RECHECKIN'].includes(previousStatus);",
    'const restoredOpeningStock = [...(eventsByRoom[roomNo] || [])].reverse().find(event =>',
    'restoredOpeningStock.canceled = false;',
    'activeByRoom[roomNo] = restoredOpeningStock;',
    'function buildRoommaidCloseJournal_',
]
missing = [marker for marker in required_markers if marker not in text]
if missing:
    raise SystemExit('PATCH_ERROR: required production markers missing: ' + ' | '.join(missing))

for forbidden in [
    'buildRoommaidCloseStockDiagnostic_',
    'stockDiagnostic',
    '재고정합 진단',
]:
    if forbidden in text:
        raise SystemExit(f'PATCH_ERROR: diagnostic marker still present: {forbidden}')

if text == original:
    raise SystemExit('PATCH_ERROR: no changes made')

path.write_text(text, encoding='utf-8')

print('PATCH_OK')
print('Repository only; production Apps Script NOT changed yet')
print('Changed: 19_RoommaidCloseJournal.js only')
print('Removed: temporary v31.2/v31.3 stock mismatch diagnostic call, response field, warning text, helper')
print('Preserved: schema 28, v31.4 opening-stock restore fix, close calculations, save/integrity logic, permissions, v30 realtime')
print('VERIFY: PASS')
