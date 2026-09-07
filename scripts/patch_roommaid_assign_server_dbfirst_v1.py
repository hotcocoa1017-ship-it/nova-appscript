from pathlib import Path

MARKER = 'ROOMMAID_ASSIGN_SERVER_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


path = Path('06_Indicator.js')
text = path.read_text(encoding='utf-8')
if MARKER in text:
    print('roommaid assign server DB-first v1 already applied')
    raise SystemExit(0)

branch_anchor = """    // 청소시작도 PostgreSQL을 원본으로 사용합니다. // CLEANING_START_SERVER_DB_FIRST_V1
"""
branch = """    // 룸메이드 배정도 PostgreSQL을 원본으로 사용합니다. // ROOMMAID_ASSIGN_SERVER_DB_FIRST_V1
    // Realtime=Y이면 Cloud Run이 직원·배정상태를 검증하고 DB를 먼저 확정합니다.
    // 현재객실현황·업무이력·배정 알림은 DB 이벤트 미러가 후행 처리합니다.
    if (action === 'ASSIGN_ROOMMAID'
        && typeof novaMobileRealtimeEnabled_ === 'function'
        && novaMobileRealtimeEnabled_()
        && typeof novaMobileRealtimeActionFetch_ === 'function') {
      return assignIndicatorRoommaidDbFirst_(token, user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // 청소시작도 PostgreSQL을 원본으로 사용합니다. // CLEANING_START_SERVER_DB_FIRST_V1
"""
text = replace_once(text, branch_anchor, branch, 'roommaid assign branch anchor')

helper_anchor = "function startIndicatorRoomCleaningDbFirst_(token, user, payload, context) { // (청소시작 PostgreSQL 원본 경로) // CLEANING_START_SERVER_DB_FIRST_V1\n"
helper = """function assignIndicatorRoommaidDbFirst_(token, user, payload, context) { // (룸메이드 배정 PostgreSQL 원본 경로) // ROOMMAID_ASSIGN_SERVER_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  if (!site || !roomNo) throw new Error('룸메이드 배정에 사업장과 객실번호가 필요합니다.');

  const employeeNo = String(safe.employeeNo || '').trim();
  const secondaryEmployeeNo = String(safe.secondaryEmployeeNo || '').trim();
  const assignmentType = String(safe.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
  const cleaningType = String(safe.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
  if (!employeeNo) throw new Error('주담당 룸메이드를 선택하세요.');
  if (['PAIR', 'PAIR_TRAINING'].includes(assignmentType)) {
    if (!secondaryEmployeeNo) throw new Error('보조 룸메이드를 선택하세요.');
    if (employeeNo === secondaryEmployeeNo) throw new Error('2인1조는 서로 다른 룸메이드 2명을 선택해야 합니다.');
  }

  const requestId = String(safe.requestId || '').trim() || `ASSIGN_ROOMMAID:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const dbPayload = {
    businessDate,
    site,
    action: 'ASSIGN_ROOMMAID',
    requestId,
    employeeNo,
    secondaryEmployeeNo,
    assignmentType,
    cleaningType,
    // Apps Script fallback의 expectedVersion은 Sheet 버전일 수 있으므로 DB version 비교에는 사용하지 않습니다.
    expectedVersion: 0,
    expectedState
  };
  const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
  if (!dbResult || !dbResult.ok) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
    error.code = String(dbResult && dbResult.code || 'ROOMMAID_ASSIGN_DB_WRITE_FAILED');
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
      cleaningStatus: String(dbRoom.cleaningStatus || 'ASSIGNED'),
      cleaningType: String(dbRoom.cleaningType || cleaningType),
      assignmentType: String(dbRoom.assignmentType || assignmentType),
      roommaidEmployeeNo: String(dbRoom.roommaidEmployeeNo || employeeNo),
      secondaryRoommaidEmployeeNo: String(dbRoom.secondaryRoommaidEmployeeNo || secondaryEmployeeNo),
      qmEmployeeNo: String(dbRoom.qmEmployeeNo || expectedState.qmEmployeeNo || ''),
      operationalStatus: String(dbRoom.operationalStatus || expectedState.operationalStatus || ''),
      updatedAt: String(dbRoom.updatedAt || ''),
      version
    },
    mirrorPending: true,
    // DB 이벤트 미러가 주/보조 룸메이드 배정 알림을 1회 생성합니다.
    notificationQueued: Boolean(dbResult.notificationQueued),
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      roommaidAssign: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
if helper_anchor not in text:
    raise SystemExit('roommaid assign helper anchor not found')
text = text.replace(helper_anchor, helper + helper_anchor, 1)
path.write_text(text, encoding='utf-8')
print('patched roommaid assign server DB-first v1')
