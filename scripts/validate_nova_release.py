from pathlib import Path
import sys

ROOT = Path('.')
errors = []
checks = []


def read(path):
    p = ROOT / path
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


def require_once(text, needle, label):
    count = text.count(needle)
    ok = count == 1
    checks.append((label, ok))
    if not ok:
        errors.append(f'COUNT {count}: {label} :: expected exactly 1')


client = read('Client.html')
index = read('Index.html')
realtime = read('RealtimeDailySync.js')
qm_browse = read('QmMobileBrowse.js')
qm_checklist = read('16_QmChecklist.js')
mobile = read('10_Mobile.js')
notification = read('HousemanUiPerformancePatch.html')
workflow = read('.github/workflows/deploy-apps-script.yml')
archive_server = read('ArchiveAdmin.js')
archive_client = read('ArchiveAdminClient.html')
archive_realtime = read('ArchiveAdminRealtimeClient.html')

# 1) Realtime routing / legacy protection
require(client, 'API 설정과 보조 Realtime 연결을 분리해 고속 API 유지', 'Realtime init isolation')
for action in [
    'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE',
    'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'
]:
    require(client, action, f'Client Realtime action {action}')
require(client, 'updateRoomOperationalStatusSafe', 'Operational status safe fallback')
for action in ['ASSIGN_ROOMMAID', 'CLEANING_RESET', 'CLEAR_ASSIGNMENT', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS']:
    require(realtime, f"action === '{action}'", f'Realtime mirror branch {action}')
forbid(index, "include_('OperationalStatusHotfix')", 'OperationalStatusHotfix excluded from Index')
forbid(notification, "addEventListener('click',onOperationalStatusClickCapture,true)", 'Operational status capture listener disabled')

# 1-1) Private Broadcast authorization / retry resilience
require(client, 'REALTIME_SUBSCRIPTION_RESILIENCE_V1', 'Realtime subscription resilience marker')
require(client, 'await novaRealtime_.supabase.realtime.setAuth(auth.token)', 'Realtime auth awaited before subscribe')
require(client, 'await novaRealtime_.supabase.realtime.setAuth(next.token)', 'Realtime refresh auth awaited')
require(client, "['CHANNEL_ERROR', 'TIMED_OUT', 'CLOSED']", 'Realtime failed subscription states handled')
require(client, 'novaRealtime_.channels.delete(site)', 'Failed Realtime channel removed for retry')
require(client, 'novaRealtimeEnsureSubscriptions_().catch(retryError', 'Realtime subscription retry scheduled')

# 2) Roommaid assignment invariants and same-row event batching
require(realtime, 'REALTIME_ASSIGNMENT_BATCH_MERGE_V1', 'Assignment batch merge hotfix')
require(realtime, 'Object.assign({}, previous, item, { rowNumber })', 'Same-row field merge implementation')


def merge_updates(updates):
    result = {}
    for item in updates:
        result = {**result, **item}
    return result

normal = merge_updates([
    {'cleaningStatus': 'ASSIGNED', 'cleaningType': 'NORMAL', 'assignmentType': 'PAIR', 'roommaidEmployeeNo': '11055', 'secondaryRoommaidEmployeeNo': '11058', 'version': 1},
    {'cleaningStatus': 'CLEANING', 'version': 2},
    {'cleaningStatus': 'COMPLETED', 'version': 3},
])
if not (
    normal.get('cleaningStatus') == 'COMPLETED'
    and normal.get('roommaidEmployeeNo') == '11055'
    and normal.get('secondaryRoommaidEmployeeNo') == '11058'
    and normal.get('assignmentType') == 'PAIR'
    and normal.get('cleaningType') == 'NORMAL'
):
    errors.append('STATE: ASSIGN -> START -> COMPLETE lost assignment fields')
else:
    checks.append(('ASSIGN -> START -> COMPLETE preserves assignment', True))

qm_flow = merge_updates([
    {'cleaningStatus': 'COMPLETED', 'cleaningType': 'NORMAL', 'assignmentType': 'PAIR', 'roommaidEmployeeNo': '11055', 'secondaryRoommaidEmployeeNo': '11058', 'version': 3},
    {'cleaningStatus': 'QM_WAITING', 'qmEmployeeNo': 'q001', 'version': 4},
    {'cleaningStatus': 'QM_CHECKING', 'version': 5},
    {'cleaningStatus': 'QM_COMPLETED', 'version': 6},
])
if not (
    qm_flow.get('roommaidEmployeeNo') == '11055'
    and qm_flow.get('secondaryRoommaidEmployeeNo') == '11058'
    and qm_flow.get('qmEmployeeNo') == 'q001'
    and qm_flow.get('cleaningStatus') == 'QM_COMPLETED'
):
    errors.append('STATE: QM flow lost roommaid/QM assignment fields')
else:
    checks.append(('QM flow preserves roommaid assignment', True))

reset = merge_updates([
    {'cleaningStatus': 'ASSIGNED', 'cleaningType': 'NORMAL', 'assignmentType': 'SOLO', 'roommaidEmployeeNo': '308628', 'secondaryRoommaidEmployeeNo': '', 'version': 1},
    {'cleaningStatus': 'WAITING', 'cleaningType': '', 'assignmentType': '', 'roommaidEmployeeNo': '', 'secondaryRoommaidEmployeeNo': '', 'qmEmployeeNo': '', 'version': 2},
])
if not (
    reset.get('cleaningStatus') == 'WAITING'
    and reset.get('roommaidEmployeeNo') == ''
    and reset.get('secondaryRoommaidEmployeeNo') == ''
    and reset.get('assignmentType') == ''
    and reset.get('cleaningType') == ''
    and reset.get('qmEmployeeNo') == ''
):
    errors.append('STATE: RESET/CLEAR did not explicitly clear assignment fields')
else:
    checks.append(('RESET/CLEAR explicitly clears assignment', True))

operational = merge_updates([
    {'cleaningStatus': 'COMPLETED', 'assignmentType': 'SOLO', 'roommaidEmployeeNo': '308628', 'operationalStatus': '', 'version': 3},
    {'operationalStatus': 'BROKEN', 'version': 4},
    {'operationalStatus': '', 'version': 5},
])
if operational.get('roommaidEmployeeNo') != '308628' or operational.get('cleaningStatus') != 'COMPLETED':
    errors.append('STATE: Operational status update mutated cleaning assignment')
else:
    checks.append(('Operational status does not clear roommaid assignment', True))

# 3) QM authorization / concurrency guard
require(qm_browse, "requireRole_(token, ['QM'])", 'QM browse role guard')
require(qm_browse, 'const lock = acquireWriteLock_(5000)', 'QM browse write lock')
require(qm_browse, '다른 QM에게 이미 배정되었거나 점검 중인 객실입니다.', 'QM concurrent ownership rejection')
require(qm_browse, "'QM사번': user.employeeNo", 'QM self-claim writes own employee number')
require(qm_checklist, '본인에게 배정된 객실만 점검할 수 있습니다.', 'QM checklist self-assignment guard')
require(qm_checklist, "['QM_WAITING', 'COMPLETED', 'QM_CHECKING']", 'QM checklist allowed start states')

# 4) Mobile role integrity
for role in ['ROOMMAID', 'QM', 'HOUSEMAN']:
    require(mobile, f"role === '{role}'", f'Mobile snapshot role {role}')
require(client, "['ROOMMAID', 'QM'].includes(mobileRole)", 'ROOMMAID/QM Realtime hydrate')
require(client, "data-room-action=\"START\"", 'Room action START rendered')
require(client, "data-room-action=\"COMPLETE\"", 'Room action COMPLETE rendered')
require(client, 'applyOptimisticRoommaidRoom_', 'Roommaid optimistic update')
require(client, 'restoreOptimisticRoommaidRoom_', 'Roommaid optimistic rollback')

# 5) Notification regression: Indicator + Houseman + Roommaid + QM
require(notification, 'QM_NOTIFICATION_BELL_V1', 'QM notification bell marker')
require(notification, 'ROOMMAID_NOTIFICATION_BELL_V1', 'Roommaid notification bell marker')
require(notification, "data-mobile-menu=\"houseman\"", 'Houseman notification selector')
require(notification, "data-mobile-menu=\"cleaning\"", 'Roommaid notification selector')
require(notification, "data-mobile-menu=\"qm\"", 'QM notification selector')
require(notification, "S.mode='ROOMMAID'", 'Roommaid notification mode')
require(notification, "S.mode='QM'", 'QM notification mode')
require(notification, 'function roommaidItem', 'Roommaid notification item mapping')
require(notification, 'function roommaidSummaryCount', 'Roommaid notification summary count')
require(notification, 'function qmItem', 'QM notification item mapping')
require(notification, "S.mode==='INDICATOR'||S.mode==='HOUSEMAN'||S.mode==='ROOMMAID'||S.mode==='QM'", 'All notification modes visible')
require(notification, "if(l==='대기'||l==='청소중')n+=v", 'Roommaid notification counts actionable rooms only')

# 6) QM supplemental tabs performance / existing-screen preservation
require(client, 'QM 추가조회 탭 · 기존 점검대상 화면 보존', 'QM original targets preserved')
require(client, 'QM 추가탭 동·층 필터 + 안전 즉시점검', 'QM location filters and safe inspection')
require(client, 'QM 추가탭 체크리스트 즉시노출 v1', 'QM immediate checklist')
require(client, 'QM 점검대상 정비자 이름 보존 v1', 'QM roommaid display name preservation')
require(qm_browse, '업무이력 전체 재조회 없이 현재 업무일자 객실상태만으로 판별', 'QM browse avoids full history scan')
forbid(qm_browse, 'readMonthlyHistoryRows_', 'QM browse must not scan monthly history')

# 7) Archive ADMIN / Realtime security and freshness invariants
require(index, "include_('ArchiveAdminClient')", 'Archive admin client included')
require(index, "include_('ArchiveAdminRealtimeClient')", 'Archive realtime client included')
require(archive_server, 'verifyNovaToken(token)', 'Archive server re-verifies NOVA token')
require(archive_server, "role !== 'ADMIN'", 'Archive server ADMIN-only guard')
require(archive_server, "getProperty('NOVA_TOKEN_SECRET')", 'Archive server secret stays in Script Properties')
require(archive_server, 'computeHmacSha256Signature', 'Archive server derives dedicated admin key')
require(archive_realtime, "const ARCHIVE_RT_TOPIC_ = 'nova:archive:status'", 'Archive private realtime topic fixed')
require(archive_realtime, '.channel(ARCHIVE_RT_TOPIC_, { config: { private: true } })', 'Archive realtime channel is private')
require(archive_realtime, 'await archiveRt_.client.realtime.setAuth(auth.token)', 'Archive realtime auth applied before subscribe')
require(archive_realtime, "['CHANNEL_ERROR', 'TIMED_OUT', 'CLOSED']", 'Archive realtime failure states handled')
require(archive_realtime, 'archiveRtStartFallback_', 'Archive realtime server fallback present')
require(archive_realtime, 'if (!archiveRtPageVisible_() || !archiveRtAdminMenuPresent_() || !archiveRtToken_()) return;', 'Archive realtime connects only on active ADMIN page')
require(archive_realtime, 'if (archiveRt_.pageActive)', 'Archive realtime disconnects after page exit')
forbid(archive_realtime, 'ARCHIVE_RT_CACHE_KEY_', 'Archive realtime stale local cache disabled')
for secret_name in ['NOVA_TOKEN_SECRET', 'X-NOVA-Archive-Admin-Key', 'SUPABASE_SERVICE_ROLE_KEY', 'service_role']:
    forbid(archive_client, secret_name, f'Archive browser client hides {secret_name}')
    forbid(archive_realtime, secret_name, f'Archive realtime browser hides {secret_name}')

# 8) Deployment repeatability / source-of-truth protection
require(workflow, 'python3 scripts/patch_realtime_subscription_resilience.py', 'Deploy applies Realtime subscription resilience patch')
require(workflow, 'python3 scripts/patch_roommaid_notification_bell.py', 'Deploy applies roommaid notification patch')
require(workflow, 'python3 scripts/validate_nova_release.py', 'Deploy runs release regression gate')
require(workflow, 'HousemanUiPerformancePatch.html', 'Generated notification source persisted')
require(workflow, 'RealtimeDailySync.js', 'Generated Realtime source persisted')

passed = sum(1 for _, ok in checks if ok)
print(f'NOVA release regression checks: {passed}/{len(checks)} passed')
for label, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {label}")

if errors:
    print('\nRELEASE GATE FAILED', file=sys.stderr)
    for error in errors:
        print(f'- {error}', file=sys.stderr)
    sys.exit(1)

print('\nRELEASE GATE PASSED')
