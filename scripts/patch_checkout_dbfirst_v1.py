from pathlib import Path

MARKER = 'CHECKOUT_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


def patch_indicator():
    path = Path('06_Indicator.js')
    text = path.read_text(encoding='utf-8')
    if MARKER in text:
        return

    old_branch = """    // 퇴실 버튼은 사용자 전체 인덱스·일반 작업분기 로딩을 건너뛰고 핵심 저장만 수행한다. 잠금은 450ms 이내 확보하고 실패 시 Client가 자동 재시도한다.
    // 화면은 Client 낙관적 반영으로 즉시 바뀌며, 서버는 동일 이력·버전·후속알림을 보존한다.
    if (action === 'CHANGE_ROOM_STATUS'
        && String(safe.roomStatus || '').trim().toUpperCase() === 'CHECKED_OUT') {
      return changeIndicatorRoomCheckoutFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }
"""
    new_branch = """    // 일반 퇴실도 PostgreSQL을 원본으로 사용합니다. // CHECKOUT_DB_FIRST_V1
    // Realtime=Y이면 Cloud Run 객실 action을 먼저 확정하고 Sheets는 DB 이벤트 미러가 후행 반영합니다.
    // Realtime=N에서만 기존 Sheet 고속경로를 유지합니다.
    if (action === 'CHANGE_ROOM_STATUS'
        && String(safe.roomStatus || '').trim().toUpperCase() === 'CHECKED_OUT') {
      if (typeof novaMobileRealtimeEnabled_ === 'function'
          && novaMobileRealtimeEnabled_()
          && typeof novaMobileRealtimeActionFetch_ === 'function') {
        return changeIndicatorRoomCheckoutDbFirst_(token, user, safe, {
          startedMs,
          businessDate,
          site,
          roomNo
        });
      }
      return changeIndicatorRoomCheckoutFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }
"""
    text = replace_once(text, old_branch, new_branch, 'indicator checkout branch')

    helper_anchor = "function changeIndicatorRoomCheckoutFast_(user, payload, context) { // (퇴실 상태변경 핵심저장 고속경로)\n"
    helper = """function changeIndicatorRoomCheckoutDbFirst_(token, user, payload, context) { // (일반 퇴실 PostgreSQL 원본 경로) // CHECKOUT_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  if (!site || !roomNo) throw new Error('퇴실 처리에 사업장과 객실번호가 필요합니다.');

  const requestId = String(safe.requestId || '').trim() || `CHECKOUT:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const dbPayload = {
    businessDate,
    site,
    action: 'CHANGE_ROOM_STATUS',
    roomStatus: 'CHECKED_OUT',
    requestId,
    // Sheet 마지막변경버전과 PostgreSQL version은 다른 도메인이므로 서버 fallback에서는 전달하지 않습니다.
    expectedVersion: 0,
    expectedState
  };
  const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
  if (!dbResult || !dbResult.ok) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
    error.code = String(dbResult && dbResult.code || 'CHECKOUT_DB_WRITE_FAILED');
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
      roomStatus: String(dbRoom.roomStatus || 'CHECKED_OUT'),
      cleaningStatus: String(dbRoom.cleaningStatus || 'WAITING'),
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
    notificationQueued: false,
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      checkout: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
    if helper_anchor not in text:
        raise SystemExit('checkout helper anchor not found')
    text = text.replace(helper_anchor, helper + helper_anchor, 1)
    path.write_text(text, encoding='utf-8')


def patch_client():
    path = Path('Client.html')
    text = path.read_text(encoding='utf-8')
    if 'CHECKOUT_DB_FIRST_V1_CLIENT' in text:
        return

    old_realtime = """    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)
      || (mappedAction === 'CHANGE_ROOM_STATUS'
        && String(safe.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT');
"""
    new_realtime = """    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)
      || mappedAction === 'CHANGE_ROOM_STATUS'; // CHECKOUT_DB_FIRST_V1_CLIENT
"""
    text = replace_once(text, old_realtime, new_realtime, 'client realtime action')

    old_retry = """      const retryableLegacyAction = mappedAction === 'UPDATE_ROOM_OPERATION_STATUS'
        || (mappedAction === 'CHANGE_ROOM_STATUS'
          && String(safe.roomStatus || '').trim().toUpperCase() === 'CHECKED_OUT');
"""
    new_retry = """      const retryableLegacyAction = mappedAction === 'UPDATE_ROOM_OPERATION_STATUS'; // CHECKOUT_DB_FIRST_V1_CLIENT
"""
    text = replace_once(text, old_retry, new_retry, 'client legacy retry')

    old_patch = """    if (action === 'CHANGE_ROOM_STATUS'
        && String(payload.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT'
        && optimisticPatch) {
"""
    new_patch = """    if (action === 'CHANGE_ROOM_STATUS' && optimisticPatch) { // CHECKOUT_DB_FIRST_V1_CLIENT
"""
    text = replace_once(text, old_patch, new_patch, 'client realtime room patch')

    old_comment = """    // 일반 객실상태 Realtime 저장 직후 Sheet 미러가 따라올 때까지만 상태를 보호한다.
    // CHECKED_OUT은 이 보호맵을 사용하지 않으므로 기존 Apps Script 퇴실 결과가 stale DB에 의해 되돌아가지 않는다.
"""
    new_comment = """    // 모든 객실상태 Realtime 저장 직후 Sheet 미러가 따라올 때까지만 DB 확정 상태를 보호한다. // CHECKOUT_DB_FIRST_V1_CLIENT
"""
    if old_comment in text:
        text = text.replace(old_comment, new_comment, 1)

    path.write_text(text, encoding='utf-8')


def patch_mirror():
    path = Path('RealtimeDailySync.js')
    text = path.read_text(encoding='utf-8')
    if 'CHECKOUT_DB_FIRST_V1_MIRROR' in text:
        return

    old_decl = """  const qmNotifications = [];
  const assignmentNotifications = [];
  const qmAssignmentNotifications = [];
"""
    new_decl = """  const qmNotifications = [];
  const assignmentNotifications = [];
  const qmAssignmentNotifications = [];
  const departureConfirmedNotifications = []; // CHECKOUT_DB_FIRST_V1_MIRROR
"""
    text = replace_once(text, old_decl, new_decl, 'mirror notification declarations')

    old_change = """        Object.assign(updates, resolveManualRoomStatusState_(requestedRoomStatus, rowInfo.data));

        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
"""
    new_change = """        Object.assign(updates, resolveManualRoomStatusState_(requestedRoomStatus, rowInfo.data));

        // DB 이벤트가 DUE_OUT -> CHECKED_OUT을 확정한 경우 기존 룸메이드 퇴실확인 알림도 같은 이벤트 기준으로 1회 후행 처리합니다. // CHECKOUT_DB_FIRST_V1_MIRROR
        if (previousRoomStatus === 'DUE_OUT' && requestedRoomStatus === 'CHECKED_OUT') {
          const departureTargetUsers = uniqueRoomOperationEmployeeNos_([
            rowInfo.data['룸메이드사번'], rowInfo.data['보조룸메이드사번']
          ])
            .map(targetEmployeeNo => usersByEmployeeNo[targetEmployeeNo] || null)
            .filter(target => target && target.enabled && String(target.role || '').trim().toUpperCase() === 'ROOMMAID');
          if (departureTargetUsers.length) {
            departureConfirmedNotifications.push({
              businessDate: eventBusinessDate,
              site: eventSite,
              roomNo: eventRoomNo,
              targetUsers: departureTargetUsers,
              cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
              preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
              vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
              importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
              registeredBy: employeeNo,
              version
            });
          }
        }

        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
"""
    text = replace_once(text, old_change, new_change, 'mirror checkout event block')

    old_queue = """    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));
    assignmentNotifications.forEach(payload => queueCleaningAssignmentTelegram_(payload));
    qmAssignmentNotifications.forEach(payload => queueQmAssignmentTelegram_(payload));
"""
    new_queue = """    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));
    assignmentNotifications.forEach(payload => queueCleaningAssignmentTelegram_(payload));
    qmAssignmentNotifications.forEach(payload => queueQmAssignmentTelegram_(payload));
    departureConfirmedNotifications.forEach(payload => queueRoommaidDepartureConfirmedTelegram_(payload)); // CHECKOUT_DB_FIRST_V1_MIRROR
"""
    text = replace_once(text, old_queue, new_queue, 'mirror checkout notification queue')
    path.write_text(text, encoding='utf-8')


patch_indicator()
patch_client()
patch_mirror()
print('patched checkout DB-first v1')
