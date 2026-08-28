from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'RealtimeDailySync.js'
text = TARGET.read_text(encoding='utf-8')

start_marker = "function syncNovaRealtimeQmAssignmentMirror(token, payload) {"
end_marker = "function novaRealtimeScheduledFinalSync() {"
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('PATCH_ERROR: QM assignment mirror function boundary not found')

replacement = r'''function novaRealtimeFetchCurrentRoomForQmMirror_(token, businessDate, site, roomNo) { // (QM 배정 직후 DB 현재객실 직접확인)
  const props = PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  if (!apiBase) throw new Error('Realtime API 주소를 확인할 수 없습니다.');

  const query = [
    `businessDate=${encodeURIComponent(String(businessDate || ''))}`,
    `site=${encodeURIComponent(String(site || ''))}`
  ].join('&');
  const response = UrlFetchApp.fetch(`${apiBase}/v1/rooms?${query}`, {
    method: 'get',
    headers: { Authorization: `Bearer ${String(token || '').trim()}` },
    muteHttpExceptions: true,
    followRedirects: true
  });
  const status = Number(response.getResponseCode() || 0);
  let body = {};
  try { body = JSON.parse(response.getContentText() || '{}'); } catch (error) { body = {}; }
  if (status < 200 || status >= 300 || !body.ok) {
    throw new Error(String(body.message || body.error || `Realtime 객실확인 실패 (${status})`));
  }

  const targetRoomNo = String(roomNo || '').trim();
  const room = (Array.isArray(body.rooms) ? body.rooms : [])
    .find(item => String(item && item.roomNo || '').trim() === targetRoomNo);
  if (!room) throw new Error(`${targetRoomNo}호를 Realtime 현재객실에서 찾을 수 없습니다.`);
  return room;
}

function syncNovaRealtimeQmAssignmentMirror(token, payload) { // (QM 배정 DB 확정값을 해당 Sheet 1행에 즉시 반영·검증)
  const user = requireRole_(token, ['ADMIN', 'ORDER']);
  const safe = payload || {};
  const businessDate = novaRealtimeFinalBusinessDate_(safe.businessDate);
  const site = String(safe.site || user.defaultSite || '').trim();
  const roomNo = String(safe.roomNo || '').trim();
  const expectedQmEmployeeNo = String(safe.employeeNo || '').trim();
  if (!site || !roomNo || !expectedQmEmployeeNo) {
    throw new Error('QM 배정 즉시동기화에 사업장·객실번호·QM 사번이 필요합니다.');
  }

  // 전체 이벤트 큐를 먼저 미러하지 않는다. 방금 배정한 객실의 DB 현재값만 직접 확인한다.
  // 이력/Telegram 보존은 기존 예약 이벤트 미러가 후행 처리한다.
  const dbRoom = novaRealtimeFetchCurrentRoomForQmMirror_(token, businessDate, site, roomNo);
  const currentQmEmployeeNo = String(dbRoom.qmEmployeeNo || '').trim();
  if (currentQmEmployeeNo !== expectedQmEmployeeNo) {
    throw new Error('QM 배정 중 더 최신 배정이 확인되었습니다. 화면을 다시 불러온 뒤 확인하세요.');
  }
  const dbCleaningStatus = String(dbRoom.cleaningStatus || 'QM_WAITING').trim().toUpperCase() || 'QM_WAITING';

  const lock = acquireWriteLock_(5000);
  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRow_(sheet, businessDate, site, roomNo);
    if (!rowInfo) throw new Error(`${roomNo}호를 현재객실현황에서 찾을 수 없습니다.`);

    const sheetQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
    const sheetCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
    let version = Number(rowInfo.data['마지막변경버전'] || 0);
    let updated = false;

    if (sheetQmEmployeeNo !== currentQmEmployeeNo || sheetCleaningStatus !== dbCleaningStatus) {
      version = reserveDataVersion_({ lockHeld: true });
      updateRowByHeaders_(sheet, rowInfo.rowNumber, {
        'QM사번': currentQmEmployeeNo,
        '청소상태': dbCleaningStatus,
        '마지막변경버전': version,
        '수정일시': nowText_()
      });
      SpreadsheetApp.flush();
      publishDataVersion_(version, {
        domains: ['ROOM'],
        businessDate,
        site: String(rowInfo.data['사업장'] || site).trim(),
        lockHeld: true
      });
      updated = true;
    }

    return {
      ok: true,
      mirror: { ok: true, direct: true, source: 'REALTIME_CURRENT_ROOM', updated },
      businessDate,
      site: String(rowInfo.data['사업장'] || site).trim(),
      roomNo,
      qmEmployeeNo: currentQmEmployeeNo,
      cleaningStatus: dbCleaningStatus,
      version,
      dbRoomVersion: Number(dbRoom.version || 0)
    };
  } finally {
    try { lock.releaseLock(); } catch (ignore) {}
  }
}

'''

text = text[:start] + replacement + text[end:]
TARGET.write_text(text, encoding='utf-8')

# Guard the exact requested scope and architecture.
updated = TARGET.read_text(encoding='utf-8')
function_start = updated.find(start_marker)
function_end = updated.find(end_marker, function_start)
function_body = updated[function_start:function_end]
checks = {
    'direct DB current-room helper': 'novaRealtimeFetchCurrentRoomForQmMirror_' in updated,
    'uses Cloud Run current rooms': '/v1/rooms?' in updated and 'UrlFetchApp.fetch' in updated,
    'no global event mirror in assignment sync': 'mirrorNovaRealtimeEventsToSheets_()' not in function_body,
    'DB QM equality guard': 'currentQmEmployeeNo !== expectedQmEmployeeNo' in function_body,
    'single Sheet row update': "'QM사번': currentQmEmployeeNo" in function_body and "'청소상태': dbCleaningStatus" in function_body,
    'event mirror preserved elsewhere': 'function mirrorNovaRealtimeEventsToSheets_()' in updated,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('PATCH_ERROR: ' + ', '.join(failed))

# Syntax check as normal JavaScript; Apps Script globals are runtime-only and parse cleanly in Node.
subprocess.run(['node', '--check', str(TARGET)], check=True)

print('QM_ASSIGNMENT_DIRECT_MIRROR_V70_OK')
print('Changed: RealtimeDailySync.js only')
print('QM_ASSIGN: DB current room -> exact Sheet row; global event queue no longer blocks assignment')
print('Scheduled event mirror/history/Telegram: preserved')
print('Syntax: PASS')
