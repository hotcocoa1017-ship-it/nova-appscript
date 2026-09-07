from pathlib import Path

MARKER = 'CLEANING_RESET_SERVER_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


path = Path('06_Indicator.js')
text = path.read_text(encoding='utf-8')
if MARKER in text:
    print('cleaning reset server DB-first v1 already applied')
    raise SystemExit(0)

old_branch = """    // 청소초기화는 해당 객실의 금일 활성 청소완료 이력을 전부 취소하고 현재 배정을 원점으로 되돌린다.
    if (action === 'CLEANING_RESET') {
      return resetIndicatorRoomCleaningFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }
"""
new_branch = """    // 청소초기화도 PostgreSQL을 원본으로 사용합니다. // CLEANING_RESET_SERVER_DB_FIRST_V1
    // Client 직통 Realtime 경로뿐 아니라 Apps Script 서버 진입점을 직접 호출해도
    // Realtime=Y이면 DB를 먼저 확정하고 Sheet/업무이력 soft-delete는 DB 이벤트 미러가 후행 처리합니다.
    if (action === 'CLEANING_RESET') {
      if (typeof novaMobileRealtimeEnabled_ === 'function'
          && novaMobileRealtimeEnabled_()
          && typeof novaMobileRealtimeActionFetch_ === 'function') {
        return resetIndicatorRoomCleaningDbFirst_(token, user, safe, {
          startedMs,
          businessDate,
          site,
          roomNo
        });
      }
      return resetIndicatorRoomCleaningFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }
"""
text = replace_once(text, old_branch, new_branch, 'cleaning reset branch')

anchor = "function resetIndicatorRoomCleaningFast_(user, payload, context) { // (객실 금일 청소완료 전체취소·배정 초기화)\n"
helper = """function resetIndicatorRoomCleaningDbFirst_(token, user, payload, context) { // (청소완료 실적초기화 PostgreSQL 원본 경로) // CLEANING_RESET_SERVER_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  if (!site || !roomNo) throw new Error('청소초기화에 사업장과 객실번호가 필요합니다.');

  const requestId = String(safe.requestId || '').trim() || `CLEANING_RESET:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const dbPayload = {
    businessDate,
    site,
    action: 'CLEANING_RESET',
    requestId,
    // Sheet 마지막변경버전과 PostgreSQL version은 서로 다른 도메인입니다.
    // DB row-lock + 상태검증을 사용하므로 서버 안전경로에서도 Sheet version을 전달하지 않습니다.
    expectedVersion: 0,
    expectedState
  };
  const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
  if (!dbResult || !dbResult.ok) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
    error.code = String(dbResult && dbResult.code || 'CLEANING_RESET_DB_WRITE_FAILED');
    throw error;
  }

  const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};
  const version = Number(dbResult.version || dbRoom.version || 0);
  const finishedMs = Date.now();
  return {
    ok: true,
    dbFirst: true,
    alreadyReset: Boolean(dbResult.idempotent || dbResult.alreadyReset || dbResult.alreadySet),
    version,
    requestId: String(dbResult.requestId || requestId),
    resetCompletionCount: Number(dbResult.resetCompletionCount || 0),
    removedCompletionRecordIds: Array.isArray(dbResult.removedCompletionRecordIds) ? dbResult.removedCompletionRecordIds : [],
    removedEmployeeNos: Array.isArray(dbResult.removedEmployeeNos) ? dbResult.removedEmployeeNos : [],
    room: {
      rowNumber: Number(safe.rowNumber || 0),
      businessDate: String(dbRoom.businessDate || businessDate),
      site: String(dbRoom.site || site),
      roomNo: String(dbRoom.roomNo || roomNo),
      roomStatus: String(dbRoom.roomStatus || expectedState.roomStatus || ''),
      cleaningStatus: String(dbRoom.cleaningStatus || 'WAITING'),
      cleaningType: '',
      assignmentType: '',
      roommaidEmployeeNo: '',
      roommaidName: '',
      secondaryRoommaidEmployeeNo: '',
      secondaryRoommaidName: '',
      qmEmployeeNo: '',
      qmName: '',
      operationalStatus: String(dbRoom.operationalStatus || expectedState.operationalStatus || ''),
      updatedAt: String(dbRoom.updatedAt || ''),
      version
    },
    mirrorPending: true,
    notificationQueued: false,
    timing: {
      cleaningReset: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
if anchor not in text:
    raise SystemExit('cleaning reset helper anchor not found')
text = text.replace(anchor, helper + anchor, 1)
path.write_text(text, encoding='utf-8')
print('patched cleaning reset server DB-first v1')
