/**
 * NOVA Realtime 운영 동기화 FINAL
 *
 * 방향 A: Google Sheets -> PostgreSQL
 *   - 당일 객실/사용자 증분 동기화 (최종 통합트리거 1분)
 *   - 신규 업무일자/JIT 단건 동기화
 *
 * 방향 B: PostgreSQL -> Google Sheets
 *   - 룸메이드 START/COMPLETE 이벤트 배치 미러 (최종 통합트리거 1분)
 *   - 현재객실현황 + 업무이력 + QM 알림을 기존 NOVA 형식으로 보존
 *   - 미러 완료 후 DB updated_by 소유권 해제(버전 일치 조건)
 *
 * NOVA_REALTIME_ENABLED=N에서는 예약 트리거가 모두 실제 데이터 변경을 건너뜁니다.
 */

const NOVA_REALTIME_FINAL = Object.freeze({
  EVENT_CURSOR_TIME: 'NOVA_REALTIME_MIRROR_CURSOR_TIME',
  EVENT_CURSOR_REQUEST: 'NOVA_REALTIME_MIRROR_CURSOR_REQUEST',
  EVENT_BATCH_LIMIT: 500,
  HISTORY_DEDUP_SCAN: 6000,
  LAST_FORWARD_SYNC_MS: 'NOVA_REALTIME_LAST_FORWARD_SYNC_MS',
  FORWARD_INTERVAL_MS: 5 * 60 * 1000
});

function syncNovaRealtimeCurrentBusinessDate(businessDate, site, options) { // (당일 Sheets -> PostgreSQL 증분동기화)
  const dateText = novaRealtimeFinalBusinessDate_(businessDate);
  const siteText = String(site || '').trim();
  const rooms = novaRealtimeFinalBuildRooms_(dateText, siteText, '');
  if (!rooms.length) throw new Error(`Realtime 동기화 대상 객실이 없습니다. (${dateText}${siteText ? ' · ' + siteText : ''})`);
  const sites = Array.from(new Set(rooms.map(row => row.site).filter(Boolean))).sort();
  const users = novaRealtimeFinalBuildUsers_(sites);
  const safeOptions = options || {};
  return novaRealtimeFinalSignedPost_('/v1/admin/sync-current-rooms', {
    businessDate: dateText,
    source: safeOptions.forceSheetCleaning ? 'GOOGLE_SHEETS_NOVA_PREFLIGHT' : 'GOOGLE_SHEETS_NOVA_CURRENT',
    generatedAt: new Date().toISOString(),
    forceSheetCleaning: safeOptions.forceSheetCleaning === true,
    users,
    rooms
  });
}

function syncNovaRealtimeRoomForAction(token, payload) { // (룸메이드 작업 직전 누락객실 JIT 동기화)
  const auth = verifyNovaToken(token);
  if (!auth.ok) throw new Error('로그인이 필요합니다.');
  const safe = payload || {};
  const businessDate = novaRealtimeFinalBusinessDate_(safe.businessDate);
  const site = String(safe.site || auth.user.defaultSite || '').trim();
  const roomNo = String(safe.roomNo || '').trim();
  if (!site || !roomNo) throw new Error('Realtime 단건 동기화에 사업장과 객실번호가 필요합니다.');
  const rooms = novaRealtimeFinalBuildRooms_(businessDate, site, roomNo);
  if (!rooms.length) throw new Error(`${roomNo}호를 현재객실현황에서 찾을 수 없습니다.`);
  const users = novaRealtimeFinalBuildUsers_([site]);
  return novaRealtimeFinalSignedPost_('/v1/admin/sync-current-rooms', {
    businessDate,
    source: 'GOOGLE_SHEETS_NOVA_JIT',
    generatedAt: new Date().toISOString(),
    users,
    rooms
  });
}

function novaRealtimeScheduledFinalSync() { // (1분 최종 통합: 이벤트 미러 + 5분 간격 정방향)
  if (!novaRealtimeFinalEnabled_()) return { ok: true, skipped: true, reason: 'REALTIME_DISABLED' };
  const mirror = mirrorNovaRealtimeEventsToSheets_();
  const props = PropertiesService.getScriptProperties();
  const nowMs = Date.now();
  const lastForwardMs = Number(props.getProperty(NOVA_REALTIME_FINAL.LAST_FORWARD_SYNC_MS) || 0);
  let current = { ok: true, skipped: true, reason: 'FORWARD_NOT_DUE' };
  if (!lastForwardMs || nowMs - lastForwardMs >= NOVA_REALTIME_FINAL.FORWARD_INTERVAL_MS) {
    current = syncNovaRealtimeCurrentBusinessDate(novaRealtimeFinalBusinessDate_(), '');
    props.setProperty(NOVA_REALTIME_FINAL.LAST_FORWARD_SYNC_MS, String(nowMs));
  }
  const result = { ok: true, mirror, current };
  console.log(JSON.stringify(result));
  return result;
}

