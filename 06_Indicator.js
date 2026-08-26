/**
 * 오더테이커 데스크톱 통합 인디케이터
 */
function getIndicatorSnapshot(token, options) { // (통합 인디케이터 전체 스냅샷)
  return measureResponse_('getIndicatorSnapshot', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeIndicatorOptions_(options, user);
    const currentVersion = getIndicatorSyncVersion_(request);

    const userIndex = getUserIndex_();
    const codeIndex = getCodeIndex_();
    const orderStatusMap = {};
    (codeIndex['하우스맨상태'] || []).forEach(code => { orderStatusMap[code.code] = code.label; });
    const orders = getHousemanOrdersForDate_(request.businessDate, request.site, userIndex.byEmployeeNo, orderStatusMap);
    const rooms = getCurrentRoomsForIndicator_(request.businessDate, request.site, orders, userIndex.byEmployeeNo);
    const sites = getSiteList_();
    const housemanRouting = request.site
      ? buildHousemanRoutingData_(request.businessDate, request.site, orders)
      : { businessDate: request.businessDate, site: '', currentShift: resolveCurrentShiftCode_(new Date()), isToday: request.businessDate === businessDateText_(), byBuilding: {} };

    const response = {
      ok: true,
      changed: true,
      version: currentVersion,
      selection: request,
      sites,
      rooms,
      orders,
      housemanRouting,
      staff: {
        housemen: publicStaffFromIndex_(userIndex.active, ['HOUSEMAN']),
        roommaids: publicStaffFromIndex_(userIndex.active, ['ROOMMAID']),
        qms: publicStaffFromIndex_(userIndex.active, ['QM'])
      },
      codes: {
        roomStatuses: codeIndex['객실상태'] || [],
        cleaningStatuses: codeIndex['청소상태'] || [],
        cleaningTypes: codeIndex['정비유형'] || [],
        assignmentTypes: codeIndex['룸메이드배정유형'] || [],
        orderStatuses: codeIndex['하우스맨상태'] || [],
        orderParts: codeIndex['하우스맨파트'] || [],
        orderItems: codeIndex['하우스맨품목'] || []
      },
      serverTime: nowText_()
    };
    return response;
  });
}

function getIndicatorDelta(token, options) { // (변경 시에만 통합 화면 갱신)
  return measureResponse_('getIndicatorDelta', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeIndicatorOptions_(options, user);
    const currentVersion = getIndicatorSyncVersion_(request);
    const sinceVersion = Number(options && options.sinceVersion || 0);
    if (sinceVersion === currentVersion) {
      return {
        ok: true,
        changed: false,
        version: currentVersion,
        serverTime: nowText_()
      };
    }

    const deltaCacheKey = buildDeltaCacheKey_('INDICATOR', [request.businessDate, request.site, currentVersion]);
    const cachedDelta = getCachedJson_(deltaCacheKey);
    if (cachedDelta) return Object.assign({}, cachedDelta, { serverTime: nowText_() });

    const userIndex = getUserIndex_();
    const codeIndex = getCodeIndex_();
    const orderStatusMap = {};
    (codeIndex['하우스맨상태'] || []).forEach(code => { orderStatusMap[code.code] = code.label; });
    const orders = getHousemanOrdersForDate_(request.businessDate, request.site, userIndex.byEmployeeNo, orderStatusMap);
    const rooms = getCurrentRoomsForIndicator_(request.businessDate, request.site, orders, userIndex.byEmployeeNo);
    const housemanRouting = request.site
      ? buildHousemanRoutingData_(request.businessDate, request.site, orders)
      : { businessDate: request.businessDate, site: '', currentShift: resolveCurrentShiftCode_(new Date()), isToday: request.businessDate === businessDateText_(), byBuilding: {} };
    const response = {
      ok: true,
      changed: true,
      version: currentVersion,
      selection: request,
      rooms,
      orders,
      housemanRouting,
      serverTime: nowText_()
    };
    putCachedJson_(deltaCacheKey, response, NOVA.DELTA_CACHE_SECONDS);
    return response;
  });
}

function updateRoomOperation(token, payload) { // (객실 청소배정·상태변경·실행시간 측정)
  return measureResponse_('updateRoomOperation', () => {
    const startedMs = Date.now();
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    const action = String(safe.action || '').trim().toUpperCase();
    if (!roomNo) throw new Error('객실번호가 없습니다.');

    // 청소완료는 전체 사용자목록·텔레그램 큐 처리 전에 핵심 저장만 끝내는 고속 경로를 사용한다.
    if (action === 'CLEANING_COMPLETE') {
      return completeIndicatorRoomCleaningFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // 청소초기화는 해당 객실의 금일 활성 청소완료 이력을 전부 취소하고 현재 배정을 원점으로 되돌린다.
    if (action === 'CLEANING_RESET') {
      return resetIndicatorRoomCleaningFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // 고장·객실확인은 사용자 전체 인덱스·일반 작업분기 로딩을 건너뛰고 핵심 저장만 수행한다. 잠금은 450ms 이내 확보하고 실패 시 Client가 자동 재시도한다.
    // 동일 상태 재요청은 멱등 성공으로 처리해 일시적 재시도에도 중복이력을 만들지 않는다.
    if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
      return changeIndicatorRoomOperationalStatusFast_(user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // 퇴실 버튼은 사용자 전체 인덱스·일반 작업분기 로딩을 건너뛰고 핵심 저장만 수행한다. 잠금은 450ms 이내 확보하고 실패 시 Client가 자동 재시도한다.
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

    // 직원 검증이 필요한 배정 작업에서만 사용자 전체 인덱스를 읽는다.
    // 객실상태·운영표시·배정초기화 등은 불필요한 사용자 조회를 건너뛰어 저장 응답을 단축한다.
    const needsUserIndex = action === 'ASSIGN_ROOMMAID' || action === 'QM_ASSIGN';
    const userIndex = needsUserIndex ? getUserIndex_() : null;
    const writeLockRequestedMs = Date.now();
    const writeLock = acquireWriteLock_();
    const writeLockAcquiredMs = Date.now();
    let version = 0;
    let refreshed = null;
    let rowNumber = 0;
    let notificationQueued = false;
    let deferredNotification = null;

    try {
      if (action === 'UPDATE_OPERATION_FLAGS') ensureRoomOperationalFlagHeaders_();
      if (action === 'UPDATE_ROOM_OPERATION_STATUS') ensureIndicatorRoomOperationalStatusHeader_();
      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const rowInfo = findCurrentRoomRowFast_(sheet, businessDate, site, roomNo, safe.rowNumber);
      if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
      assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);
      rowNumber = rowInfo.rowNumber;

      const updates = { '수정일시': nowText_() };
      let recordType = NOVA.RECORD_TYPES.CLEANING;
      let targetEmployeeNo = String(safe.employeeNo || '').trim();
      let secondaryEmployeeNo = String(safe.secondaryEmployeeNo || '').trim();
      let assignmentType = String(safe.assignmentType || rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
      let assignmentUser = null;
      let secondaryAssignmentUser = null;
      let cleaningType = String(safe.cleaningType || rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
      const previousRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
      let requestedRoomStatusForHistory = '';
      let requestedOperationalStatusForHistory = '';

      switch (action) {
        case 'ASSIGN_ROOMMAID': {
          const resolved = resolveRoommaidAssignment_(targetEmployeeNo, secondaryEmployeeNo, assignmentType, userIndex.byEmployeeNo);
          assignmentUser = resolved.primary;
          secondaryAssignmentUser = resolved.secondary;
          assignmentType = resolved.assignmentType;
          secondaryEmployeeNo = secondaryAssignmentUser ? secondaryAssignmentUser.employeeNo : '';
          const allowedCleaningTypes = new Set(getCodes_('정비유형').map(code => String(code.code || '').trim().toUpperCase()));
          if (!allowedCleaningTypes.has(cleaningType)) throw new Error('사용할 수 없는 정비유형입니다.');
          updates['정비유형'] = cleaningType;
          updates['배정유형'] = assignmentType;
          updates['룸메이드사번'] = assignmentUser.employeeNo;
          updates['보조룸메이드사번'] = secondaryEmployeeNo;
          updates['청소상태'] = 'ASSIGNED';
          break;
        }
        case 'CLEANING_START':
          updates['청소상태'] = 'CLEANING';
          break;
        case 'CLEANING_COMPLETE':
          updates['청소상태'] = 'COMPLETED';
          // 청소완료 후에도 최초 업로드·수동변경으로 확정된 객실상태를 유지한다.
          // 공실(VACANT_CLEAN)은 객실현황 업로드 시 원본에 포함되지 않은 객실에만 사용한다.
          break;
        case 'QM_ASSIGN':
          recordType = NOVA.RECORD_TYPES.QM;
          assignmentUser = userIndex.byEmployeeNo[targetEmployeeNo] || null;
          if (!assignmentUser || !assignmentUser.enabled || String(assignmentUser.role || '').toUpperCase() !== 'QM') throw new Error('배정할 QM을 선택하세요.');
          updates['QM사번'] = targetEmployeeNo;
          updates['청소상태'] = 'QM_WAITING';
          break;
        case 'QM_WAITING':
          recordType = NOVA.RECORD_TYPES.QM;
          updates['청소상태'] = 'QM_WAITING';
          break;
        case 'CLEAR_ASSIGNMENT':
          updates['정비유형'] = '';
          updates['배정유형'] = '';
          updates['룸메이드사번'] = '';
          updates['보조룸메이드사번'] = '';
          updates['QM사번'] = '';
          updates['청소상태'] = 'WAITING';
          targetEmployeeNo = '';
          break;
        case 'CHANGE_ROOM_STATUS': {
          recordType = NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE;
          requestedRoomStatusForHistory = String(safe.roomStatus || '').trim().toUpperCase();
          if (!requestedRoomStatusForHistory) throw new Error('변경할 객실상태를 선택하세요.');
          const allowedRoomStatuses = new Set(getCodes_('객실상태').map(code => String(code.code || '').trim().toUpperCase()));
          if (!allowedRoomStatuses.has(requestedRoomStatusForHistory)) throw new Error('사용할 수 없는 객실상태입니다.');
          if (isNovaRoomCleaningTargetStatus_(requestedRoomStatusForHistory)) {
            Object.assign(updates, buildIndicatorPreviousCycleArchiveUpdates_(rowInfo.data));
          }
          updates['객실상태'] = requestedRoomStatusForHistory;
          updates[indicatorLastRoomStatusHeader_()] = resolveIndicatorLastRoomStatusAfterChange_(requestedRoomStatusForHistory, rowInfo.data);
          if (requestedRoomStatusForHistory === 'VACANT_CLEAN') {
            // 명시적 공실 전환 시 카드에 남아 있는 과거 정비주기 표시도 제거한다.
            indicatorPreviousCycleHeaders_().forEach(header => { updates[header] = ''; });
          }
          Object.assign(updates, resolveManualRoomStatusState_(requestedRoomStatusForHistory, rowInfo.data));
          break;
        }
        case 'UPDATE_OPERATION_FLAGS':
          recordType = NOVA.RECORD_TYPES.ADMIN_SETTING;
          updates['선배정여부'] = safe.preassigned ? 'Y' : 'N';
          updates['VIP여부'] = safe.vip ? 'Y' : 'N';
          updates['중요객실여부'] = safe.importantRoom ? 'Y' : 'N';
          targetEmployeeNo = '';
          break;
        case 'UPDATE_ROOM_OPERATION_STATUS': {
          recordType = NOVA.RECORD_TYPES.ADMIN_SETTING;
          const rawOperationalStatus = String(safe.operationalStatus || '').trim();
          requestedOperationalStatusForHistory = normalizeIndicatorRoomOperationalStatus_(rawOperationalStatus);
          if (rawOperationalStatus && !requestedOperationalStatusForHistory) throw new Error('사용할 수 없는 객실 조치상태입니다.');
          updates[indicatorRoomOperationalStatusHeader_()] = requestedOperationalStatusForHistory;
          targetEmployeeNo = '';
          break;
        }
        default:
          throw new Error('지원하지 않는 객실 작업입니다.');
      }

      version = reserveDataVersion_({ lockHeld: true });
      updates['마지막변경버전'] = version;
      updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
      publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });

      appendUnifiedHistory_({
        recordType,
        businessDate,
        site: rowInfo.data['사업장'],
        roomNo,
        targetEmployeeNo,
        status: action,
        detail: {
          action,
          previousRoomStatus,
          sourceRoomStatus: action === 'CLEANING_COMPLETE' ? previousRoomStatus : '',
          roomStatus: updates['객실상태'] || rowInfo.data['객실상태'],
          specialDepartureStarted: action === 'CHANGE_ROOM_STATUS'
            && isNovaSpecialDepartureStatus_(requestedRoomStatusForHistory)
            && requestedRoomStatusForHistory !== previousRoomStatus,
          cleaningStatus: updates['청소상태'] || rowInfo.data['청소상태'],
          cleaningType: updates['정비유형'] || rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL,
          assignmentType: updates['배정유형'] || rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO,
          primaryEmployeeNo: updates['룸메이드사번'] || rowInfo.data['룸메이드사번'] || '',
          secondaryEmployeeNo: Object.prototype.hasOwnProperty.call(updates, '보조룸메이드사번') ? updates['보조룸메이드사번'] : (rowInfo.data['보조룸메이드사번'] || ''),
          creditUnit: getRoommaidCleaningCreditUnit_(updates['정비유형'] || rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
          preassigned: Object.prototype.hasOwnProperty.call(updates, '선배정여부') ? updates['선배정여부'] === 'Y' : normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
          vip: Object.prototype.hasOwnProperty.call(updates, 'VIP여부') ? updates['VIP여부'] === 'Y' : normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
          importantRoom: Object.prototype.hasOwnProperty.call(updates, '중요객실여부') ? updates['중요객실여부'] === 'Y' : normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
          previousOperationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
          operationalStatus: Object.prototype.hasOwnProperty.call(updates, indicatorRoomOperationalStatusHeader_())
            ? requestedOperationalStatusForHistory
            : normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()])
        },
        registeredBy: user.employeeNo,
        version
      });

      refreshed = Object.assign({}, rowInfo.data, updates);
      deferredNotification = buildRoomOperationDeferredTelegramPayload_(action, {
        businessDate,
        site: String(refreshed['사업장'] || site).trim(),
        roomNo,
        previous: rowInfo.data,
        current: refreshed,
        requestedRoomStatus: requestedRoomStatusForHistory,
        version
      });
      // 배정/QM 알림은 저장 성공 응답 후 Client가 비동기로 큐 등록한다.
    } finally {
      writeLock.releaseLock();
    }

    // Client가 이미 즉시 반영한 이름·표시정보는 유지하고, 서버에서 확정된 핵심 필드만 반환한다.
    // 이로써 상태변경·운영표시 등에서 응답 직전 사용자 전체 인덱스 재의존을 제거한다.
    const responseRoom = {
      rowNumber,
      businessDate,
      site: String(refreshed['사업장'] || site).trim(),
      roomNo,
      roomStatus: String(refreshed['객실상태'] || '').trim(),
      displayBaseRoomStatus: resolveIndicatorDisplayBaseRoomStatus_(refreshed),
      cleaningStatus: String(refreshed['청소상태'] || '').trim(),
      cleaningType: String(refreshed['정비유형'] || '').trim() || NOVA.CLEANING_TYPES.NORMAL,
      assignmentType: String(refreshed['배정유형'] || '').trim() || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO,
      roommaidEmployeeNo: String(refreshed['룸메이드사번'] || '').trim(),
      secondaryRoommaidEmployeeNo: String(refreshed['보조룸메이드사번'] || '').trim(),
      qmEmployeeNo: String(refreshed['QM사번'] || '').trim(),
      preassigned: normalizeYesNo_(refreshed['선배정여부']) === 'Y',
      vip: normalizeYesNo_(refreshed['VIP여부']) === 'Y',
      importantRoom: normalizeYesNo_(refreshed['중요객실여부']) === 'Y',
      operationalStatus: normalizeIndicatorRoomOperationalStatus_(refreshed[indicatorRoomOperationalStatusHeader_()]),
      updatedAt: String(refreshed['수정일시'] || '').trim(),
      version: Number(refreshed['마지막변경버전'] || version || 0)
    };
    const finishedMs = Date.now();
    return {
      ok: true,
      version,
      room: responseRoom,
      notificationQueued,
      notificationDeferred: Boolean(deferredNotification),
      deferredNotification,
      timing: {
        lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),
        coreMs: Math.max(0, finishedMs - writeLockAcquiredMs),
        totalMs: Math.max(0, finishedMs - startedMs)
      }
    };
  });
}


