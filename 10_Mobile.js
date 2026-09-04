/**
 * NOVA 직원 스마트폰 전용 화면
 * 기존 사용자계정·현재객실현황·업무이력 시트만 사용합니다.
 */
function getMobileSnapshot(token, options) { // (직무별 모바일 화면 데이터 조회)
  return measureResponse_('getMobileSnapshot', () => buildMobileSnapshot_(token, options));
}

function getMobileDelta(token, options) { // (모바일 변경분 확인)
  return measureResponse_('getMobileDelta', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const role = String(auth.user.role || '').toUpperCase();
    const request = normalizeMobileOptions_(options, auth.user);
    const currentVersion = getMobileSyncVersion_(role, request);
    const sinceVersion = Number(options && options.sinceVersion || 0);
    if (currentVersion === sinceVersion) {
      return { ok: true, changed: false, version: currentVersion, serverTime: nowText_() };
    }
    const deltaCacheKey = buildDeltaCacheKey_('MOBILE', [auth.user.employeeNo, role, request.businessDate, request.site, currentVersion]);
    const cachedDelta = getCachedJson_(deltaCacheKey);
    if (cachedDelta) return Object.assign({}, cachedDelta, { serverTime: nowText_() });
    const response = Object.assign(buildMobileSnapshot_(token, options), { changed: true, version: currentVersion });
    putCachedJson_(deltaCacheKey, response, NOVA.DELTA_CACHE_SECONDS);
    return response;
  });
}

function buildMobileSnapshot_(token, options) { // (직무별 모바일 스냅샷 구성)
  const auth = verifyNovaToken(token);
  if (!auth.ok) throw new Error('로그인이 필요합니다.');
  const user = auth.user;
  const role = String(user.role || '').toUpperCase();
  if (!['ROOMMAID', 'QM', 'HOUSEMAN', 'PUBLIC'].includes(role)) {
    throw new Error('직원 모바일 화면을 사용할 권한이 없습니다.');
  }

  const request = normalizeMobileOptions_(options, user);
  const codeIndex = getCodeIndex_();
  const userIndex = getUserIndex_();
  const response = {
    ok: true,
    role,
    selection: request,
    version: getMobileSyncVersion_(role, request),
    sites: user.siteScopeLocked && request.site ? [request.site] : getSiteList_(), // SITE_SCOPE_INDICATOR_CLOSE_V2
    codes: {
      roomStatuses: codeIndex['객실상태'] || [],
      cleaningStatuses: codeIndex['청소상태'] || [],
      cleaningTypes: codeIndex['정비유형'] || [],
      assignmentTypes: codeIndex['룸메이드배정유형'] || [],
      orderStatuses: codeIndex['하우스맨상태'] || [],
      orderParts: codeIndex['하우스맨파트'] || []
    },
    serverTime: nowText_()
  };

  if (role === 'HOUSEMAN') {
    const statusMap = {};
    (codeIndex['하우스맨상태'] || []).forEach(code => { statusMap[code.code] = code.label; });
    const allOrders = getHousemanOrdersForDate_(request.businessDate, request.site, userIndex.byEmployeeNo, statusMap);
    response.orders = allOrders
      .filter(order => isHousemanOrderVisibleForUser_(order, user, request))
      .sort(compareMobileOrders_);
    response.shift = buildHousemanShiftContext_(request.businessDate, request.site, user.employeeNo);
    response.summary = buildMobileOrderSummary_(response.orders, user.employeeNo);
    queueHousemanHandoverLoginDigest_(user, request, response.orders, response.shift);
    return response;
  }

  const rooms = getCurrentRoomsForMobile_(request.businessDate, request.site, userIndex.byEmployeeNo);
  if (role === 'ROOMMAID') {
    response.rooms = rooms
      .filter(room => room.roommaidEmployeeNo === user.employeeNo || room.secondaryRoommaidEmployeeNo === user.employeeNo)
      .sort(compareMobileCleaningRooms_);
    response.summary = buildRoommaidSummary_(response.rooms);
  } else if (role === 'QM') {
    response.rooms = rooms
      .filter(room => room.qmEmployeeNo === user.employeeNo)
      .sort(compareMobileQmRooms_);
    response.summary = buildQmSummary_(response.rooms);
    response.qmChecklist = getQmChecklistForMobile_();
  } else {
    const delayRule = getDepartureDelayRule_(request.businessDate, new Date());
    response.rooms = rooms
      .map(room => Object.assign({}, room, {
        departureDelayed: Boolean(delayRule.reached && room.roomStatus === 'DUE_OUT')
      }))
      .sort(compareRooms_);
    response.departureDelayRule = delayRule;
    response.summary = buildPublicSummary_(response.rooms);
  }
  return response;
}

