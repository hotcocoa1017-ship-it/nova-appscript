from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '19_RoommaidCloseJournal.js'
text = TARGET.read_text(encoding='utf-8')
original = text

# 1) Force saved close journals to recalculate with the corrected workload-cycle logic.
old_schema = '  SCHEMA_VERSION: 27,'
new_schema = '  SCHEMA_VERSION: 28,'
if text.count(old_schema) != 1:
    raise SystemExit(f'PATCH_ERROR: schema anchor expected 1 match, found {text.count(old_schema)}')
text = text.replace(old_schema, new_schema, 1)

# 2) Detect an opening-stock room returning from STAY/RECHECKIN to its original STOCK variant.
old_flags = """      const isManualInitialStock = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(nextStatus)\n        && previousStatus === 'VACANT_CLEAN';\n\n      if (isDeparture) {"""
new_flags = """      const isManualInitialStock = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(nextStatus)\n        && previousStatus === 'VACANT_CLEAN';\n      const isOpeningStockReturn = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(nextStatus)\n        && ['STAY', 'RECHECKIN'].includes(previousStatus);\n\n      if (isDeparture) {"""
if text.count(old_flags) != 1:
    raise SystemExit(f'PATCH_ERROR: opening-stock return flag anchor expected 1 match, found {text.count(old_flags)}')
text = text.replace(old_flags, new_flags, 1)

# 3) Restore only the original upload-time stock cycle that was canceled by STAY/RECHECKIN.
#    Do not invent a new previous-stock cycle when no matching opening-stock cycle exists.
old_branch = """      } else if (isManualInitialStock) {\n        if (active && !active.completed && !active.canceled && (active.initialStock || active.departure)) {"""
new_branch = """      } else if (isOpeningStockReturn) {\n        // 업로드 당시 전일재고가 STAY/RECHECKIN으로 잠시 취소된 뒤\n        // 같은 STOCK/RC/HU 상태로 돌아오면 새 작업을 만들지 않고 원래 전일재고 주기를 복구한다.\n        // 예: STOCK -> STAY -> STOCK -> 청소완료.\n        const restoredOpeningStock = [...(eventsByRoom[roomNo] || [])].reverse().find(event =>\n          event && event.initialStock && !event.manualInitialStock\n          && !event.completed && event.canceled\n          && ['STAY', 'RECHECKIN'].includes(String(event.cancelReason || '').trim().toUpperCase())\n          && normalizeRoommaidCloseRoomStatus_(event.sourceStatus, statusNormalizer) === nextStatus\n        ) || null;\n        if (restoredOpeningStock) {\n          restoredOpeningStock.canceled = false;\n          restoredOpeningStock.cancelReason = '';\n          restoredOpeningStock.restoredAfterStatus = previousStatus;\n          restoredOpeningStock.restoredVersion = item.version;\n          restoredOpeningStock.restoredAt = item.eventAt;\n          activeByRoom[roomNo] = restoredOpeningStock;\n        }\n      } else if (isManualInitialStock) {\n        if (active && !active.completed && !active.canceled && (active.initialStock || active.departure)) {"""
if text.count(old_branch) != 1:
    raise SystemExit(f'PATCH_ERROR: restore branch anchor expected 1 match, found {text.count(old_branch)}')
text = text.replace(old_branch, new_branch, 1)

TARGET.write_text(text, encoding='utf-8')

# Verification: keep scope intentionally narrow and preserve the temporary read-only diagnostic
# so production verification can prove 6556 is no longer missing before diagnostic cleanup.
checks = {
    'schema 28': 'SCHEMA_VERSION: 28' in text,
    'return detector': 'const isOpeningStockReturn =' in text,
    'restore cycle': 'restoredOpeningStock.canceled = false;' in text,
    'restore active pointer': 'activeByRoom[roomNo] = restoredOpeningStock;' in text,
    'diagnostic retained': 'function buildRoommaidCloseStockDiagnostic_' in text,
    'legacy STAY cancellation retained': "active.cancelReason = nextStatus;" in text,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    TARGET.write_text(original, encoding='utf-8')
    raise SystemExit('VERIFY_ERROR: ' + ', '.join(failed))

# Standard JavaScript syntax check.
try:
    subprocess.run(['node', '--check', str(TARGET)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
except subprocess.CalledProcessError as exc:
    TARGET.write_text(original, encoding='utf-8')
    print(exc.stdout)
    print(exc.stderr)
    raise SystemExit('SYNTAX_ERROR: 19_RoommaidCloseJournal.js')

print('PATCH_OK')
print('Repository only; production Apps Script NOT changed yet')
print('Changed: 19_RoommaidCloseJournal.js only')
print('Fixed: opening STOCK/STOCK_RC/STOCK_HU cycle restores after temporary STAY/RECHECKIN return to the same stock status')
print('Preserved: departure/reclassification logic, completion linking, permissions, v30 realtime, all other close calculations')
print('Schema: roommaid close journal 27 -> 28 so saved old journal recalculates')
print('Diagnostic: v31.3 read-only mismatch diagnostic retained temporarily for verification')
print('Syntax: PASS')
print('VERIFY: PASS')