function acquireIndicatorFastWriteLock_() { // (객실조치·퇴실 고속경로 전용 짧은 잠금)
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(450)) {
    const busyError = new Error('동시 요청 처리 중입니다. 잠시 후 자동으로 다시 시도합니다.');
    busyError.code = 'BUSY_RETRY';
    throw busyError;
  }
  return lock;
}

function changeIndicatorRoomOperationalStatusFast_(user, payload, context) { // (고장·객실확인 핵심저장 고속경로)
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  const rawOperationalStatus = String(safe.operationalStatus || '').trim();
  const requestedOperationalStatus = normalizeIndicatorRoomOperationalStatus_(rawOperationalStatus);
  if (rawOperationalStatus && !requestedOperationalStatus) {
    throw new Error('사용할 수 없는 객실 조치상태입니다.');
  }

  // 헤더 확인은 잠금 밖에서 끝내 실제 객실 저장 잠금시간을 최소화한다.
  ensureIndicatorRoomOperationalStatusHeader_();

  const writeLockRequestedMs = Date.now();
  const writeLock = acquireIndicatorFastWriteLock_();
  const writeLockAcquiredMs = Date.now();
  let version = 0;
  let rowNumber = 0;
  let responseSite = site;
  let updatedAt = '';
  let previousOperationalStatus = '';
  let roomStatus = '';
  let cleaningStatus = '';

  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRowFast_(sheet, businessDate, site, roomNo, safe.rowNumber);
    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');

    rowNumber = rowInfo.rowNumber;
    responseSite = String(rowInfo.data['사업장'] || site).trim();
    roomStatus = String(rowInfo.data['객실상태'] || '').trim();
    cleaningStatus = String(rowInfo.data['청소상태'] || '').trim();
    previousOperationalStatus = normalizeIndicatorRoomOperationalStatus_(
      rowInfo.data[indicatorRoomOperationalStatusHeader_()]
    );

    // 같은 상태를 다시 누른 경우에는 이미 저장된 결과를 그대로 성공 반환한다.
    // 첫 요청은 저장됐지만 브라우저 응답만 지연/실패한 경우의 안전한 재시도도 여기서 흡수한다.
    if (previousOperationalStatus === requestedOperationalStatus) {
      version = Number(rowInfo.data['마지막변경버전'] || 0);
      updatedAt = String(rowInfo.data['수정일시'] || '').trim();
      const finishedMs = Date.now();
      return {
        ok: true,
        alreadySet: true,
        version,
        room: {
          rowNumber,
          businessDate,
          site: responseSite,
          roomNo,
          roomStatus,
          cleaningStatus,
          operationalStatus: requestedOperationalStatus,
          updatedAt,
          version
        },
        notificationQueued: false,
        notificationDeferred: false,
        deferredNotification: null,
        timing: {
          fastPath: true,
          operationalStatus: true,
          idempotent: true,
          lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),
          coreMs: Math.max(0, finishedMs - writeLockAcquiredMs),
          totalMs: Math.max(0, finishedMs - startedMs)
        }
      };
    }

    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);

    updatedAt = nowText_();
    version = reserveDataVersion_({ lockHeld: true });
    updateRowByHeaders_(sheet, rowNumber, {
      [indicatorRoomOperationalStatusHeader_()]: requestedOperationalStatus,
      '수정일시': updatedAt,
      '마지막변경버전': version
    });
    publishDataVersion_(version, {
      domains: ['ROOM'],
      businessDate,
      site: responseSite,
      lockHeld: true
    });

    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
      businessDate,
      site: responseSite,
      roomNo,
      targetEmployeeNo: '',
      status: 'UPDATE_ROOM_OPERATION_STATUS',
      detail: {
        action: 'UPDATE_ROOM_OPERATION_STATUS',
        previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
        roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
        cleaningStatus: String(rowInfo.data['청소상태'] || '').trim(),
        cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
        assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
        primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
        secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
        preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
        vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
        importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
        previousOperationalStatus,
        operationalStatus: requestedOperationalStatus
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
      rowNumber,
      businessDate,
      site: responseSite,
      roomNo,
      roomStatus,
      cleaningStatus,
      operationalStatus: requestedOperationalStatus,
      updatedAt,
      version
    },
    notificationQueued: false,
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      fastPath: true,
      operationalStatus: true,
      idempotent: false,
      lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),
      coreMs: Math.max(0, finishedMs - writeLockAcquiredMs),
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}


