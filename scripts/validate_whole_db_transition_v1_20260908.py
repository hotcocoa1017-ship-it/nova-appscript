from pathlib import Path
import sys

errors = []
checks = []


def read(path):
    p = Path(path)
    if not p.exists():
        errors.append(f'MISSING FILE: {path}')
        return ''
    return p.read_text(encoding='utf-8')


def require(text, needle, label):
    ok = needle in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'MISSING: {label} :: {needle}')


def forbid(text, needle, label):
    ok = needle not in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'FORBIDDEN: {label} :: {needle}')


def order(text, left, right, label):
    li = text.find(left)
    ri = text.find(right)
    ok = li >= 0 and ri >= 0 and li < ri
    checks.append((label, ok))
    if not ok:
        errors.append(f'ORDER: {label} :: {left} -> {right}')


bridge = read('DbFirstBridge.js')
daily = read('DailyCloseDbFirstBridge.js')
monthly_bridge = read('MonthlyDbFirstBridge.js')
report_bridge = read('RoommaidReportingDbFirstBridge.js')
client = read('Client.html')
shift_server = read('12_ShiftManagement.js')
delay = read('13_DepartureDelay.js')
monthly = read('11_Monthly.js')
perf = read('17_RoommaidPerformance.js')
close = read('19_RoommaidCloseJournal.js')
api = read('04_Api.js')
center = read('NotificationCenterV1.html')
workflow = read('.github/workflows/deploy-apps-script.yml')
shift_sql = read('supabase/migrations/20260907_shift_zone_bootstrap_v3.sql')
delay_sql = read('supabase/migrations/20260907_departure_delay_db_first_v3.sql')

# 1) Common DB bridge: short-lived authenticated JWT, strict RPC allowlist and ambiguous-write fail closed.
require(bridge, 'NOVA_WHOLE_DB_FIRST_BRIDGE_V1', 'whole DB bridge marker')
require(bridge, '/v1/auth/realtime-token', 'existing Realtime auth bridge')
require(bridge, "error.code = 'NOVA_DB_RESULT_UNKNOWN'", 'ambiguous DB write fail-closed')
require(bridge, 'readOnly || safe.allowLegacyFallback === true', 'fallback restricted to safe cases')
for rpc in [
    'nova_houseman_shift_zone_get_v2', 'nova_houseman_shift_zone_bootstrap_v3',
    'nova_houseman_shift_save_v2', 'nova_houseman_zone_save_v1',
    'nova_departure_delay_dashboard_v1', 'nova_daily_close_source_v1',
    'nova_daily_close_save_v2', 'nova_daily_close_read_v1',
    'nova_monthly_history_v1', 'nova_roommaid_performance_history_v1',
    'nova_roommaid_close_history_v1'
]:
    require(bridge, f"'{rpc}'", f'RPC allowlist {rpc}')

# 2) Shift/zone: DB is authority after one-time initialization; Sheet writer remains mirror/fallback only.
require(client, "callServer('getShiftManagementDataDbFirst'", 'shift DB-first read route')
require(client, "callServer('saveShiftAssignmentsDbFirst'", 'shift DB-first save route')
require(client, "callServer('saveHousemanZoneAssignmentDbFirst'", 'zone DB-first save route')
require(client, "novaRealtimeRequestId_('SHIFT_SAVE_V3'", 'shift idempotent request id')
require(client, 'ZONE_${action}_V3', 'zone idempotent request id')
require(bridge, 'if (db && db.ok && db.initialized === true)', 'initialized DB authority')
require(bridge, 'initialized=false', 'one-time bootstrap comment/guard')
require(bridge, "'nova_houseman_shift_zone_bootstrap_v3'", 'shift bootstrap RPC')
require(bridge, 'mirrorShiftZoneDbStateToSheets_', 'shift compatibility mirror')
order(bridge, "'nova_houseman_shift_save_v2'", 'mirrorShiftZoneDbStateToSheets_(token, dbState)', 'shift DB commit before Sheet mirror')
require(shift_server, 'function saveShiftAssignments(', 'legacy shift writer preserved')
require(shift_server, 'function saveHousemanZoneAssignment(', 'legacy zone writer preserved')
require(shift_sql, 'HOUSEMAN_SHIFT_ZONE_BOOTSTRAP_V3', 'bootstrap dedupe action')
require(shift_sql, '초기화표시 없는 기존 데이터', 'bootstrap partial-state fail closed')
require(shift_sql, 'nova_houseman_roster_state', 'bootstrap initialization state')

# 3) Departure delay: DB cron + internal NOVA notification center; no Archive key/extra Edge coupling.
require(delay, 'DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4', 'departure notification-native app marker')
require(delay, "reason: 'DB_CRON_NATIVE'", 'Apps Script auto trigger delegates to DB cron')
require(delay, "nova_departure_delay_dashboard_v1", 'departure DB dashboard')
require(delay, 'processDepartureDelayAlertsLegacy_', 'legacy delay processor retained for compatibility only')
forbid(delay, 'NOVA_DEPARTURE_DELAY_SYSTEM_EDGE_', 'obsolete departure Edge endpoint')
forbid(delay, 'novaDepartureDelaySystemPost_', 'obsolete departure Edge bridge')
forbid(delay, 'novaArchiveAdminKey_', 'Archive credential coupling')
require(api, "['cleaning', 'qm', 'houseman', 'archive', 'indicator']", 'indicator PWA deep-link route')
require(center, "indicator:['통합 인디케이터']", 'notification center indicator route')
require(delay_sql, 'NOVA_DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4', 'departure DB-native migration marker')
require(delay_sql, 'nova_private.capture_departure_delays_v1', 'existing cron capture function retained')
require(delay_sql, 'nova_private.nova_notification_emit', 'internal notification emit')
require(delay_sql, "'DEPARTURE_DELAY'", 'departure notification kind')
require(delay_sql, "'route','indicator'", 'departure notification payload route')
forbid(delay_sql, 'Telegram', 'Telegram removed from native departure migration')
forbid(delay_sql, 'claim_service', 'obsolete claim service removed')
forbid(delay_sql, 'finalize_service', 'obsolete finalize service removed')
if Path('supabase/functions/nova-departure-delay-system-v1/index.ts').exists():
    errors.append('FORBIDDEN FILE: obsolete departure-delay Edge still present')
