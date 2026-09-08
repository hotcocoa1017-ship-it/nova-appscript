from pathlib import Path
import hashlib
import re
import subprocess
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


def node_check(path, label):
    p = Path(path)
    if not p.exists():
        errors.append(f'SYNTAX MISSING: {path}')
        checks.append((label, False))
        return
    result = subprocess.run(['node', '--check', str(p)], text=True, capture_output=True, check=False)
    ok = result.returncode == 0
    checks.append((label, ok))
    if not ok:
        errors.append(f'SYNTAX: {label} :: {(result.stderr or result.stdout).strip()}')


def node_check_html(path, label):
    text = read(path)
    blocks = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
    if not blocks:
        errors.append(f'SYNTAX: {label} :: no script block')
        checks.append((label, False))
        return
    result = subprocess.run(['node', '--check', '-'], input='\n'.join(blocks), text=True, capture_output=True, check=False)
    ok = result.returncode == 0
    checks.append((label, ok))
    if not ok:
        errors.append(f'SYNTAX: {label} :: {(result.stderr or result.stdout).strip()}')


def digest(paths):
    h = hashlib.sha256()
    for path in paths:
        p = Path(path)
        h.update(path.encode('utf-8'))
        h.update(b'\0')
        h.update(p.read_bytes() if p.exists() else b'<missing>')
        h.update(b'\0')
    return h.hexdigest()


bridge = read('DbFirstBridge.js')
daily = read('DailyCloseDbFirstBridge.js')
monthly_bridge = read('MonthlyDbFirstBridge.js')
report_bridge = read('RoommaidReportingDbFirstBridge.js')
client = read('Client.html')
shift_server = read('12_Shifts.js')
delay = read('13_DepartureDelay.js')
monthly = read('11_Monthly.js')
perf = read('17_RoommaidPerformance.js')
close = read('19_RoommaidCloseJournal.js')
api = read('04_Api.js')
center = read('NotificationCenterV1.html')
canonical = read('scripts/fix_patch_site_scope_v2.py')
workflow = read('.github/workflows/deploy-apps-script.yml')
shift_sql = read('supabase/migrations/20260907_shift_zone_bootstrap_v3.sql')
delay_sql = read('supabase/migrations/20260907_departure_delay_db_first_v3.sql')
roommaid_close_cancel_sql = read('supabase/migrations/20260908_roommaid_close_cancel_db_first_v1.sql')
roommaid_close_cancel_sql = read('supabase/migrations/20260908_roommaid_close_cancel_db_first_v1.sql')

# Common DB bridge.
require(bridge, 'NOVA_WHOLE_DB_FIRST_BRIDGE_V1', 'whole DB bridge marker')
require(bridge, '/v1/auth/realtime-token', 'existing Realtime auth bridge')
require(bridge, "error.code = 'NOVA_DB_RESULT_UNKNOWN'", 'ambiguous DB write fail-closed')
require(bridge, 'readOnly || safe.allowLegacyFallback === true', 'fallback restricted to safe cases')
for rpc in [
    'nova_houseman_shift_zone_get_v2', 'nova_houseman_shift_zone_bootstrap_v3',
    'nova_houseman_shift_save_v2', 'nova_houseman_zone_save_v1',
    'nova_departure_delay_dashboard_v1', 'nova_daily_close_source_v1',
    'nova_daily_close_save_v2', 'nova_daily_close_read_v1', 'nova_roommaid_close_cancel_v1',
    'nova_monthly_history_v1', 'nova_roommaid_performance_history_v1',
    'nova_roommaid_close_history_v1'
]:
    require(bridge, f"'{rpc}'", f'RPC allowlist {rpc}')