function changeIndicatorRoomCheckoutFast_(user, payload, context) { // (퇴실 상태변경 핵심저장 고속경로)
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  const requestedRoomStatus = String(safe.roomStatus || '').trim().toUpperCase();
  if (requestedRoomStatus !== 'CHECKED_OUT') throw new Error('퇴실 고속경로는 퇴실 상태에서만 사용할 수 있습니다.');

  // 코드설정 조회는 잠금 밖에서 끝내 동시 객실작업의 대기시간을 줄인다.
  const allowedRoomStatuses = new Set(
    getCodes_('객실상태').map(code => String(code.code || '').trim().toUpperCase())
  );
  if (!allowedRoomStatuses.has(requestedRoomStatus)) throw new Error('사용할 수 없는 객실상태입니다.');

  const writeLockRequestedMs = Date.now();
  const writeLock = acquireIndicatorFastWriteLock_();
  const writeLockAcquiredMs = Date.now();
  let version = 0;
  let rowNumber = 0;
  let responseSite = site;
  let deferredNotification = null;
  let responseRoom = null;

  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRowFast_(sheet, businessDate, site, roomNo, safe.rowNumber);
    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');

    rowNumber = rowInfo.rowNumber;
    responseSite = String(rowInfo.data['사업장'] || site).trim();
    const previousRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();

    // 이미 퇴실로 저장된 동일 요청은 중복 이력을 만들지 않고 현재 상태를 성공 반환한다.
    if (previousRoomStatus === requestedRoomStatus) {
      const currentVersion = Number(rowInfo.data['마지막변경버전'] || 0);
      const currentUpdatedAt = String(rowInfo.data['수정일시'] || '').trim();
      const finishedMs = Date.now();
      return {
        ok: true,
        alreadySet: true,
        version: currentVersion,
        room: {
          rowNumber,
          businessDate,
          site: responseSite,
          roomNo,
          roomStatus: requestedRoomStatus,
          displayBaseRoomStatus: resolveIndicatorDisplayBaseRoomStatus_(rowInfo.data),
          cleaningStatus: String(rowInfo.data['청소상태'] || '').trim(),
          updatedAt: currentUpdatedAt,
          version: currentVersion
        },
        notificationQueued: false,
        notificationDeferred: false,
        deferredNotification: null,
        timing: {
          fastPath: true,
          checkout: true,
          idempotent: true,
          lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),
          coreMs: Math.max(0, finishedMs - writeLockAcquiredMs),
          totalMs: Math.max(0, finishedMs - startedMs)
        }
      };
    }

    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);

    const updatedAt = nowText_();
    const updates = { '수정일시': updatedAt };

    if (isNovaRoomCleaningTargetStatus_(requestedRoomStatus)) {
      Object.assign(updates, buildIndicatorPreviousCycleArchiveUpdates_(rowInfo.data));
    }
    updates['객실상태'] = requestedRoomStatus;
    updates[indicatorLastRoomStatusHeader_()] = resolveIndicatorLastRoomStatusAfterChange_(requestedRoomStatus, rowInfo.data);
    Object.assign(updates, resolveManualRoomStatusState_(requestedRoomStatus, rowInfo.data));

    version = reserveDataVersion_({ lockHeld: true });
    updates['마지막변경버전'] = version;
    updateRowByHeaders_(sheet, rowNumber, updates);
    publishDataVersion_(version, {
      domains: ['ROOM'],
      businessDate,
      site: responseSite,
      lockHeld: true
    });

    const refreshed = Object.assign({}, rowInfo.data, updates);
    const effectiveCleaningType = String(refreshed['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE,
      businessDate,
      site: responseSite,
      roomNo,
      targetEmployeeNo: '',
      status: 'CHANGE_ROOM_STATUS',
      detail: {
        action: 'CHANGE_ROOM_STATUS',
        previousRoomStatus,
        sourceRoomStatus: '',
        roomStatus: requestedRoomStatus,
        specialDepartureStarted: false,
        cleaningStatus: String(refreshed['청소상태'] || '').trim(),
        cleaningType: effectiveCleaningType,
        assignmentType: String(refreshed['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
        primaryEmployeeNo: String(refreshed['룸메이드사번'] || '').trim(),
        secondaryEmployeeNo: String(refreshed['보조룸메이드사번'] || '').trim(),
        creditUnit: getRoommaidCleaningCreditUnit_(effectiveCleaningType),
        preassigned: normalizeYesNo_(refreshed['선배정여부']) === 'Y',
        vip: normalizeYesNo_(refreshed['VIP여부']) === 'Y',
        importantRoom: normalizeYesNo_(refreshed['중요객실여부']) === 'Y',
        previousOperationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
        operationalStatus: normalizeIndicatorRoomOperationalStatus_(refreshed[indicatorRoomOperationalStatusHeader_()])
      },
      registeredBy: user.employeeNo,
      version
    });

    deferredNotification = buildRoomOperationDeferredTelegramPayload_('CHANGE_ROOM_STATUS', {
      businessDate,
      site: responseSite,
      roomNo,
      previous: rowInfo.data,
      current: refreshed,
      requestedRoomStatus,
      version
    });

    // Client가 이미 즉시 반영한 카드에 필요한 필드만 확인 응답한다.
    // 이름·운영표시·배정정보는 기존 카드 값을 그대로 유지하므로 전체 사용자 인덱스를 다시 읽지 않는다.
    responseRoom = {
      rowNumber,
      businessDate,
      site: responseSite,
      roomNo,
      roomStatus: requestedRoomStatus,
      displayBaseRoomStatus: resolveIndicatorDisplayBaseRoomStatus_(refreshed),
      cleaningStatus: String(refreshed['청소상태'] || '').trim(),
      updatedAt,
      version
    };
  } finally {
    writeLock.releaseLock();
  }

  const finishedMs = Date.now();
  return {
    ok: true,
    version,
    room: responseRoom,
    notificationQueued: false,
    notificationDeferred: Boolean(deferredNotification),
    deferredNotification,
    timing: {
      fastPath: true,
      checkout: true,
      lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),
      coreMs: Math.max(0, finishedMs - writeLockAcquiredMs),
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}


function completeIndicatorRoomCleaningFast_(user, payload, context) { // (청소완료 핵심저장·중복요청 멱등 차단)
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  const writeLockRequestedMs = Date.now();
  const writeLock = acquireWriteLock_();
  const writeLockAcquiredMs = Date.now();
  let version = 0;
  let rowNumber = 0;
  let responseSite = site;
  let qmEmployeeNo = '';
  let preassigned = false;
  let vip = false;
  let importantRoom = false;

  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRowFast_(sheet, businessDate, site, roomNo, safe.rowNumber);
    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
    rowNumber = rowInfo.rowNumber;
    responseSite = String(rowInfo.data['사업장'] || site).trim();

    const currentCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
    const completionLockedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
    if (completionLockedStatuses.has(currentCleaningStatus)) {
      // 같은 객실의 완료요청이 연속·동시에 도착해도 기존 완료이력과 버전을 그대로 반환합니다.
      const currentVersion = Number(rowInfo.data['마지막변경버전'] || 0);
      const finishedMs = Date.now();
      return {
        ok: true,
        alreadyCompleted: true,
        version: currentVersion,
        room: {
          site: responseSite,
          roomNo,
          rowNumber,
          cleaningStatus: currentCleaningStatus,
          version: currentVersion
        },
        notificationQueued: false,
        notificationDeferred: false,
        deferredNotification: null,
        timing: {
          fastPath: true,
          idempotent: true,
          lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),
          coreMs: Math.max(0, finishedMs - writeLockAcquiredMs),
          totalMs: Math.max(0, finishedMs - startedMs)
        }
      };
    }

    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);

    const updatedAt = nowText_();
    const previousRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
    const cleaningType = String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
    const assignmentType = String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
    const primaryEmployeeNo = String(rowInfo.data['룸메이드사번'] || '').trim();
    const secondaryEmployeeNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
    qmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
    preassigned = normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y';
    vip = normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y';
    importantRoom = normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y';

    version = reserveDataVersion_({ lockHeld: true });
    updateRowByHeaders_(sheet, rowInfo.rowNumber, {
      '청소상태': 'COMPLETED',
      '수정일시': updatedAt,
      '마지막변경버전': version
    });
    publishDataVersion_(version, {
      domains: ['ROOM'],
      businessDate,
      site: responseSite,
      lockHeld: true
    });

    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.CLEANING,
      businessDate,
      site: responseSite,
      roomNo,
      targetEmployeeNo: primaryEmployeeNo,
      status: 'CLEANING_COMPLETE',
      detail: {
        action: 'CLEANING_COMPLETE',
        previousRoomStatus,
        sourceRoomStatus: previousRoomStatus,
        roomStatus: previousRoomStatus,
        specialDepartureStarted: false,
        cleaningStatus: 'COMPLETED',
        cleaningType,
        assignmentType,
        primaryEmployeeNo,
        secondaryEmployeeNo,
        creditUnit: getRoommaidCleaningCreditUnit_(cleaningType),
        preassigned,
        vip,
        importantRoom,
        previousOperationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
        operationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()])
      },
      registeredBy: user.employeeNo,
      completedAt: updatedAt,
      version
    });
  } finally {
    writeLock.releaseLock();
  }

  const finishedMs = Date.now();
  return {
    ok: true,
    alreadyCompleted: false,
    version,
    room: {
      site: responseSite,
      roomNo,
      rowNumber,
      cleaningStatus: 'COMPLETED',
      version
    },
    notificationQueued: false,
    notificationDeferred: Boolean(qmEmployeeNo),
    deferredNotification: qmEmployeeNo ? {
      action: 'CLEANING_COMPLETE',
      businessDate,
      site: responseSite,
      roomNo,
      qmEmployeeNo,
      preassigned,
      vip,
      importantRoom,
      version
    } : null,
    timing: {
      fastPath: true,
      idempotent: false,
      lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),
      coreMs: Math.max(0, finishedMs - writeLockAcquiredMs),
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}


function resetIndicatorRoomCleaningFast_(user, payload, context) { // (객실 금일 청소완료 전체취소·배정 초기화)
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  const writeLockRequestedMs = Date.now();
  const writeLock = acquireWriteLock_();
  const writeLockAcquiredMs = Date.now();
  let version = 0;
  let rowNumber = 0;
  let responseSite = site;
  let removedCompletionCount = 0;
  let removedCompletionRecordIds = [];
  let removedEmployeeNos = [];
  const phaseTiming = {};
  let phaseStartedMs = Date.now();

  try {
    const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRowFast_(currentSheet, businessDate, site, roomNo, safe.rowNumber);
    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);
    phaseTiming.currentRoomLookupMs = Math.max(0, Date.now() - phaseStartedMs);

    rowNumber = rowInfo.rowNumber;
    responseSite = String(rowInfo.data['사업장'] || site).trim();
    const roomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
    const currentCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
    const resetAllowedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
    if (!isNovaRoomCleaningTargetStatus_(roomStatus)) {
      throw new Error(`${roomNo}호는 청소초기화 대상 객실상태가 아닙니다.`);
    }
    if (!resetAllowedStatuses.has(currentCleaningStatus)) {
      throw new Error(`${roomNo}호는 청소완료 상태에서만 청소초기화할 수 있습니다.`);
    }

    phaseStartedMs = Date.now();
    const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const completions = findIndicatorRoomActiveCleaningCompletions_(historySheet, businessDate, responseSite, roomNo);
    phaseTiming.historyLookupMs = Math.max(0, Date.now() - phaseStartedMs);
    if (!completions.length) {
      throw new Error(`${roomNo}호에 초기화할 활성 청소완료 이력이 없습니다.`);
    }

    const resetAt = nowText_();
    const previousCleaningType = String(rowInfo.data['정비유형'] || '').trim().toUpperCase();
    const previousAssignmentType = String(rowInfo.data['배정유형'] || '').trim().toUpperCase();
    const previousPrimaryEmployeeNo = String(rowInfo.data['룸메이드사번'] || '').trim();
    const previousSecondaryEmployeeNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
    const previousQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();

    phaseStartedMs = Date.now();
    version = reserveDataVersion_({ lockHeld: true });
    phaseTiming.reserveVersionMs = Math.max(0, Date.now() - phaseStartedMs);

    phaseStartedMs = Date.now();
    markIndicatorRoomCleaningCompletionsDeleted_(historySheet, completions, resetAt);
    phaseTiming.markHistoryDeletedMs = Math.max(0, Date.now() - phaseStartedMs);
    removedCompletionCount = completions.length;
    removedCompletionRecordIds = completions.map(item => item.recordId).filter(Boolean);
    removedEmployeeNos = Array.from(new Set(completions.flatMap(item => [
      item.targetEmployeeNo,
      item.primaryEmployeeNo,
      item.secondaryEmployeeNo
    ]).map(value => String(value || '').trim()).filter(Boolean)));

    phaseStartedMs = Date.now();
    updateRowByHeaders_(currentSheet, rowInfo.rowNumber, {
      '청소상태': 'WAITING',
      '정비유형': '',
      '배정유형': '',
      '룸메이드사번': '',
      '보조룸메이드사번': '',
      'QM사번': '',
      '수정일시': resetAt,
      '마지막변경버전': version
    });
    phaseTiming.updateCurrentRoomMs = Math.max(0, Date.now() - phaseStartedMs);

    phaseStartedMs = Date.now();
    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.CLEANING,
      businessDate,
      site: responseSite,
      roomNo,
      targetEmployeeNo: '',
      status: 'CLEANING_RESET',
      detail: {
        action: 'CLEANING_RESET',
        resetScope: 'ALL_ACTIVE_COMPLETIONS_FOR_ROOM_DATE_SITE',
        roomStatus,
        previousCleaningStatus: currentCleaningStatus,
        cleaningStatus: 'WAITING',
        previousCleaningType,
        previousAssignmentType,
        previousPrimaryEmployeeNo,
        previousSecondaryEmployeeNo,
        previousQmEmployeeNo,
        removedCompletionCount,
        removedCompletionRecordIds,
        removedEmployeeNos,
        resetBy: user.employeeNo,
        resetAt
      },
      registeredBy: user.employeeNo,
      version
    });
    phaseTiming.appendResetHistoryMs = Math.max(0, Date.now() - phaseStartedMs);

    phaseStartedMs = Date.now();
    SpreadsheetApp.flush();
    phaseTiming.flushMs = Math.max(0, Date.now() - phaseStartedMs);

    phaseStartedMs = Date.now();
    publishDataVersion_(version, {
      domains: ['ROOM', 'REPORT'],
      businessDate,
      site: responseSite,
      lockHeld: true
    });
    phaseTiming.publishVersionMs = Math.max(0, Date.now() - phaseStartedMs);
  } finally {
    writeLock.releaseLock();
  }

  const finishedMs = Date.now();
  return {
    ok: true,
    version,
    resetCompletionCount: removedCompletionCount,
    removedCompletionRecordIds,
    removedEmployeeNos,
    room: {
      site: responseSite,
      roomNo,
      rowNumber,
      cleaningStatus: 'WAITING',
      cleaningType: '',
      assignmentType: '',
      roommaidEmployeeNo: '',
      roommaidName: '',
      secondaryRoommaidEmployeeNo: '',
      secondaryRoommaidName: '',
      qmEmployeeNo: '',
      qmName: '',
      version
    },
    notificationQueued: false,
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      fastPath: true,
      cleaningReset: true,
      lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),
      coreMs: Math.max(0, finishedMs - writeLockAcquiredMs),
      totalMs: Math.max(0, finishedMs - startedMs),
      phases: phaseTiming
    }
  };
}

