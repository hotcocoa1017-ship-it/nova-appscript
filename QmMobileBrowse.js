/**
 * QM 모바일 보조 조회
 * - 기존 QM 배정/점검/완료 권한과 getMobileSnapshot 구조는 변경하지 않습니다.
 * - 추가 탭을 실제로 열 때만 공실 또는 당일 청소완료 객실을 조회합니다.
 * - 조회 전용이며 객실 상태/배정/점검 권한을 변경하지 않습니다.
 * - 성능보호: 업무이력 전체 재조회 없이 현재 업무일자 객실상태만으로 판별합니다.
 */
function getQmMobileBrowseRooms(token, options) { // (QM 추가탭 지연조회 · 업무이력 무스캔)
  return measureResponse_('getQmMobileBrowseRooms', () => {
    const user = requireRole_(token, ['QM']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2
    const view = String(safe.view || '').trim().toUpperCase();
    if (!['CLEANED', 'VACANT'].includes(view)) throw new Error('지원하지 않는 QM 객실 조회입니다.');

    const cacheKey = `NOVA_QM_BROWSE_V2:${getDataVersion_()}:${businessDate}:${site || 'ALL'}:${view}`;
    const cached = getCachedJson_(cacheKey);
    if (cached) return Object.assign({}, cached, { serverTime: nowText_() });

    const userIndex = getUserIndex_();
    const rooms = getCurrentRoomsForMobile_(businessDate, site, userIndex.byEmployeeNo);
    let selectedRooms = [];

    if (view === 'VACANT') {
      selectedRooms = rooms.filter(room => String(room.roomStatus || '').trim().toUpperCase() === 'VACANT_CLEAN');
    } else {
      // 현재객실현황은 선택한 업무일자 자체의 데이터입니다.
      // 실제 당일 정비를 거친 객실만 잡기 위해 완료계열 상태 + 룸메이드 배정 존재를 함께 확인합니다.
      // 업로드 당시부터 공실인 객실은 룸메이드 배정이 없으므로 제외되고,
      // 청소초기화/재정비 객실은 완료계열 상태가 아니므로 자동 제외됩니다.
      const completedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
      selectedRooms = rooms.filter(room => {
        const cleaningStatus = String(room.cleaningStatus || '').trim().toUpperCase();
        const roomStatus = String(room.roomStatus || '').trim().toUpperCase();
        const hasRoommaid = Boolean(
          String(room.roommaidEmployeeNo || '').trim()
          || String(room.secondaryRoommaidEmployeeNo || '').trim()
        );
        return completedStatuses.has(cleaningStatus)
          && hasRoommaid
          && roomStatus !== 'VACANT_CLEAN';
      });
    }

    selectedRooms.sort(compareRooms_);
    const result = {
      ok: true,
      view,
      selection: { businessDate, site },
      rooms: selectedRooms.map(qmMobileBrowseRoomDto_),
      summary: { count: selectedRooms.length },
      serverTime: nowText_()
    };
    putCachedJson_(cacheKey, result, Math.max(6, Number(NOVA.DELTA_CACHE_SECONDS || 12)));
    return result;
  });
}

function qmMobileBrowseRoomDto_(room) { // (QM 조회전용 최소 객실정보)
  const source = room || {};
  return {
    rowNumber: Number(source.rowNumber || 0),
    businessDate: String(source.businessDate || ''),
    site: String(source.site || ''),
    roomNo: String(source.roomNo || ''),
    building: String(source.building || ''),
    floor: String(source.floor || ''),
    roomStatus: String(source.roomStatus || ''),
    cleaningStatus: String(source.cleaningStatus || ''),
    cleaningType: String(source.cleaningType || ''),
    assignmentType: String(source.assignmentType || ''),
    roommaidEmployeeNo: String(source.roommaidEmployeeNo || ''),
    roommaidName: String(source.roommaidName || ''),
    secondaryRoommaidEmployeeNo: String(source.secondaryRoommaidEmployeeNo || ''),
    secondaryRoommaidName: String(source.secondaryRoommaidName || ''),
    qmEmployeeNo: String(source.qmEmployeeNo || ''),
    qmName: String(source.qmName || ''),
    preassigned: Boolean(source.preassigned),
    vip: Boolean(source.vip),
    importantRoom: Boolean(source.importantRoom),
    operationalStatus: String(source.operationalStatus || ''),
    updatedAt: String(source.updatedAt || ''),
    version: Number(source.version || 0)
  };
}

function startQmMobileBrowseInspection(token, payload) { // (QM 추가탭 미배정 객실 본인확보 + 기존 체크리스트 즉시 시작)
  return measureResponse_('startQmMobileBrowseInspection', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2
    const roomNo = String(safe.roomNo || '').trim();
    const view = String(safe.view || '').trim().toUpperCase();
    if (!site || !roomNo) throw new Error('점검할 사업장과 객실번호가 필요합니다.');
    if (!['CLEANED', 'VACANT'].includes(view)) throw new Error('지원하지 않는 QM 점검경로입니다.');

    let startVersion = 0;
    let previousCleaningStatus = '';
    let responseSite = site;
    let rowNumber = Number(safe.rowNumber || 0);
    let alreadyChecking = false;
    const lock = acquireWriteLock_(5000);
    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const rowInfo = findCurrentRoomRowForMobileUpdate_(sheet, businessDate, site, roomNo, rowNumber);
      if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
      rowNumber = rowInfo.rowNumber;
      responseSite = String(rowInfo.data['사업장'] || site).trim();

      const roomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
      const cleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
      const roommaidNo = String(rowInfo.data['룸메이드사번'] || '').trim();
      const secondaryRoommaidNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
      const currentQmNo = String(rowInfo.data['QM사번'] || '').trim();
      const startableStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING']);
      const hasRoommaid = Boolean(roommaidNo || secondaryRoommaidNo);

      if (view === 'VACANT') {
        if (roomStatus !== 'VACANT_CLEAN' || !startableStatuses.has(cleaningStatus)) {
          throw new Error('현재 공실 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.');
        }
      } else if (roomStatus === 'VACANT_CLEAN' || !hasRoommaid || !startableStatuses.has(cleaningStatus)) {
        throw new Error('현재 당일 청소완료 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.');
      }

      if (currentQmNo && currentQmNo !== user.employeeNo) {
        throw new Error('다른 QM에게 이미 배정되었거나 점검 중인 객실입니다.');
      }

      previousCleaningStatus = cleaningStatus;
      if (currentQmNo === user.employeeNo && cleaningStatus === 'QM_CHECKING') {
        alreadyChecking = true;
        startVersion = Number(rowInfo.data['마지막변경버전'] || 0);
      } else {
        startVersion = reserveDataVersion_({ lockHeld: true });
        const startedAt = nowText_();
        updateRowByHeaders_(sheet, rowInfo.rowNumber, {
          'QM사번': user.employeeNo,
          '청소상태': 'QM_CHECKING',
          '마지막변경버전': startVersion,
          '수정일시': startedAt
        });
        SpreadsheetApp.flush();
        publishDataVersion_(startVersion, {
          domains: ['ROOM'], businessDate, site: responseSite, lockHeld: true
        });
        appendUnifiedHistory_({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate,
          site: responseSite,
          roomNo,
          targetEmployeeNo: user.employeeNo,
          status: 'QM_START',
          registeredBy: user.employeeNo,
          startedAt,
          version: startVersion,
          detail: {
            action: 'START',
            role: 'QM',
            source: 'QM_BROWSE_SELF_START',
            browseView: view,
            beforeCleaningStatus: previousCleaningStatus,
            cleaningStatus: 'QM_CHECKING',
            primaryEmployeeNo: roommaidNo,
            secondaryEmployeeNo: secondaryRoommaidNo,
            vacantSpotCheck: view === 'VACANT'
          }
        });
      }
    } finally {
      try { lock.releaseLock(); } catch (ignore) {}
    }

    let dbRoom = null;
    if (typeof novaRealtimeFinalEnabled_ === 'function'
        && novaRealtimeFinalEnabled_()
        && typeof syncNovaRealtimeRoomForAction === 'function') {
      syncNovaRealtimeRoomForAction(token, {
        businessDate,
        site: responseSite,
        roomNo,
        action: 'QM_START'
      });
      if (typeof novaRealtimeFetchCurrentRoomForQmMirror_ === 'function') {
        dbRoom = novaRealtimeFetchCurrentRoomForQmMirror_(token, businessDate, responseSite, roomNo);
      }
    }

    const started = startQmInspection(token, {
      businessDate,
      site: responseSite,
      roomNo,
      realtimeStarted: true,
      realtimeVersion: startVersion
    });
    if (!started || !started.ok) {
      throw new Error(started && started.message ? started.message : 'QM 체크리스트를 시작하지 못했습니다.');
    }

    if (dbRoom) {
      started.version = Number(dbRoom.version || started.version || 0);
      started.room = Object.assign({}, started.room || {}, dbRoom, {
        rowNumber,
        businessDate,
        site: responseSite,
        roomNo,
        qmEmployeeNo: user.employeeNo,
        cleaningStatus: 'QM_CHECKING',
        version: Number(dbRoom.version || 0)
      });
    } else if (started.room) {
      started.room.rowNumber = rowNumber;
    }

    return Object.assign({}, started, {
      browseView: view,
      browseSelfStarted: true,
      alreadyChecking
    });
  });
}