# Shift / zone DB authority and compatibility mirror.
require(client, "callServer('getShiftManagementDataDbFirst'", 'shift DB-first read route')
require(client, "callServer('saveShiftAssignmentsDbFirst'", 'shift DB-first save route')
require(client, "callServer('saveHousemanZoneAssignmentDbFirst'", 'zone DB-first save route')
require(client, "novaRealtimeRequestId_('SHIFT_SAVE_V3'", 'shift request id')
require(client, 'ZONE_${action}_V3', 'zone request id')
require(bridge, 'if (db && db.ok && db.initialized === true)', 'initialized DB authority')
require(bridge, 'initialized=false', 'one-time bootstrap guard')
require(bridge, "'nova_houseman_shift_zone_bootstrap_v3'", 'shift bootstrap RPC')
require(bridge, 'mirrorShiftZoneDbStateToSheets_', 'shift compatibility mirror')
require(shift_server, 'function saveShiftAssignments(', 'legacy shift writer preserved')
require(shift_server, 'function saveHousemanZoneAssignment(', 'legacy zone writer preserved')
require(shift_sql, 'HOUSEMAN_SHIFT_ZONE_BOOTSTRAP_V3', 'bootstrap dedupe action')
require(shift_sql, '초기화표시 없는 기존 데이터', 'bootstrap partial-state fail closed')
require(shift_sql, 'nova_houseman_roster_state', 'bootstrap initialization state')

# Departure delay is native DB cron + NOVA notification center.
require(delay, 'DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4', 'departure app marker')
require(delay, "reason: 'DB_CRON_NATIVE'", 'Apps Script delegates auto check to DB cron')
require(delay, 'nova_departure_delay_dashboard_v1', 'departure DB dashboard')
require(delay, 'processDepartureDelayAlertsLegacy_', 'legacy processor preserved but inactive')
forbid(delay, 'NOVA_DEPARTURE_DELAY_SYSTEM_EDGE_', 'obsolete departure Edge endpoint')
forbid(delay, 'novaDepartureDelaySystemPost_', 'obsolete departure Edge bridge')
forbid(delay, 'novaArchiveAdminKey_', 'Archive credential coupling')
require(api, "['cleaning', 'qm', 'houseman', 'archive', 'indicator']", 'indicator PWA deep-link route')
require(center, "indicator:['통합 인디케이터']", 'notification center indicator route')
require(delay_sql, 'NOVA_DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4', 'departure migration marker')
require(delay_sql, 'nova_private.capture_departure_delays_v1', 'existing cron capture function')
require(delay_sql, 'nova_private.nova_notification_emit', 'internal notification emit')
require(delay_sql, "'DEPARTURE_DELAY'", 'departure notification kind')
require(delay_sql, "'route','indicator'", 'departure notification route payload')
forbid(delay_sql, 'queueTelegramNotification_', 'Telegram delivery call removed from DB path')
forbid(delay_sql, 'claim_service', 'obsolete claim service removed')
forbid(delay_sql, 'finalize_service', 'obsolete finalize service removed')
if Path('supabase/functions/nova-departure-delay-system-v1/index.ts').exists():
    errors.append('FORBIDDEN FILE: obsolete departure-delay Edge still present')
else:
    checks.append(('obsolete departure Edge removed', True))

