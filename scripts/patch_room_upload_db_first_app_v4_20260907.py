from pathlib import Path

SERVER = Path('09_RoomStatusUpload.js')
CLIENT = Path('Client.html')
MARKER = 'ROOM_UPLOAD_DB_FIRST_APP_V4'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected=1')
    return text.replace(old, new, 1)


server = SERVER.read_text(encoding='utf-8')
if MARKER not in server:
    anchor = "function applyRoomStatusUpload(token, previewId, options) { // (검증된 객실현황 최종 반영·초기화 후 교체)\n"
    block = r'''
// ROOM_UPLOAD_DB_FIRST_APP_V4
// 업로드 계산은 기존 상태결정 helper를 그대로 재사용하고 DB commit 전에는 Sheet를 쓰지 않습니다.
function prepareRoomStatusUploadDbFirst(token, previewId, options) {
  return measureResponse_('prepareRoomStatusUploadDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = options || {};
    const resetExisting = safe.resetExisting === true;
    const dbCurrentRows = Array.isArray(safe.dbCurrentRows) ? safe.dbCurrentRows : [];
    const suppliedExpectedVersions = safe.expectedVersions && typeof safe.expectedVersions === 'object'
      ? safe.expectedVersions
      : {};
    const preview = loadRoomUploadPreview_(previewId);
    if (!preview) throw new Error('업로드 미리보기가 만료되었습니다. 파일을 다시 선택하세요.');
    if (preview.employeeNo !== user.employeeNo) throw new Error('다른 사용자가 만든 업로드 미리보기입니다.');

    const master = getActiveRoomMasterForSite_(preview.site);
    if (master.signature !== preview.masterSignature) {
      throw new Error('미리보기 이후 객실마스터가 변경되었습니다. 파일을 다시 검증하세요.');
    }

    const existingForTarget = {};
    const expectedVersions = {};
    dbCurrentRows.forEach(raw => {
      const data = raw && typeof raw === 'object' ? raw : {};
      if (String(data['업무일자'] || '').trim() !== preview.businessDate) return;
      if (String(data['사업장'] || '').trim() !== preview.site) return;
      const roomNo = normalizeRoomNo_(data['객실번호']);
      if (!roomNo) return;
      if (existingForTarget[roomNo]) throw new Error(`${roomNo}호 DB 현재객실 정보가 중복되어 있습니다.`);
      existingForTarget[roomNo] = data;
      const supplied = Number(suppliedExpectedVersions[roomNo]);
      const rowVersion = Number(data['마지막변경버전'] || 0);
      if (Number.isFinite(supplied) && supplied >= 0 && supplied !== rowVersion) {
        throw new Error(`${roomNo}호 DB 버전 스냅샷이 일치하지 않습니다. 다시 불러온 뒤 업로드해 주세요.`);
      }
      expectedVersions[roomNo] = rowVersion;
    });

    const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
    const requestedAssignments = normalizeRoommaidUploadAssignment_(preview.roommaidAssignment).byRoom;
    const appliedAssignments = [];
    const skippedAssignments = [];
    const departureConfirmedAssignments = [];
    const planRooms = [];

    master.rooms.forEach(room => {
      const uploadedRoomStatus = preview.statusByRoom[room.roomNo] || 'VACANT_CLEAN';
      const existingRoom = existingForTarget[room.roomNo] || {};
      const previous = resetExisting ? {} : existingRoom;
      const roomStatus = resolveEffectiveUploadRoomStatus_(uploadedRoomStatus, previous);
      const baseOperation = enforceUploadRoomOperationState_(
        roomStatus,
        resolveUploadOperationState_(roomStatus, previous)
      );
      const assignmentResolution = resolveUploadedRoommaidAssignment_(
        room.roomNo,
        roomStatus,
        previous,
        baseOperation,
        requestedAssignments[room.roomNo],
        usersByEmployeeNo
      );
      const operation = resetExisting && !assignmentResolution.applied
        ? baseOperation
        : assignmentResolution.operation;
      if (assignmentResolution.applied) appliedAssignments.push(assignmentResolution.assignment);
      if (assignmentResolution.skipped) skippedAssignments.push(assignmentResolution.skipped);

      const departureConfirmedAssignment = buildUploadDepartureConfirmedAssignment_(
        room.roomNo,
        existingRoom,
        roomStatus,
        operation,
        resetExisting
      );
      if (departureConfirmedAssignment) departureConfirmedAssignments.push(departureConfirmedAssignment);

      if (!Object.prototype.hasOwnProperty.call(expectedVersions, room.roomNo)) {
        expectedVersions[room.roomNo] = 0;
      }

      planRooms.push({
        roomNo: room.roomNo,
        building: room.building,
        roomStatus,
        lastRoomStatus: resolveIndicatorLastRoomStatusForUpload_(uploadedRoomStatus, roomStatus, previous),
        previousRoomStatus: String(previous['이전객실상태'] || '').trim(),
        previousCleaningStatus: String(previous['이전청소상태'] || '').trim(),
        previousRoommaidEmployeeNo: String(previous['이전룸메이드사번'] || '').trim(),
        previousSecondaryRoommaidEmployeeNo: String(previous['이전보조룸메이드사번'] || '').trim(),
        cleaningStatus: String(operation.cleaningStatus || '').trim().toUpperCase(),
        cleaningType: String(operation.cleaningType || '').trim().toUpperCase(),
        assignmentType: String(operation.assignmentType || '').trim().toUpperCase(),
        roommaidEmployeeNo: String(operation.roommaidEmployeeNo || '').trim(),
        secondaryRoommaidEmployeeNo: String(operation.secondaryRoommaidEmployeeNo || '').trim(),
        qmEmployeeNo: String(operation.qmEmployeeNo || '').trim(),
        operationalStatus: typeof normalizeIndicatorRoomOperationalStatus_ === 'function'
          ? normalizeIndicatorRoomOperationalStatus_(existingRoom['객실운영상태'])
          : String(existingRoom['객실운영상태'] || '').trim(),
        // 운영표시 3종은 정비초기화 대상이 아니므로 DB 현재값을 그대로 보존합니다.
        preassigned: normalizeYesNo_(existingRoom['선배정여부']) === 'Y',
        vip: normalizeYesNo_(existingRoom['VIP여부']) === 'Y',
        importantRoom: normalizeYesNo_(existingRoom['중요객실여부']) === 'Y'
      });
    });

    const planId = `RUP4-${Utilities.getUuid()}`;
    const plan = {
      kind: MARKER,
      employeeNo: user.employeeNo,
      previewId,
      businessDate: preview.businessDate,
      site: preview.site,
      fileName: preview.fileName,
      extension: preview.extension,
      resetExisting,
      counts: preview.counts,
      roomsByStatus: buildUploadRoomsByStatus_(preview.statusByRoom),
      roommaidAssignment: {
        sheetFound: Boolean(preview.roommaidAssignment && preview.roommaidAssignment.sheetFound),
        requestedCount: Number(preview.roommaidAssignment && preview.roommaidAssignment.requestedCount || 0),
        validCount: Number(preview.roommaidAssignment && preview.roommaidAssignment.validCount || 0)
      },
      appliedAssignments,
      skippedAssignments,
      departureConfirmedAssignments,
      createdAt: Date.now()
    };
    saveRoomUploadPreview_(planId, plan);

    return {
      ok: true,
      dbFirstPrepared: true,
      planId,
      businessDate: preview.businessDate,
      site: preview.site,
      rooms: planRooms,
      expectedVersions,
      upload: {
        fileName: preview.fileName,
        extension: preview.extension,
        applyMode: resetExisting ? 'RESET_REPLACE' : 'MERGE_REPLACE',
        counts: preview.counts,
        roomsByStatus: plan.roomsByStatus,
        roommaidAssignment: plan.roommaidAssignment
      },
      resetExisting,
      totalRooms: planRooms.length
    };
  });
}

function mirrorRoomStatusUploadDbFirst(token, previewId, planId, payload) {
  return measureResponse_('mirrorRoomStatusUploadDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const completionKey = `NOVA_RUP4_MIRROR_${String(planId || '').slice(0, 64)}`;
    const cache = CacheService.getScriptCache();
    const cached = cache.get(completionKey);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        if (parsed && parsed.ok) return Object.assign({}, parsed, { idempotentMirror: true });
      } catch (ignore) {}
    }

    const plan = loadRoomUploadPreview_(planId);
    if (!plan || plan.kind !== MARKER) {
      throw new Error('DB 반영은 완료되었을 수 있으나 Sheet 미러 계획을 찾지 못했습니다. 현재 상태를 다시 확인해 주세요.');
    }
    if (plan.employeeNo !== user.employeeNo || plan.previewId !== previewId) {
      throw new Error('다른 사용자의 객실업로드 DB 미러 계획입니다.');
    }

    const preview = loadRoomUploadPreview_(previewId);
    if (!preview || preview.employeeNo !== user.employeeNo) {
      throw new Error('원본 업로드 미리보기가 만료되어 DB 미러를 완료할 수 없습니다.');
    }

    const dbCurrentRows = Array.isArray(safe.dbCurrentRows) ? safe.dbCurrentRows : [];
    const dbVersion = Number(safe.version || 0);
    if (!dbVersion || !dbCurrentRows.length) {
      throw new Error('DB 확정 객실정보를 확인하지 못해 Sheet 미러를 중단했습니다.');
    }

    const master = getActiveRoomMasterForSite_(plan.site);
    if (master.signature !== preview.masterSignature) {
      throw new Error('DB 반영 후 객실마스터가 변경되었습니다. Sheet 미러를 중단하고 현재 상태를 확인해 주세요.');
    }

    const dbByRoom = {};
    dbCurrentRows.forEach(raw => {
      const data = raw && typeof raw === 'object' ? raw : {};
      if (String(data['업무일자'] || '').trim() !== plan.businessDate) return;
      if (String(data['사업장'] || '').trim() !== plan.site) return;
      const roomNo = normalizeRoomNo_(data['객실번호']);
      if (!roomNo) return;
      if (dbByRoom[roomNo]) throw new Error(`${roomNo}호 DB 미러 객실정보가 중복되어 있습니다.`);
      dbByRoom[roomNo] = data;
    });
    master.rooms.forEach(room => {
      if (!dbByRoom[room.roomNo]) {
        throw new Error(`${room.roomNo}호 DB 확정값이 없어 Sheet 미러를 중단했습니다.`);
      }
    });

    const lock = acquireWriteLock_(30000);
    const startedAt = Date.now();
    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const headerMap = getHeaderMap_(sheet);
      const lastColumn = sheet.getLastColumn();
      const existingRows = sheet.getLastRow() > 1
        ? sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).getDisplayValues()
        : [];
      const keptRows = [];
      const targetRowNumbers = [];
      const sheetOnlyByRoom = {};
      let removedTargetRowCount = 0;

      existingRows.forEach((row, index) => {
        const data = rowObjectFromValues_(row, headerMap);
        const isTarget = String(data['업무일자'] || '').trim() === plan.businessDate
          && String(data['사업장'] || '').trim() === plan.site;
        if (isTarget) {
          removedTargetRowCount += 1;
          targetRowNumbers.push(index + 2);
          const roomNo = normalizeRoomNo_(data['객실번호']);
          if (roomNo) {
            sheetOnlyByRoom[roomNo] = {
              housemanStatus: String(data['하우스맨상태'] || '').trim(),
              housemanPending: Number(data['하우스맨미완료수'] || 0)
            };
          }
        } else {
          keptRows.push(row);
        }
      });

      const newRows = master.rooms.map(room => {
        const db = dbByRoom[room.roomNo];
        const sheetOnly = sheetOnlyByRoom[room.roomNo] || {};
        return rowFromHeaderMap_(lastColumn, headerMap, {
          '업무일자': plan.businessDate,
          '객실번호': room.roomNo,
          '사업장': plan.site,
          '객실상태': String(db['객실상태'] || '').trim().toUpperCase(),
          '마지막객실상태': String(db['마지막객실상태'] || '').trim().toUpperCase(),
          '이전객실상태': String(db['이전객실상태'] || '').trim().toUpperCase(),
          '이전청소상태': String(db['이전청소상태'] || '').trim().toUpperCase(),
          '이전룸메이드사번': String(db['이전룸메이드사번'] || '').trim(),
          '이전보조룸메이드사번': String(db['이전보조룸메이드사번'] || '').trim(),
          '청소상태': String(db['청소상태'] || '').trim().toUpperCase(),
          '정비유형': String(db['정비유형'] || '').trim().toUpperCase(),
          '배정유형': String(db['배정유형'] || '').trim().toUpperCase(),
          '룸메이드사번': String(db['룸메이드사번'] || '').trim(),
          '보조룸메이드사번': String(db['보조룸메이드사번'] || '').trim(),
          'QM사번': String(db['QM사번'] || '').trim(),
          '마지막변경버전': Number(db['마지막변경버전'] || dbVersion),
          '수정일시': String(db['수정일시'] || nowText_()).trim(),
          '동': String(db['동'] || room.building || '').trim(),
          '하우스맨상태': sheetOnly.housemanStatus || '',
          '하우스맨미완료수': Number(sheetOnly.housemanPending || 0),
          '객실운영상태': String(db['객실운영상태'] || '').trim(),
          '선배정여부': normalizeYesNo_(db['선배정여부']) === 'Y' ? 'Y' : 'N',
          'VIP여부': normalizeYesNo_(db['VIP여부']) === 'Y' ? 'Y' : 'N',
          '중요객실여부': normalizeYesNo_(db['중요객실여부']) === 'Y' ? 'Y' : 'N'
        });
      });

      const targetRowsContiguous = targetRowNumbers.length === newRows.length
        && targetRowNumbers.length > 0
        && targetRowNumbers.every((rowNumber, index) => rowNumber === targetRowNumbers[0] + index);
      let roomWriteMode = 'FULL_REWRITE';
      let firstWrittenRow = keptRows.length + 2;
      if (targetRowsContiguous) {
        firstWrittenRow = targetRowNumbers[0];
        ensureSheetRowCapacity_(sheet, firstWrittenRow + newRows.length - 1);
        sheet.getRange(firstWrittenRow, 1, newRows.length, lastColumn).setValues(newRows);
        roomWriteMode = 'IN_PLACE_BLOCK';
      } else {
        const allRows = keptRows.concat(newRows);
        if (sheet.getLastRow() > 1) {
          sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).clearContent();
        }
        if (allRows.length) {
          ensureSheetRowCapacity_(sheet, allRows.length + 1);
          sheet.getRange(2, 1, allRows.length, lastColumn).setValues(allRows);
        }
      }

      const updatedAt = nowText_();
      const maintenanceReset = plan.resetExisting
        ? resetRoomMaintenanceHistoryForUpload_(plan.businessDate, plan.site, updatedAt)
        : createRoomMaintenanceResetSummary_();
      SpreadsheetApp.flush();

      // 다음 Sheet write가 DB 확정버전보다 낮은 전체버전을 예약하지 않도록 전역 버전도 단조증가시킵니다.
      const properties = PropertiesService.getScriptProperties();
      const globalVersion = Number(properties.getProperty('NOVA_DATA_VERSION') || 0);
      if (dbVersion > globalVersion) properties.setProperty('NOVA_DATA_VERSION', String(dbVersion));
      publishDataVersion_(dbVersion, {
        domains: plan.resetExisting ? ['ROOM', 'REPORT'] : ['ROOM'],
        businessDate: plan.businessDate,
        site: plan.site,
        lockHeld: true
      });

      appendUnifiedHistory_({
        recordType: NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD,
        businessDate: plan.businessDate,
        site: plan.site,
        roomNo: '',
        targetEmployeeNo: '',
        status: 'APPLIED',
        detail: {
          source: MARKER,
          fileName: plan.fileName,
          extension: plan.extension,
          counts: plan.counts,
          totalRooms: newRows.length,
          roomStatusSchema: 1,
          applyMode: plan.resetExisting ? 'RESET_REPLACE' : 'MERGE_REPLACE',
          removedTargetRowCount,
          maintenanceReset,
          roomsByStatus: plan.roomsByStatus,
          roommaidAssignment: {
            sheetFound: Boolean(plan.roommaidAssignment && plan.roommaidAssignment.sheetFound),
            requestedCount: Number(plan.roommaidAssignment && plan.roommaidAssignment.requestedCount || 0),
            validCount: Number(plan.roommaidAssignment && plan.roommaidAssignment.validCount || 0),
            appliedCount: plan.appliedAssignments.length,
            skippedCount: plan.skippedAssignments.length,
            appliedByEmployee: buildAppliedAssignmentSummary_(plan.appliedAssignments)
          },
          dbVersion
        },
        registeredBy: user.employeeNo,
        version: dbVersion
      });

      const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
      const assignmentPostWarnings = [];
      if (plan.appliedAssignments.length) {
        try {
          appendRoomUploadAssignmentHistory_(plan.appliedAssignments, {
            businessDate: plan.businessDate,
            site: plan.site,
            fileName: plan.fileName,
            registeredBy: user.employeeNo,
            registeredAt: updatedAt,
            version: dbVersion
          });
        } catch (error) {
          assignmentPostWarnings.push(`룸메이드 배정 업무이력 기록 실패: ${error.message}`);
        }
        assignmentPostWarnings.push(...queueRoomUploadAssignmentTelegrams_(plan.appliedAssignments, {
          businessDate: plan.businessDate,
          site: plan.site,
          registeredBy: user.employeeNo,
          version: dbVersion,
          usersByEmployeeNo
        }));
      }
      if (plan.departureConfirmedAssignments.length) {
        assignmentPostWarnings.push(...queueRoomUploadDepartureConfirmedTelegrams_(plan.departureConfirmedAssignments, {
          businessDate: plan.businessDate,
          site: plan.site,
          registeredBy: user.employeeNo,
          version: dbVersion,
          usersByEmployeeNo
        }));
      }

      const roomObjects = newRows.map((row, index) => currentRoomObject_(
        rowObjectFromValues_(row, headerMap),
        firstWrittenRow + index,
        {},
        usersByEmployeeNo
      ));
      const result = {
        ok: true,
        dbFirst: true,
        uploadRpcVersion: 'V4',
        version: dbVersion,
        businessDate: plan.businessDate,
        site: plan.site,
        totalRooms: newRows.length,
        counts: plan.counts,
        rooms: roomObjects,
        roommaidAssignment: {
          sheetFound: Boolean(plan.roommaidAssignment && plan.roommaidAssignment.sheetFound),
          requestedCount: Number(plan.roommaidAssignment && plan.roommaidAssignment.requestedCount || 0),
          appliedCount: plan.appliedAssignments.length,
          skippedCount: plan.skippedAssignments.length,
          skipped: plan.skippedAssignments,
          warnings: assignmentPostWarnings
        },
        resetExisting: plan.resetExisting,
        removedTargetRowCount,
        maintenanceReset,
        timing: {
          totalMs: Date.now() - startedAt,
          roomWriteMode
        },
        message: buildRoomStatusUploadApplyMessage_(
          preview,
          newRows.length,
          plan.appliedAssignments.length,
          plan.skippedAssignments.length,
          plan.resetExisting,
          removedTargetRowCount,
          maintenanceReset
        )
      };

      cache.put(completionKey, JSON.stringify({
        ok: true,
        dbFirst: true,
        uploadRpcVersion: 'V4',
        version: dbVersion,
        businessDate: plan.businessDate,
        site: plan.site,
        totalRooms: newRows.length,
        counts: plan.counts,
        resetExisting: plan.resetExisting,
        message: result.message
      }), 3600);
      removeRoomUploadPreview_(planId, true);
      removeRoomUploadPreview_(previewId, true);
      return result;
    } finally {
      lock.releaseLock();
    }
  });
}

'''
    server = replace_once(server, anchor, block + anchor, '09_RoomStatusUpload apply function')
    SERVER.write_text(server, encoding='utf-8')

