from pathlib import Path
import re
import sys

MARKER = 'CONCURRENT_WRITE_RESILIENCE_V1'
perf_path = Path('05_Performance.js')
qm_path = Path('16_QmChecklist.js')

perf = perf_path.read_text(encoding='utf-8')
qm = qm_path.read_text(encoding='utf-8')
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

if changed:
    perf_path.write_text(perf, encoding='utf-8')
    qm_path.write_text(qm, encoding='utf-8')
    print('Applied CONCURRENT_WRITE_RESILIENCE_V1: QM autosave/photo writes now use per-user locks.')
else:
    print('Concurrent write resilience V1 already applied.')