# Daily close: all DB sources validate, existing calculation reused, DB commit precedes Sheet mirror.
require(daily, 'NOVA_DAILY_CLOSE_DB_FIRST_V3', 'daily-close bridge marker')
require(daily, 'DAILY_CLOSE_SAVE_FALLBACK_FAILSAFE_V1', 'daily-close fallback fail-safe')
require(daily, "'nova_daily_close_source_v1'", 'daily-close DB source RPC')
require(daily, 'validateRoommaidCloseIntegrityForSave_', 'existing integrity validator reused')
require(daily, 'buildDailyCloseSnapshot_', 'existing close calculation reused')
require(daily, "'nova_daily_close_save_v2'", 'daily-close DB save RPC')
require(daily, 'novaDailyCloseMirrorSnapshotToSheet_', 'daily-close Sheet compatibility mirror')
require(daily, 'let saveLegacyFallback = false', 'daily-close fallback state')
require(daily, 'if (saveLegacyFallback) return saveDailyCloseSnapshot(token, payload);', 'daily-close safe fallback')
order(daily, 'const prepared = [];', "const db = novaDbFirstRpc_(token, 'nova_daily_close_save_v2'", 'all sources prepared before first DB write')
order(daily, "const db = novaDbFirstRpc_(token, 'nova_daily_close_save_v2'", 'mirror = novaDailyCloseMirrorSnapshotToSheet_(', 'DB close commit before Sheet mirror call')
require(client, "callServer('saveDailyCloseSnapshotDbFirst'", 'client daily-close DB route')
require(client, "novaRealtimeRequestId_('DAILY_CLOSE_V3'", 'daily-close request id')
require(daily, 'ROOMMAID_CLOSE_SAVE_DB_FIRST_V1', 'roommaid close DB-first marker')
require(daily, 'novaDailyCloseLegacyUploadCompatSource_', 'pre-V4 upload metadata compatibility')
require(daily, 'function saveRoommaidCloseJournalDbFirst(', 'roommaid close DB-first save wrapper')
require(daily, 'function resetRoommaidCloseJournalDbFirst(', 'roommaid close DB-first reset wrapper')
require(daily, "'nova_roommaid_close_cancel_v1'", 'roommaid close cancel RPC')
require(client, "callServer('saveRoommaidCloseJournalDbFirst'", 'roommaid close save DB route')
require(client, "callServer('resetRoommaidCloseJournalDbFirst'", 'roommaid close reset DB route')
forbid(client, "callServer('saveRoommaidCloseJournal', state.token", 'roommaid close direct Sheet save removed')
forbid(client, "callServer('resetRoommaidCloseJournal', state.token", 'roommaid close direct Sheet reset removed')
require(close, 'function saveRoommaidCloseJournal(', 'legacy roommaid close writer preserved')
require(close, 'function resetRoommaidCloseJournal(', 'legacy roommaid reset writer preserved')
require(roommaid_close_cancel_sql, 'NOVA_ROOMMAID_CLOSE_CANCEL_DB_FIRST_V1', 'roommaid close cancel migration marker')
require(roommaid_close_cancel_sql, "not in ('ADMIN', 'ORDER')", 'roommaid close reset role parity')
require(roommaid_close_cancel_sql, 'revoke all on function public.nova_roommaid_close_cancel_v1', 'roommaid close cancel default execute revoked')
require(daily, 'ROOMMAID_CLOSE_SAVE_DB_FIRST_V1', 'roommaid close DB-first marker')
require(daily, 'novaDailyCloseLegacyUploadCompatSource_', 'pre-V4 upload metadata compatibility')
require(daily, 'function saveRoommaidCloseJournalDbFirst(', 'roommaid close DB-first save wrapper')
require(daily, 'function resetRoommaidCloseJournalDbFirst(', 'roommaid close DB-first reset wrapper')
require(daily, "'nova_roommaid_close_cancel_v1'", 'roommaid close cancel RPC')
require(client, "callServer('saveRoommaidCloseJournalDbFirst'", 'roommaid close save DB route')
require(client, "callServer('resetRoommaidCloseJournalDbFirst'", 'roommaid close reset DB route')
forbid(client, "callServer('saveRoommaidCloseJournal', state.token", 'roommaid close direct Sheet save removed')
forbid(client, "callServer('resetRoommaidCloseJournal', state.token", 'roommaid close direct Sheet reset removed')
require(close, 'function saveRoommaidCloseJournal(', 'legacy roommaid close writer preserved')
require(close, 'function resetRoommaidCloseJournal(', 'legacy roommaid reset writer preserved')
require(roommaid_close_cancel_sql, 'NOVA_ROOMMAID_CLOSE_CANCEL_DB_FIRST_V1', 'roommaid close cancel migration marker')
require(roommaid_close_cancel_sql, "not in ('ADMIN', 'ORDER')", 'roommaid close reset role parity')
require(roommaid_close_cancel_sql, 'revoke all on function public.nova_roommaid_close_cancel_v1', 'roommaid close cancel default execute revoked')