function novaRealtimeScheduledCurrentRoomsSync() { // (기존 핸들러 호환: 단독 정방향 실행)
  if (!novaRealtimeFinalEnabled_()) return { ok: true, skipped: true, reason: 'REALTIME_DISABLED' };
  const result = syncNovaRealtimeCurrentBusinessDate(novaRealtimeFinalBusinessDate_(), '');
  console.log(JSON.stringify(result));
  return result;
}

function testNovaRealtimeCurrentBusinessDateSync() { // (N 상태에서도 수동 검증 가능)
  const result = syncNovaRealtimeCurrentBusinessDate(novaRealtimeFinalBusinessDate_(), '');
  console.log(JSON.stringify(result, null, 2));
  return result;
}

function novaRealtimeScheduledEventMirror() { // (1분 예약: PostgreSQL -> Sheets)
  if (!novaRealtimeFinalEnabled_()) return { ok: true, skipped: true, reason: 'REALTIME_DISABLED' };
  const result = mirrorNovaRealtimeEventsToSheets_();
  console.log(JSON.stringify(result));
  return result;
}

function testNovaRealtimeEventMirror() { // (수동 이벤트 미러 검증)
  const result = mirrorNovaRealtimeEventsToSheets_();
  console.log(JSON.stringify(result, null, 2));
  return result;
}

