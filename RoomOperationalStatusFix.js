/**
 * 객실조치 상태(고장·객실확인·완료) 전용 안전 저장.
 * Realtime(PostgreSQL) version과 Sheets 마지막변경버전을 혼용하지 않고
 * 실제 객실조치 상태 자체를 낙관적 동시수정 기준으로 사용합니다.
 */
function updateRoomOperationalStatusSafe(token, payload) {
  return measureResponse_('updateRoomOperationalStatusSafe', () => {
    const startedMs = Date.now();
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const requestedSite = String(safe.site || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!roomNo) throw new Error('객실번호가 없습니다.');

    const rawRequestedStatus = String(safe.operationalStatus || '').trim();
    const requestedStatus = normalizeIndicatorRoomOperationalStatus_(rawRequestedStatus);
    if (rawRequestedStatus && !requestedStatus) throw new Error('사용할 수 없는 객실 조치상태입니다.');

    const hasExpectedStatus = Object.prototype.hasOwnProperty.call(safe, 'expectedOperationalStatus');
    const rawExpectedStatus = String(safe.expectedOperationalStatus || '').trim();
    const expectedStatus = normalizeIndicatorRoomOperationalStatus_(rawExpectedStatus);
    if (rawExpectedStatus && !expectedStatus) throw new Error('현재 객실 조치상태를 확인하지 못했습니다.');

    ensureIndicatorRoomOperationalStatusHeader_();
    const lockRequestedMs = Date.now();
    const writeLock = acquireIndicatorFastWriteLock_();
    const lockAcquiredMs = Date.now();
    let rowNumber = 0;
    let site = requestedSite;
    let version = 0;
    let updatedAt = '';
    let roomStatus = '';
    let cleaningStatus = '';
    let previousStatus = '';

    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      let rowInfo = null;

      if (requestedSite) {
        rowInfo = findCurrentRoomRowFast_(sheet, businessDate, requestedSite, roomNo, safe.rowNumber);
      } else {
        const matches = getCurrentRowsForSelection_(businessDate, '')
          .items
          .filter(item => String(item.data['객실번호'] || '').trim() === roomNo);
        if (matches.length > 1) throw new Error('사업장을 선택한 뒤 다시 처리하세요. 동일 객실번호가 여러 사업장에 있습니다.');
        rowInfo = matches.length ? matches[0] : null;
      }

      if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');

      rowNumber = rowInfo.rowNumber;
      site = String(rowInfo.data['사업장'] || requestedSite).trim();
      roomStatus = String(rowInfo.data['객실상태'] || '').trim();
      cleaningStatus = String(rowInfo.data['청소상태'] || '').trim();
      previousStatus = normalizeIndicatorRoomOperationalStatus_(
        rowInfo.data[indicatorRoomOperationalStatusHeader_()]
      );

      // 재전송은 동일 상태라면 중복 이력 없이 성공 처리합니다.
      if (previousStatus === requestedStatus) {
        version = Number(rowInfo.data['마지막변경버전'] || 0);
        updatedAt = String(rowInfo.data['수정일시'] || '').trim();
        const finishedMs = Date.now();
        return {
          ok: true,
          alreadySet: true,
          version,
          room: {
            rowNumber, businessDate, site, roomNo,
            roomStatus, cleaningStatus,
            operationalStatus: requestedStatus,
            updatedAt, version
          },
          timing: {
            safeOperationalStatus: true,
            idempotent: true,
            lockWaitMs: Math.max(0, lockAcquiredMs - lockRequestedMs),
            coreMs: Math.max(0, finishedMs - lockAcquiredMs),
            totalMs: Math.max(0, finishedMs - startedMs)
          }
        };
      }

      // 전체 행 버전이 아니라 사용자가 보고 있던 '객실조치 상태'만 비교합니다.
      // 청소 Realtime 갱신 등 다른 필드 변경은 객실확인/완료를 불필요하게 막지 않습니다.
      if (hasExpectedStatus && previousStatus !== expectedStatus) {
        const conflict = new Error(`${roomNo}호 객실조치 상태가 다른 사용자에 의해 먼저 변경되었습니다. 최신 화면을 불러온 뒤 다시 처리하세요.`);
        conflict.code = 'OPERATION_STATUS_CONFLICT';
        throw conflict;
      }

      updatedAt = nowText_();
      version = reserveDataVersion_({ lockHeld: true });
      updateRowByHeaders_(sheet, rowNumber, {
        [indicatorRoomOperationalStatusHeader_()]: requestedStatus,
        '수정일시': updatedAt,
        '마지막변경버전': version
      });
      publishDataVersion_(version, {
        domains: ['ROOM'],
        businessDate,
        site,
        lockHeld: true
      });

      appendUnifiedHistory_({
        recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
        businessDate,
        site,
        roomNo,
        targetEmployeeNo: '',
        status: 'UPDATE_ROOM_OPERATION_STATUS',
        detail: {
          action: 'UPDATE_ROOM_OPERATION_STATUS',
          previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
          roomStatus,
          cleaningStatus,
          cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
          assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
          primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
          secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
          preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
          vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
          importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
          previousOperationalStatus: previousStatus,
          operationalStatus: requestedStatus
        },
        registeredBy: user.employeeNo,
        version
      });
    } finally {
      writeLock.releaseLock();
    }

    const finishedMs = Date.now();
    return {
      ok: true,
      alreadySet: false,
      version,
      room: {
        rowNumber, businessDate, site, roomNo,
        roomStatus, cleaningStatus,
        operationalStatus: requestedStatus,
        updatedAt, version
      },
      timing: {
        safeOperationalStatus: true,
        idempotent: false,
        lockWaitMs: Math.max(0, lockAcquiredMs - lockRequestedMs),
        coreMs: Math.max(0, finishedMs - lockAcquiredMs),
        totalMs: Math.max(0, finishedMs - startedMs)
      }
    };
  });
}