function findIndicatorRoomActiveCleaningCompletions_(sheet, businessDate, site, roomNo) { // (객실 금일 활성 청소완료 이력 전체 조회·업무일자 우선검색)
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const requiredHeaders = ['기록ID', '기록구분', '업무일자', '사업장', '객실번호', '대상사번', '처리상태', '세부내용JSON', '삭제여부'];
  requiredHeaders.forEach(header => {
    if (!headerMap[header]) throw new Error(`업무이력 시트의 ${header} 열을 확인하세요.`);
  });

  // 기존에는 업무이력 전체 행×전체 열을 매번 읽어 청소초기화가 수 초~수십 초 걸렸다.
  // 먼저 업무일자 열에서 오늘 날짜 행만 서버측 TextFinder로 찾고,
  // 그 날짜가 존재하는 최소~최대 행 범위의 필요한 열 구간만 1회 읽는다.
  // 필터 조건과 결과 형식은 기존 로직과 동일하게 유지한다.
  const dateColumn = Number(headerMap['업무일자']);
  const dateMatches = sheet
    .getRange(2, dateColumn, lastRow - 1, 1)
    .createTextFinder(String(businessDate || '').trim())
    .matchEntireCell(true)
    .findAll();

  if (!dateMatches.length) return [];

  const matchedRows = Array.from(new Set(dateMatches.map(cell => cell.getRow())))
    .filter(rowNumber => rowNumber >= 2)
    .sort((a, b) => a - b);
  if (!matchedRows.length) return [];

  const matchedRowSet = new Set(matchedRows);
  const firstRow = matchedRows[0];
  const lastMatchedRow = matchedRows[matchedRows.length - 1];

  const requiredColumns = requiredHeaders.map(header => Number(headerMap[header]));
  const firstColumn = Math.min.apply(null, requiredColumns);
  const lastColumn = Math.max.apply(null, requiredColumns);
  const width = lastColumn - firstColumn + 1;
  const values = sheet
    .getRange(firstRow, firstColumn, lastMatchedRow - firstRow + 1, width)
    .getDisplayValues();

  const columnIndex = header => Number(headerMap[header] || 0) - firstColumn;
  const index = {
    recordId: columnIndex('기록ID'),
    type: columnIndex('기록구분'),
    date: columnIndex('업무일자'),
    site: columnIndex('사업장'),
    room: columnIndex('객실번호'),
    target: columnIndex('대상사번'),
    status: columnIndex('처리상태'),
    detail: columnIndex('세부내용JSON'),
    deleted: columnIndex('삭제여부')
  };
  const completionStatuses = new Set(['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE']);
  const normalizedRoomNo = normalizeRoomNo_(roomNo);
  const result = [];

  matchedRows.forEach(rowNumber => {
    if (!matchedRowSet.has(rowNumber)) return;
    const row = values[rowNumber - firstRow];
    if (!row) return;
    if (String(row[index.type] || '').trim() !== NOVA.RECORD_TYPES.CLEANING) return;
    if (String(row[index.date] || '').trim() !== businessDate) return;
    if (String(row[index.site] || '').trim() !== site) return;
    if (normalizeRoomNo_(row[index.room]) !== normalizedRoomNo) return;
    if (String(row[index.deleted] || 'N').trim().toUpperCase() === 'Y') return;
    const status = String(row[index.status] || '').trim().toUpperCase();
    if (!completionStatuses.has(status)) return;

    let detail = {};
    try { detail = JSON.parse(String(row[index.detail] || '{}')); } catch (error) { detail = {}; }
    result.push({
      rowNumber,
      recordId: String(row[index.recordId] || '').trim(),
      targetEmployeeNo: String(row[index.target] || '').trim(),
      status,
      primaryEmployeeNo: String(detail.primaryEmployeeNo || '').trim(),
      secondaryEmployeeNo: String(detail.secondaryEmployeeNo || '').trim()
    });
  });
  return result;
}

function markIndicatorRoomCleaningCompletionsDeleted_(sheet, completions, resetAt) { // (청소초기화 완료이력 소프트삭제)
  const rows = Array.from(new Set((completions || []).map(item => Number(item.rowNumber || 0)).filter(rowNumber => rowNumber >= 2))).sort((a, b) => a - b);
  if (!rows.length) return 0;
  const headerMap = getHeaderMap_(sheet);
  const deletedColumn = headerMap['삭제여부'];
  const updatedColumn = headerMap['수정일시'];
  if (!deletedColumn || !updatedColumn) throw new Error('업무이력 시트의 삭제여부·수정일시 열을 확인하세요.');
  sheet.getRangeList(rows.map(rowNumber => sheet.getRange(rowNumber, deletedColumn).getA1Notation())).setValue('Y');
  sheet.getRangeList(rows.map(rowNumber => sheet.getRange(rowNumber, updatedColumn).getA1Notation())).setValue(resetAt);
  return rows.length;
}

function queueDeferredRoomOperationNotification(token, payload) { // (객실작업 저장 후 알림큐 비동기 등록)
  return measureResponse_('queueDeferredRoomOperationNotification', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const action = String(safe.action || '').trim().toUpperCase();
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!site || !roomNo) return { ok: true, queued: false, reason: 'MISSING_ROOM' };

    if (action === 'CLEANING_COMPLETE') {
      const qmEmployeeNo = String(safe.qmEmployeeNo || '').trim();
      if (!qmEmployeeNo) return { ok: true, queued: false, reason: 'MISSING_TARGET' };
      const qmUser = getUserIndex_().byEmployeeNo[qmEmployeeNo] || null;
      if (!qmUser || !qmUser.enabled || String(qmUser.role || '').trim().toUpperCase() !== 'QM') {
        return { ok: true, queued: false, reason: 'QM_NOT_AVAILABLE' };
      }
      const result = queueQmReadyTelegram_({
        businessDate, site, roomNo, targetUser: qmUser,
        preassigned: Boolean(safe.preassigned),
        vip: Boolean(safe.vip),
        importantRoom: Boolean(safe.importantRoom),
        registeredBy: user.employeeNo, version: Number(safe.version || 0)
      });
      return roomOperationDeferredQueueResult_(result);
    }

    const usersByEmployeeNo = getUserIndex_().byEmployeeNo;

    if (action === 'ASSIGN_ROOMMAID') {
      const primaryEmployeeNo = String(safe.primaryEmployeeNo || '').trim();
      const secondaryEmployeeNo = String(safe.secondaryEmployeeNo || '').trim();
      const primaryUser = primaryEmployeeNo ? usersByEmployeeNo[primaryEmployeeNo] || null : null;
      const secondaryUser = secondaryEmployeeNo ? usersByEmployeeNo[secondaryEmployeeNo] || null : null;
      if (!primaryUser || !primaryUser.enabled || String(primaryUser.role || '').trim().toUpperCase() !== 'ROOMMAID') {
        return { ok: true, queued: false, count: 0, reason: 'ROOMMAID_NOT_AVAILABLE' };
      }
      const telegramBase = {
        businessDate, site, roomNo,
        roomStatus: String(safe.roomStatus || '').trim(),
        cleaningType: String(safe.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
        cleaningStatus: String(safe.cleaningStatus || 'ASSIGNED').trim().toUpperCase(),
        assignmentType: String(safe.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
        preassigned: Boolean(safe.preassigned),
        vip: Boolean(safe.vip),
        importantRoom: Boolean(safe.importantRoom),
        registeredBy: user.employeeNo,
        version: Number(safe.version || 0)
      };
      let queuedCount = 0;
      const first = queueCleaningAssignmentTelegram_(Object.assign({}, telegramBase, {
        targetUser: primaryUser, assignmentRole: 'PRIMARY'
      }));
      if (first && first.queued) queuedCount += 1;
      if (secondaryEmployeeNo && secondaryUser && secondaryUser.enabled
          && String(secondaryUser.role || '').trim().toUpperCase() === 'ROOMMAID') {
        const second = queueCleaningAssignmentTelegram_(Object.assign({}, telegramBase, {
          targetUser: secondaryUser, assignmentRole: 'SECONDARY'
        }));
        if (second && second.queued) queuedCount += 1;
      }
      return { ok: true, queued: queuedCount > 0, count: queuedCount, reason: queuedCount ? '' : 'TELEGRAM_NOT_QUEUED' };
    }

    if (action === 'QM_ASSIGN') {
      const qmEmployeeNo = String(safe.qmEmployeeNo || '').trim();
      const qmUser = qmEmployeeNo ? usersByEmployeeNo[qmEmployeeNo] || null : null;
      if (!qmUser || !qmUser.enabled || String(qmUser.role || '').trim().toUpperCase() !== 'QM') {
        return { ok: true, queued: false, count: 0, reason: 'QM_NOT_AVAILABLE' };
      }
      const result = queueQmAssignmentTelegram_({
        businessDate, site, roomNo, targetUser: qmUser,
        preassigned: Boolean(safe.preassigned),
        vip: Boolean(safe.vip),
        importantRoom: Boolean(safe.importantRoom),
        registeredBy: user.employeeNo,
        version: Number(safe.version || 0)
      });
      return roomOperationDeferredQueueResult_(result);
    }

    const roommaidUsers = uniqueRoomOperationEmployeeNos_(safe.roommaidEmployeeNos)
      .map(employeeNo => usersByEmployeeNo[employeeNo] || null)
      .filter(target => target && target.enabled && String(target.role || '').trim().toUpperCase() === 'ROOMMAID');

    if (action === 'CLEAR_ASSIGNMENT') {
      let queuedCount = 0;
      let lastReason = '';
      const roommaidResult = queueRoommaidAssignmentCancellationTelegram_({
        businessDate, site, roomNo, targetUsers: roommaidUsers,
        cleaningType: safe.cleaningType, assignmentType: safe.assignmentType,
        preassigned: Boolean(safe.preassigned), vip: Boolean(safe.vip), importantRoom: Boolean(safe.importantRoom),
        registeredBy: user.employeeNo, version: Number(safe.version || 0)
      });
      if (roommaidResult && roommaidResult.queued) queuedCount += Number(roommaidResult.count || 0);
      else lastReason = String(roommaidResult && roommaidResult.reason || lastReason);

      const qmEmployeeNo = String(safe.qmEmployeeNo || '').trim();
      const qmUser = qmEmployeeNo ? usersByEmployeeNo[qmEmployeeNo] || null : null;
      if (qmUser && qmUser.enabled && String(qmUser.role || '').trim().toUpperCase() === 'QM') {
        const qmResult = queueQmAssignmentCancellationTelegram_({
          businessDate, site, roomNo, targetUser: qmUser,
          preassigned: Boolean(safe.preassigned), vip: Boolean(safe.vip), importantRoom: Boolean(safe.importantRoom),
          registeredBy: user.employeeNo, version: Number(safe.version || 0)
        });
        if (qmResult && qmResult.queued) queuedCount += Number(qmResult.count || 0);
        else lastReason = String(qmResult && qmResult.reason || lastReason);
      }
      return { ok: true, queued: queuedCount > 0, count: queuedCount, reason: queuedCount ? '' : (lastReason || 'NO_RECIPIENT') };
    }

    if (action === 'DUE_OUT_TO_CHECKED_OUT') {
      const result = queueRoommaidDepartureConfirmedTelegram_({
        businessDate, site, roomNo, targetUsers: roommaidUsers,
        cleaningType: safe.cleaningType,
        preassigned: Boolean(safe.preassigned), vip: Boolean(safe.vip), importantRoom: Boolean(safe.importantRoom),
        registeredBy: user.employeeNo, version: Number(safe.version || 0)
      });
      return roomOperationDeferredQueueResult_(result);
    }

    if (action === 'OPERATION_FLAGS_CHANGED') {
      const result = queueRoommaidOperationFlagsTelegram_({
        businessDate, site, roomNo, targetUsers: roommaidUsers,
        previousPreassigned: safe.previousPreassigned,
        preassigned: safe.preassigned,
        previousVip: safe.previousVip,
        vip: safe.vip,
        previousImportantRoom: safe.previousImportantRoom,
        importantRoom: safe.importantRoom,
        registeredBy: user.employeeNo, version: Number(safe.version || 0)
      });
      return roomOperationDeferredQueueResult_(result);
    }

    return { ok: true, queued: false, reason: 'UNSUPPORTED_ACTION' };
  });
}

