from pathlib import Path
import re
import sys

MARKER = 'CONCURRENT_WRITE_RESILIENCE_V1'
QM_BROWSE_SYNC_MARKER = 'QM_BROWSE_REALTIME_STATE_SYNC_V1'
perf_path = Path('05_Performance.js')
qm_path = Path('16_QmChecklist.js')
client_path = Path('Client.html')

perf = perf_path.read_text(encoding='utf-8')
qm = qm_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')
changed = False

# 1) 사용자별로 독립 가능한 저장을 위한 UserLock helper를 추가합니다.
if MARKER not in perf:
    anchor = '''function acquireWriteLock_(timeoutMs) { // (모든 핵심 쓰기를 하나의 짧은 ScriptLock으로 직렬화)\n  const lock = LockService.getScriptLock();\n  const waitMs = Math.max(500, Number(timeoutMs || NOVA.WRITE_LOCK_TIMEOUT_MS || 2500));\n  if (!lock.tryLock(waitMs)) {\n    const error = new Error('동시 저장 요청이 많습니다. 잠시 후 다시 처리하세요.');\n    error.code = 'BUSY_RETRY';\n    throw error;\n  }\n  return lock;\n}\n'''
    replacement = anchor + '''\nfunction acquireUserWriteLock_(timeoutMs) { // CONCURRENT_WRITE_RESILIENCE_V1 · 사용자별 독립 저장 직렬화\n  const lock = LockService.getUserLock();\n  const waitMs = Math.max(500, Number(timeoutMs || NOVA.WRITE_LOCK_TIMEOUT_MS || 2500));\n  if (!lock.tryLock(waitMs)) {\n    const error = new Error('현재 계정의 저장 요청이 겹쳤습니다. 잠시 후 다시 처리하세요.');\n    error.code = 'BUSY_RETRY';\n    throw error;\n  }\n  return lock;\n}\n'''
    if anchor not in perf:
        print('ERROR: acquireWriteLock_ anchor not found.', file=sys.stderr)
        raise SystemExit(101)
    perf = perf.replace(anchor, replacement, 1)
    changed = True

# 함수 범위 안에서 첫 global write lock만 UserLock으로 교체합니다.
def replace_lock_in_function(source, function_name):
    pattern = re.compile(
        rf"(function {re.escape(function_name)}\(.*?\) \{{.*?)(const writeLock = acquireWriteLock_\(\);)",
        re.S,
    )
    match = pattern.search(source)
    if not match:
        return source, False
    if 'acquireUserWriteLock_(); // CONCURRENT_WRITE_RESILIENCE_V1' in match.group(0):
        return source, False
    start, end = match.span(2)
    replacement = 'const writeLock = acquireUserWriteLock_(); // CONCURRENT_WRITE_RESILIENCE_V1'
    return source[:start] + replacement + source[end:], True

for function_name in [
    'saveQmInspectionDraft',
    'uploadQmInspectionPhoto',
    'deleteQmInspectionPhoto',
]:
    qm, did_change = replace_lock_in_function(qm, function_name)
    if did_change:
        changed = True
    elif f'function {function_name}' not in qm:
        print(f'ERROR: {function_name} not found.', file=sys.stderr)
        raise SystemExit(102)

# 안전 검증: 공용 데이터 변경 경로는 반드시 기존 ScriptLock을 유지합니다.
required_global_functions = [
    'startQmInspection',
    'submitQmChecklistInspection',
]
for function_name in required_global_functions:
    pattern = re.compile(rf"function {re.escape(function_name)}\(.*?\) \{{.*?const writeLock = acquireWriteLock_\(\);", re.S)
    if not pattern.search(qm):
        print(f'ERROR: shared-write protection changed unexpectedly in {function_name}.', file=sys.stderr)
        raise SystemExit(103)

# 대상 함수는 모두 UserLock이어야 합니다.
for function_name in [
    'saveQmInspectionDraft',
    'uploadQmInspectionPhoto',
    'deleteQmInspectionPhoto',
]:
    pattern = re.compile(rf"function {re.escape(function_name)}\(.*?\) \{{.*?acquireUserWriteLock_\(\); // {MARKER}", re.S)
    if not pattern.search(qm):
        print(f'ERROR: user-scoped lock missing in {function_name}.', file=sys.stderr)
        raise SystemExit(104)

