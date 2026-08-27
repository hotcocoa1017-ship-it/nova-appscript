from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'
QM = ROOT / '16_QmChecklist.js'
SYNC = ROOT / 'RealtimeDailySync.js'


def fail(message):
    raise SystemExit(f'PATCH_ERROR: {message}')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# 1) Public server wrapper: after Cloud Run QM_ASSIGN commits, immediately consume
#    the DB event into Sheets and verify that the requested QM is now the Sheet
#    assignment. The existing event mirror owns history/dedup/cursor semantics.
# -----------------------------------------------------------------------------
sync = SYNC.read_text(encoding='utf-8')
anchor = "function novaRealtimeScheduledFinalSync() { // (1분 최종 통합: 이벤트 미러 + 5분 간격 정방향)\n"
if anchor not in sync:
    fail('RealtimeDailySync insertion anchor not found')

helper = r"""
function syncNovaRealtimeQmAssignmentMirror(token, payload) { // (QM 배정 DB 이벤트 즉시 Sheet 반영·검증)
  const user = requireRole_(token, ['ADMIN', 'ORDER']);
  const safe = payload || {};
  const businessDate = novaRealtimeFinalBusinessDate_(safe.businessDate);
  const site = String(safe.site || user.defaultSite || '').trim();
  const roomNo = String(safe.roomNo || '').trim();
  const expectedQmEmployeeNo = String(safe.employeeNo || '').trim();
  if (!site || !roomNo || !expectedQmEmployeeNo) {
    throw new Error('QM 배정 즉시동기화에 사업장·객실번호·QM 사번이 필요합니다.');
  }

  const mirror = mirrorNovaRealtimeEventsToSheets_();
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const rowInfo = findCurrentRoomRow_(sheet, businessDate, site, roomNo);
  if (!rowInfo) throw new Error(`${roomNo}호를 현재객실현황에서 찾을 수 없습니다.`);

  const currentQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
  if (currentQmEmployeeNo !== expectedQmEmployeeNo) {
    throw new Error('QM 배정정보 동기화 중 다른 배정이 반영되었습니다. 다시 불러온 뒤 확인하세요.');
  }

  return {
    ok: true,
    mirror,
    businessDate,
    site: String(rowInfo.data['사업장'] || site).trim(),
    roomNo,
    qmEmployeeNo: currentQmEmployeeNo,
    cleaningStatus: String(rowInfo.data['청소상태'] || '').trim().toUpperCase(),
    version: Number(rowInfo.data['마지막변경버전'] || 0)
  };
}

"""
if 'function syncNovaRealtimeQmAssignmentMirror(' not in sync:
    sync = sync.replace(anchor, helper + anchor, 1)
SYNC.write_text(sync, encoding='utf-8')


# -----------------------------------------------------------------------------
# 2) Client: a Cloud Run QM_ASSIGN is not considered complete until the existing
#    DB->Sheet event mirror has consumed and verified the assignment. This closes
#    the window where QM mobile sees DB assignment while startQmInspection still
#    reads an old Sheet QM사번.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')
old = """    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : mappedAction === 'CLEAR_ASSIGNMENT' ? '배정을 초기화했습니다.' : mappedAction === 'CLEANING_RESET' ? '청소완료 실적 초기화를 저장했습니다.' : '청소완료 처리했습니다.');\n"""
new = """    if (mappedAction === 'QM_ASSIGN') {\n      // QM 점검 시작/제출은 아직 Sheet 업무흐름을 사용한다.\n      // DB 배정 이벤트가 Sheet까지 반영된 것을 확인한 뒤에만 배정 완료로 처리한다.\n      const qmMirror = await callServer('syncNovaRealtimeQmAssignmentMirror', state.token, {\n        businessDate: safe.businessDate,\n        site: safe.site,\n        roomNo: safe.roomNo,\n        employeeNo: safe.employeeNo\n      });\n      if (!qmMirror?.ok) throw new Error('QM 배정정보를 업무시트에 동기화하지 못했습니다.');\n      if (result.room) {\n        result.room.qmEmployeeNo = String(qmMirror.qmEmployeeNo || result.room.qmEmployeeNo || '');\n        result.room.cleaningStatus = String(qmMirror.cleaningStatus || result.room.cleaningStatus || 'QM_WAITING');\n      }\n    }\n    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : mappedAction === 'CLEAR_ASSIGNMENT' ? '배정을 초기화했습니다.' : mappedAction === 'CLEANING_RESET' ? '청소완료 실적 초기화를 저장했습니다.' : '청소완료 처리했습니다.');\n"""
client = replace_once(client, old, new, 'Client immediate QM mirror')
CLIENT.write_text(client, encoding='utf-8')


# -----------------------------------------------------------------------------
# 3) QM start self-heal: older QM_ASSIGN events created before this release may
#    already exist in DB while Sheet QM사번 is blank/stale. Before taking the QM
#    write lock, perform one event-mirror pass only when the preflight Sheet row
#    does not show the logged-in QM. Then the existing locked assignment/status
#    checks remain authoritative.
# -----------------------------------------------------------------------------
qm = QM.read_text(encoding='utf-8')
old = """    if (!roomNo) throw new Error('객실번호가 없습니다.');\n    const writeLock = acquireWriteLock_();\n    try {\n    const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);\n"""
new = """    if (!roomNo) throw new Error('객실번호가 없습니다.');\n\n    // v57 이전/전환 직후 DB에는 QM 배정이 있으나 Sheet QM사번이 아직 미러되지 않은\n    // 짧은 구간을 자동 복구한다. 잠금 내부에서 mirror를 호출하면 이중 잠금이 되므로\n    // 반드시 사전조회 단계에서만 1회 실행하고, 아래 잠금에서 다시 원본을 검증한다.\n    const preflightSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);\n    const preflightRowInfo = findCurrentRoomRow_(preflightSheet, businessDate, site, roomNo);\n    if (preflightRowInfo\n        && String(preflightRowInfo.data['QM사번'] || '').trim() !== user.employeeNo\n        && typeof novaRealtimeFinalEnabled_ === 'function'\n        && novaRealtimeFinalEnabled_()\n        && typeof mirrorNovaRealtimeEventsToSheets_ === 'function') {\n      try {\n        mirrorNovaRealtimeEventsToSheets_();\n      } catch (syncError) {\n        console.warn('[NOVA QM] 점검시작 전 Realtime 배정 미러 실패:', syncError);\n      }\n    }\n\n    const writeLock = acquireWriteLock_();\n    try {\n    const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);\n"""
qm = replace_once(qm, old, new, 'QM start assignment self-heal')
QM.write_text(qm, encoding='utf-8')


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
for path in [SYNC, QM]:
    subprocess.run(['node', '--check', str(path)], cwd=ROOT, check=True)

client_text = CLIENT.read_text(encoding='utf-8')
start = client_text.find('<script>')
end = client_text.rfind('</script>')
if start < 0 or end <= start:
    fail('Client script block not found')
client_js = ROOT / '.tmp_qm_v58_client.js'
client_js.write_text(client_text[start + len('<script>'):end], encoding='utf-8')
try:
    subprocess.run(['node', '--check', str(client_js)], cwd=ROOT, check=True)
finally:
    if client_js.exists():
        client_js.unlink()

print('QM_ASSIGNMENT_MIRROR_V58_OK')
print('Changed: Client.html, RealtimeDailySync.js, 16_QmChecklist.js')
print('Policy: Cloud Run QM_ASSIGN -> immediate DB event mirror -> Sheet verification')
print('Self-heal: QM start mirrors pending pre-v58 assignment event once before locked validation')
print('Syntax: PASS')
