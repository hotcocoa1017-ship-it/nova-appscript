from pathlib import Path

checks = []

def require(text, needle, label):
    if needle not in text:
        raise SystemExit(f"MISSING: {label} :: {needle}")
    checks.append(label)

journal = Path('19_RoommaidCloseJournal.js').read_text(encoding='utf-8')
bridge = Path('RoommaidReportingDbFirstBridge.js').read_text(encoding='utf-8')
migration = Path('supabase/migrations/20260909_roommaid_close_single_bundle_v5.sql').read_text(encoding='utf-8')

require(journal, 'ROOMMAID_CLOSE_SINGLE_BUNDLE_V5', 'journal single-bundle marker')
require(journal, 'Array.isArray(historyBundle.currentRows) ? historyBundle.currentRows : []', 'journal consumes bundled current rows')
require(journal, "currentSource = currentRows.length ? 'DB_SINGLE_BUNDLE_V5' : 'SHEET'", 'journal exposes bundled current source')
require(journal, 'readRoommaidCloseRealtimeCurrentRows_(token, businessDate, preferredSite)', 'Realtime DB fallback preserved')
require(journal, 'readRoommaidCloseCurrentSelection_(businessDate, preferredSite, defaultSite)', 'Sheet fallback preserved')
require(bridge, 'NOVA_ROOMMAID_REPORTING_DB_FIRST_V2', 'legacy reporting marker preserved')
require(bridge, 'ROOMMAID_CLOSE_SINGLE_BUNDLE_V5', 'bridge single-bundle marker')
require(bridge, 'roommaidCloseCurrentRowsFromDbBundle_', 'compact current-row mapper exists')
require(bridge, "readPath: currentRows.length ? 'DB_NATIVE_SINGLE_BUNDLE_V5' : 'DB_NATIVE_BUNDLE_V4'", 'DB read path identifies single bundle')
require(migration, 'ROOMMAID_CLOSE_SINGLE_BUNDLE_V5', 'migration marker')
require(migration, "'currentRowSchema'", 'RPC returns current-row schema')
require(migration, "'currentRows'", 'RPC returns current rows')
require(migration, 'jsonb_build_array(', 'RPC uses compact row arrays')
require(migration, "upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER')", 'RPC role guard preserved')
require(migration, 'security definer', 'RPC security mode preserved')

print(f'ROOMMAID_CLOSE_SINGLE_BUNDLE_V5 validation PASS: {len(checks)}/{len(checks)}')