if 'function acquireWriteLock_' not in perf or 'function acquireUserWriteLock_' not in perf:
    print('ERROR: lock helpers validation failed.', file=sys.stderr)
    raise SystemExit(105)

# 2) QM 추가조회(VACANT/CLEANED) 카드도 Realtime 완료 응답으로 즉시 갱신합니다.
# 기존 구현은 state.mobile.data.rooms만 갱신해 추가조회 캐시가 QM_CHECKING으로 남을 수 있었습니다.
# 그 상태에서 사용자가 다시 누르면 서버의 실제 QM_COMPLETED 상태와 충돌해
# "현재 공실 점검을 시작할 수 있는 상태가 아닙니다"가 잘못 노출될 수 있습니다.
if QM_BROWSE_SYNC_MARKER not in client:
    old_function = '''  function applyQmRealtimeRoomLocal_(roomNo, realtimeRoom) { // (QM Realtime 응답 즉시 모바일 반영)\n    const rooms = state.mobile.data?.rooms || [];\n    const index = rooms.findIndex(item => String(item.roomNo || '') === String(roomNo || ''));\n    if (index < 0 || !realtimeRoom) return null;\n    const mapped = novaRealtimeMapRow_(realtimeRoom);\n    const previousRoom = rooms[index];\n    rooms[index] = preserveQmMobileRoommaidNames_(previousRoom, novaRealtimeMergeRoom_(previousRoom, mapped));\n    if (state.activeMenu === 'qm') {\n      renderMobileSummary();\n      renderMobileList();\n    }\n    return rooms[index];\n  }\n'''
    new_function = '''  function applyQmRealtimeRoomLocal_(roomNo, realtimeRoom) { // (QM Realtime 응답 즉시 모바일·추가조회 반영) // QM_BROWSE_REALTIME_STATE_SYNC_V1\n    if (!realtimeRoom) return null;\n    const mapped = novaRealtimeMapRow_(realtimeRoom);\n    let resolvedRoom = null;\n\n    const rooms = state.mobile.data?.rooms || [];\n    const index = rooms.findIndex(item => String(item.roomNo || '') === String(roomNo || ''));\n    if (index >= 0) {\n      const previousRoom = rooms[index];\n      rooms[index] = preserveQmMobileRoommaidNames_(previousRoom, novaRealtimeMergeRoom_(previousRoom, mapped));\n      resolvedRoom = rooms[index];\n    }\n\n    const browse = state.mobile.qmBrowseData;\n    if (browse && Array.isArray(browse.rooms)) {\n      const browseIndex = browse.rooms.findIndex(item => String(item.roomNo || '') === String(roomNo || ''));\n      if (browseIndex >= 0) {\n        const previousBrowseRoom = browse.rooms[browseIndex];\n        browse.rooms[browseIndex] = preserveQmMobileRoommaidNames_(\n          previousBrowseRoom,\n          novaRealtimeMergeRoom_(previousBrowseRoom, mapped)\n        );\n        resolvedRoom = resolvedRoom || browse.rooms[browseIndex];\n      }\n    }\n\n    if (state.activeMenu === 'qm') {\n      if (typeof renderQmBrowseLocationFilters_ === 'function') renderQmBrowseLocationFilters_();\n      renderMobileSummary();\n      renderMobileList();\n    }\n    return resolvedRoom;\n  }\n'''
    if old_function not in client:
        print('ERROR: applyQmRealtimeRoomLocal_ anchor not found.', file=sys.stderr)
        raise SystemExit(106)
    client = client.replace(old_function, new_function, 1)
    changed = True

if QM_BROWSE_SYNC_MARKER not in client:
    print('ERROR: QM browse realtime state sync marker missing.', file=sys.stderr)
    raise SystemExit(107)
if "const browse = state.mobile.qmBrowseData;" not in client:
    print('ERROR: QM browse realtime cache update missing.', file=sys.stderr)
    raise SystemExit(108)

if changed:
    perf_path.write_text(perf, encoding='utf-8')
    qm_path.write_text(qm, encoding='utf-8')
    client_path.write_text(client, encoding='utf-8')
    print('Applied concurrent-write resilience and QM browse realtime state sync.')
else:
    print('Concurrent write resilience V1 and QM browse realtime state sync already applied.')