function novaMobileRealtimeEnabled_() { // (서버측 Realtime 활성여부 확인)
  const props = PropertiesService.getScriptProperties();
  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() === 'Y';
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  return Boolean(enabled && apiBase);
}

function novaMobileRealtimeActionFetch_(token, roomNo, payload) { // (Apps Script 서버에서 Cloud Run 객실작업 호출)
  const props = PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  if (!apiBase) throw new Error('Realtime API 주소가 설정되지 않았습니다.');

  const response = UrlFetchApp.fetch(
    `${apiBase}/v1/rooms/${encodeURIComponent(String(roomNo || '').trim())}/action`,
    {
      method: 'post',
      contentType: 'application/json; charset=utf-8',
      payload: JSON.stringify(payload || {}),
      headers: {
        Authorization: `Bearer ${String(token || '').trim()}`,
        'X-Request-Id': String(payload && payload.requestId || '').trim()
      },
      muteHttpExceptions: true,
      followRedirects: true
    }
  );

  const status = response.getResponseCode();
  const text = response.getContentText();
  let result = {};
  try {
    result = JSON.parse(text || '{}');
  } catch (error) {
    result = { ok: false, code: 'INVALID_RESPONSE', message: text || 'Realtime 응답을 해석하지 못했습니다.' };
  }
  result.__httpStatus = status;
  return result;
}

function novaMobileRealtimeEnrichRoom_(resultRoom, businessDate, site, roomNo, preferredRowNumber) { // (Realtime 응답에 기존 모바일 표시정보 보완)
  const realtimeRoom = resultRoom || {};
  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRowForMobileUpdate_(sheet, businessDate, site, roomNo, preferredRowNumber);
    if (!rowInfo) return realtimeRoom;
    const base = currentRoomObject_(rowInfo.data, rowInfo.rowNumber, {}, getUserIndex_().byEmployeeNo);
    return Object.assign({}, base, realtimeRoom, {
      rowNumber: rowInfo.rowNumber,
      businessDate: String(realtimeRoom.businessDate || base.businessDate || businessDate),
      site: String(realtimeRoom.site || base.site || site),
      roomNo: String(realtimeRoom.roomNo || base.roomNo || roomNo),
      version: Number(realtimeRoom.version || 0),
      updatedAt: String(realtimeRoom.updatedAt || base.updatedAt || '')
    });
  } catch (error) {
    return realtimeRoom;
  }
}