else:
    checks.append(('obsolete departure Edge removed', True))

# 4) Daily close: DB source -> unchanged existing calculation -> DB save -> Sheet compatibility mirror.
require(daily, 'NOVA_DAILY_CLOSE_DB_FIRST_V3', 'daily-close bridge marker')
require(daily, 'DAILY_CLOSE_SAVE_FALLBACK_FAILSAFE_V1', 'daily-close fallback fail-safe marker')
require(daily, "'nova_daily_close_source_v1'", 'daily-close DB source RPC')
require(daily, 'validateRoommaidCloseIntegrityForSave_', 'existing close integrity validation reused')
require(daily, 'buildDailyCloseSnapshot_', 'existing close calculation reused')
require(daily, "'nova_daily_close_save_v2'", 'daily-close DB save RPC')
require(daily, 'novaDailyCloseMirrorSnapshotToSheet_', 'daily-close Sheet compatibility mirror')
require(daily, 'let saveLegacyFallback = false', 'daily-close save fallback state')
require(daily, 'if (saveLegacyFallback) return saveDailyCloseSnapshot(token, payload);', 'safe pre-mutation legacy fallback')
order(daily, 'const prepared = [];', "'nova_daily_close_save_v2'", 'all sources prepared before first DB close write')
order(daily, "'nova_daily_close_save_v2'", 'novaDailyCloseMirrorSnapshotToSheet_', 'daily-close DB save before Sheet mirror')
require(client, "callServer('saveDailyCloseSnapshotDbFirst'", 'client daily-close DB-first route')
require(client, "novaRealtimeRequestId_('DAILY_CLOSE_V3'", 'daily-close request id')

# 5) Monthly/reporting: only native-complete date/site keys suppress legacy Sheet rows.
require(monthly_bridge, 'NOVA_MONTHLY_DB_FIRST_V2', 'monthly DB bridge marker')
require(monthly_bridge, "'nova_monthly_history_v1'", 'monthly DB history RPC')
require(monthly_bridge, 'const nativeKeys = new Set', 'monthly native-complete key set')
require(monthly_bridge, '.filter(row => !nativeKeys.has(', 'monthly duplicate Sheet suppression')
require(monthly, 'function readMonthlyHistoryRowsLegacy_', 'monthly legacy reader preserved')
require(monthly, 'readMonthlyHistoryRowsDbFirst_', 'monthly DB-aware reader')
require(client, "callServer('getMonthlyHistoryDbFirst'", 'monthly client DB read route')
require(client, "callServer('getMonthlyHistoryExportDbFirst'", 'monthly Excel DB route')
require(client, "callServer('writeMonthlyViewSheetDbFirst'", 'monthly Sheet export DB route')

require(report_bridge, 'NOVA_ROOMMAID_REPORTING_DB_FIRST_V2', 'roommaid reporting bridge marker')
require(report_bridge, "'nova_roommaid_close_history_v1'", 'roommaid close DB history RPC')
require(report_bridge, 'db.nativeComplete !== true', 'roommaid close hybrid boundary')
require(perf, 'ROOMMAID_REPORTING_DB_FIRST_APP_V2', 'roommaid performance DB token route')
require(close, 'ROOMMAID_REPORTING_DB_FIRST_APP_V2', 'roommaid close DB route')
require(close, 'readRoommaidCloseHistoryBundleDbFirst_', 'roommaid close DB history bridge')

# 6) Canonical workflow must gate these paths before any production push.
for script in [
    'patch_shift_zone_dbfirst_v3_20260907.py',
    'patch_departure_delay_dbfirst_v3_20260907.py',
    'patch_daily_close_dbfirst_fallback_v1_20260908.py',
    'patch_monthly_daily_dbfirst_v2_20260907.py',
    'patch_roommaid_reporting_dbfirst_v2_20260907.py',
    'validate_whole_db_transition_v1_20260908.py'
]:
    require(workflow, script, f'canonical workflow {script}')
for file in [
    'DbFirstBridge.js', 'DailyCloseDbFirstBridge.js', 'MonthlyDbFirstBridge.js',
    'RoommaidReportingDbFirstBridge.js', '13_DepartureDelay.js', '04_Api.js'
]:
    require(workflow, file, f'workflow tracks/syntax {file}')

if errors:
    print(f'Whole DB transition gate FAILED: {len(errors)} issue(s), {len(checks)} checks.', file=sys.stderr)
    for error in errors:
        print(f' - {error}', file=sys.stderr)
    raise SystemExit(98)

print(f'Whole DB transition integration gate passed: {len(checks)} checks.')
