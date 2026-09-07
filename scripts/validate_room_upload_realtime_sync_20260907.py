from pathlib import Path
import re
import runpy
import subprocess
import tempfile

client = Path('Client.html').read_text(encoding='utf-8')
sync = Path('RealtimeDailySync.js').read_text(encoding='utf-8')
upload = Path('09_RoomStatusUpload.js').read_text(encoding='utf-8')


def require(text: str, needle: str, label: str):
    if needle not in text:
        raise SystemExit(f'ERROR: missing {label}: {needle}')


def forbid(text: str, needle: str, label: str):
    if needle in text:
        raise SystemExit(f'ERROR: forbidden {label}: {needle}')


def require_order(text: str, first: str, second: str, label: str):
    a = text.find(first)
    b = text.find(second)
    if a < 0 or b < 0 or a >= b:
        raise SystemExit(f'ERROR: invalid order for {label}')


def require_regex(text: str, pattern: str, label: str):
    if not re.search(pattern, text, flags=re.S):
        raise SystemExit(f'ERROR: missing {label}: {pattern}')


# SQL/read-authority contract must be valid before the app bridge is accepted.
runpy.run_path('scripts/validate_room_upload_db_first_v4_20260907.py', run_name='__main__')

# Existing DB read authority / legacy convergence remains as fallback only.
require(client, 'ROOM_UPLOAD_REALTIME_CONVERGENCE_V1', 'client convergence marker')
require(sync, 'ROOM_UPLOAD_REALTIME_CONVERGENCE_V1', 'server convergence marker')
require(sync, "mirrorNovaRealtimeEventsDrain_({ maxBatches: 2, timeBudgetMs: 45000 })", 'legacy mirror-first drain')
require_order(sync, "mirrorNovaRealtimeEventsDrain_({ maxBatches: 2, timeBudgetMs: 45000 })", "syncNovaRealtimeCurrentBusinessDate(dateText, siteText, {})", 'legacy DB events mirror before Sheet forward sync')
require(client, 'ROOM_STATUS_DB_READ_AUTHORITY_V1', 'roomStatus DB read-authority marker')
require_regex(client, r"const NOVA_REALTIME_ROOM_FIELDS_ = Object\.freeze\(\[.*?'roomStatus',\s*'cleaningStatus'", 'roomStatus in DB-owned merge fields')
require(client, "roomStatus: String(row.room_status ?? row.roomStatus ?? '')", 'full DB row roomStatus mapping')
require(client, "putText('roomStatus', 'room_status', 'roomStatus');", 'partial DB row roomStatus mapping')
require(client, 'CHECKOUT_DB_FIRST_CLIENT_V1', 'CHECKED_OUT DB-first path remains')

# New operational DB-first V4 server bridge.
require(upload, 'ROOM_UPLOAD_DB_FIRST_APP_V4', 'V4 app marker')
require(upload, 'function prepareRoomStatusUploadDbFirst(token, previewId, options)', 'prepare function')
require(upload, 'function mirrorRoomStatusUploadDbFirst(token, previewId, planId, payload)', 'mirror function')
require(upload, "kind: 'ROOM_UPLOAD_DB_FIRST_APP_V4'", 'runtime marker literal')
require(upload, "plan.kind !== 'ROOM_UPLOAD_DB_FIRST_APP_V4'", 'mirror plan marker literal')
require(upload, "source: 'ROOM_UPLOAD_DB_FIRST_APP_V4'", 'history source marker literal')
forbid(upload, 'kind: MARKER', 'Python marker leaked into JS')
forbid(upload, 'plan.kind !== MARKER', 'Python marker leaked into mirror guard')
forbid(upload, 'source: MARKER', 'Python marker leaked into history')

prepare_start = upload.index('function prepareRoomStatusUploadDbFirst(')
mirror_start = upload.index('function mirrorRoomStatusUploadDbFirst(')
legacy_start = upload.index('function applyRoomStatusUpload(')
prepare_block = upload[prepare_start:mirror_start]
mirror_block = upload[mirror_start:legacy_start]

# Prepare may use the existing temporary preview store, but must not mutate operational current/history state before DB commit.
for needle, label in [
    ('getRequiredSheet_(NOVA.SHEETS.CURRENT)', 'current-sheet mutation'),
    ('appendUnifiedHistory_(', 'operational history write'),
    ('resetRoomMaintenanceHistoryForUpload_(', 'maintenance reset'),
    ('publishDataVersion_(', 'published room version'),
    ('SpreadsheetApp.flush()', 'operational flush'),
]:
    forbid(prepare_block, needle, f'prepare-before-DB {label}')
require(prepare_block, 'saveRoomUploadPreview_(planId, plan);', 'non-authoritative mirror-plan persistence')

# Existing business rules are reused rather than reimplemented.
for helper in [
    'resolveEffectiveUploadRoomStatus_',
    'resolveUploadOperationState_',
    'enforceUploadRoomOperationState_',
    'resolveUploadedRoommaidAssignment_',
    'buildUploadDepartureConfirmedAssignment_',
    'resolveIndicatorLastRoomStatusForUpload_',
]:
    require(prepare_block, helper, f'existing business helper {helper}')

# Full DB state payload, including previous-cycle and operation flags.
for field in [
    'lastRoomStatus:', 'previousRoomStatus:', 'previousCleaningStatus:',
    'previousRoommaidEmployeeNo:', 'previousSecondaryRoommaidEmployeeNo:',
    'operationalStatus:', 'preassigned:', 'vip:', 'importantRoom:',
    'expectedVersions',
]:
    require(prepare_block, field, f'V4 prepare field {field}')