function updateMobileRoomOperationRealtime_(token, safe, user) { // (초기화 지연 시에도 ROOMMAID 작업을 Cloud Run으로 강제 라우팅)
  const businessDate = normalizeBusinessDate_(safe.businessDate);
  const site = resolveUserSessionSite_(user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2
  const roomNo = String(safe.roomNo || '').trim();
  const rawAction = String(safe.action || '').trim().toUpperCase();
  const action = rawAction === 'START' ? 'CLEANING_START'
    : rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'
    : rawAction;

  if (!roomNo) throw new Error('객실번호가 없습니다.');
  if (!['CLEANING_START', 'CLEANING_COMPLETE'].includes(action)) {
    throw new Error('지원하지 않는 룸메이드 작업입니다.');
  }

  let qmEmployeeNo = '';
  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRowForMobileUpdate_(sheet, businessDate, site, roomNo, safe.rowNumber);
    qmEmployeeNo = String(rowInfo && rowInfo.data && rowInfo.data['QM사번'] || '').trim();
  } catch (error) {}

  const requestId = String(safe.requestId || '').trim() || `NOVA-GAS-${Date.now()}-${Utilities.getUuid()}`;
  const apiPayload = {
    businessDate,
    site,
    action,
    requestId,
    qmEmployeeNo,
    // Sheet의 마지막변경버전과 PostgreSQL version은 서로 다른 버전 체계입니다.
    // 서버측 안전경로에서는 DB row-lock + 상태검증을 사용하므로 Sheet version을 전달하지 않습니다.
    expectedVersion: 0
  };

  let result = novaMobileRealtimeActionFetch_(token, roomNo, apiPayload);

  // 신규 업무일자 미생성 또는 최근 배정정보가 아직 DB에 반영되지 않은 경우
  // 해당 객실만 즉시 동기화한 뒤 같은 requestId로 1회 재시도합니다.
  if (!result.ok && ['ROOM_NOT_FOUND', 'FORBIDDEN', 'INVALID_STATE'].includes(String(result.code || '').trim().toUpperCase())) {
    if (typeof syncNovaRealtimeRoomForAction !== 'function') {
      throw new Error(result.message || 'Realtime 객실 동기화 기능을 찾을 수 없습니다.');
    }
    syncNovaRealtimeRoomForAction(token, {
      businessDate,
      site,
      roomNo,
      action: rawAction
    });
    result = novaMobileRealtimeActionFetch_(token, roomNo, apiPayload);
  }

  if (!result.ok) {
    const message = result.message || result.code || `Realtime API 오류 (${result.__httpStatus || '-'})`;
    throw new Error(message);
  }

  result.room = novaMobileRealtimeEnrichRoom_(result.room, businessDate, site, roomNo, safe.rowNumber);
  result.version = Number(result.version || result.room && result.room.version || 0);
  result.message = result.message || (action === 'CLEANING_START' ? '청소를 시작했습니다.' : '청소완료로 처리했습니다.');
  delete result.__httpStatus;
  return result;
}

