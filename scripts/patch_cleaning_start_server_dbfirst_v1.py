from pathlib import Path

MARKER = 'CLEANING_START_SERVER_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


path = Path('06_Indicator.js')
text = path.read_text(encoding='utf-8')
if MARKER in text:
    print('cleaning start server DB-first v1 already applied')
    raise SystemExit(0)

anchor_branch = """    // 청소완료도 PostgreSQL을 원본으로 사용합니다. // CLEANING_COMPLETE_SERVER_DB_FIRST_V1
"""
new_branch = """    // 청소시작도 PostgreSQL을 원본으로 사용합니다. // CLEANING_START_SERVER_DB_FIRST_V1
    // Realtime=Y이면 DB를 먼저 확정하고 현재객실현황·업무이력은 DB 이벤트 미러가 후행 처리합니다.
    // Realtime=N일 때만 아래 기존 Sheet switch 경로를 사용합니다.
    if (action === 'CLEANING_START'
        && typeof novaMobileRealtimeEnabled_ === 'function'
        && novaMobileRealtimeEnabled_()
        && typeof novaMobileRealtimeActionFetch_ === 'function') {
      return startIndicatorRoomCleaningDbFirst_(token, user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // 청소완료도 PostgreSQL을 원본으로 사용합니다. // CLEANING_COMPLETE_SERVER_DB_FIRST_V1
"""
text = replace_once(text, anchor_branch, new_branch, 'cleaning start branch anchor')

helper_anchor = "function completeIndicatorRoomCleaningDbFirst_(token, user, payload, context) { // (청소완료 PostgreSQL 원본 경로) // CLEANING_COMPLETE_SERVER_DB_FIRST_V1\n"
helper = """function startIndicatorRoomCleaningDbFirst_(token, user, payload, context) { // (청소시작 PostgreSQL 원본 경로) // CLEANING_START_SERVER_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  if (!site || !roomNo) throw new Error('청소시작 처리에 사업장과 객실번호가 필요합니다.');

  const requestId = String(safe.requestId || '').trim() || `CLEANING_START:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const dbPayload = {
    businessDate,
    site,
    action: 'CLEANING_START',
    requestId,
    // Apps Script fallback의 expectedVersion은 Sheet 버전일 수 있으므로 DB version 비교에는 사용하지 않습니다.
    // Cloud Run row-lock + expectedState 검증으로 동시변경을 판정합니다.
    expectedVersion: 0,
    expectedState
  };
  const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
  if (!dbResult || !dbResult.ok) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
    error.code = String(dbResult && dbResult.code || 'CLEANING_START_DB_WRITE_FAILED');
    throw error;
  }

  const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};
  const version = Number(dbResult.version || dbRoom.version || 0);
  const finishedMs = Date.now();
  return {
    ok: true,
    dbFirst: true,
    alreadyStarted: Boolean(dbResult.idempotent || dbResult.alreadyStarted || dbResult.alreadySet),
    version,
    requestId: String(dbResult.requestId || requestId),
    room: {
      rowNumber: Number(safe.rowNumber || 0),
      businessDate: String(dbRoom.businessDate || businessDate),
      site: String(dbRoom.site || site),
      roomNo: String(dbRoom.roomNo || roomNo),
      roomStatus: String(dbRoom.roomStatus || expectedState.roomStatus || ''),
      cleaningStatus: String(dbRoom.cleaningStatus || 'CLEANING'),
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
    notificationQueued: Boolean(dbResult.notificationQueued),
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      cleaningStart: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
if helper_anchor not in text:
    raise SystemExit('cleaning start helper anchor not found')
text = text.replace(helper_anchor, helper + helper_anchor, 1)
path.write_text(text, encoding='utf-8')
print('patched cleaning start server DB-first v1')
