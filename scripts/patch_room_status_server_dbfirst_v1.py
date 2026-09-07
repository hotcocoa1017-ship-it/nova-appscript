from pathlib import Path

MARKER = 'ROOM_STATUS_SERVER_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


path = Path('06_Indicator.js')
text = path.read_text(encoding='utf-8')
if MARKER in text:
    print('room status server DB-first v1 already applied')
    raise SystemExit(0)

branch_anchor = """    // 일반 퇴실도 PostgreSQL을 원본으로 사용합니다. // CHECKOUT_DB_FIRST_V1
"""
branch = """    // 퇴실 외 일반 객실상태 변경도 PostgreSQL을 원본으로 사용합니다. // ROOM_STATUS_SERVER_DB_FIRST_V1
    // Realtime=Y이면 DB를 먼저 확정하고 현재객실현황·상태변경 이력은 DB 이벤트 미러가 후행 처리합니다.
    // CHECKED_OUT은 아래 전용 퇴실 경로를 그대로 사용해 기존 퇴실 알림 계약을 유지합니다.
    if (action === 'CHANGE_ROOM_STATUS'
        && String(safe.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT'
        && typeof novaMobileRealtimeEnabled_ === 'function'
        && novaMobileRealtimeEnabled_()
        && typeof novaMobileRealtimeActionFetch_ === 'function') {
      return changeIndicatorRoomStatusDbFirst_(token, user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // 일반 퇴실도 PostgreSQL을 원본으로 사용합니다. // CHECKOUT_DB_FIRST_V1
"""
text = replace_once(text, branch_anchor, branch, 'room status branch anchor')

helper_anchor = "function changeIndicatorRoomCheckoutDbFirst_(token, user, payload, context) { // (일반 퇴실 PostgreSQL 원본 경로) // CHECKOUT_DB_FIRST_V1\n"
helper = """function changeIndicatorRoomStatusDbFirst_(token, user, payload, context) { // (일반 객실상태 PostgreSQL 원본 경로) // ROOM_STATUS_SERVER_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  const requestedRoomStatus = String(safe.roomStatus || '').trim().toUpperCase();
  if (!site || !roomNo) throw new Error('객실상태 변경에 사업장과 객실번호가 필요합니다.');
  if (!requestedRoomStatus) throw new Error('변경할 객실상태를 선택하세요.');
  if (requestedRoomStatus === 'CHECKED_OUT') throw new Error('퇴실 상태는 전용 DB-first 경로를 사용해야 합니다.');

  const requestId = String(safe.requestId || '').trim() || `CHANGE_ROOM_STATUS:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const dbPayload = {
    businessDate,
    site,
    action: 'CHANGE_ROOM_STATUS',
    roomStatus: requestedRoomStatus,
    requestId,
    // Sheet 마지막변경버전과 PostgreSQL version은 서로 다른 도메인이므로 서버 fallback에서는 DB version 비교를 생략합니다.
    expectedVersion: 0,
    expectedState
  };
  const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
  if (!dbResult || !dbResult.ok) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
    error.code = String(dbResult && dbResult.code || 'ROOM_STATUS_DB_WRITE_FAILED');
    throw error;
  }

  const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};
  const version = Number(dbResult.version || dbRoom.version || 0);
  const finishedMs = Date.now();
  return {
    ok: true,
    dbFirst: true,
    alreadySet: Boolean(dbResult.idempotent || dbResult.alreadySet),
    version,
    requestId: String(dbResult.requestId || requestId),
    room: {
      rowNumber: Number(safe.rowNumber || 0),
      businessDate: String(dbRoom.businessDate || businessDate),
      site: String(dbRoom.site || site),
      roomNo: String(dbRoom.roomNo || roomNo),
      roomStatus: String(dbRoom.roomStatus || requestedRoomStatus),
      cleaningStatus: String(dbRoom.cleaningStatus || expectedState.cleaningStatus || ''),
      cleaningType: String(dbRoom.cleaningType || expectedState.cleaningType || NOVA.CLEANING_TYPES.NORMAL),
      assignmentType: String(dbRoom.assignmentType || expectedState.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO),
      roommaidEmployeeNo: String(dbRoom.roommaidEmployeeNo || expectedState.roommaidEmployeeNo || ''),
      secondaryRoommaidEmployeeNo: String(dbRoom.secondaryRoommaidEmployeeNo || expectedState.secondaryRoommaidEmployeeNo || ''),
      qmEmployeeNo: String(dbRoom.qmEmployeeNo || expectedState.qmEmployeeNo || ''),
      operationalStatus: String(dbRoom.operationalStatus || expectedState.operationalStatus || ''),
      updatedAt: String(dbRoom.updatedAt || ''),
      version
    },
    mirrorPending: true,
    // 상태변경 업무이력과 특수퇴실 후속 처리는 DB 이벤트 미러가 1회 수행합니다.
    notificationQueued: Boolean(dbResult.notificationQueued),
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      roomStatus: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
if helper_anchor not in text:
    raise SystemExit('room status helper anchor not found')
text = text.replace(helper_anchor, helper + helper_anchor, 1)
path.write_text(text, encoding='utf-8')
print('patched room status server DB-first v1')
