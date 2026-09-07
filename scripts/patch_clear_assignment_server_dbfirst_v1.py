from pathlib import Path

MARKER = 'CLEAR_ASSIGNMENT_SERVER_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


path = Path('06_Indicator.js')
text = path.read_text(encoding='utf-8')
if MARKER in text:
    print('clear assignment server DB-first v1 already applied')
    raise SystemExit(0)

branch_anchor = """    // 룸메이드 배정도 PostgreSQL을 원본으로 사용합니다. // ROOMMAID_ASSIGN_SERVER_DB_FIRST_V1
"""
branch = """    // 배정 초기화도 PostgreSQL을 원본으로 사용합니다. // CLEAR_ASSIGNMENT_SERVER_DB_FIRST_V1
    // Realtime=Y이면 DB에서 룸메이드·보조·QM·정비유형을 먼저 초기화하고
    // 현재객실현황·업무이력은 DB 이벤트 미러가 후행 처리합니다.
    if (action === 'CLEAR_ASSIGNMENT'
        && typeof novaMobileRealtimeEnabled_ === 'function'
        && novaMobileRealtimeEnabled_()
        && typeof novaMobileRealtimeActionFetch_ === 'function') {
      return clearIndicatorRoomAssignmentDbFirst_(token, user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // 룸메이드 배정도 PostgreSQL을 원본으로 사용합니다. // ROOMMAID_ASSIGN_SERVER_DB_FIRST_V1
"""
text = replace_once(text, branch_anchor, branch, 'clear assignment branch anchor')

helper_anchor = "function assignIndicatorRoommaidDbFirst_(token, user, payload, context) { // (룸메이드 배정 PostgreSQL 원본 경로) // ROOMMAID_ASSIGN_SERVER_DB_FIRST_V1\n"
helper = """function clearIndicatorRoomAssignmentDbFirst_(token, user, payload, context) { // (배정 초기화 PostgreSQL 원본 경로) // CLEAR_ASSIGNMENT_SERVER_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  if (!site || !roomNo) throw new Error('배정 초기화에 사업장과 객실번호가 필요합니다.');

  const requestId = String(safe.requestId || '').trim() || `CLEAR_ASSIGNMENT:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const dbPayload = {
    businessDate,
    site,
    action: 'CLEAR_ASSIGNMENT',
    requestId,
    // Apps Script fallback의 expectedVersion은 Sheet 버전일 수 있으므로 DB version 비교에는 사용하지 않습니다.
    expectedVersion: 0,
    expectedState
  };
  const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
  if (!dbResult || !dbResult.ok) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
    error.code = String(dbResult && dbResult.code || 'CLEAR_ASSIGNMENT_DB_WRITE_FAILED');
    throw error;
  }

  const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};
  const version = Number(dbResult.version || dbRoom.version || 0);
  const finishedMs = Date.now();
  return {
    ok: true,
    dbFirst: true,
    alreadyCleared: Boolean(dbResult.idempotent || dbResult.alreadyCleared || dbResult.alreadySet),
    version,
    requestId: String(dbResult.requestId || requestId),
    room: {
      rowNumber: Number(safe.rowNumber || 0),
      businessDate: String(dbRoom.businessDate || businessDate),
      site: String(dbRoom.site || site),
      roomNo: String(dbRoom.roomNo || roomNo),
      roomStatus: String(dbRoom.roomStatus || expectedState.roomStatus || ''),
      cleaningStatus: String(dbRoom.cleaningStatus || 'WAITING'),
      cleaningType: String(dbRoom.cleaningType || ''),
      assignmentType: String(dbRoom.assignmentType || ''),
      roommaidEmployeeNo: String(dbRoom.roommaidEmployeeNo || ''),
      secondaryRoommaidEmployeeNo: String(dbRoom.secondaryRoommaidEmployeeNo || ''),
      qmEmployeeNo: String(dbRoom.qmEmployeeNo || ''),
      operationalStatus: String(dbRoom.operationalStatus || expectedState.operationalStatus || ''),
      updatedAt: String(dbRoom.updatedAt || ''),
      version
    },
    mirrorPending: true,
    notificationQueued: Boolean(dbResult.notificationQueued),
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      clearAssignment: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
if helper_anchor not in text:
    raise SystemExit('clear assignment helper anchor not found')
text = text.replace(helper_anchor, helper + helper_anchor, 1)
path.write_text(text, encoding='utf-8')
print('patched clear assignment server DB-first v1')
