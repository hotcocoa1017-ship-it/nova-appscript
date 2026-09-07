from pathlib import Path

MARKER = 'CLEANING_COMPLETE_SERVER_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


path = Path('06_Indicator.js')
text = path.read_text(encoding='utf-8')
if MARKER in text:
    print('cleaning complete server DB-first v1 already applied')
    raise SystemExit(0)

old_branch = """    // 청소완료는 전체 사용자목록·텔레그램 큐 처리 전에 핵심 저장만 끝내는 고속 경로를 사용한다.
    if (action === 'CLEANING_COMPLETE') {
      return completeIndicatorRoomCleaningFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }
"""
new_branch = """    // 청소완료도 PostgreSQL을 원본으로 사용합니다. // CLEANING_COMPLETE_SERVER_DB_FIRST_V1
    // Realtime=Y이면 DB를 먼저 확정하고 현재객실현황·업무이력·QM 알림은 DB 이벤트 미러가 후행 처리합니다.
    // Realtime=N일 때만 기존 Sheet 고속경로를 유지합니다.
    if (action === 'CLEANING_COMPLETE') {
      if (typeof novaMobileRealtimeEnabled_ === 'function'
          && novaMobileRealtimeEnabled_()
          && typeof novaMobileRealtimeActionFetch_ === 'function') {
        return completeIndicatorRoomCleaningDbFirst_(token, user, safe, {
          startedMs,
          businessDate,
          site,
          roomNo
        });
      }
      return completeIndicatorRoomCleaningFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }
"""
text = replace_once(text, old_branch, new_branch, 'cleaning complete branch')

anchor = "function completeIndicatorRoomCleaningFast_(user, payload, context) { // (청소완료 핵심저장·중복요청 멱등 차단)\n"
helper = """function completeIndicatorRoomCleaningDbFirst_(token, user, payload, context) { // (청소완료 PostgreSQL 원본 경로) // CLEANING_COMPLETE_SERVER_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  if (!site || !roomNo) throw new Error('청소완료 처리에 사업장과 객실번호가 필요합니다.');

  const requestId = String(safe.requestId || '').trim() || `CLEANING_COMPLETE:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const qmEmployeeNo = String(expectedState.qmEmployeeNo || safe.qmEmployeeNo || '').trim();
  const dbPayload = {
    businessDate,
    site,
    action: 'CLEANING_COMPLETE',
    requestId,
    qmEmployeeNo,
    // Apps Script fallback의 expectedVersion은 Sheet 버전일 수 있으므로 DB 버전 충돌검사에 사용하지 않습니다.
    // Cloud Run의 row-lock + expectedState 검증으로 동일 요청/경합을 판정합니다.
    expectedVersion: 0,
    expectedState
  };
  const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
  if (!dbResult || !dbResult.ok) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
    error.code = String(dbResult && dbResult.code || 'CLEANING_COMPLETE_DB_WRITE_FAILED');
    throw error;
  }

  const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};
  const version = Number(dbResult.version || dbRoom.version || 0);
  const finishedMs = Date.now();
  return {
    ok: true,
    dbFirst: true,
    alreadyCompleted: Boolean(dbResult.idempotent || dbResult.alreadyCompleted || dbResult.alreadySet),
    version,
    requestId: String(dbResult.requestId || requestId),
    room: {
      rowNumber: Number(safe.rowNumber || 0),
      businessDate: String(dbRoom.businessDate || businessDate),
      site: String(dbRoom.site || site),
      roomNo: String(dbRoom.roomNo || roomNo),
      roomStatus: String(dbRoom.roomStatus || expectedState.roomStatus || ''),
      cleaningStatus: String(dbRoom.cleaningStatus || 'COMPLETED'),
      cleaningType: String(dbRoom.cleaningType || expectedState.cleaningType || NOVA.CLEANING_TYPES.NORMAL),
      assignmentType: String(dbRoom.assignmentType || expectedState.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO),
      roommaidEmployeeNo: String(dbRoom.roommaidEmployeeNo || expectedState.roommaidEmployeeNo || ''),
      secondaryRoommaidEmployeeNo: String(dbRoom.secondaryRoommaidEmployeeNo || expectedState.secondaryRoommaidEmployeeNo || ''),
      qmEmployeeNo: String(dbRoom.qmEmployeeNo || qmEmployeeNo),
      operationalStatus: String(dbRoom.operationalStatus || expectedState.operationalStatus || ''),
      updatedAt: String(dbRoom.updatedAt || ''),
      version
    },
    mirrorPending: true,
    // DB 이벤트 미러가 CLEANING_COMPLETE 이력과 QM_READY 알림을 1회 생성합니다.
    // 여기서 deferredNotification을 만들면 동일 알림이 중복될 수 있습니다.
    notificationQueued: Boolean(dbResult.notificationQueued),
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      cleaningComplete: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
if anchor not in text:
    raise SystemExit('cleaning complete helper anchor not found')
text = text.replace(anchor, helper + anchor, 1)
path.write_text(text, encoding='utf-8')
print('patched cleaning complete server DB-first v1')