function updateMobileRoomOperation(token, payload) { // (룸메이드·QM 모바일 상태 처리)
  return measureResponse_('updateMobileRoomOperation', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const user = auth.user;
    const role = String(user.role || '').toUpperCase();
    if (!['ROOMMAID', 'QM'].includes(role)) throw new Error('객실 작업 권한이 없습니다.');

    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2
    const roomNo = String(safe.roomNo || '').trim();
    const action = String(safe.action || '').trim().toUpperCase();
    if (!roomNo) throw new Error('객실번호가 없습니다.');

    // Realtime=Y인 동안 ROOMMAID의 START/COMPLETE가 브라우저 초기화 지연으로
    // legacy 경로에 들어와도 Sheets에 쓰지 않고 Cloud Run/PostgreSQL로 강제 전달합니다.
    if (role === 'ROOMMAID' && ['START', 'COMPLETE'].includes(action) && novaMobileRealtimeEnabled_()) {
      return updateMobileRoomOperationRealtime_(token, safe, user);
    }

    const writeLock = acquireWriteLock_();
    try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRowForMobileUpdate_(sheet, businessDate, site, roomNo, safe.rowNumber);
    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
    // QM은 아래의 본인배정 검증과 작업상태 검증을 원본으로 사용한다.
    // Sheet 전체버전은 Realtime 미러 등 독립 변경에도 증가하므로 QM 작업에는 직접 충돌키로 쓰지 않는다.
    if (role !== 'QM') {
      assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);
    }

    const roommaidNo = String(rowInfo.data['룸메이드사번'] || '').trim();
    const secondaryRoommaidNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
    const assignmentType = String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
    const qmNo = String(rowInfo.data['QM사번'] || '').trim();
    const cleaningType = String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
    if (role === 'ROOMMAID' && ![roommaidNo, secondaryRoommaidNo].includes(user.employeeNo)) throw new Error('본인에게 배정된 객실만 처리할 수 있습니다.');
    if (role === 'QM' && qmNo !== user.employeeNo) throw new Error('본인에게 배정된 객실만 처리할 수 있습니다.');

    const updates = { '수정일시': nowText_() };
    let recordType = NOVA.RECORD_TYPES.CLEANING;
    if (role === 'ROOMMAID') {
      if (action === 'START') {
        updates['청소상태'] = 'CLEANING';
      } else if (action === 'COMPLETE') {
        updates['청소상태'] = qmNo ? 'QM_WAITING' : 'COMPLETED';
        // 룸메이드 완료 시 재고·퇴실·R/C·H/U 객실상태를 공실로 변경하지 않는다.
      } else {
        throw new Error('지원하지 않는 룸메이드 작업입니다.');
      }
    } else {
      recordType = NOVA.RECORD_TYPES.QM;
      if (action === 'START') {
        updates['청소상태'] = 'QM_CHECKING';
      } else if (action === 'COMPLETE') {
        throw new Error('QM 점검완료는 체크리스트 작성 후 처리하세요.');
      } else if (action === 'REWORK') {
        const reason = String(safe.reason || '').trim();
        if (!reason) throw new Error('재정비 사유를 입력하세요.');
        ensureIndicatorRoomOperationalStatusHeader_();
        updates[indicatorRoomOperationalStatusHeader_()] = 'REWORK'; // QM_REWORK_OPERATIONAL_STATUS_V1
        updates.__reason = reason;
      } else {
        throw new Error('지원하지 않는 QM 작업입니다.');
      }
    }

    const version = reserveDataVersion_({ lockHeld: true });
    updates['마지막변경버전'] = version;
    const reason = updates.__reason || '';
    delete updates.__reason;
    updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
    publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });

    appendUnifiedHistory_({
      recordType,
      businessDate,
      site: rowInfo.data['사업장'],
      roomNo,
      targetEmployeeNo: user.employeeNo,
      status: `${role}_${action}`,
      detail: {
        action,
        role,
        reason,
        previousOperationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
        operationalStatus: role === 'QM' && action === 'REWORK'
          ? 'REWORK'
          : normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
        beforeCleaningStatus: rowInfo.data['청소상태'],
        previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
        sourceRoomStatus: role === 'ROOMMAID' && action === 'COMPLETE'
          ? String(rowInfo.data['객실상태'] || '').trim().toUpperCase()
          : '',
        roomStatus: updates['객실상태'] || rowInfo.data['객실상태'],
        cleaningStatus: updates['청소상태'] || rowInfo.data['청소상태'],
        cleaningType,
        assignmentType,
        primaryEmployeeNo: roommaidNo,
        secondaryEmployeeNo: secondaryRoommaidNo,
        creditUnit: getRoommaidCleaningCreditUnit_(cleaningType)
      },
      registeredBy: user.employeeNo,
      version
    });

    const refreshed = Object.assign({}, rowInfo.data, updates);
    const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
    if (role === 'ROOMMAID' && action === 'COMPLETE' && qmNo && usersByEmployeeNo[qmNo]) {
      queueQmReadyTelegram_({
        businessDate, site: String(refreshed['사업장'] || site).trim(), roomNo,
        targetUser: usersByEmployeeNo[qmNo],
        preassigned: normalizeYesNo_(refreshed['선배정여부']) === 'Y',
        vip: normalizeYesNo_(refreshed['VIP여부']) === 'Y',
        importantRoom: normalizeYesNo_(refreshed['중요객실여부']) === 'Y',
        registeredBy: user.employeeNo, version
      });
    }
    if (role === 'QM' && action === 'REWORK') {
      [roommaidNo, secondaryRoommaidNo].filter(Boolean).forEach(employeeNo => {
        if (!usersByEmployeeNo[employeeNo]) return;
        queueRoommaidReworkTelegram_({
          businessDate, site: String(refreshed['사업장'] || site).trim(), roomNo,
          targetUser: usersByEmployeeNo[employeeNo], reason,
          preassigned: normalizeYesNo_(refreshed['선배정여부']) === 'Y',
          vip: normalizeYesNo_(refreshed['VIP여부']) === 'Y',
          importantRoom: normalizeYesNo_(refreshed['중요객실여부']) === 'Y',
          registeredBy: user.employeeNo, version
        });
      });
    }
    return {
      ok: true,
      version,
      room: currentRoomObject_(refreshed, rowInfo.rowNumber, {}, usersByEmployeeNo),
      message: mobileActionMessage_(role, action)
    };
     } finally {
      writeLock.releaseLock();
    }
  });
}

