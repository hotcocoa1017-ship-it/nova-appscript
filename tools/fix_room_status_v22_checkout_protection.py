#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'


def fail(message):
    print(f'PATCH_ERROR: {message}')
    sys.exit(1)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)

if not CLIENT.exists():
    fail('Client.html not found')

text = CLIENT.read_text(encoding='utf-8')
original = text

# Do not make roomStatus globally DB-owned because CHECKED_OUT still uses the existing
# Apps Script fast path. A stale DB roomStatus must never overwrite a just-saved checkout.
text = replace_once(
    text,
    "    'roomStatus', 'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'version', 'updatedAt'",
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'version', 'updatedAt'",
    'remove global DB ownership of roomStatus'
)

# Add a short per-room protection map only for CHANGE_ROOM_STATUS requests that actually
# use Realtime. Legacy CHECKED_OUT never creates an entry and therefore remains Sheet-owned.
text = replace_once(
    text,
    "    indicatorEventCursorTime: '',\n    indicatorEventCursorRequestId: ''\n  };",
    "    indicatorEventCursorTime: '',\n    indicatorEventCursorRequestId: '',\n    roomStatusProtections: new Map()\n  };",
    'room status protection map'
)

merge_anchor = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;\n\n    if (Object.prototype.hasOwnProperty.call(realtimeRoom, 'roommaidEmployeeNo')"""
merge_insert = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;\n\n    // 일반 객실상태 Realtime 저장 직후 Sheet 미러가 따라올 때까지만 상태를 보호한다.\n    // CHECKED_OUT은 이 보호맵을 사용하지 않으므로 기존 Apps Script 퇴실 결과가 stale DB에 의해 되돌아가지 않는다.\n    const protectionKey = `${String(merged.site || '').trim()}|${String(merged.roomNo || '').trim()}`;\n    const statusProtection = novaRealtime_.roomStatusProtections.get(protectionKey);\n    if (statusProtection) {\n      if (Date.now() >= Number(statusProtection.expiresAt || 0)) {\n        novaRealtime_.roomStatusProtections.delete(protectionKey);\n      } else if (String(legacyRoom?.roomStatus || '').trim().toUpperCase() === String(statusProtection.roomStatus || '').trim().toUpperCase()) {\n        // Sheet 미러가 새 상태를 따라오면 즉시 보호 해제.\n        novaRealtime_.roomStatusProtections.delete(protectionKey);\n      } else {\n        merged.roomStatus = String(statusProtection.roomStatus || merged.roomStatus || '');\n      }\n    }\n\n    if (Object.prototype.hasOwnProperty.call(realtimeRoom, 'roommaidEmployeeNo')"""
text = replace_once(text, merge_anchor, merge_insert, 'merge room status protection')

result_anchor = """    result.version = Number(result.version || result.room?.version || 0);\n    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : '청소완료 처리했습니다.');\n    return result;"""
result_insert = """    result.version = Number(result.version || result.room?.version || 0);\n    if (mappedAction === 'CHANGE_ROOM_STATUS') {\n      const protectedStatus = String(result.room?.roomStatus || safe.roomStatus || '').trim().toUpperCase();\n      const protectionKey = `${String(safe.site || '').trim()}|${String(safe.roomNo || '').trim()}`;\n      if (protectedStatus && protectionKey !== '|') {\n        novaRealtime_.roomStatusProtections.set(protectionKey, {\n          roomStatus: protectedStatus,\n          expiresAt: Date.now() + 75000\n        });\n      }\n    }\n    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : '청소완료 처리했습니다.');\n    return result;"""
text = replace_once(text, result_anchor, result_insert, 'set status protection after realtime success')

CLIENT.write_text(text, encoding='utf-8')

# Client.html is an HTML fragment, so validate the embedded script by extracting it into a temp JS file.
start = text.find('<script>')
end = text.rfind('</script>')
if start < 0 or end <= start:
    fail('Client embedded script not found')
script = text[start + len('<script>'):end]
tmp = ROOT / '.tmp_client_status_guard.js'
tmp.write_text(script, encoding='utf-8')
try:
    subprocess.run(['node', '--check', str(tmp)], cwd=ROOT, check=True)
    subprocess.run(['git', 'diff', '--check', '--', 'Client.html'], cwd=ROOT, check=True)
finally:
    if tmp.exists():
        tmp.unlink()

print('FIX_OK')
print('Changed: Client.html only')
print('Protected: legacy CHECKED_OUT remains Sheet-owned and cannot be overwritten by stale DB roomStatus')
print('Protected: general Realtime room-status changes keep a temporary 75s local guard until Sheet mirror catches up')
print('Syntax: PASS')
subprocess.run(['git', 'diff', '--stat', '--', 'Client.html'], cwd=ROOT, check=True)