function mirrorNovaRealtimeEventsToSheets_() { // (DB 이벤트를 기존 NOVA 자료구조로 배치반영)
  const props = PropertiesService.getScriptProperties();
  const cursorTime = String(props.getProperty(NOVA_REALTIME_FINAL.EVENT_CURSOR_TIME) || '1970-01-01T00:00:00.000Z').trim();
  const cursorRequestId = String(props.getProperty(NOVA_REALTIME_FINAL.EVENT_CURSOR_REQUEST) || '').trim();

  // 날짜 필터 없이 복합커서로 회수하여 자정 전후 이벤트도 누락시키지 않는다.
  const pulled = novaRealtimeFinalSignedPost_('/v1/admin/realtime-events', {
    cursorTime,
    cursorRequestId,
    limit: NOVA_REALTIME_FINAL.EVENT_BATCH_LIMIT
  });
  const events = Array.isArray(pulled.events) ? pulled.events : [];
  if (!events.length) return { ok: true, mirrored: 0, duplicates: 0, cursorTime, cursorRequestId };

  const alreadyApplied = novaRealtimeFinalRecentRequestIds_();
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const roomIndex = novaRealtimeFinalCurrentRoomIndex_(sheet);
  const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
  const lock = acquireWriteLock_(5000);
  let version = 0;
  let mirrored = 0;
  let duplicates = 0;
  const ackItems = [];
  const roomUpdates = [];
  const historyPayloads = [];
  const qmNotifications = [];
  const assignmentNotifications = [];
  const qmAssignmentNotifications = [];
  let finalCursorTime = cursorTime;
  let finalCursorRequestId = cursorRequestId;

  try {
    for (const event of events) {
      const requestId = String(event.requestId || '').trim();
      if (!requestId) continue;
      finalCursorTime = String(event.eventTime || finalCursorTime);
      finalCursorRequestId = requestId;
      ackItems.push({
        businessDate: String(event.businessDate || ''),
        site: String(event.site || ''),
        roomNo: String(event.roomNo || ''),
        roomVersion: Number(event.roomVersion || 0)
      });

      if (alreadyApplied.has(requestId)) {
        duplicates += 1;
        continue;
      }

      const key = novaRealtimeFinalRoomKey_(event.businessDate, event.site, event.roomNo);
      const rowInfo = roomIndex.get(key);
      if (!rowInfo) {
        throw new Error(`DB 이벤트 미러 실패: ${event.site} ${event.roomNo}호 현재객실현황 행을 찾을 수 없습니다.`);
      }

      if (!version) version = reserveDataVersion_({ lockHeld: true });
      const afterStatus = String(event.afterStatus || '').trim().toUpperCase();
      const beforeStatus = String(event.beforeStatus || rowInfo.data['청소상태'] || '').trim().toUpperCase();
      const employeeNo = String(event.employeeNo || '').trim();
      const action = String(event.action || '').trim().toUpperCase();
      const cleaningType = String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
      const assignmentType = String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
      const roommaidNo = String(rowInfo.data['룸메이드사번'] || '').trim();
      const secondaryRoommaidNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
      const qmNo = String(rowInfo.data['QM사번'] || '').trim();
      const eventBusinessDate = novaRealtimeFinalBusinessDate_(event.businessDate);
      const eventSite = String(event.site || rowInfo.data['사업장'] || '').trim();
      const eventRoomNo = String(event.roomNo || '').trim();

      if (action === 'ASSIGN_ROOMMAID') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const assignedCleaningType = String(eventDetail.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
        const assignedAssignmentType = String(eventDetail.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
        const assignedPrimaryNo = String(eventDetail.primaryEmployeeNo || '').trim();
        const assignedSecondaryNo = String(eventDetail.secondaryEmployeeNo || '').trim();
        if (!assignedPrimaryNo) throw new Error(`DB 배정 이벤트에 주담당 사번이 없습니다. (${eventSite} ${eventRoomNo}호)`);

        roomUpdates.push({
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: 'ASSIGNED',
          cleaningType: assignedCleaningType,
          assignmentType: assignedAssignmentType,
          roommaidEmployeeNo: assignedPrimaryNo,
          secondaryRoommaidEmployeeNo: assignedSecondaryNo,
          version,
          updatedAt: nowText_()
        });

        rowInfo.data['청소상태'] = 'ASSIGNED';
        rowInfo.data['정비유형'] = assignedCleaningType;
        rowInfo.data['배정유형'] = assignedAssignmentType;
        rowInfo.data['룸메이드사번'] = assignedPrimaryNo;
        rowInfo.data['보조룸메이드사번'] = assignedSecondaryNo;

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.CLEANING,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: assignedPrimaryNo,
          status: 'ASSIGN_ROOMMAID',
          detail: {
            requestId,
            realtime: true,
            action: 'ASSIGN_ROOMMAID',
            role: String(eventDetail.role || 'ORDER').trim().toUpperCase(),
            previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            cleaningStatus: 'ASSIGNED',
            cleaningType: assignedCleaningType,
            assignmentType: assignedAssignmentType,
            primaryEmployeeNo: assignedPrimaryNo,
            secondaryEmployeeNo: assignedSecondaryNo,
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        const telegramBase = {
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
          cleaningType: assignedCleaningType,
          cleaningStatus: 'ASSIGNED',
          assignmentType: assignedAssignmentType,
          preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
          vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
          importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
          registeredBy: employeeNo,
          version
        };
        if (usersByEmployeeNo[assignedPrimaryNo]) {
          assignmentNotifications.push(Object.assign({}, telegramBase, {
            targetUser: usersByEmployeeNo[assignedPrimaryNo], assignmentRole: 'PRIMARY'
          }));
        }
        if (assignedSecondaryNo && usersByEmployeeNo[assignedSecondaryNo]) {
          assignmentNotifications.push(Object.assign({}, telegramBase, {
            targetUser: usersByEmployeeNo[assignedSecondaryNo], assignmentRole: 'SECONDARY'
          }));
        }

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      if (action === 'QM_ASSIGN') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const assignedQmNo = String(eventDetail.qmEmployeeNo || '').trim();
        if (!assignedQmNo) throw new Error(`DB QM 배정 이벤트에 QM 사번이 없습니다. (${eventSite} ${eventRoomNo}호)`);

        roomUpdates.push({
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: 'QM_WAITING',
          qmEmployeeNo: assignedQmNo,
          version,
          updatedAt: nowText_()
        });
        rowInfo.data['청소상태'] = 'QM_WAITING';
        rowInfo.data['QM사번'] = assignedQmNo;

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: assignedQmNo,
          status: 'QM_ASSIGN',
          detail: {
            requestId,
            realtime: true,
            action: 'QM_ASSIGN',
            role: String(eventDetail.role || 'ORDER').trim().toUpperCase(),
            previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            cleaningStatus: 'QM_WAITING',
            cleaningType,
            assignmentType,
            primaryEmployeeNo: roommaidNo,
            secondaryEmployeeNo: secondaryRoommaidNo,
            qmEmployeeNo: assignedQmNo,
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        if (usersByEmployeeNo[assignedQmNo]) {
          qmAssignmentNotifications.push({
            businessDate: eventBusinessDate,
            site: eventSite,
            roomNo: eventRoomNo,
            targetUser: usersByEmployeeNo[assignedQmNo],
            preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
            registeredBy: employeeNo,
            version
          });
        }

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      if (action === 'CLEAR_ASSIGNMENT') {
        const previousRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
        const previousCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
        const previousCleaningType = String(rowInfo.data['정비유형'] || '').trim().toUpperCase();
        const previousAssignmentType = String(rowInfo.data['배정유형'] || '').trim().toUpperCase();
        const previousPrimaryEmployeeNo = String(rowInfo.data['룸메이드사번'] || '').trim();
        const previousSecondaryEmployeeNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
        const previousQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
        const previousOperationalStatus = normalizeIndicatorRoomOperationalStatus_(
          rowInfo.data[indicatorRoomOperationalStatusHeader_()]
        );

        const updates = {
          '정비유형': '',
          '배정유형': '',
          '룸메이드사번': '',
          '보조룸메이드사번': '',
          'QM사번': '',
          '청소상태': 'WAITING',
          '수정일시': nowText_(),
          '마지막변경버전': version
        };
        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.CLEANING,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'CLEAR_ASSIGNMENT',
          detail: {
            requestId,
            realtime: true,
            action: 'CLEAR_ASSIGNMENT',
            previousRoomStatus,
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            previousCleaningStatus,
            cleaningStatus: 'WAITING',
            previousCleaningType,
            cleaningType: '',
            previousAssignmentType,
            assignmentType: '',
            previousPrimaryEmployeeNo,
            previousSecondaryEmployeeNo,
            previousQmEmployeeNo,
            primaryEmployeeNo: '',
            secondaryEmployeeNo: '',
            qmEmployeeNo: '',
            preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
            previousOperationalStatus,
            operationalStatus: previousOperationalStatus,
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      if (action === 'UPDATE_OPERATION_FLAGS') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const preassigned = eventDetail.preassigned === true;
        const vip = eventDetail.vip === true;
        const importantRoom = eventDetail.importantRoom === true;

        ensureRoomOperationalFlagHeaders_();
        const updates = {
          '선배정여부': preassigned ? 'Y' : 'N',
          'VIP여부': vip ? 'Y' : 'N',
          '중요객실여부': importantRoom ? 'Y' : 'N',
          '수정일시': nowText_(),
          '마지막변경버전': version
        };
        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'UPDATE_OPERATION_FLAGS',
          detail: {
            requestId,
            realtime: true,
            action: 'UPDATE_OPERATION_FLAGS',
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            cleaningStatus: String(rowInfo.data['청소상태'] || '').trim(),
            cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
            assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
            primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
            secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
            creditUnit: getRoommaidCleaningCreditUnit_(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
            preassigned,
            vip,
            importantRoom,
            previousOperationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
            operationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const rawOperationalStatus = String(
          Object.prototype.hasOwnProperty.call(eventDetail, 'operationalStatus')
            ? eventDetail.operationalStatus
            : event.afterStatus || ''
        ).trim();
        const requestedOperationalStatus = normalizeIndicatorRoomOperationalStatus_(rawOperationalStatus);
        if (rawOperationalStatus && !requestedOperationalStatus) {
          throw new Error(`DB 객실 조치상태 이벤트 값이 올바르지 않습니다. (${eventSite} ${eventRoomNo}호)`);
        }

        ensureIndicatorRoomOperationalStatusHeader_();
        const previousOperationalStatus = normalizeIndicatorRoomOperationalStatus_(
          rowInfo.data[indicatorRoomOperationalStatusHeader_()]
        );
        const updates = {
          '수정일시': nowText_(),
          '마지막변경버전': version
        };
        updates[indicatorRoomOperationalStatusHeader_()] = requestedOperationalStatus;
        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'UPDATE_ROOM_OPERATION_STATUS',
          detail: {
            requestId,
            realtime: true,
            action: 'UPDATE_ROOM_OPERATION_STATUS',
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            cleaningStatus: String(rowInfo.data['청소상태'] || '').trim(),
            cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
            assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
            primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
            secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
            creditUnit: getRoommaidCleaningCreditUnit_(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
            preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
            previousOperationalStatus,
            operationalStatus: requestedOperationalStatus,
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      if (action === 'CHANGE_ROOM_STATUS') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const requestedRoomStatus = String(eventDetail.roomStatus || event.afterStatus || '').trim().toUpperCase();
        if (!requestedRoomStatus) {
          throw new Error(`DB 객실상태 변경 이벤트에 상태값이 없습니다. (${eventSite} ${eventRoomNo}호)`);
        }

        const previousRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
        const updates = {
          '수정일시': nowText_(),
          '마지막변경버전': version
        };

        if (isNovaRoomCleaningTargetStatus_(requestedRoomStatus)) {
          Object.assign(updates, buildIndicatorPreviousCycleArchiveUpdates_(rowInfo.data));
        }
        updates['객실상태'] = requestedRoomStatus;
        updates[indicatorLastRoomStatusHeader_()] = resolveIndicatorLastRoomStatusAfterChange_(requestedRoomStatus, rowInfo.data);
        if (requestedRoomStatus === 'VACANT_CLEAN') {
          indicatorPreviousCycleHeaders_().forEach(header => { updates[header] = ''; });
        }
        Object.assign(updates, resolveManualRoomStatusState_(requestedRoomStatus, rowInfo.data));

        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'CHANGE_ROOM_STATUS',
          detail: {
            requestId,
            realtime: true,
            action: 'CHANGE_ROOM_STATUS',
            previousRoomStatus,
            roomStatus: requestedRoomStatus,
            specialDepartureStarted: isNovaSpecialDepartureStatus_(requestedRoomStatus)
              && requestedRoomStatus !== previousRoomStatus,
            cleaningStatus: String(rowInfo.data['청소상태'] || '').trim(),
            cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
            assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
            primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
            secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
            creditUnit: getRoommaidCleaningCreditUnit_(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
            preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
            previousOperationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
            operationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      roomUpdates.push({
        rowNumber: rowInfo.rowNumber,
        cleaningStatus: afterStatus,
        version,
        updatedAt: nowText_()
      });
      // 같은 배치에서 같은 객실 후속 이벤트가 오면 다음 이벤트가 갱신상태를 보도록 메모리도 즉시 갱신한다.
      rowInfo.data['청소상태'] = afterStatus;

      historyPayloads.push({
        recordType: NOVA.RECORD_TYPES.CLEANING,
        businessDate: eventBusinessDate,
        site: eventSite,
        roomNo: eventRoomNo,
        targetEmployeeNo: employeeNo,
        status: action === 'CLEANING_START' ? 'ROOMMAID_START' : 'ROOMMAID_COMPLETE',
        detail: {
          requestId,
          realtime: true,
          action: action === 'CLEANING_START' ? 'START' : 'COMPLETE',
          role: 'ROOMMAID',
          beforeCleaningStatus: beforeStatus,
          previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
          sourceRoomStatus: action === 'CLEANING_COMPLETE' ? String(rowInfo.data['객실상태'] || '').trim().toUpperCase() : '',
          roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
          cleaningStatus: afterStatus,
          cleaningType,
          assignmentType,
          primaryEmployeeNo: roommaidNo,
          secondaryEmployeeNo: secondaryRoommaidNo,
          creditUnit: getRoommaidCleaningCreditUnit_(cleaningType),
          dbRoomVersion: Number(event.roomVersion || 0),
          dbEventTime: String(event.eventTime || '')
        },
        registeredBy: employeeNo,
        version
      });

      if (action === 'CLEANING_COMPLETE' && afterStatus === 'QM_WAITING' && qmNo && usersByEmployeeNo[qmNo]) {
        qmNotifications.push({
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetUser: usersByEmployeeNo[qmNo],
          preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
          vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
          importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
          registeredBy: employeeNo,
          version
        });
      }

      alreadyApplied.add(requestId);
      mirrored += 1;
    }

    if (roomUpdates.length) novaRealtimeFinalBatchUpdateCurrentRows_(sheet, roomUpdates);
    if (historyPayloads.length) novaRealtimeFinalAppendHistoryBatch_(historyPayloads);
    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));
    assignmentNotifications.forEach(payload => queueCleaningAssignmentTelegram_(payload));
    qmAssignmentNotifications.forEach(payload => queueQmAssignmentTelegram_(payload));

    if (version) {
      const affectedDates = Array.from(new Set(historyPayloads.map(item => item.businessDate).filter(Boolean)));
      affectedDates.forEach(date => publishDataVersion_(version, { domains: ['ROOM'], businessDate: date, lockHeld: true }));
    }
  } finally {
    lock.releaseLock();
  }

  // Sheets/업무이력 반영이 끝난 뒤에만 DB 소유권을 해제한다.
  // 실패하면 커서를 진행시키지 않아 다음 실행에서 재시도한다.
  if (ackItems.length) {
    const ack = novaRealtimeFinalSignedPost_('/v1/admin/ack-mirrored-events', { items: ackItems });
    if (!ack || !ack.ok) throw new Error('Realtime 이벤트 미러 확인(ACK)에 실패했습니다.');
  }

  props.setProperty(NOVA_REALTIME_FINAL.EVENT_CURSOR_TIME, finalCursorTime);
  props.setProperty(NOVA_REALTIME_FINAL.EVENT_CURSOR_REQUEST, finalCursorRequestId);

  return {
    ok: true,
    mirrored,
    duplicates,
    pulled: events.length,
    cursorTime: finalCursorTime,
    cursorRequestId: finalCursorRequestId,
    hasMore: Boolean(pulled.hasMore)
  };
}

function novaRealtimeFinalRoomKey_(businessDate, site, roomNo) {
  return `${novaRealtimeFinalBusinessDate_(businessDate)}|${String(site || '').trim()}|${String(roomNo || '').trim()}`;
}

function novaRealtimeFinalCurrentRoomIndex_(sheet) { // (현재객실현황을 실행당 1회만 읽어 최신행 인덱스 구성)
  const result = new Map();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return result;
  const headerMap = getHeaderMap_(sheet);
  const values = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getDisplayValues();
  values.forEach((row, offset) => {
    const data = rowObjectFromValues_(row, headerMap);
    const businessDate = novaRealtimeFinalNormalizeSheetDate_(data['업무일자']);
    const site = String(data['사업장'] || '').trim();
    const roomNo = String(data['객실번호'] || '').trim();
    if (!businessDate || !site || !roomNo) return;
    // 아래쪽 행을 최신행으로 간주한다.
    result.set(`${businessDate}|${site}|${roomNo}`, { rowNumber: offset + 2, data });
  });
  return result;
}

function novaRealtimeFinalBatchUpdateCurrentRows_(sheet, updates) { // (Realtime 객실상태·배정·버전 일괄기록)
  if (!updates.length) return;
  const headerMap = getHeaderMap_(sheet);
  const columns = {
    cleaningStatus: Number(headerMap['청소상태'] || 0),
    cleaningType: Number(headerMap['정비유형'] || 0),
    assignmentType: Number(headerMap['배정유형'] || 0),
    roommaidEmployeeNo: Number(headerMap['룸메이드사번'] || 0),
    secondaryRoommaidEmployeeNo: Number(headerMap['보조룸메이드사번'] || 0),
    qmEmployeeNo: Number(headerMap['QM사번'] || 0),
    version: Number(headerMap['마지막변경버전'] || 0),
    updatedAt: Number(headerMap['수정일시'] || 0)
  };
  if (Object.values(columns).some(value => !value)) {
    throw new Error('현재객실현황 Realtime 반영 열을 찾을 수 없습니다.');
  }

  const latestByRow = new Map();
  updates.forEach(item => latestByRow.set(Number(item.rowNumber), item));
  const rows = Array.from(latestByRow.keys()).filter(row => row >= 2).sort((a, b) => a - b);
  if (!rows.length) return;
  const firstRow = rows[0];
  const lastRow = rows[rows.length - 1];
  const count = lastRow - firstRow + 1;

  const valuesByKey = {};
  Object.entries(columns).forEach(([key, column]) => {
    valuesByKey[key] = sheet.getRange(firstRow, column, count, 1).getValues();
  });
  rows.forEach(rowNumber => {
    const item = latestByRow.get(rowNumber);
    const offset = rowNumber - firstRow;
    Object.keys(columns).forEach(key => {
      if (Object.prototype.hasOwnProperty.call(item, key)) valuesByKey[key][offset][0] = item[key];
    });
  });
  Object.entries(columns).forEach(([key, column]) => {
    sheet.getRange(firstRow, column, count, 1).setValues(valuesByKey[key]);
  });
}

function novaRealtimeFinalAppendHistoryBatch_(payloads) { // (업무이력을 한 번의 setValues로 추가)
  if (!payloads.length) return;
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const now = nowText_();
  const rows = payloads.map(payload => createRowByHeaders_(sheet, {
    '기록ID': payload.recordId || `${payload.recordType}-${Utilities.getUuid()}`,
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
  }));
  const startRow = sheet.getLastRow() + 1;
  ensureSheetRowCapacity_(sheet, startRow + rows.length - 1);
  sheet.getRange(startRow, 1, rows.length, rows[0].length).setValues(rows);
}

function installNovaRealtimeFinalTriggers() { // (운영 트리거 최종 설치: 1분 통합트리거 1개)
  const targets = new Set([
    'novaRealtimeScheduledFinalSync',
    'novaRealtimeScheduledCurrentRoomsSync',
    'novaRealtimeScheduledEventMirror'
  ]);
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (targets.has(trigger.getHandlerFunction())) ScriptApp.deleteTrigger(trigger);
  });
  ScriptApp.newTrigger('novaRealtimeScheduledFinalSync').timeBased().everyMinutes(1).create();
  return { ok: true, handler: 'novaRealtimeScheduledFinalSync', interval: '1분', mirror: '매 1분', currentRooms: '5분 간격' };
}

function installNovaRealtimeDailySyncTrigger() { // (기존 호출명 호환)
  return installNovaRealtimeFinalTriggers();
}

function removeNovaRealtimeDailySyncTrigger() { // (Realtime 동기화 트리거 전체 제거)
  const targets = new Set([
    'novaRealtimeScheduledFinalSync',
    'novaRealtimeScheduledCurrentRoomsSync',
    'novaRealtimeScheduledEventMirror'
  ]);
  let removed = 0;
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (!targets.has(trigger.getHandlerFunction())) return;
    ScriptApp.deleteTrigger(trigger);
    removed += 1;
  });
  return { ok: true, removed };
}

function prepareNovaRealtimeFinalCutover() { // (N 상태 최종 사전정렬: Sheets 기준 DB 초기화 + 과거테스트 커서 차단 + 트리거 설치)
  if (novaRealtimeFinalEnabled_()) {
    throw new Error('최종 사전정렬은 NOVA_REALTIME_ENABLED=N 상태에서만 실행하세요.');
  }
  const businessDate = novaRealtimeFinalBusinessDate_();
  const current = syncNovaRealtimeCurrentBusinessDate(businessDate, '', { forceSheetCleaning: true });
  const cursor = resetNovaRealtimeMirrorCursorToNow();
  PropertiesService.getScriptProperties().setProperty(NOVA_REALTIME_FINAL.LAST_FORWARD_SYNC_MS, String(Date.now()));
  const triggers = installNovaRealtimeFinalTriggers();
  const result = { ok: true, businessDate, current, cursor, triggers, message: '최종 사전정렬 완료. 아직 Realtime은 N 상태입니다.' };
  console.log(JSON.stringify(result, null, 2));
  return result;
}

function resetNovaRealtimeMirrorCursorToNow() { // (최초 운영 전 과거 테스트이벤트를 건너뛸 때만 수동 사용)
  const props = PropertiesService.getScriptProperties();
  props.setProperty(NOVA_REALTIME_FINAL.EVENT_CURSOR_TIME, new Date().toISOString());
  props.setProperty(NOVA_REALTIME_FINAL.EVENT_CURSOR_REQUEST, '');
  return { ok: true, cursorTime: props.getProperty(NOVA_REALTIME_FINAL.EVENT_CURSOR_TIME) };
}

function novaRealtimeFinalEnabled_() {
  return String(PropertiesService.getScriptProperties().getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() === 'Y';
}

function novaRealtimeFinalBusinessDate_(value) {
  const text = String(value || '').trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  return Utilities.formatDate(new Date(), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
}

function novaRealtimeFinalBuildUsers_(knownSites) {
  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  if (sheet.getLastRow() < 2) return [];
  const values = sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).getDisplayValues();
  const headers = values[0].map(value => String(value || '').trim());
  const map = {};
  headers.forEach((header, index) => { map[header] = index; });
  const sites = Array.from(new Set((knownSites || []).map(String).map(v => v.trim()).filter(Boolean)));
  const result = [];
  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    const employeeNo = String(row[map['사번']] || '').trim();
    const name = String(row[map['이름']] || '').trim();
    const role = String(row[map['권한']] || '').trim().toUpperCase();
    if (!employeeNo || !name || !['ADMIN', 'ORDER', 'QM', 'HOUSEMAN', 'ROOMMAID', 'PUBLIC'].includes(role)) continue;
    const enabledRaw = String(row[map['사용여부']] || 'Y').trim().toUpperCase();
    const defaultSite = String(row[map['기본사업장']] || '').trim();
    result.push({
      employeeNo,
      name,
      role,
      enabled: !['N', 'NO', 'FALSE', '0', '중지', '미사용'].includes(enabledRaw),
      defaultSite,
      allowedSites: ['ADMIN', 'ORDER'].includes(role) ? sites : (defaultSite ? [defaultSite] : [])
    });
  }
  return result;
}

function novaRealtimeFinalBuildRooms_(businessDate, site, roomNo) {
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  if (sheet.getLastRow() < 2) return [];
  const values = sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).getDisplayValues();
  const headers = values[0].map(value => String(value || '').trim());
  const map = {};
  headers.forEach((header, index) => { map[header] = index; });
  ['업무일자', '사업장', '객실번호', '객실상태', '청소상태'].forEach(header => {
    if (map[header] === undefined) throw new Error(`현재객실현황에 ${header} 열이 없습니다.`);
  });
  const dateText = novaRealtimeFinalBusinessDate_(businessDate);
  const siteText = String(site || '').trim();
  const roomText = String(roomNo || '').trim();
  const byKey = new Map();
  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    const rowDate = novaRealtimeFinalNormalizeSheetDate_(row[map['업무일자']]);
    const rowSite = String(row[map['사업장']] || '').trim();
    const rowRoom = String(row[map['객실번호']] || '').trim();
    if (rowDate !== dateText || !rowSite || !rowRoom) continue;
    if (siteText && rowSite !== siteText) continue;
    if (roomText && rowRoom !== roomText) continue;
    byKey.set(`${rowDate}|${rowSite}|${rowRoom}`, {
      businessDate: rowDate,
      site: rowSite,
      roomNo: rowRoom,
      building: String(row[map['동']] || row[map['건물']] || '').trim(),
      roomStatus: String(row[map['객실상태']] || '').trim().toUpperCase(),
      cleaningStatus: String(row[map['청소상태']] || 'WAITING').trim().toUpperCase(),
      cleaningType: String(row[map['정비유형']] || 'NORMAL').trim().toUpperCase(),
      assignmentType: String(row[map['배정유형']] || 'SOLO').trim().toUpperCase(),
      roommaidEmployeeNo: String(row[map['룸메이드사번']] || '').trim(),
      secondaryRoommaidEmployeeNo: String(row[map['보조룸메이드사번']] || '').trim(),
      qmEmployeeNo: String(row[map['QM사번']] || '').trim(),
      // 통합 인디게이터의 고장/객실확인 원본 열은 '객실운영상태'입니다.
      // '하우스맨상태'는 오더 처리상태이므로 절대 대체값으로 사용하지 않습니다.
      operationalStatus: typeof normalizeIndicatorRoomOperationalStatus_ === 'function'
        ? normalizeIndicatorRoomOperationalStatus_(
            map['객실운영상태'] !== undefined ? row[map['객실운영상태']]
              : (map['운영상태'] !== undefined ? row[map['운영상태']] : '')
          )
        : String(
            map['객실운영상태'] !== undefined ? row[map['객실운영상태']]
              : (map['운영상태'] !== undefined ? row[map['운영상태']] : '')
          ).trim()
    });
  }
  return Array.from(byKey.values());
}

function novaRealtimeFinalFindLatestRoomRow_(sheet, businessDate, site, roomNo) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  const headerMap = getHeaderMap_(sheet);
  const values = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getDisplayValues();
  const dateText = novaRealtimeFinalBusinessDate_(businessDate);
  const siteText = String(site || '').trim();
  const roomText = String(roomNo || '').trim();
  for (let i = values.length - 1; i >= 0; i--) {
    const data = rowObjectFromValues_(values[i], headerMap);
    if (novaRealtimeFinalNormalizeSheetDate_(data['업무일자']) !== dateText) continue;
    if (String(data['사업장'] || '').trim() !== siteText) continue;
    if (String(data['객실번호'] || '').trim() !== roomText) continue;
    return { rowNumber: i + 2, data };
  }
  return null;
}

function novaRealtimeFinalRecentRequestIds_() {
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const result = new Set();
  if (sheet.getLastRow() < 2) return result;
  const headerMap = getHeaderMap_(sheet);
  const detailColumn = Number(headerMap['세부내용JSON'] || 0);
  if (!detailColumn) return result;
  const count = Math.min(NOVA_REALTIME_FINAL.HISTORY_DEDUP_SCAN, sheet.getLastRow() - 1);
  const startRow = sheet.getLastRow() - count + 1;
  const values = sheet.getRange(startRow, detailColumn, count, 1).getDisplayValues();
  values.forEach(row => {
    const text = String(row[0] || '').trim();
    if (!text || text.indexOf('requestId') < 0) return;
    try {
      const detail = JSON.parse(text);
      const requestId = String(detail && detail.requestId || '').trim();
      if (requestId) result.add(requestId);
    } catch (_) {}
  });
  return result;
}

function novaRealtimeFinalSignedPost_(path, payload) {
  const props = PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  const secret = String(props.getProperty('NOVA_TOKEN_SECRET') || '').trim();
  if (!apiBase) throw new Error('NOVA_REALTIME_API_BASE가 설정되지 않았습니다.');
  if (!secret) throw new Error('NOVA_TOKEN_SECRET이 설정되지 않았습니다.');
  const body = JSON.stringify(payload || {});
  const timestamp = String(Date.now());
  const signature = novaRealtimeFinalHmacHex_(timestamp + '.' + body, secret);
  const response = UrlFetchApp.fetch(apiBase + String(path || ''), {
    method: 'post',
    contentType: 'application/json; charset=utf-8',
    payload: body,
    headers: {
      'X-NOVA-Timestamp': timestamp,
      'X-NOVA-Signature': signature
    },
    muteHttpExceptions: true,
    followRedirects: true
  });
  const status = response.getResponseCode();
  const text = response.getContentText();
  let result = {};
  try { result = JSON.parse(text || '{}'); } catch (_) { result = { ok: false, message: text || '응답 해석 실패' }; }
  if (status < 200 || status >= 300 || !result.ok) {
    throw new Error(result.message || result.code || `Realtime API 오류 (${status})`);
  }
  return result;
}

function novaRealtimeFinalHmacHex_(message, secret) {
  const bytes = Utilities.computeHmacSha256Signature(String(message || ''), String(secret || ''), Utilities.Charset.UTF_8);
  return bytes.map(byte => {
    const value = byte < 0 ? byte + 256 : byte;
    return ('0' + value.toString(16)).slice(-2);
  }).join('');
}

function novaRealtimeFinalNormalizeSheetDate_(value) {
  const text = String(value || '').trim();
  const direct = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (direct) return `${direct[1]}-${String(direct[2]).padStart(2, '0')}-${String(direct[3]).padStart(2, '0')}`;
  const slash = text.match(/^(\d{4})[./](\d{1,2})[./](\d{1,2})/);
  if (slash) return `${slash[1]}-${String(slash[2]).padStart(2, '0')}-${String(slash[3]).padStart(2, '0')}`;
  return text;
}