# Sheet/history is a post-commit mirror from the latest DB snapshot; preserve Sheet-only houseman display state.
for needle, label in [
    ('getRequiredSheet_(NOVA.SHEETS.CURRENT)', 'current Sheet mirror'),
    ("housemanStatus: String(data['하우스맨상태'] || '').trim()", 'houseman status preservation'),
    ("housemanPending: Number(data['하우스맨미완료수'] || 0)", 'houseman pending preservation'),
    ("'마지막객실상태': String(db['마지막객실상태']", 'last room status DB mirror'),
    ("'이전객실상태': String(db['이전객실상태']", 'previous room DB mirror'),
    ("'이전청소상태': String(db['이전청소상태']", 'previous cleaning DB mirror'),
    ("'이전룸메이드사번': String(db['이전룸메이드사번']", 'previous primary DB mirror'),
    ("'이전보조룸메이드사번': String(db['이전보조룸메이드사번']", 'previous secondary DB mirror'),
    ("'선배정여부': normalizeYesNo_(db['선배정여부'])", 'preassigned DB mirror'),
    ("'VIP여부': normalizeYesNo_(db['VIP여부'])", 'VIP DB mirror'),
    ("'중요객실여부': normalizeYesNo_(db['중요객실여부'])", 'important DB mirror'),
    ("properties.getProperty('NOVA_DATA_VERSION')", 'global version monotonic guard'),
    ('publishDataVersion_(dbVersion', 'DB version publish'),
    ('resetRoomMaintenanceHistoryForUpload_', 'reset maintenance parity'),
    ('NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD', 'upload history parity'),
    ('appendRoomUploadAssignmentHistory_', 'assignment history parity'),
    ('queueRoomUploadAssignmentTelegrams_', 'assignment notification parity'),
    ('queueRoomUploadDepartureConfirmedTelegrams_', 'departure notification parity'),
    ('removeRoomUploadPreview_(previewId, true)', 'preview cleanup'),
]:
    require(mirror_block, needle, label)

# Client orchestration: read DB -> calculate -> atomic V4 commit -> re-read DB -> mirror.
for needle, label in [
    ('async function novaRoomUploadRpcV4_', 'direct RPC helper'),
    ("novaRoomUploadRpcV4_('nova_room_upload_state_v3'", 'state V3 read'),
    ("callServer('prepareRoomStatusUploadDbFirst'", 'legacy-rule prepare call'),
    ("novaRoomUploadRpcV4_('nova_room_upload_apply_v4'", 'atomic apply V4'),
    ('p_expected_versions: prepared.expectedVersions', 'per-room optimistic versions'),
    ('p_request_id: stable.requestId', 'stable DB request id'),
    ("sessionStorage.getItem(key)", 'request-id retry persistence'),
    ("error.code = 'ROOM_UPLOAD_DB_RESULT_UNKNOWN'", 'ambiguous network fail-closed'),
    ("error.code = 'ROOM_UPLOAD_DB_COMMITTED_MIRROR_PENDING'", 'post-commit mirror pending state'),
    ("callServer('mirrorRoomStatusUploadDbFirst'", 'post-commit Sheet mirror'),
    ("if (novaRealtimeIsEnabled_() && result?.dbFirst !== true)", 'legacy-only forward convergence'),
    ('const result = await novaRoomUploadDbFirstV4_(previewId, resetMode);', 'UI final apply routed through V4'),
]:
    require(client, needle, label)

require_order(client, "beforeState = await novaRoomUploadStateV3_", "callServer('prepareRoomStatusUploadDbFirst'", 'DB snapshot before prepare')
require_order(client, "callServer('prepareRoomStatusUploadDbFirst'", "novaRoomUploadRpcV4_('nova_room_upload_apply_v4'", 'prepare before DB commit')
require_order(client, "novaRoomUploadRpcV4_('nova_room_upload_apply_v4'", "afterState = await novaRoomUploadStateV3_", 'DB commit before latest-state read')
require_order(client, "afterState = await novaRoomUploadStateV3_", "callServer('mirrorRoomStatusUploadDbFirst'", 'latest DB read before Sheet mirror')

# A post-mutation unknown/conflict must never enter the legacy Sheet-first final apply path.
require_regex(
    client,
    r"committed = await novaRoomUploadRpcV4_\('nova_room_upload_apply_v4'.*?catch \(error\) \{.*?if \(error\?\.missingRpc\).*?return callServer\('applyRoomStatusUpload'.*?\n\s*\}\n\s*// 네트워크 결과불명/버전충돌/권한오류에서는 Sheet-first를 병행하지 않습니다\.\n\s*throw error;",
    'only missing-RPC can fallback after V4 call attempt'
)

# Legacy function remains intact as pre-mutation compatibility fallback.
require(upload, 'function applyRoomStatusUpload(token, previewId, options)', 'legacy apply fallback preserved')
require(upload, "sheet.getRange(firstWrittenRow, 1, newRows.length, lastColumn).setValues(newRows)", 'legacy in-place write preserved')

# Syntax-gate both generated Apps Script and the generated Client script blocks now, not only at deploy time.
subprocess.run(['node', '--check', '09_RoomStatusUpload.js'], check=True)
with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8', delete=False) as handle:
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', client, flags=re.S | re.I)
    if not scripts:
        raise SystemExit('ERROR: Client.html has no script blocks')
    handle.write('\n'.join(scripts))
    client_js = handle.name
subprocess.run(['node', '--check', client_js], check=True)

print('PASS: room upload DB-first V4 app bridge preserves legacy rules and side effects, commits DB before operational Sheet writes, uses exact per-room versions, fails closed on ambiguous results, and passes JS syntax checks.')