function findCurrentRoomRowForMobileUpdate_(sheet, businessDate, site, roomNo, preferredRowNumber) { // (객실 행번호 우선 단건 조회·불일치 시 기존 조회)
  const lastRow = sheet.getLastRow();
  const directRowNumber = Number(preferredRowNumber || 0);
  if (Number.isInteger(directRowNumber) && directRowNumber >= 2 && directRowNumber <= lastRow) {
    const headerMap = getHeaderMap_(sheet);
    const row = sheet.getRange(directRowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
    const data = rowObjectFromValues_(row, headerMap);
    const rowBusinessDate = String(data['업무일자'] || '').trim();
    const rowSite = String(data['사업장'] || '').trim();
    const rowRoomNo = String(data['객실번호'] || '').trim();
    if (rowRoomNo === roomNo && rowBusinessDate === businessDate && (!site || rowSite === site)) {
      return { rowNumber: directRowNumber, data };
    }
  }
  return findCurrentRoomRow_(sheet, businessDate, site, roomNo);
}

function getMobilePublicHousemanAutoAssignment(token, payload) { // (객실퍼블릭 습득물 요청 담당동 자동배정) // PUBLIC_HOUSEMAN_REQUEST_V1
  return measureResponse_('getMobilePublicHousemanAutoAssignment', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const user = auth.user;
    if (String(user.role || '').trim().toUpperCase() !== 'PUBLIC') throw new Error('객실퍼블릭 계정만 사용할 수 있습니다.');
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site);
    const roomNo = String(safe.roomNo || '').trim();
    if (!businessDate || !site || !roomNo) throw new Error('자동배정 확인에 업무일자·사업장·객실번호가 필요합니다.');
    const assignment = resolveHousemanPublicFastAssignee_(businessDate, site, roomNo); // PUBLIC_HOUSEMAN_REQUEST_FAST_V2
    if (!assignment || !String(assignment.employeeNo || '').trim()) throw new Error('해당 동에 자동배정 가능한 하우스맨이 없습니다.');
    return { ok: true, businessDate, site, roomNo, assignment };
  });
}