function roomOperationDeferredQueueResult_(result) { // (객실 후속알림 결과 공통정리)
  return {
    ok: true,
    queued: Boolean(result && result.queued),
    count: Number(result && result.count || 0),
    reason: String(result && result.reason || '')
  };
}

function uniqueRoomOperationEmployeeNos_(values) { // (객실 후속알림 대상사번 중복제거)
  return Array.from(new Set((Array.isArray(values) ? values : [values])
    .map(value => String(value || '').trim()).filter(Boolean)));
}

function buildRoomOperationDeferredTelegramPayload_(action, context) { // (객실변경 후속 텔레그램 이벤트 생성)
  const event = String(action || '').trim().toUpperCase();
  const safe = context || {};
  const previous = safe.previous || {};
  const current = safe.current || {};
  const common = {
    businessDate: safe.businessDate,
    site: safe.site,
    roomNo: safe.roomNo,
    version: Number(safe.version || 0)
  };

  if (event === 'ASSIGN_ROOMMAID') {
    const primaryEmployeeNo = String(current['룸메이드사번'] || '').trim();
    const secondaryEmployeeNo = String(current['보조룸메이드사번'] || '').trim();
    if (!primaryEmployeeNo) return null;
    return Object.assign({}, common, {
      action: 'ASSIGN_ROOMMAID',
      primaryEmployeeNo,
      secondaryEmployeeNo,
      roomStatus: String(current['객실상태'] || '').trim(),
      cleaningStatus: String(current['청소상태'] || 'ASSIGNED').trim().toUpperCase(),
      cleaningType: String(current['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
      assignmentType: String(current['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
      preassigned: normalizeYesNo_(current['선배정여부']) === 'Y',
      vip: normalizeYesNo_(current['VIP여부']) === 'Y',
      importantRoom: normalizeYesNo_(current['중요객실여부']) === 'Y'
    });
  }

  if (event === 'QM_ASSIGN') {
    const qmEmployeeNo = String(current['QM사번'] || '').trim();
    if (!qmEmployeeNo) return null;
    return Object.assign({}, common, {
      action: 'QM_ASSIGN',
      qmEmployeeNo,
      preassigned: normalizeYesNo_(current['선배정여부']) === 'Y',
      vip: normalizeYesNo_(current['VIP여부']) === 'Y',
      importantRoom: normalizeYesNo_(current['중요객실여부']) === 'Y'
    });
  }

  if (event === 'CLEAR_ASSIGNMENT') {
    const roommaidEmployeeNos = uniqueRoomOperationEmployeeNos_([
      previous['룸메이드사번'], previous['보조룸메이드사번']
    ]);
    const qmEmployeeNo = String(previous['QM사번'] || '').trim();
    if (!roommaidEmployeeNos.length && !qmEmployeeNo) return null;
    return Object.assign({}, common, {
      action: 'CLEAR_ASSIGNMENT',
      roommaidEmployeeNos,
      qmEmployeeNo,
      cleaningType: String(previous['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
      assignmentType: String(previous['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
      preassigned: normalizeYesNo_(previous['선배정여부']) === 'Y',
      vip: normalizeYesNo_(previous['VIP여부']) === 'Y',
      importantRoom: normalizeYesNo_(previous['중요객실여부']) === 'Y'
    });
  }

  if (event === 'CHANGE_ROOM_STATUS') {
    const previousRoomStatus = String(previous['객실상태'] || '').trim().toUpperCase();
    const nextRoomStatus = String(safe.requestedRoomStatus || current['객실상태'] || '').trim().toUpperCase();
    if (previousRoomStatus !== 'DUE_OUT' || nextRoomStatus !== 'CHECKED_OUT') return null;
    const roommaidEmployeeNos = uniqueRoomOperationEmployeeNos_([
      current['룸메이드사번'], current['보조룸메이드사번']
    ]);
    if (!roommaidEmployeeNos.length) return null;
    return Object.assign({}, common, {
      action: 'DUE_OUT_TO_CHECKED_OUT',
      roommaidEmployeeNos,
      cleaningType: String(current['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
      preassigned: normalizeYesNo_(current['선배정여부']) === 'Y',
      vip: normalizeYesNo_(current['VIP여부']) === 'Y',
      importantRoom: normalizeYesNo_(current['중요객실여부']) === 'Y'
    });
  }

  if (event === 'UPDATE_OPERATION_FLAGS') {
    const previousPreassigned = normalizeYesNo_(previous['선배정여부']) === 'Y';
    const preassigned = normalizeYesNo_(current['선배정여부']) === 'Y';
    const previousVip = normalizeYesNo_(previous['VIP여부']) === 'Y';
    const vip = normalizeYesNo_(current['VIP여부']) === 'Y';
    const previousImportantRoom = normalizeYesNo_(previous['중요객실여부']) === 'Y';
    const importantRoom = normalizeYesNo_(current['중요객실여부']) === 'Y';
    if (previousPreassigned === preassigned && previousVip === vip && previousImportantRoom === importantRoom) return null;
    const roommaidEmployeeNos = uniqueRoomOperationEmployeeNos_([
      current['룸메이드사번'], current['보조룸메이드사번']
    ]);
    if (!roommaidEmployeeNos.length) return null;
    return Object.assign({}, common, {
      action: 'OPERATION_FLAGS_CHANGED',
      roommaidEmployeeNos,
      previousPreassigned, preassigned,
      previousVip, vip,
      previousImportantRoom, importantRoom
    });
  }

  return null;
}


function resolveRoommaidAssignment_(primaryEmployeeNo, secondaryEmployeeNo, assignmentType, usersByEmployeeNo) { // (1인·2인1조 룸메이드 배정 검증)
  const type = String(assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
  const allowed = new Set(Object.values(NOVA.ROOMMAID_ASSIGNMENT_TYPES));
  if (!allowed.has(type)) throw new Error('사용할 수 없는 룸메이드 배정유형입니다.');
  const users = usersByEmployeeNo || getUserIndex_().byEmployeeNo;
  const primary = users[String(primaryEmployeeNo || '').trim()] || null;
  if (!primary || !primary.enabled || String(primary.role || '').toUpperCase() !== 'ROOMMAID') throw new Error('주담당 룸메이드를 선택하세요.');
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO) {
    return { assignmentType: type, primary, secondary: null };
  }
  const secondary = users[String(secondaryEmployeeNo || '').trim()] || null;
  if (!secondary || !secondary.enabled || String(secondary.role || '').toUpperCase() !== 'ROOMMAID') throw new Error('보조 룸메이드를 선택하세요.');
  if (secondary.employeeNo === primary.employeeNo) throw new Error('2인1조는 서로 다른 룸메이드 2명을 선택해야 합니다.');
  return { assignmentType: type, primary, secondary };
}

function isInitialRoommaidAssignmentAvailable_(roomData) { // (최초 일괄배정 가능 여부)
  const data = roomData || {};
  return !String(data['룸메이드사번'] || '').trim()
    && !String(data['보조룸메이드사번'] || '').trim();
}

function bulkAssignRoommaids(token, payload) { // (최초 룸메이드 다수 객실 일괄배정)
  return measureResponse_('bulkAssignRoommaids', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('사업장을 선택하세요.');
    const roomNos = Array.from(new Set((Array.isArray(safe.roomNos) ? safe.roomNos : [])
      .map(value => String(value || '').trim()).filter(Boolean)));
    if (!roomNos.length) throw new Error('배정할 객실을 선택하세요.');
    if (roomNos.length > 300) throw new Error('한 번에 최대 300실까지 배정할 수 있습니다.');
    const cleaningType = String(safe.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
    const allowedCleaningTypes = new Set(getCodes_('정비유형').map(code => String(code.code || '').trim().toUpperCase()));
    if (!allowedCleaningTypes.has(cleaningType)) throw new Error('사용할 수 없는 정비유형입니다.');
    const resolved = resolveRoommaidAssignment_(safe.primaryEmployeeNo, safe.secondaryEmployeeNo, safe.assignmentType);
    const writeLock = acquireWriteLock_();
    try {

    ensureRoomOperationalFlagHeaders_();
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const selection = getCurrentRowsForSelection_(businessDate, site);
    const wanted = new Set(roomNos);
    const selectedItems = selection.items.filter(item => wanted.has(String(item.data['객실번호'] || '').trim()));
    if (selectedItems.length !== roomNos.length) {
      const found = new Set(selectedItems.map(item => String(item.data['객실번호'] || '').trim()));
      const missing = roomNos.filter(roomNo => !found.has(roomNo));
      throw new Error(`현재객실현황에서 찾지 못한 객실: ${missing.slice(0, 20).join(', ')}${missing.length > 20 ? ` 외 ${missing.length - 20}실` : ''}`);
    }
    const alreadyAssigned = selectedItems
      .filter(item => !isInitialRoommaidAssignmentAvailable_(item.data))
      .map(item => String(item.data['객실번호'] || '').trim());
    if (alreadyAssigned.length) {
      throw new Error(`이미 배정된 객실은 최초 일괄배정에서 제외됩니다: ${alreadyAssigned.slice(0, 20).join(', ')}${alreadyAssigned.length > 20 ? ` 외 ${alreadyAssigned.length - 20}실` : ''}`);
    }
    const expectedVersions = safe.expectedVersions && typeof safe.expectedVersions === 'object' ? safe.expectedVersions : {};
    selectedItems.forEach(item => {
      const selectedRoomNo = String(item.data['객실번호'] || '').trim();
      assertExpectedVersion_(expectedVersions[selectedRoomNo], item.data['마지막변경버전'], `${selectedRoomNo}호 객실`);
    });

    const headerMap = getHeaderMap_(sheet);
    const firstRow = Math.min(...selectedItems.map(item => item.rowNumber));
    const lastRow = Math.max(...selectedItems.map(item => item.rowNumber));
    const lastColumn = sheet.getLastColumn();
    const range = sheet.getRange(firstRow, 1, lastRow - firstRow + 1, lastColumn);
    const values = range.getValues();
    const selectedRows = new Set(selectedItems.map(item => item.rowNumber));
    const version = reserveDataVersion_({ lockHeld: true });
    const now = nowText_();
    const setCell = (row, header, value) => {
      const column = headerMap[header];
      if (column) row[column - 1] = value;
    };
    values.forEach((row, offset) => {
      const rowNumber = firstRow + offset;
      if (!selectedRows.has(rowNumber)) return;
      setCell(row, '정비유형', cleaningType);
      setCell(row, '배정유형', resolved.assignmentType);
      setCell(row, '룸메이드사번', resolved.primary.employeeNo);
      setCell(row, '보조룸메이드사번', resolved.secondary ? resolved.secondary.employeeNo : '');
      setCell(row, '청소상태', 'ASSIGNED');
      setCell(row, '선배정여부', safe.preassigned ? 'Y' : 'N');
      setCell(row, 'VIP여부', safe.vip ? 'Y' : 'N');
      setCell(row, '중요객실여부', safe.importantRoom ? 'Y' : 'N');
      setCell(row, '마지막변경버전', version);
      setCell(row, '수정일시', now);
    });
    range.setValues(values);
    publishDataVersion_(version, { domains: ['ROOM'], businessDate, site, lockHeld: true });

    appendRoommaidBulkAssignmentHistory_(selectedItems, {
      businessDate, site, cleaningType, assignmentType: resolved.assignmentType,
      primaryEmployeeNo: resolved.primary.employeeNo,
      secondaryEmployeeNo: resolved.secondary ? resolved.secondary.employeeNo : '',
      preassigned: Boolean(safe.preassigned), vip: Boolean(safe.vip), importantRoom: Boolean(safe.importantRoom),
      registeredBy: user.employeeNo, version, now
    });
    queueRoommaidBulkAssignmentTelegram_({
      businessDate, site, roomNos,
      cleaningType, assignmentType: resolved.assignmentType,
      primaryUser: resolved.primary, secondaryUser: resolved.secondary,
      preassigned: Boolean(safe.preassigned), vip: Boolean(safe.vip), importantRoom: Boolean(safe.importantRoom),
      registeredBy: user.employeeNo, version
    });

    const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
    const updatedRooms = selectedItems.map(item => currentRoomObject_(Object.assign({}, item.data, {
      '정비유형': cleaningType,
      '배정유형': resolved.assignmentType,
      '룸메이드사번': resolved.primary.employeeNo,
      '보조룸메이드사번': resolved.secondary ? resolved.secondary.employeeNo : '',
      '청소상태': 'ASSIGNED',
      '선배정여부': safe.preassigned ? 'Y' : 'N',
      'VIP여부': safe.vip ? 'Y' : 'N',
      '중요객실여부': safe.importantRoom ? 'Y' : 'N',
      '마지막변경버전': version,
      '수정일시': now
    }), item.rowNumber, {}, usersByEmployeeNo)).sort(compareRooms_);
    return { ok: true, version, count: updatedRooms.length, rooms: updatedRooms };
     } finally {
      writeLock.releaseLock();
    }
  });
}



function autoAssignRoommaids(token, payload) { // (선택 미배정 객실 룸메이드 자동 균형배정)
  return measureResponse_('autoAssignRoommaids', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('사업장을 선택하세요.');

    const roomNos = Array.from(new Set((Array.isArray(safe.roomNos) ? safe.roomNos : [])
      .map(value => String(value || '').trim()).filter(Boolean)));
    if (!roomNos.length) throw new Error('자동배정할 객실을 선택하세요.');
    if (roomNos.length > 300) throw new Error('한 번에 최대 300실까지 자동배정할 수 있습니다.');

    const userIndex = getUserIndex_();
    const requestedEmployees = new Set((Array.isArray(safe.employeeNos) ? safe.employeeNos : [])
      .map(value => String(value || '').trim()).filter(Boolean));
    const candidates = userIndex.active
      .filter(candidate => String(candidate.role || '').trim().toUpperCase() === 'ROOMMAID')
      .filter(candidate => !requestedEmployees.size || requestedEmployees.has(String(candidate.employeeNo || '').trim()))
      .filter(candidate => {
        const defaultSite = String(candidate.defaultSite || '').trim();
        return !defaultSite || defaultSite === site;
      })
      .map(candidate => ({
        employeeNo: String(candidate.employeeNo || '').trim(),
        name: String(candidate.name || candidate.employeeNo || '').trim(),
        user: candidate,
        defaultBuildings: Array.isArray(candidate.defaultBuildings)
          ? candidate.defaultBuildings.map(value => normalizeRoomBuilding_(value, '')).filter(Boolean)
          : String(candidate.defaultBuildings || '').split(/[,/·\s]+/).map(value => normalizeRoomBuilding_(value, '')).filter(Boolean),
        assignedCount: 0,
        creditLoad: 0
      }))
      .filter(candidate => candidate.employeeNo);
    if (!candidates.length) throw new Error('자동배정할 활성 룸메이드가 없습니다.');

    const writeLock = acquireWriteLock_();
    try {
      ensureRoomOperationalFlagHeaders_();
      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const selection = getCurrentRowsForSelection_(businessDate, site);
      const wanted = new Set(roomNos);
      const selectedItems = selection.items.filter(item => wanted.has(String(item.data['객실번호'] || '').trim()));
      if (selectedItems.length !== roomNos.length) {
        const found = new Set(selectedItems.map(item => String(item.data['객실번호'] || '').trim()));
        const missing = roomNos.filter(roomNo => !found.has(roomNo));
        throw new Error(`현재객실현황에서 찾지 못한 객실: ${missing.slice(0, 20).join(', ')}${missing.length > 20 ? ` 외 ${missing.length - 20}실` : ''}`);
      }

      const alreadyAssigned = selectedItems
        .filter(item => !isInitialRoommaidAssignmentAvailable_(item.data))
        .map(item => String(item.data['객실번호'] || '').trim());
      if (alreadyAssigned.length) {
        throw new Error(`이미 배정된 객실은 자동배정에서 제외됩니다: ${alreadyAssigned.slice(0, 20).join(', ')}${alreadyAssigned.length > 20 ? ` 외 ${alreadyAssigned.length - 20}실` : ''}`);
      }

      const expectedVersions = safe.expectedVersions && typeof safe.expectedVersions === 'object' ? safe.expectedVersions : {};
      selectedItems.forEach(item => {
        const roomNo = String(item.data['객실번호'] || '').trim();
        assertExpectedVersion_(expectedVersions[roomNo], item.data['마지막변경버전'], `${roomNo}호 객실`);
      });

      const candidateByNo = Object.fromEntries(candidates.map(candidate => [candidate.employeeNo, candidate]));
      selection.items.forEach(item => {
        const data = item.data || {};
        const primaryNo = String(data['룸메이드사번'] || '').trim();
        const primary = candidateByNo[primaryNo];
        if (!primary) return;
        const cleaningType = String(data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
        primary.assignedCount += 1;
        primary.creditLoad += getRoommaidCleaningCreditUnit_(cleaningType);
      });

      const roomPriority = roomStatus => {
        const status = String(roomStatus || '').trim().toUpperCase();
        const order = {
          CHECKED_OUT: 1, CHECKED_OUT_RC: 1, CHECKED_OUT_HU: 1,
          STOCK: 2, STOCK_RC: 2, STOCK_HU: 2,
          DEPARTURE_EXPECTED: 3
        };
        return order[status] || 9;
      };
      const jobs = selectedItems.slice().sort((a, b) => {
        const ad = a.data || {};
        const bd = b.data || {};
        const aImportant = normalizeYesNo_(ad['중요객실여부']) === 'Y' ? 0 : 1;
        const bImportant = normalizeYesNo_(bd['중요객실여부']) === 'Y' ? 0 : 1;
        if (aImportant !== bImportant) return aImportant - bImportant;
        const aVip = normalizeYesNo_(ad['VIP여부']) === 'Y' ? 0 : 1;
        const bVip = normalizeYesNo_(bd['VIP여부']) === 'Y' ? 0 : 1;
        if (aVip !== bVip) return aVip - bVip;
        const statusDiff = roomPriority(ad['객실상태']) - roomPriority(bd['객실상태']);
        if (statusDiff) return statusDiff;
        return compareRooms_({ roomNo: ad['객실번호'] }, { roomNo: bd['객실번호'] });
      });

      const plans = jobs.map(item => {
        const data = item.data || {};
        const roomNo = String(data['객실번호'] || '').trim();
        const building = normalizeRoomBuilding_(data['동'], roomNo);
        const cleaningType = String(data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
        const credit = getRoommaidCleaningCreditUnit_(cleaningType);
        const preferred = candidates.filter(candidate => !candidate.defaultBuildings.length || candidate.defaultBuildings.includes(building));
        const pool = preferred.length ? preferred : candidates;
        pool.sort((a, b) =>
          a.creditLoad - b.creditLoad
          || a.assignedCount - b.assignedCount
          || a.name.localeCompare(b.name, 'ko')
          || a.employeeNo.localeCompare(b.employeeNo, 'ko')
        );
        const chosen = pool[0];
        chosen.assignedCount += 1;
        chosen.creditLoad += credit;
        return { item, roomNo, building, cleaningType, credit, chosen };
      });

      const headerMap = getHeaderMap_(sheet);
      const firstRow = Math.min(...selectedItems.map(item => item.rowNumber));
      const lastRow = Math.max(...selectedItems.map(item => item.rowNumber));
      const lastColumn = sheet.getLastColumn();
      const range = sheet.getRange(firstRow, 1, lastRow - firstRow + 1, lastColumn);
      const values = range.getValues();
      const planByRow = Object.fromEntries(plans.map(plan => [plan.item.rowNumber, plan]));
      const version = reserveDataVersion_({ lockHeld: true });
      const now = nowText_();
      const setCell = (row, header, value) => {
        const column = headerMap[header];
        if (column) row[column - 1] = value;
      };
      values.forEach((row, offset) => {
        const rowNumber = firstRow + offset;
        const plan = planByRow[rowNumber];
        if (!plan) return;
        setCell(row, '배정유형', NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO);
        setCell(row, '룸메이드사번', plan.chosen.employeeNo);
        setCell(row, '보조룸메이드사번', '');
        setCell(row, '청소상태', 'ASSIGNED');
        setCell(row, '마지막변경버전', version);
        setCell(row, '수정일시', now);
      });
      range.setValues(values);
      publishDataVersion_(version, { domains: ['ROOM'], businessDate, site, lockHeld: true });

      const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const historyRows = plans.map(plan => createRowByHeaders_(historySheet, {
        '기록ID': `CLEANING-${Utilities.getUuid()}`,
        '기록구분': NOVA.RECORD_TYPES.CLEANING,
        '업무일자': businessDate,
        '사업장': site,
        '객실번호': plan.roomNo,
        '대상사번': plan.chosen.employeeNo,
        '처리상태': 'AUTO_ASSIGN_ROOMMAID',
        '세부내용JSON': JSON.stringify({
          action: 'AUTO_ASSIGN_ROOMMAID',
          cleaningType: plan.cleaningType,
          assignmentType: NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO,
          primaryEmployeeNo: plan.chosen.employeeNo,
          secondaryEmployeeNo: '',
          creditUnit: plan.credit,
          building: plan.building,
          balancingCreditAfter: plan.chosen.creditLoad,
          balancingCountAfter: plan.chosen.assignedCount
        }),
        '등록사번': user.employeeNo,
        '등록일시': now,
        '수정일시': now,
        '변경버전': version,
        '삭제여부': 'N'
      }));
      if (historyRows.length) {
        const startRow = historySheet.getLastRow() + 1;
        ensureSheetRowCapacity_(historySheet, startRow + historyRows.length - 1);
        historySheet.getRange(startRow, 1, historyRows.length, historyRows[0].length).setValues(historyRows);
      }

      const telegramGroups = {};
      plans.forEach(plan => {
        const key = `${plan.chosen.employeeNo}|${plan.cleaningType}`;
        if (!telegramGroups[key]) telegramGroups[key] = { candidate: plan.chosen, cleaningType: plan.cleaningType, roomNos: [] };
        telegramGroups[key].roomNos.push(plan.roomNo);
      });
      Object.values(telegramGroups).forEach(group => {
        queueRoommaidBulkAssignmentTelegram_({
          businessDate,
          site,
          roomNos: group.roomNos,
          cleaningType: group.cleaningType,
          assignmentType: NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO,
          primaryUser: group.candidate.user,
          secondaryUser: null,
          preassigned: false,
          vip: false,
          importantRoom: false,
          registeredBy: user.employeeNo,
          version
        });
      });

      const usersByEmployeeNo = userIndex.byEmployeeNo;
      const updatedRooms = plans.map(plan => currentRoomObject_(Object.assign({}, plan.item.data, {
        '배정유형': NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO,
        '룸메이드사번': plan.chosen.employeeNo,
        '보조룸메이드사번': '',
        '청소상태': 'ASSIGNED',
        '마지막변경버전': version,
        '수정일시': now
      }), plan.item.rowNumber, {}, usersByEmployeeNo)).sort(compareRooms_);
      const distribution = candidates
        .filter(candidate => plans.some(plan => plan.chosen.employeeNo === candidate.employeeNo))
        .map(candidate => ({
          employeeNo: candidate.employeeNo,
          name: candidate.name,
          assignedCount: plans.filter(plan => plan.chosen.employeeNo === candidate.employeeNo).length,
          totalAssignedCount: candidate.assignedCount,
          totalCreditLoad: Math.round(candidate.creditLoad * 100) / 100
        }))
        .sort((a, b) => a.name.localeCompare(b.name, 'ko'));
      return { ok: true, version, count: updatedRooms.length, rooms: updatedRooms, distribution };
    } finally {
      writeLock.releaseLock();
    }
  });
}

function appendRoommaidBulkAssignmentHistory_(items, context) { // (일괄배정 업무이력 한 번에 기록)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const rows = (items || []).map(item => {
    const roomNo = String(item.data['객실번호'] || '').trim();
    return createRowByHeaders_(sheet, {
      '기록ID': `CLEANING-${Utilities.getUuid()}`,
      '기록구분': NOVA.RECORD_TYPES.CLEANING,
      '업무일자': context.businessDate,
      '사업장': context.site,
      '객실번호': roomNo,
      '대상사번': context.primaryEmployeeNo,
      '처리상태': 'BULK_ASSIGN_ROOMMAID',
      '세부내용JSON': JSON.stringify({
        action: 'BULK_ASSIGN_ROOMMAID',
        cleaningType: context.cleaningType,
        assignmentType: context.assignmentType,
        primaryEmployeeNo: context.primaryEmployeeNo,
        secondaryEmployeeNo: context.secondaryEmployeeNo,
        creditUnit: getRoommaidCleaningCreditUnit_(context.cleaningType),
        preassigned: Boolean(context.preassigned),
        vip: Boolean(context.vip),
        importantRoom: Boolean(context.importantRoom)
      }),
      '등록사번': context.registeredBy,
      '등록일시': context.now,
      '수정일시': context.now,
      '변경버전': context.version,
      '삭제여부': 'N'
    });
  });
  if (!rows.length) return;
  const startRow = sheet.getLastRow() + 1;
  ensureSheetRowCapacity_(sheet, startRow + rows.length - 1);
  sheet.getRange(startRow, 1, rows.length, rows[0].length).setValues(rows);
}

function isNovaSpecialDepartureStatus_(roomStatus) { // (퇴실 R/C·퇴실 H/U 상태 판정)
  return ['CHECKED_OUT_RC', 'CHECKED_OUT_HU'].includes(String(roomStatus || '').trim().toUpperCase());
}

function isNovaRoomCleaningTargetStatus_(roomStatus) { // (일반·R/C·H/U 퇴실 및 재고 정비대상 판정)
  return ['CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU', 'STOCK', 'STOCK_RC', 'STOCK_HU']
    .includes(String(roomStatus || '').trim().toUpperCase());
}

function indicatorPreviousCycleHeaders_() { // (객실카드 이전 정비주기 저장 열명)
  return ['이전객실상태', '이전청소상태', '이전룸메이드사번', '이전보조룸메이드사번'];
}

function buildIndicatorPreviousCycleArchiveUpdates_(data) { // (새 정비대상 발생 전 완료된 직전 정비주기 보존)
  const currentCleaningStatus = String(data && data['청소상태'] || '').trim().toUpperCase();
  if (!['COMPLETED', 'QM_COMPLETED'].includes(currentCleaningStatus)) return {};
  const baseStatus = resolveIndicatorDisplayBaseRoomStatus_(data);
  if (!isNovaRoomCleaningTargetStatus_(baseStatus)) return {};
  return {
    '이전객실상태': baseStatus,
    '이전청소상태': currentCleaningStatus,
    '이전룸메이드사번': String(data && data['룸메이드사번'] || '').trim(),
    '이전보조룸메이드사번': String(data && data['보조룸메이드사번'] || '').trim()
  };
}

function indicatorLastRoomStatusHeader_() { // (객실카드 마지막 상태 보존 열명)
  return '마지막객실상태';
}

function resolveIndicatorLastRoomStatusAfterChange_(nextRoomStatus, currentData) { // (수동 상태변경 후 객실카드 표시기준 상태)
  const next = String(nextRoomStatus || '').trim().toUpperCase();
  const current = String(currentData && currentData['객실상태'] || '').trim().toUpperCase();
  const stored = String(currentData && currentData[indicatorLastRoomStatusHeader_()] || '').trim().toUpperCase();
  if (isNovaRoomCleaningTargetStatus_(next)) return next;
  if (next === 'VACANT_CLEAN') {
    // 사용자가 통합 인디게이터에서 공실로 직접 변경한 경우에는
    // 이전 재고·퇴실 상태를 보존하지 않고 실제 공실로 전환한다.
    return '';
  }
  return '';
}

function resolveIndicatorDisplayBaseRoomStatus_(data) { // (객실카드에 노출할 마지막 재고·퇴실 상태)
  const current = String(data && data['객실상태'] || '').trim().toUpperCase();
  if (isNovaRoomCleaningTargetStatus_(current)) return current;
  const stored = String(data && data[indicatorLastRoomStatusHeader_()] || '').trim().toUpperCase();
  return current === 'VACANT_CLEAN' && isNovaRoomCleaningTargetStatus_(stored) ? stored : '';
}

function resolveIndicatorLastRoomStatusForUpload_(uploadedRoomStatus, effectiveRoomStatus, previous) { // (객실현황 업로드 시 표시기준 상태 보존)
  const uploaded = String(uploadedRoomStatus || '').trim().toUpperCase();
  const effective = String(effectiveRoomStatus || '').trim().toUpperCase();
  if (isNovaRoomCleaningTargetStatus_(effective)) return effective;
  if (effective === 'VACANT_CLEAN' && isNovaRoomCleaningTargetStatus_(uploaded)) return uploaded;
  return '';
}

function resolveManualRoomStatusState_(roomStatus, currentData) { // (수동 객실상태 변경 시 청소상태 정합)
  const normalizedRoomStatus = String(roomStatus || '').trim().toUpperCase();
  const currentCleaningStatus = String(currentData['청소상태'] || '').trim();
  const activeCleaningStatuses = new Set(['ASSIGNED', 'CLEANING', 'QM_WAITING', 'QM_CHECKING', 'REWORK']);
  const resetAssignment = { '정비유형': '', '배정유형': '', '룸메이드사번': '', '보조룸메이드사번': '', 'QM사번': '' };

  if (normalizedRoomStatus === 'VACANT_CLEAN') {
    return Object.assign({ '청소상태': 'COMPLETED' }, resetAssignment);
  }
  if (normalizedRoomStatus === 'RECHECKIN') {
    return Object.assign({ '청소상태': 'COMPLETED' }, resetAssignment);
  }
  if (['CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU'].includes(normalizedRoomStatus)) {
    return { '청소상태': 'WAITING' }; // 최초배정 정보는 유지하고 실제 정비 가능 상태로 전환
  }
  if (['STAY', 'DUE_OUT'].includes(normalizedRoomStatus)) {
    return Object.assign({ '청소상태': 'NOT_REQUIRED' }, resetAssignment);
  }
  if (activeCleaningStatuses.has(currentCleaningStatus)) {
    return {}; // 재고 유형만 변경하는 경우 진행 중 배정·청소·QM 상태 유지
  }
  return Object.assign({ '청소상태': 'WAITING' }, resetAssignment);
}

function normalizeIndicatorOptions_(options, user) { // (인디케이터 조회조건 정리)
  const safe = options || {};
  return {
    businessDate: normalizeBusinessDate_(safe.businessDate),
    site: String(safe.site || user.defaultSite || '').trim()
  };
}

function getCurrentRoomsForIndicator_(businessDate, site, orders, usersByEmployeeNo) { // (현재 객실카드 데이터 조회·중복행은 최신 1건만 표시)
  const selection = getCurrentRowsForSelection_(businessDate, site);
  const pendingByRoom = {};
  (orders || []).forEach(order => {
    if (!['COMPLETED', 'UNABLE'].includes(order.statusCode)) {
      pendingByRoom[order.roomNo] = (pendingByRoom[order.roomNo] || 0) + 1;
    }
  });

  const latestByRoom = {};
  selection.items.forEach(item => {
    const data = item.data || {};
    const roomNo = String(data['객실번호'] || '').trim();
    const rowSite = String(data['사업장'] || '').trim();
    if (!roomNo) return;
    const key = `${rowSite}|${roomNo}`;
    const current = latestByRoom[key];
    if (!current || compareCurrentRoomRowsForDisplay_(item, current) > 0) latestByRoom[key] = item;
  });

  return Object.keys(latestByRoom)
    .map(key => latestByRoom[key])
    .map(item => currentRoomObject_(item.data, item.rowNumber, pendingByRoom, usersByEmployeeNo))
    .sort(compareRooms_);
}

function compareCurrentRoomRowsForDisplay_(left, right) { // (중복 현재객실현황 행 중 최신 표시행 판정)
  const leftData = left && left.data || {};
  const rightData = right && right.data || {};
  const leftVersion = Number(leftData['마지막변경버전'] || 0);
  const rightVersion = Number(rightData['마지막변경버전'] || 0);
  if (leftVersion !== rightVersion) return leftVersion - rightVersion;
  const leftUpdated = String(leftData['수정일시'] || '').trim();
  const rightUpdated = String(rightData['수정일시'] || '').trim();
  if (leftUpdated !== rightUpdated) return leftUpdated.localeCompare(rightUpdated);
  return Number(left && left.rowNumber || 0) - Number(right && right.rowNumber || 0);
}

function getCurrentRowsForSelection_(businessDate, site) { // (업무일자·사업장 구간 고속 조회·행 인덱스 캐시)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const headerMap = getHeaderMap_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { headerMap, items: [] };

  const matchedRows = getCurrentSelectionRowNumbers_(sheet, headerMap, businessDate, site);
  if (!matchedRows.length) return { headerMap, items: [] };

  const headerCount = sheet.getLastColumn();
  const groups = groupConsecutiveRows_(matchedRows);
  const items = [];

  const startRow = matchedRows[0];
  const endRow = matchedRows[matchedRows.length - 1];
  const span = endRow - startRow + 1;
  const useSingleRead = groups.length === 1 || groups.length > 4 || span <= matchedRows.length * 3;

  if (useSingleRead) {
    const values = sheet.getRange(startRow, 1, span, headerCount).getDisplayValues();
    const matchedSet = groups.length === 1 ? null : new Set(matchedRows);
    values.forEach((row, offset) => {
      const rowNumber = startRow + offset;
      if (matchedSet && !matchedSet.has(rowNumber)) return;
      items.push({ rowNumber, data: rowObjectFromValues_(row, headerMap) });
    });
    return { headerMap, items };
  }

  groups.forEach(group => {
    const values = sheet.getRange(group.start, 1, group.count, headerCount).getDisplayValues();
    values.forEach((row, offset) => {
      items.push({ rowNumber: group.start + offset, data: rowObjectFromValues_(row, headerMap) });
    });
  });
  return { headerMap, items };
}

function getCurrentSelectionRowNumbers_(sheet, headerMap, businessDate, site) { // (현재객실현황 조회행 인덱스 캐시)
  const normalizedDate = normalizeBusinessDate_(businessDate);
  const normalizedSite = String(site || '').trim();
  const dataVersion = getSyncVersion_(['ROOM'], normalizedDate, normalizedSite);
  const cacheKey = `NOVA_CURRENT_ROWS_RC62:${dataVersion}:${normalizedDate}:${normalizedSite || '*'}`;
  const cache = CacheService.getScriptCache();
  const cached = cache.get(cacheKey);
  if (cached) {
    try { return JSON.parse(cached); } catch (error) { /* 캐시 손상 시 재구성 */ }
  }

  const lastRow = sheet.getLastRow();
  const dateColumn = headerMap['업무일자'];
  const siteColumn = headerMap['사업장'];
  if (lastRow < 2 || !dateColumn || !siteColumn) return [];

  const firstColumn = Math.min(dateColumn, siteColumn);
  const columnCount = Math.abs(dateColumn - siteColumn) + 1;
  const keys = sheet.getRange(2, firstColumn, lastRow - 1, columnCount).getDisplayValues();
  const dateOffset = dateColumn - firstColumn;
  const siteOffset = siteColumn - firstColumn;
  const matchedRows = [];
  keys.forEach((row, index) => {
    if (String(row[dateOffset] || '').trim() !== normalizedDate) return;
    if (normalizedSite && String(row[siteOffset] || '').trim() !== normalizedSite) return;
    matchedRows.push(index + 2);
  });

  const serialized = JSON.stringify(matchedRows);
  if (serialized.length <= Number(NOVA.CACHE_MAX_CHARS || 90000)) {
    cache.put(cacheKey, serialized, Number(NOVA.CURRENT_INDEX_CACHE_SECONDS || 120));
  }
  return matchedRows;
}

function indicatorRoomOperationalStatusHeader_() { // (통합 인디게이터 객실 조치상태 열명)
  return '객실운영상태';
}

function normalizeIndicatorRoomOperationalStatus_(value) { // (고장·객실확인 상태 코드 정리)
  const raw = String(value || '').trim();
  const upper = raw.toUpperCase().replace(/\s+/g, '_');
  if (!raw) return '';
  if (['BROKEN', 'OUT_OF_ORDER', 'OOO', 'O.O.O', '0.0.0', '고장'].includes(upper) || raw === '고장') return 'BROKEN';
  if (['ROOM_CHECK', 'ROOMCHECK', 'CHECK_ROOM', '객실확인'].includes(upper) || raw === '객실확인') return 'ROOM_CHECK';
  return '';
}

function ensureIndicatorRoomOperationalStatusHeader_() { // (객실 조치상태 열 1회 자동 추가)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const lastColumn = Math.max(1, sheet.getLastColumn());
  const headers = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0].map(value => String(value || '').trim());
  const header = indicatorRoomOperationalStatusHeader_();
  if (headers.includes(header)) return false;
  sheet.getRange(1, lastColumn + 1).setValue(header);
  SpreadsheetApp.flush();
  clearNovaCaches_();
  return true;
}

function currentRoomObject_(data, rowNumber, pendingByRoom, usersByEmployeeNo) { // (현재객실현황 화면 객체 변환)
  const users = usersByEmployeeNo || getUserIndex_().byEmployeeNo;
  const roomNo = String(data['객실번호'] || '').trim();
  const roommaidNo = String(data['룸메이드사번'] || '').trim();
  const secondaryRoommaidNo = String(data['보조룸메이드사번'] || '').trim();
  const assignmentType = String(data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
  const qmNo = String(data['QM사번'] || '').trim();
  const previousRoommaidNo = String(data['이전룸메이드사번'] || '').trim();
  const previousSecondaryRoommaidNo = String(data['이전보조룸메이드사번'] || '').trim();
  return {
    rowNumber,
    businessDate: String(data['업무일자'] || '').trim(),
    roomNo,
    site: String(data['사업장'] || '').trim(),
    building: normalizeRoomBuilding_(data['동'], roomNo),
    floor: deriveRoomFloor_(roomNo),
    roomStatus: String(data['객실상태'] || '').trim(),
    displayBaseRoomStatus: resolveIndicatorDisplayBaseRoomStatus_(data),
    previousCycle: String(data['이전객실상태'] || '').trim() ? {
      roomStatus: String(data['이전객실상태'] || '').trim(),
      cleaningStatus: String(data['이전청소상태'] || '').trim(),
      roommaidEmployeeNo: previousRoommaidNo,
      roommaidName: users[previousRoommaidNo] ? users[previousRoommaidNo].name : '',
      secondaryRoommaidEmployeeNo: previousSecondaryRoommaidNo,
      secondaryRoommaidName: users[previousSecondaryRoommaidNo] ? users[previousSecondaryRoommaidNo].name : ''
    } : null,
    cleaningStatus: String(data['청소상태'] || '').trim(),
    cleaningType: String(data['정비유형'] || '').trim() || NOVA.CLEANING_TYPES.NORMAL,
    assignmentType,
    roommaidEmployeeNo: roommaidNo,
    roommaidName: users[roommaidNo] ? users[roommaidNo].name : '',
    secondaryRoommaidEmployeeNo: secondaryRoommaidNo,
    secondaryRoommaidName: users[secondaryRoommaidNo] ? users[secondaryRoommaidNo].name : '',
    qmEmployeeNo: qmNo,
    qmName: users[qmNo] ? users[qmNo].name : '',
    preassigned: normalizeYesNo_(data['선배정여부']) === 'Y',
    vip: normalizeYesNo_(data['VIP여부']) === 'Y',
    importantRoom: normalizeYesNo_(data['중요객실여부']) === 'Y',
    operationalStatus: normalizeIndicatorRoomOperationalStatus_(data[indicatorRoomOperationalStatusHeader_()]),
    pendingOrderCount: Number((pendingByRoom || {})[roomNo] || data['하우스맨미완료수'] || 0),
    updatedAt: String(data['수정일시'] || '').trim(),
    version: Number(data['마지막변경버전'] || 0)
  };
}

function deriveRoomFloor_(roomNo) { // (4자리 객실번호에서 층 추출)
  const digits = String(roomNo || '').replace(/\D/g, '');
  if (digits.length !== 4) return '';
  const floor = digits.charAt(1);
  return /^\d$/.test(floor) ? String(Number(floor)) : '';
}

function compareRooms_(a, b) { // (객실번호 정렬)
  const aNumber = Number(String(a.roomNo).replace(/\D/g, ''));
  const bNumber = Number(String(b.roomNo).replace(/\D/g, ''));
  if (Number.isFinite(aNumber) && Number.isFinite(bNumber) && aNumber !== bNumber) return aNumber - bNumber;
  return String(a.roomNo).localeCompare(String(b.roomNo), 'ko');
}

function findCurrentRoomRow_(sheet, businessDate, site, roomNo) { // (현재 객실 행 찾기)
  const selection = getCurrentRowsForSelection_(businessDate, site);
  const found = selection.items.find(item => String(item.data['객실번호'] || '').trim() === roomNo);
  return found ? { rowNumber: found.rowNumber, data: found.data } : null;
}

function findCurrentRoomRowFast_(sheet, businessDate, site, roomNo, preferredRowNumber) { // (객실카드 행번호 우선 단건 조회)
  const rowNumber = Math.floor(Number(preferredRowNumber || 0));
  const normalizedDate = normalizeBusinessDate_(businessDate);
  const normalizedSite = String(site || '').trim();
  if (rowNumber >= 2 && rowNumber <= sheet.getLastRow()) {
    const headerMap = getHeaderMap_(sheet);
    const values = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
    const data = rowObjectFromValues_(values, headerMap);
    const sameDate = String(data['업무일자'] || '').trim() === normalizedDate;
    const sameSite = !normalizedSite || String(data['사업장'] || '').trim() === normalizedSite;
    const sameRoom = String(data['객실번호'] || '').trim() === String(roomNo || '').trim();
    if (sameDate && sameSite && sameRoom) return { rowNumber, data };
  }
  return findCurrentRoomRow_(sheet, normalizedDate, normalizedSite, roomNo);
}

function getSiteList_() { // (사업장 목록 조회)
  const cache = CacheService.getScriptCache();
  const cached = cache.get('NOVA_SITE_LIST_V1');
  if (cached) return JSON.parse(cached);
  const sites = new Set(getCodes_('사업장').map(item => String(item.label || '').trim()).filter(Boolean));
  [NOVA.SHEETS.ROOMS, NOVA.SHEETS.CURRENT].forEach(name => {
    const sheet = getSpreadsheet_().getSheetByName(name);
    if (!sheet || sheet.getLastRow() < 2) return;
    const headerMap = getHeaderMap_(sheet);
    const siteColumn = headerMap['사업장'];
    if (!siteColumn) return;
    sheet.getRange(2, siteColumn, sheet.getLastRow() - 1, 1).getDisplayValues()
      .forEach(row => {
        const site = String(row[0] || '').trim();
        if (site) sites.add(site);
      });
  });
  const result = Array.from(sites).sort((a, b) => a.localeCompare(b, 'ko'));
  cache.put('NOVA_SITE_LIST_V1', JSON.stringify(result), NOVA.CACHE_SECONDS);
  return result;
}

function publicStaffFromIndex_(activeUsers, roles) { // (이미 조회한 사용자 인덱스로 직원 선택목록 생성)
  const allowed = new Set((roles || []).map(role => String(role || '').toUpperCase()));
  return (activeUsers || [])
    .filter(user => allowed.has(String(user.role || '').toUpperCase()))
    .map(user => ({
      employeeNo: user.employeeNo,
      name: user.name,
      job: user.job,
      role: user.role,
      defaultSite: user.defaultSite,
      defaultBuildings: user.defaultBuildings
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'ko'));
}

function requireRole_(token, allowedRoles) { // (API 권한 검증)
  const auth = verifyNovaToken(token);
  if (!auth.ok) throw new Error('로그인이 필요합니다.');
  const allowed = new Set((allowedRoles || []).map(role => String(role).toUpperCase()));
  if (!allowed.has(String(auth.user.role || '').toUpperCase())) {
    throw new Error('해당 기능을 사용할 권한이 없습니다.');
  }
  return auth.user;
}

function appendUnifiedHistory_(payload) { // (업무이력 통합 기록)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const now = nowText_();
  const recordId = payload.recordId || `${payload.recordType}-${Utilities.getUuid()}`;
  const row = createRowByHeaders_(sheet, {
    '기록ID': recordId,
    '기록구분': payload.recordType,
    '업무일자': payload.businessDate,
    '사업장': payload.site,
    '객실번호': payload.roomNo,
    '대상사번': payload.targetEmployeeNo || '',
    '처리상태': payload.status || '',
    '세부내용JSON': JSON.stringify(payload.detail || {}),
    '등록사번': payload.registeredBy || '',
    '등록일시': payload.registeredAt || now,
    '수정일시': now,
    '접수일시': payload.acceptedAt || '',
    '처리시작일시': payload.startedAt || '',
    '완료일시': payload.completedAt || '',
    '변경버전': payload.version || getDataVersion_(),
    '삭제여부': 'N'
  });
  const rowNumber = sheet.getLastRow() + 1;
  ensureSheetRowCapacity_(sheet, rowNumber);
  sheet.getRange(rowNumber, 1, 1, row.length).setValues([row]);
  return recordId;
}