# Monthly/reporting hybrid boundary.
require(monthly_bridge, 'NOVA_MONTHLY_DB_FIRST_V2', 'monthly bridge marker')
require(monthly_bridge, "'nova_monthly_history_v1'", 'monthly DB history RPC')
require(monthly_bridge, 'const nativeKeys = new Set', 'monthly native key set')
require(monthly_bridge, '.filter(row => !nativeKeys.has(', 'monthly duplicate suppression')
require(monthly, 'function readMonthlyHistoryRowsLegacy_', 'monthly legacy reader preserved')
require(monthly, 'readMonthlyHistoryRowsDbFirst_', 'monthly DB-aware reader')
require(client, "callServer('getMonthlyHistoryDbFirst'", 'monthly DB route')
require(client, "callServer('getMonthlyHistoryExportDbFirst'", 'monthly Excel DB route')
require(client, "callServer('writeMonthlyViewSheetDbFirst'", 'monthly Sheet export DB route')
require(report_bridge, 'NOVA_ROOMMAID_REPORTING_DB_FIRST_V2', 'roommaid reporting bridge marker')
require(report_bridge, "'nova_roommaid_close_history_v1'", 'roommaid close DB RPC')
require(report_bridge, 'db.nativeComplete !== true', 'roommaid hybrid boundary')
require(perf, 'ROOMMAID_REPORTING_DB_FIRST_APP_V2', 'roommaid performance DB token')
require(close, 'ROOMMAID_REPORTING_DB_FIRST_APP_V2', 'roommaid close DB route')
require(close, 'readRoommaidCloseHistoryBundleDbFirst_', 'roommaid close DB bridge')

# Canonical workflow still owns a single meta-patch step; the meta-patcher owns all new changes.
require(workflow, 'python3 scripts/fix_patch_site_scope_v2.py', 'canonical workflow meta-patcher')
for script in [
    'patch_shift_zone_dbfirst_v3_20260907.py',
    'patch_departure_delay_dbfirst_v3_20260907.py',
    'patch_daily_close_dbfirst_fallback_v1_20260908.py',
    'patch_monthly_daily_dbfirst_v2_20260907.py',
    'patch_roommaid_reporting_dbfirst_v2_20260907.py',
    'patch_roommaid_close_save_dbfirst_v1_20260908.py',
    'validate_whole_db_transition_v2_20260908.py'
]:
    require(canonical, script, f'canonical meta-patcher {script}')

# Syntax gate for every newly introduced/touched runtime source.
for path in [
    'DbFirstBridge.js', 'DailyCloseDbFirstBridge.js', 'MonthlyDbFirstBridge.js',
    'RoommaidReportingDbFirstBridge.js', '13_DepartureDelay.js', '04_Api.js'
]:
    node_check(path, f'JavaScript syntax {path}')
node_check_html('NotificationCenterV1.html', 'Notification center script syntax')

# Self-contained idempotence for the new subset.
new_tracked = [
    'DbFirstBridge.js', 'DailyCloseDbFirstBridge.js', 'MonthlyDbFirstBridge.js', 'RoommaidReportingDbFirstBridge.js',
    'Client.html', '11_Monthly.js', '13_DepartureDelay.js', '17_RoommaidPerformance.js', '19_RoommaidCloseJournal.js',
    '04_Api.js', 'NotificationCenterV1.html', 'scripts/patch_pwa_web_push_v2.py'
]
before = digest(new_tracked)
for script in [
    'scripts/patch_shift_zone_dbfirst_v3_20260907.py',
    'scripts/patch_departure_delay_dbfirst_v3_20260907.py',
    'scripts/patch_daily_close_dbfirst_fallback_v1_20260908.py',
    'scripts/patch_monthly_daily_dbfirst_v2_20260907.py',
    'scripts/patch_roommaid_reporting_dbfirst_v2_20260907.py',
    'scripts/patch_roommaid_close_save_dbfirst_v1_20260908.py'
]:
    result = subprocess.run([sys.executable, script], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        errors.append(f'IDEMPOTENCE PATCH FAILED: {script} :: {(result.stderr or result.stdout).strip()}')
after = digest(new_tracked)
idempotent = before == after
checks.append(('whole-DB patch subset idempotent', idempotent))
if not idempotent:
    errors.append('IDEMPOTENCE: whole-DB patch subset changed sources on second run')

if errors:
    print(f'Whole DB transition gate FAILED: {len(errors)} issue(s), {len(checks)} checks.', file=sys.stderr)
    for error in errors:
        print(f' - {error}', file=sys.stderr)
    raise SystemExit(98)

print(f'Whole DB transition integration gate passed: {len(checks)} checks.')
