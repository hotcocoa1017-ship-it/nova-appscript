/**
 * 객실조치 상태(고장·객실확인·완료) 전용 안전 저장.
 * Realtime(PostgreSQL) version과 Sheets 마지막변경버전을 혼용하지 않고
 * 실제 객실조치 상태 자체를 낙관적 동시수정 기준으로 사용합니다.
 * OPERATION_STATUS_DURABLE_WRITE_V1
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

      // 전달받은 행번호가 지연된 화면값이어도 다른 객실을 수정하지 않도록 최종 대상행을 다시 확인합니다.
      const resolvedRoomNo = String(rowInfo.data['객실번호'] || '').trim();
      const resolvedSite = String(rowInfo.data['사업장'] || '').trim();
      const resolvedBusinessDate = normalizeBusinessDate_(rowInfo.data['업무일자'] || businessDate);
      if (resolvedRoomNo !== roomNo || resolvedBusinessDate !== businessDate || (requestedSite && resolvedSite !== requestedSite)) {
        const targetError = new Error(`${roomNo}호 저장 대상행이 변경되었습니다. 최신 화면을 불러온 뒤 다시 처리하세요.`);
        targetError.code = 'OPERATION_STATUS_TARGET_CHANGED';
        throw targetError;
      }

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
            durableWriteVerified: true,
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
      const operationalHeader = indicatorRoomOperationalStatusHeader_();
      const headerMap = getHeaderMap_(sheet);
      const operationalColumn = Number(headerMap[operationalHeader] || 0);
      if (!operationalColumn) throw new Error('객실운영상태 열을 확인할 수 없습니다.');

      updateRowByHeaders_(sheet, rowNumber, {
        [operationalHeader]: requestedStatus,
        '수정일시': updatedAt,
        '마지막변경버전': version
      });

      // 완료 직후 별도 Apps Script 실행이 이전 값을 다시 읽지 않도록
      // 시트 반영을 여기서 확정하고 같은 셀을 직접 재조회한 뒤에만 성공 처리합니다.
      SpreadsheetApp.flush();
      const persistedRawStatus = String(sheet.getRange(rowNumber, operationalColumn).getDisplayValue() || '').trim();
      const persistedStatus = normalizeIndicatorRoomOperationalStatus_(persistedRawStatus);
      const durableWriteOk = requestedStatus
        ? persistedStatus === requestedStatus
        : persistedRawStatus === '';
      if (!durableWriteOk) {
        const verifyError = new Error(`${roomNo}호 객실조치 저장값을 확인하지 못했습니다. 화면을 다시 불러온 뒤 다시 처리하세요.`);
        verifyError.code = 'OPERATION_STATUS_WRITE_VERIFY_FAILED';
        throw verifyError;
      }

      // 같은 실행의 Sheet/헤더 객체를 비우고, 새 데이터 버전 게시 이후 후속 조회가
      // 반드시 확정된 셀값을 기준으로 시작하도록 합니다.
      clearNovaCaches_();
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
        durableWriteVerified: true,
        idempotent: false,
        lockWaitMs: Math.max(0, lockAcquiredMs - lockRequestedMs),
        coreMs: Math.max(0, finishedMs - lockAcquiredMs),
        totalMs: Math.max(0, finishedMs - startedMs)
      }
    };
  });
}