client = CLIENT.read_text(encoding='utf-8')
if MARKER not in client:
    anchor = "  async function applyRoomUploadPreview_(resetExisting) { // (검증된 객실현황 유지 반영·초기화 후 교체)\n"
    block = r'''  // ROOM_UPLOAD_DB_FIRST_APP_V4
  // DB snapshot -> 기존 Apps Script 업무규칙 계산 -> PostgreSQL 원자 commit -> 최신 DB값 Sheet mirror.
  async function novaRoomUploadRpcV4_(functionName, body, attempt = 0) {
    const auth = await novaQmDraftAuthBundle_();
    if (!auth?.token || !auth?.supabaseUrl || !auth?.publishableKey) {
      const error = new Error('객실업로드 DB 인증정보를 준비하지 못했습니다.');
      error.code = 'ROOM_UPLOAD_DB_AUTH_UNAVAILABLE';
      throw error;
    }
    const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/${functionName}`;
    let response;
    try {
      response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${String(auth.token || '')}`,
          'apikey': String(auth.publishableKey || '')
        },
        body: JSON.stringify(body || {})
      });
    } catch (networkError) {
      if (attempt < 2) {
        await novaRealtimeSleep_([180, 450, 900][attempt] || 900);
        return novaRoomUploadRpcV4_(functionName, body, attempt + 1);
      }
      const error = new Error('객실업로드 DB 처리 결과를 확인하지 못했습니다. 현재 상태를 다시 확인해 주세요.');
      error.code = 'ROOM_UPLOAD_DB_RESULT_UNKNOWN';
      throw error;
    }

    const data = await response.json().catch(() => ({}));
    if (response.ok && data?.ok) return data;

    const error = new Error(data?.message || data?.details || data?.hint || `객실업로드 DB 오류 (${response.status})`);
    error.status = Number(response.status || 0);
    error.code = String(data?.code || '').trim();
    error.data = data || null;
    const code = error.code.toUpperCase();

    if (response.status === 401 && attempt < 2) {
      novaRealtime_.qmDraftAuthBundle = null;
      await novaRealtimeSleep_(180);
      return novaRoomUploadRpcV4_(functionName, body, attempt + 1);
    }
    if ((response.status === 429 || response.status >= 500) && attempt < 2) {
      await novaRealtimeSleep_([180, 450, 900][attempt] || 900);
      return novaRoomUploadRpcV4_(functionName, body, attempt + 1);
    }
    error.missingRpc = response.status === 404 || ['PGRST202', 'PGRST205'].includes(code);
    throw error;
  }

  function novaRoomUploadStableRequestId_(previewId, resetMode) {
    const key = `nova-room-upload-v4:${String(previewId || '')}:${resetMode ? 'reset' : 'merge'}`;
    try {
      const existing = String(sessionStorage.getItem(key) || '').trim();
      if (existing) return { key, requestId: existing };
    } catch (ignore) {}
    const requestId = novaRealtimeRequestId_('ROOM_UPLOAD_V4', previewId || 'UPLOAD');
    try { sessionStorage.setItem(key, requestId); } catch (ignore) {}
    return { key, requestId };
  }

  async function novaRoomUploadStateV3_(businessDate, site) {
    return novaRoomUploadRpcV4_('nova_room_upload_state_v3', {
      p_business_date: String(businessDate || ''),
      p_site: String(site || '')
    });
  }

  async function novaRoomUploadDbFirstV4_(previewId, resetMode) {
    const businessDate = String(state.indicator.businessDate || state.bootstrap?.app?.businessDate || '').trim();
    const site = String(state.indicator.site || '').trim();
    if (!businessDate || !site) {
      return callServer('applyRoomStatusUpload', state.token, previewId, { resetExisting: resetMode });
    }

    let beforeState;
    try {
      beforeState = await novaRoomUploadStateV3_(businessDate, site);
    } catch (error) {
      if (error?.missingRpc || error?.code === 'ROOM_UPLOAD_DB_AUTH_UNAVAILABLE') {
        console.warn('[NOVA Upload] DB-first state unavailable before mutation · legacy fallback:', error?.message || error);
        return callServer('applyRoomStatusUpload', state.token, previewId, { resetExisting: resetMode });
      }
      throw error;
    }

    const prepared = await callServer('prepareRoomStatusUploadDbFirst', state.token, previewId, {
      resetExisting: resetMode,
      dbCurrentRows: Array.isArray(beforeState.currentRows) ? beforeState.currentRows : [],
      expectedVersions: beforeState.expectedVersions || {}
    });
    if (!prepared?.ok || !prepared?.dbFirstPrepared || !prepared?.planId) {
      throw new Error(prepared?.message || '객실업로드 DB-first 계산을 준비하지 못했습니다.');
    }

    const stable = novaRoomUploadStableRequestId_(previewId, resetMode);
    let committed;
    try {
      committed = await novaRoomUploadRpcV4_('nova_room_upload_apply_v4', {
        p_business_date: prepared.businessDate,
        p_site: prepared.site,
        p_rooms: prepared.rooms,
        p_upload: prepared.upload,
        p_expected_versions: prepared.expectedVersions,
        p_version: 0,
        p_request_id: stable.requestId
      });
    } catch (error) {
      if (error?.missingRpc) {
        console.warn('[NOVA Upload] V4 RPC missing before DB mutation · legacy fallback:', error?.message || error);
        try { sessionStorage.removeItem(stable.key); } catch (ignore) {}
        return callServer('applyRoomStatusUpload', state.token, previewId, { resetExisting: resetMode });
      }
      // 네트워크 결과불명/버전충돌/권한오류에서는 Sheet-first를 병행하지 않습니다.
      throw error;
    }
    if (!committed?.ok || committed?.dbFirst !== true) {
      throw new Error(committed?.message || '객실업로드 DB 확정 결과를 확인하지 못했습니다.');
    }

    let afterState = null;
    let afterError = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        afterState = await novaRoomUploadStateV3_(prepared.businessDate, prepared.site);
        if (afterState?.ok && Number(afterState.version || 0) >= Number(committed.version || 0)) break;
        afterState = null;
      } catch (error) {
        afterError = error;
      }
      await novaRealtimeSleep_([180, 450, 900][attempt] || 900);
    }
    if (!afterState?.ok) {
      const error = new Error(afterError?.message || 'DB 반영은 완료되었으나 최신 객실값을 다시 읽지 못했습니다. 같은 업로드 버튼을 다시 누르면 동일 요청으로 복구를 시도합니다.');
      error.code = 'ROOM_UPLOAD_DB_COMMITTED_MIRROR_PENDING';
      throw error;
    }

    let mirrored = null;
    let mirrorError = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        mirrored = await callServer('mirrorRoomStatusUploadDbFirst', state.token, previewId, prepared.planId, {
          dbCurrentRows: Array.isArray(afterState.currentRows) ? afterState.currentRows : [],
          version: Number(afterState.version || committed.version || 0),
          requestId: stable.requestId
        });
        if (mirrored?.ok) break;
        mirrorError = new Error(mirrored?.message || 'Sheet 미러 실패');
      } catch (error) {
        mirrorError = error;
      }
      await novaRealtimeSleep_([220, 650, 1200][attempt] || 1200);
    }
    if (!mirrored?.ok) {
      const error = new Error(mirrorError?.message || 'DB 반영은 완료되었으나 기존 Sheet 이력 동기화가 지연되었습니다. 같은 업로드 버튼을 다시 눌러 복구해 주세요.');
      error.code = 'ROOM_UPLOAD_DB_COMMITTED_MIRROR_PENDING';
      throw error;
    }

    try { sessionStorage.removeItem(stable.key); } catch (ignore) {}
    return Object.assign({}, mirrored, {
      dbFirst: true,
      requestId: stable.requestId,
      dbCommittedVersion: Number(committed.version || 0)
    });
  }

'''
    client = replace_once(client, anchor, block + anchor, 'Client applyRoomUploadPreview')

    old_call = """      const result = await callServer('applyRoomStatusUpload', state.token, previewId, {\n        resetExisting: resetMode\n      });"""
    new_call = """      const result = await novaRoomUploadDbFirstV4_(previewId, resetMode);"""
    client = replace_once(client, old_call, new_call, 'Client upload final apply call')

    old_gate = """      // ROOM_UPLOAD_REALTIME_CONVERGENCE_V1 · Sheet 잠금이 해제된 뒤 별도 요청으로 DB를 즉시 수렴시킵니다.\n      // 서버가 먼저 pending DB 이벤트를 미러하므로 라이브 배정/QM 상태를 stale 업로드값으로 덮지 않습니다.\n      if (novaRealtimeIsEnabled_()) {"""
    new_gate = """      // ROOM_UPLOAD_REALTIME_CONVERGENCE_V1 · legacy Sheet-first에만 후행 DB 수렴이 필요합니다.\n      // V4는 DB가 이미 원본이므로 다시 Sheet→DB forward sync를 실행하지 않습니다.\n      if (novaRealtimeIsEnabled_() && result?.dbFirst !== true) {"""
    client = replace_once(client, old_gate, new_gate, 'legacy upload convergence gate')
    CLIENT.write_text(client, encoding='utf-8')

print('PASS: staged room upload DB-first app V4 bridge without deploying production sources')
