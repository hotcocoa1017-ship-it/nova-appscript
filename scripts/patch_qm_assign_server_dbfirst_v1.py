from pathlib import Path

MARKER = 'QM_ASSIGN_SERVER_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


path = Path('06_Indicator.js')
text = path.read_text(encoding='utf-8')
if MARKER in text:
    print('QM assign server DB-first v1 already applied')
    raise SystemExit(0)

branch_anchor = """    // 배정 초기화도 PostgreSQL을 원본으로 사용합니다. // CLEAR_ASSIGNMENT_SERVER_DB_FIRST_V1
"""
branch = """    // QM 배정도 PostgreSQL을 원본으로 사용합니다. // QM_ASSIGN_SERVER_DB_FIRST_V1
    // Realtime=Y이면 Cloud Run이 QM 권한/상태를 검증하고 DB를 먼저 확정합니다.
    // 현재객실현황·QM 업무이력·담당 QM 알림은 DB 이벤트 미러가 후행 처리합니다.
    if (action === 'QM_ASSIGN'
        && typeof novaMobileRealtimeEnabled_ === 'function'
        && novaMobileRealtimeEnabled_()
        && typeof novaMobileRealtimeActionFetch_ === 'function') {
      return assignIndicatorQmDbFirst_(token, user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // 배정 초기화도 PostgreSQL을 원본으로 사용합니다. // CLEAR_ASSIGNMENT_SERVER_DB_FIRST_V1
"""
text = replace_once(text, branch_anchor, branch, 'QM assign branch anchor')

helper_anchor = "function clearIndicatorRoomAssignmentDbFirst_(token, user, payload, context) { // (배정 초기화 PostgreSQL 원본 경로) // CLEAR_ASSIGNMENT_SERVER_DB_FIRST_V1\n"
helper = """function assignIndicatorQmDbFirst_(token, user, payload, context) { // (QM 배정 PostgreSQL 원본 경로) // QM_ASSIGN_SERVER_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  if (!site || !roomNo) throw new Error('QM 배정에 사업장과 객실번호가 필요합니다.');

  const employeeNo = String(safe.employeeNo || '').trim();
  if (!employeeNo) throw new Error('배정할 QM을 선택하세요.');
  const requestId = String(safe.requestId || '').trim() || `QM_ASSIGN:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const dbPayload = {
    businessDate,
    site,
    action: 'QM_ASSIGN',
    requestId,
    // 기존 브라우저 직통 Realtime과 동일하게 선택 QM은 employeeNo로 전달합니다.
    // Cloud Run이 DB 이벤트 detail.qmEmployeeNo로 정규화합니다.
    employeeNo,
    // Apps Script fallback의 expectedVersion은 Sheet 버전일 수 있으므로 DB version 비교에는 사용하지 않습니다.
    expectedVersion: 0,
    expectedState
  };
  const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
  if (!dbResult || !dbResult.ok) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
    error.code = String(dbResult && dbResult.code || 'QM_ASSIGN_DB_WRITE_FAILED');
    throw error;
  }

  const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};
  const version = Number(dbResult.version || dbRoom.version || 0);
  const finishedMs = Date.now();
  return {
    ok: true,
    dbFirst: true,
    alreadyAssigned: Boolean(dbResult.idempotent || dbResult.alreadyAssigned || dbResult.alreadySet),
    version,
    requestId: String(dbResult.requestId || requestId),
    room: {
      rowNumber: Number(safe.rowNumber || 0),
      businessDate: String(dbRoom.businessDate || businessDate),
      site: String(dbRoom.site || site),
      roomNo: String(dbRoom.roomNo || roomNo),
      roomStatus: String(dbRoom.roomStatus || expectedState.roomStatus || ''),
      cleaningStatus: String(dbRoom.cleaningStatus || 'QM_WAITING'),
      cleaningType: String(dbRoom.cleaningType || expectedState.cleaningType || ''),
      assignmentType: String(dbRoom.assignmentType || expectedState.assignmentType || ''),
      roommaidEmployeeNo: String(dbRoom.roommaidEmployeeNo || expectedState.roommaidEmployeeNo || ''),
      secondaryRoommaidEmployeeNo: String(dbRoom.secondaryRoommaidEmployeeNo || expectedState.secondaryRoommaidEmployeeNo || ''),
      qmEmployeeNo: String(dbRoom.qmEmployeeNo || employeeNo),
      operationalStatus: String(dbRoom.operationalStatus || expectedState.operationalStatus || ''),
      updatedAt: String(dbRoom.updatedAt || ''),
      version
    },
    mirrorPending: true,
    // QM_ASSIGN 이벤트 미러가 담당자 알림을 1회 생성하므로 서버에서 중복 알림을 만들지 않습니다.
    notificationQueued: Boolean(dbResult.notificationQueued),
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      qmAssign: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
if helper_anchor not in text:
    raise SystemExit('QM assign helper anchor not found')
text = text.replace(helper_anchor, helper + helper_anchor, 1)
path.write_text(text, encoding='utf-8')
print('patched QM assign server DB-first v1')