function createMobileHousemanRequest(token, payload) { // (룸메이드·QM·객실퍼블릭 객실 하우스맨 요청) // PUBLIC_HOUSEMAN_REQUEST_V1
  return measureResponse_('createMobileHousemanRequest', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const user = auth.user;
    const role = String(user.role || '').toUpperCase();
    if (!['ROOMMAID', 'QM', 'PUBLIC'].includes(role)) throw new Error('하우스맨 요청 권한이 없습니다.'); // PUBLIC_HOUSEMAN_REQUEST_V1

    const rawPayload = prepareNovaHousemanOrderPayloadForStorage_(payload || {}); // NOVA_I18N_V1 · 모바일 오더 저장 전 한국어 변환
    const safe = normalizeHousemanPayload_(rawPayload);
    safe.site = resolveUserSessionSite_(user, safe.site); // SITE_SCOPE_INDICATOR_CLOSE_V2
    if (!safe.roomNo) throw new Error('객실번호가 없습니다.');
    if (!safe.part) throw new Error('파트를 선택하세요.');
    if (role === 'PUBLIC' && !['습득물', '기타'].includes(String(safe.part || '').trim())) throw new Error('객실퍼블릭 요청 파트는 습득물 또는 기타만 선택할 수 있습니다.'); // PUBLIC_HOUSEMAN_REQUEST_V1
    if (!safe.items.length) throw new Error('요청 품목을 입력하세요.');

    const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRow_(currentSheet, safe.businessDate, safe.site, safe.roomNo);
    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
    const assignedNos = role === 'ROOMMAID'
      ? [String(rowInfo.data['룸메이드사번'] || '').trim(), String(rowInfo.data['보조룸메이드사번'] || '').trim()].filter(Boolean)
      : role === 'QM'
        ? [String(rowInfo.data['QM사번'] || '').trim()].filter(Boolean)
        : [];
    if (role !== 'PUBLIC' && !assignedNos.includes(user.employeeNo)) throw new Error('본인에게 배정된 객실에서만 요청할 수 있습니다.');

    let publicAssignment = null; // PUBLIC_HOUSEMAN_REQUEST_V1
    if (role === 'PUBLIC') {
      const supplied = rawPayload.realtimeAssignmentSnapshot && typeof rawPayload.realtimeAssignmentSnapshot === 'object'
        ? rawPayload.realtimeAssignmentSnapshot : null;
      publicAssignment = supplied && String(supplied.employeeNo || '').trim()
        ? normalizeRealtimeHousemanAssignmentSnapshot_(safe.businessDate, safe.site, safe.roomNo, supplied)
        : resolveHousemanPublicFastAssignee_(safe.businessDate, safe.site, safe.roomNo); // PUBLIC_HOUSEMAN_REQUEST_FAST_V2
      if (!publicAssignment || !String(publicAssignment.employeeNo || '').trim()) throw new Error('해당 동에 자동배정 가능한 하우스맨이 없습니다.');
      safe.assignedEmployeeNo = String(publicAssignment.employeeNo || '').trim();
    }

    const writeLock = acquireWriteLock_();
    let order;
    let version;
    try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);

    // Realtime 선등록 후 브라우저 재시도에도 같은 오더를 한 번만 Sheet에 미러한다.
    if (safe.realtimeOrderId) {
      const existing = findHousemanOrderRow_(sheet, safe.realtimeOrderId, 0);
      if (existing) {
        const existingOrder = housemanOrderObject_(existing.data, existing.rowNumber);
        return {
          ok: true,
          version: Number(existingOrder.version || 0),
          order: existingOrder,
          mirrorDuplicate: true,
          message: '하우스맨 요청을 등록했습니다.'
        };
      }
    }

    version = reserveDataVersion_({ lockHeld: true });
    const orderId = safe.realtimeOrderId || `HO-${safe.businessDate.replaceAll('-', '')}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;
    const now = nowText_();
    const itemSummary = safe.items.map(item => item.quantity > 1 ? `${item.name}×${item.quantity}` : item.name).join(', ');
    const totalQuantity = safe.items.reduce((sum, item) => sum + item.quantity, 0);
    const detail = {
      items: safe.items,
      sourceLanguage: safe.sourceLanguage || 'ko', // NOVA_I18N_V1 · 원문/한국어 번역 메타
      translation: safe.translation || null,
      requester: user.name,
      requestSource: role,
      createdFrom: 'MOBILE',
      assignmentMode: role === 'PUBLIC' ? 'AUTO' : 'UNASSIGNED', // PUBLIC_HOUSEMAN_REQUEST_V1
      autoAssigned: Boolean(publicAssignment),
      assignedBuilding: publicAssignment ? publicAssignment.building : normalizeRoomBuilding_('', safe.roomNo),
      assignedShiftCode: publicAssignment ? publicAssignment.currentShift : '',
      assignedShiftCodes: publicAssignment ? publicAssignment.activeShiftCodes : [],
      routeCandidateEmployeeNos: publicAssignment ? publicAssignment.employeeNos : [],
      routeCandidateNames: publicAssignment ? publicAssignment.names : [],
      routeLocked: !publicAssignment
    };
    const row = createRowByHeaders_(sheet, {
      '기록ID': orderId,
      '기록구분': NOVA.RECORD_TYPES.HOUSEMAN_ORDER,
      '업무일자': safe.businessDate,
      '사업장': String(rowInfo.data['사업장'] || safe.site).trim(),
      '객실번호': safe.roomNo,
      '대상사번': role === 'PUBLIC' ? safe.assignedEmployeeNo : '',
      '처리상태': role === 'PUBLIC' && safe.assignedEmployeeNo ? 'ASSIGNED' : 'REGISTERED', // PUBLIC_HOUSEMAN_REQUEST_V1
      '세부내용JSON': JSON.stringify(detail),
      '등록사번': user.employeeNo,
      '등록일시': now,
      '수정일시': now,
      '파트': safe.part,
      '품목': itemSummary,
      '수량': totalQuantity,
      '추가내용': safe.note,
      '요청자': user.name,
      '배정사번': role === 'PUBLIC' ? safe.assignedEmployeeNo : '', // PUBLIC_HOUSEMAN_REQUEST_V1
      '중요여부': safe.important ? 'Y' : 'N',
      '인수인계여부': 'N',
      '변경버전': version,
      '삭제여부': 'N'
    });
    const rowNumber = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, rowNumber);
    sheet.getRange(rowNumber, 1, 1, row.length).setValues([row]);
    SpreadsheetApp.flush();
    publishDataVersion_(version, { domains: ['ORDER'], businessDate: safe.businessDate, site: String(rowInfo.data['사업장'] || safe.site).trim(), lockHeld: true });
    order = housemanOrderObject_(rowObjectFromValues_(row, getHeaderMap_(sheet)), rowNumber);
    appendHousemanAudit_(order, 'CREATED_MOBILE', user.employeeNo, version, { role, autoAssignment: publicAssignment || null }); // PUBLIC_HOUSEMAN_REQUEST_V1
    } finally {
      writeLock.releaseLock();
    }
    queueHousemanOrderTelegram_(order, 'CREATED');
    return { ok: true, version, order, message: '하우스맨 요청을 등록했습니다.' };
  });
}

function normalizeMobileOptions_(options, user) { // (모바일 조회조건 정리)
  const safe = options || {};
  return {
    businessDate: normalizeBusinessDate_(safe.businessDate),
    site: resolveUserSessionSite_(user, safe.site) // SITE_SCOPE_INDICATOR_CLOSE_V2
  };
}

function getCurrentRoomsForMobile_(businessDate, site, usersByEmployeeNo) { // (모바일 객실 일괄 조회 · 동일 객실 중복 자동정리)
  const items = getCurrentRowsForSelection_(businessDate, site).items || [];
  const latestByRoom = new Map();

  items.forEach(item => {
    const data = item && item.data ? item.data : {};
    const rowSite = String(data['사업장'] || site || '').trim();
    const roomNo = String(data['객실번호'] || '').trim();
    if (!roomNo) return;

    const key = `${rowSite}|${roomNo}`;
    const previous = latestByRoom.get(key);
    if (!previous || Number(item.rowNumber || 0) >= Number(previous.rowNumber || 0)) {
      latestByRoom.set(key, item);
    }
  });

  return Array.from(latestByRoom.values())
    .sort((a, b) => Number(a.rowNumber || 0) - Number(b.rowNumber || 0))
    .map(item => currentRoomObject_(item.data, item.rowNumber, {}, usersByEmployeeNo));
}

function compareMobileOrders_(a, b) { // (모바일 오더 최신 등록 우선 정렬 · HOUSEMAN_LATEST_FIRST_V1)
  const completed = new Set(['COMPLETED', 'UNABLE']);
  const aDone = completed.has(a.statusCode) ? 1 : 0;
  const bDone = completed.has(b.statusCode) ? 1 : 0;
  if (aDone !== bDone) return aDone - bDone;
  const registeredCompare = String(b.registeredAt || '').localeCompare(String(a.registeredAt || ''));
  if (registeredCompare) return registeredCompare;
  if (a.important !== b.important) return a.important ? -1 : 1;
  if (a.handover !== b.handover) return a.handover ? -1 : 1;
  return Number(b.rowNumber || 0) - Number(a.rowNumber || 0);
}

function compareMobileCleaningRooms_(a, b) { // (룸메이드 진행객실 우선 정렬)
  const rank = { REWORK: 0, CLEANING: 1, ASSIGNED: 2, WAITING: 3, QM_WAITING: 4, COMPLETED: 5, QM_COMPLETED: 6 };
  const difference = (rank[a.cleaningStatus] ?? 9) - (rank[b.cleaningStatus] ?? 9);
  return difference || compareRooms_(a, b);
}

function compareMobileQmRooms_(a, b) { // (QM 점검대상 우선 정렬)
  const rank = { REWORK: 0, QM_WAITING: 1, QM_CHECKING: 2, COMPLETED: 3, QM_COMPLETED: 4 };
  const difference = (rank[a.cleaningStatus] ?? 9) - (rank[b.cleaningStatus] ?? 9);
  return difference || compareRooms_(a, b);
}

function buildRoommaidSummary_(rooms) { // (룸메이드 요약)
  return {
    total: rooms.length,
    waiting: rooms.filter(room => ['ASSIGNED', 'WAITING', 'REWORK'].includes(room.cleaningStatus)).length,
    working: rooms.filter(room => room.cleaningStatus === 'CLEANING').length,
    completed: rooms.filter(room => ['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED'].includes(room.cleaningStatus)).length
  };
}

function buildQmSummary_(rooms) { // (QM 요약)
  return {
    total: rooms.length,
    waiting: rooms.filter(room => ['QM_WAITING', 'COMPLETED'].includes(room.cleaningStatus)).length,
    checking: rooms.filter(room => room.cleaningStatus === 'QM_CHECKING' && room.operationalStatus !== 'REWORK').length,
    rework: rooms.filter(room => room.operationalStatus === 'REWORK').length,
    completed: rooms.filter(room => room.cleaningStatus === 'QM_COMPLETED').length
  };
}

function buildMobileOrderSummary_(orders, employeeNo) { // (하우스맨 공동 전달 포함 요약)
  return {
    total: orders.length,
    assigned: orders.filter(order => order.statusCode === 'ASSIGNED'
      && (order.assignedEmployeeNo === employeeNo || isHousemanOrderRouteCandidate_(order, employeeNo))).length,
    working: orders.filter(order => ['ACCEPTED', 'PROCESSING'].includes(order.statusCode)).length,
    completed: orders.filter(order => ['COMPLETED', 'UNABLE'].includes(order.statusCode)).length
  };
}

function buildPublicSummary_(rooms) { // (객실퍼블릭 퇴실·지연 요약)
  return {
    total: rooms.length,
    delayed: rooms.filter(room => room.departureDelayed).length,
    dueOut: rooms.filter(room => room.roomStatus === 'DUE_OUT').length,
    checkedOut: rooms.filter(room => room.roomStatus === 'CHECKED_OUT').length,
    stay: rooms.filter(room => room.roomStatus === 'STAY').length
  };
}

function mobileActionMessage_(role, action) { // (모바일 작업 결과 문구)
  const messages = {
    'ROOMMAID_START': '청소를 시작했습니다.',
    'ROOMMAID_COMPLETE': '청소완료로 처리했습니다.',
    'QM_START': '점검을 시작했습니다.',
    'QM_COMPLETE': 'QM 점검을 완료했습니다.',
    'QM_REWORK': '재정비를 요청했습니다.'
  };
  return messages[`${role}_${action}`] || '처리했습니다.';
}
