/**
 * NOVA v1.0 RC3: 장소별 QM 실시간 점검·사진 하자·품질실적
 * 체크리스트/장소 마스터는 코드설정, 진행중 초안·최종 결과는 업무이력에 저장합니다.
 */
const NOVA_QM_CHECKLIST = Object.freeze({
  GROUP: 'QM체크리스트',
  PLACE_GROUP: 'QM점검장소',
  MAX_ITEMS: 100,
  MAX_PLACES: 30,
  MAX_PHOTOS_PER_TARGET: 3,
  MAX_PHOTO_BYTES: 2621440,
  HISTORY_SCAN_ROWS: 12000,
  PHOTO_ROOT_PROPERTY: 'NOVA_QM_PHOTO_ROOT_FOLDER_ID',
  DEFAULT_PLACES: Object.freeze([
    { code: 'ENTRANCE', label: '현관', order: 10 },
    { code: 'KITCHEN', label: '주방', order: 20 },
    { code: 'BATHROOM', label: '욕실', order: 30 },
    { code: 'BEDROOM', label: '침실', order: 40 },
    { code: 'BED_LINEN', label: '침대·이불', order: 50 },
    { code: 'FLOOR', label: '바닥', order: 60 },
    { code: 'FURNITURE', label: '가구·유리', order: 70 },
    { code: 'AMENITY', label: '비품·소모품', order: 80 },
    { code: 'FACILITY', label: '시설·하자', order: 90 },
    { code: 'OVERALL', label: '객실 전체', order: 100 }
  ]),
  DEFAULT_ITEMS: Object.freeze([
    { code: 'QMCL-01', label: '침구 정돈 및 오염 상태', placeCode: 'BED_LINEN', order: 10 },
    { code: 'QMCL-02', label: '객실 바닥·먼지·머리카락 상태', placeCode: 'FLOOR', order: 20 },
    { code: 'QMCL-03', label: '욕실 청결 및 배수 상태', placeCode: 'BATHROOM', order: 30 },
    { code: 'QMCL-04', label: '거울·유리·가구 오염 상태', placeCode: 'FURNITURE', order: 40 },
    { code: 'QMCL-05', label: '소모품·비품 세팅 상태', placeCode: 'AMENITY', order: 50 },
    { code: 'QMCL-06', label: '냄새·환기 및 침실 상태', placeCode: 'BEDROOM', order: 60 },
    { code: 'QMCL-07', label: '시설 이상 및 하자 여부', placeCode: 'FACILITY', order: 70 },
    { code: 'QMCL-08', label: '최종 객실 전체 확인', placeCode: 'OVERALL', order: 80 },
    { code: 'QMCL-09', label: '주방 싱크대·식기·오염 상태', placeCode: 'KITCHEN', order: 25 },
    { code: 'QMCL-10', label: '현관문·신발장·입구 청결 상태', placeCode: 'ENTRANCE', order: 5 }
  ])
});

function getQmChecklistManagementData(token) { // (관리자·오더테이커 체크리스트·장소 관리 조회)
  return measureResponse_('getQmChecklistManagementData', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    seedQmChecklistPlaces_();
    seedQmChecklistCodes_();
    migrateQmChecklistLocations_();
    const places = getActiveQmChecklistPlaces_();
    const items = getActiveQmChecklistItems_();
    return {
      ok: true,
      places,
      items,
      revision: buildQmChecklistRevision_(items, places),
      maxItems: NOVA_QM_CHECKLIST.MAX_ITEMS,
      maxPlaces: NOVA_QM_CHECKLIST.MAX_PLACES,
      sites: getSiteList_(),
      serverTime: nowText_()
    };
  });
}

function saveQmChecklistPlace(token, payload) { // (점검 장소 추가·수정)
  return measureResponse_('saveQmChecklistPlace', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    seedQmChecklistPlaces_();
    const requestedCode = String(safe.code || '').trim().toUpperCase();
    const code = requestedCode || `QMPLACE-${Utilities.getUuid().replace(/-/g, '').slice(0, 8).toUpperCase()}`;
    const existing = findCodeRow_(NOVA_QM_CHECKLIST.PLACE_GROUP, code);
    if (!existing && getActiveQmChecklistPlaces_().length >= NOVA_QM_CHECKLIST.MAX_PLACES) {
      throw new Error(`점검 장소는 최대 ${NOVA_QM_CHECKLIST.MAX_PLACES}개까지 등록할 수 있습니다.`);
    }
    const label = String(safe.label || '').trim();
    if (!label) throw new Error('점검 장소명을 입력하세요.');
    if (label.length > 40) throw new Error('점검 장소명은 40자 이내로 입력하세요.');
    const order = Math.max(0, Math.min(9999, Number(safe.order || 9999)));
    upsertCodeRow_(NOVA_QM_CHECKLIST.PLACE_GROUP, code, label, order, 'Y', '');
    clearNovaCaches_();
    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
      businessDate: businessDateText_(),
      status: existing ? 'QM_PLACE_UPDATED' : 'QM_PLACE_CREATED',
      registeredBy: user.employeeNo,
      detail: { code, label, order }
    });
    bumpDataVersion_({ domains: ['CONFIG'] });
    return { ok: true, code, message: existing ? '점검 장소를 수정했습니다.' : '점검 장소를 추가했습니다.' };
  });
}

function deleteQmChecklistPlace(token, payload) { // (점검 장소 삭제)
  return measureResponse_('deleteQmChecklistPlace', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const code = String(payload && payload.code || '').trim().toUpperCase();
    if (!code) throw new Error('삭제할 점검 장소가 없습니다.');
    const existing = findCodeRow_(NOVA_QM_CHECKLIST.PLACE_GROUP, code);
    if (!existing || existing.enabled !== 'Y') throw new Error('점검 장소를 찾을 수 없습니다.');
    const usingItems = getActiveQmChecklistItems_().filter(item => item.placeCode === code);
    if (usingItems.length) throw new Error(`해당 장소를 사용하는 체크리스트 ${usingItems.length}개가 있습니다. 항목의 장소를 먼저 변경하세요.`);
    upsertCodeRow_(NOVA_QM_CHECKLIST.PLACE_GROUP, code, existing.label, existing.order, 'N', existing.note);
    clearNovaCaches_();
    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
      businessDate: businessDateText_(),
      status: 'QM_PLACE_DELETED',
      registeredBy: user.employeeNo,
      detail: { code, label: existing.label }
    });
    bumpDataVersion_({ domains: ['CONFIG'] });
    return { ok: true, message: '점검 장소를 삭제했습니다. 과거 점검이력은 유지됩니다.' };
  });
}

function saveQmChecklistItem(token, payload) { // (체크리스트 항목 추가·수정)
  return measureResponse_('saveQmChecklistItem', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    seedQmChecklistPlaces_();
    seedQmChecklistCodes_();
    const activeItems = getActiveQmChecklistItems_();
    const requestedCode = String(safe.code || '').trim();
    const code = requestedCode || `QMCL-${Utilities.getUuid().replace(/-/g, '').slice(0, 10).toUpperCase()}`;
    const existing = findCodeRow_(NOVA_QM_CHECKLIST.GROUP, code);
    if (!existing && activeItems.length >= NOVA_QM_CHECKLIST.MAX_ITEMS) throw new Error(`체크리스트는 최대 ${NOVA_QM_CHECKLIST.MAX_ITEMS}개까지 등록할 수 있습니다.`);
    const label = String(safe.label || '').trim();
    if (!label) throw new Error('점검 항목명을 입력하세요.');
    if (label.length > 120) throw new Error('점검 항목명은 120자 이내로 입력하세요.');
    const places = getActiveQmChecklistPlaces_();
    const placeCode = String(safe.placeCode || '').trim().toUpperCase();
    if (!places.some(place => place.code === placeCode)) throw new Error('점검 장소를 선택하세요.');
    const order = Math.max(0, Math.min(9999, Number(safe.order || 9999)));
    const note = JSON.stringify({
      placeCode,
      required: safe.required !== false && String(safe.required || 'Y').toUpperCase() !== 'N',
      photoRequired: safe.photoRequired === true || String(safe.photoRequired || '').toUpperCase() === 'Y'
    });
    upsertCodeRow_(NOVA_QM_CHECKLIST.GROUP, code, label, order, 'Y', note);
    clearNovaCaches_();
    const meta = JSON.parse(note);
    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
      businessDate: businessDateText_(),
      status: existing ? 'QM_CHECKLIST_UPDATED' : 'QM_CHECKLIST_CREATED',
      registeredBy: user.employeeNo,
      detail: { code, label, order, placeCode, required: meta.required, photoRequired: meta.photoRequired }
    });
    bumpDataVersion_({ domains: ['CONFIG'] });
    return { ok: true, code, message: existing ? '체크리스트 항목을 수정했습니다.' : '체크리스트 항목을 추가했습니다.' };
  });
}

function deleteQmChecklistItem(token, payload) { // (체크리스트 항목 삭제·과거이력 보존)
  return measureResponse_('deleteQmChecklistItem', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const code = String(payload && payload.code || '').trim();
    if (!code) throw new Error('삭제할 체크리스트 항목이 없습니다.');
    const existing = findCodeRow_(NOVA_QM_CHECKLIST.GROUP, code);
    if (!existing || existing.enabled !== 'Y') throw new Error('체크리스트 항목을 찾을 수 없습니다.');
    upsertCodeRow_(NOVA_QM_CHECKLIST.GROUP, code, existing.label, existing.order, 'N', existing.note);
    clearNovaCaches_();
    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
      businessDate: businessDateText_(),
      status: 'QM_CHECKLIST_DELETED',
      registeredBy: user.employeeNo,
      detail: { code, label: existing.label }
    });
    bumpDataVersion_({ domains: ['CONFIG'] });
    return { ok: true, message: '체크리스트 항목을 삭제했습니다. 과거 점검이력은 유지됩니다.' };
  });
}

function startQmInspection(token, payload) { // (QM 점검 시작·Realtime 상태확정 후 초안 준비)
  return measureResponse_('startQmInspection', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const realtimeStarted = safe.realtimeStarted === true;
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || user.defaultSite || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!roomNo) throw new Error('객실번호가 없습니다.');

    if (!realtimeStarted) {
      const preflightSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const preflightRowInfo = findCurrentRoomRow_(preflightSheet, businessDate, site, roomNo);
      if (preflightRowInfo
          && String(preflightRowInfo.data['QM사번'] || '').trim() !== user.employeeNo
          && typeof novaRealtimeFinalEnabled_ === 'function'
          && novaRealtimeFinalEnabled_()
          && typeof mirrorNovaRealtimeEventsToSheets_ === 'function') {
        try { mirrorNovaRealtimeEventsToSheets_(); }
        catch (syncError) { console.warn('[NOVA QM] 점검시작 전 Realtime 배정 미러 실패:', syncError); }
      }
    }

    const writeLock = acquireWriteLock_();
    try {
      const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const rowInfo = findCurrentRoomRow_(currentSheet, businessDate, site, roomNo);
      if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
      if (String(rowInfo.data['QM사번'] || '').trim() !== user.employeeNo) throw new Error('본인에게 배정된 객실만 점검할 수 있습니다.');
      const currentStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
      if (!['QM_WAITING', 'COMPLETED', 'QM_CHECKING'].includes(currentStatus)) throw new Error('QM 점검대기 또는 점검중 객실만 시작할 수 있습니다.');

      let version = realtimeStarted
        ? Number(safe.realtimeVersion || rowInfo.data['마지막변경버전'] || 0)
        : Number(rowInfo.data['마지막변경버전'] || getMobileSyncVersion_('QM', { businessDate, site }));
      if (!realtimeStarted && currentStatus !== 'QM_CHECKING') {
        version = reserveDataVersion_({ lockHeld: true });
        updateRowByHeaders_(currentSheet, rowInfo.rowNumber, {
          '청소상태': 'QM_CHECKING',
          '마지막변경버전': version,
          '수정일시': nowText_()
        });
        SpreadsheetApp.flush();
        publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });
        appendUnifiedHistory_({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate,
          site: String(rowInfo.data['사업장'] || site).trim(),
          roomNo,
          targetEmployeeNo: user.employeeNo,
          status: 'QM_START',
          registeredBy: user.employeeNo,
          startedAt: nowText_(),
          version,
          detail: {
            action: 'START', role: 'QM', beforeCleaningStatus: currentStatus,
            cleaningStatus: 'QM_CHECKING', primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
            secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim()
          }
        });
      }
      const checklist = realtimeStarted ? getQmChecklistForSubmit_() : getQmChecklistForMobile_();
      const draft = ensureQmInspectionDraft_(user, businessDate, String(rowInfo.data['사업장'] || site).trim(), roomNo, rowInfo.data, checklist);
      const refreshed = Object.assign({}, rowInfo.data, { '청소상태': 'QM_CHECKING', '마지막변경버전': version });
      return {
        ok: true,
        version,
        checklist,
        draft,
        room: realtimeStarted ? {
          businessDate,
          site: String(rowInfo.data['사업장'] || site).trim(),
          roomNo,
          roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
          cleaningStatus: 'QM_CHECKING',
          roommaidEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
          secondaryRoommaidEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
          qmEmployeeNo: user.employeeNo,
          version
        } : currentRoomObject_(refreshed, rowInfo.rowNumber, {}, getUserIndex_().byEmployeeNo),
        message: currentStatus === 'QM_CHECKING' ? '진행 중인 점검을 불러왔습니다.' : 'QM 점검을 시작했습니다.'
      };
    } finally {
      writeLock.releaseLock();
    }
  });
}

function saveQmInspectionDraft(token, payload) { // (QM 점검 실시간 자동저장·최종제출과 충돌 방지)
  return measureResponse_('saveQmInspectionDraft', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const checklist = getQmChecklistForSubmit_();
    const writeLock = acquireUserWriteLock_(); // CONCURRENT_WRITE_RESILIENCE_V1
    try {
      const draftInfo = getQmInspectionRecordById_(String(safe.draftId || '').trim(), safe.draftRowNumber);
      validateQmDraftOwnership_(draftInfo, user);
      if (String(draftInfo.data['처리상태'] || '').trim().toUpperCase() !== 'IN_PROGRESS') throw new Error('이미 완료된 점검입니다.');
      const detail = parseQmHistoryDetail_(draftInfo.data);
      const normalized = normalizeQmDraftPayload_(safe, checklist, detail);
      const savedAt = nowText_();
      const nextDetail = Object.assign({}, detail, normalized, { revision: checklist.revision, savedAt });
      updateRowByHeaders_(getRequiredSheet_(NOVA.SHEETS.HISTORY), draftInfo.rowNumber, {
        '세부내용JSON': JSON.stringify(nextDetail),
        '수정일시': savedAt
      });
      return { ok: true, draft: buildQmDraftResponse_(draftInfo, nextDetail), savedAt, message: '실시간 저장됨' };
    } finally {
      writeLock.releaseLock();
    }
  });
}

function uploadQmInspectionPhoto(token, payload) { // (QM 점검 하자사진 업로드·동시 자동저장 병합)
  return measureResponse_('uploadQmInspectionPhoto', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const initialDraft = getQmInspectionRecordById_(String(safe.draftId || '').trim());
    validateQmDraftOwnership_(initialDraft, user);
    if (String(initialDraft.data['처리상태'] || '').trim().toUpperCase() !== 'IN_PROGRESS') throw new Error('완료된 점검에는 사진을 추가할 수 없습니다.');
    const targetType = String(safe.targetType || 'ITEM').trim().toUpperCase();
    const targetCode = String(safe.targetCode || '').trim();
    if (!targetCode || !['ITEM', 'DEFECT'].includes(targetType)) throw new Error('사진을 연결할 점검 항목이 없습니다.');
    const base64 = String(safe.base64 || '').replace(/^data:[^;]+;base64,/, '');
    if (!base64) throw new Error('사진 데이터가 없습니다.');
    const bytes = Utilities.base64Decode(base64);
    if (!bytes.length || bytes.length > NOVA_QM_CHECKLIST.MAX_PHOTO_BYTES) throw new Error('사진은 2.5MB 이하로 등록하세요.');
    const mimeType = /^image\//.test(String(safe.mimeType || '')) ? String(safe.mimeType) : 'image/jpeg';
    const fileName = safeQmPhotoFileName_(safe.fileName || `${targetCode}.jpg`);
    const folder = getQmInspectionPhotoFolder_(String(initialDraft.data['업무일자'] || '').trim(), String(initialDraft.data['사업장'] || '').trim(), String(initialDraft.data['객실번호'] || '').trim());
    const file = folder.createFile(Utilities.newBlob(bytes, mimeType, fileName));
    const photo = {
      fileId: file.getId(), name: file.getName(), mimeType, size: bytes.length,
      uploadedAt: nowText_(), uploadedBy: user.employeeNo
    };
    const writeLock = acquireUserWriteLock_(); // CONCURRENT_WRITE_RESILIENCE_V1
    try {
      const draftInfo = getQmInspectionRecordById_(String(safe.draftId || '').trim());
      validateQmDraftOwnership_(draftInfo, user);
      if (String(draftInfo.data['처리상태'] || '').trim().toUpperCase() !== 'IN_PROGRESS') throw new Error('점검이 이미 완료되어 사진을 연결할 수 없습니다.');
      const detail = parseQmHistoryDetail_(draftInfo.data);
      const targetPhotos = getQmDraftTargetPhotos_(detail, targetType, targetCode, true);
      if (targetPhotos.length >= NOVA_QM_CHECKLIST.MAX_PHOTOS_PER_TARGET) throw new Error(`항목별 사진은 최대 ${NOVA_QM_CHECKLIST.MAX_PHOTOS_PER_TARGET}장입니다.`);
      targetPhotos.push(photo);
      detail.savedAt = nowText_();
      updateRowByHeaders_(getRequiredSheet_(NOVA.SHEETS.HISTORY), draftInfo.rowNumber, {
        '세부내용JSON': JSON.stringify(detail), '수정일시': detail.savedAt
      });
      return { ok: true, photo, draft: buildQmDraftResponse_(draftInfo, detail), message: '하자 사진을 등록했습니다.' };
    } catch (error) {
      try { file.setTrashed(true); } catch (ignore) {}
      throw error;
    } finally {
      writeLock.releaseLock();
    }
  });
}

function deleteQmInspectionPhoto(token, payload) { // (QM 점검 하자사진 삭제·동시 자동저장 보호)
  return measureResponse_('deleteQmInspectionPhoto', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const fileId = String(safe.fileId || '').trim();
    const writeLock = acquireUserWriteLock_(); // CONCURRENT_WRITE_RESILIENCE_V1
    let response;
    try {
      const draftInfo = getQmInspectionRecordById_(String(safe.draftId || '').trim());
      validateQmDraftOwnership_(draftInfo, user);
      if (String(draftInfo.data['처리상태'] || '').trim().toUpperCase() !== 'IN_PROGRESS') throw new Error('완료된 점검의 사진은 삭제할 수 없습니다.');
      const detail = parseQmHistoryDetail_(draftInfo.data);
      const photos = getQmDraftTargetPhotos_(detail, String(safe.targetType || 'ITEM').toUpperCase(), String(safe.targetCode || '').trim(), false);
      const index = photos.findIndex(photo => String(photo.fileId || '') === fileId);
      if (index < 0) throw new Error('사진을 찾을 수 없습니다.');
      photos.splice(index, 1);
      detail.savedAt = nowText_();
      updateRowByHeaders_(getRequiredSheet_(NOVA.SHEETS.HISTORY), draftInfo.rowNumber, {
        '세부내용JSON': JSON.stringify(detail), '수정일시': detail.savedAt
      });
      response = { ok: true, draft: buildQmDraftResponse_(draftInfo, detail), message: '사진을 삭제했습니다.' };
    } finally {
      writeLock.releaseLock();
    }
    try { DriveApp.getFileById(fileId).setTrashed(true); } catch (error) { console.warn(`QM photo trash skipped: ${error.message}`); }
    return response;
  });
}

function getQmInspectionPhoto(token, payload) { // (권한검증 후 QM 사진 미리보기)
  return measureResponse_('getQmInspectionPhoto', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const role = String(auth.user.role || '').toUpperCase();
    if (!['ADMIN', 'ORDER', 'QM'].includes(role)) throw new Error('사진을 확인할 권한이 없습니다.');
    const fileId = String(payload && payload.fileId || '').trim();
    if (!fileId) throw new Error('사진 파일이 없습니다.');
    const reference = findQmPhotoReference_(fileId);
    if (!reference) throw new Error('점검이력에서 사진을 찾을 수 없습니다.');
    if (role === 'QM' && String(reference.data['대상사번'] || '').trim() !== auth.user.employeeNo) throw new Error('본인이 등록한 점검사진만 확인할 수 있습니다.');
    const file = DriveApp.getFileById(fileId);
    const blob = file.getBlob();
    return {
      ok: true,
      fileId,
      name: file.getName(),
      mimeType: blob.getContentType(),
      dataUrl: `data:${blob.getContentType()};base64,${Utilities.base64Encode(blob.getBytes())}`
    };
  });
}

// QM_FINALIZE_PREFLIGHT_V2
// DB 최종확정 전에 기존 Apps Script 체크리스트 revision/필수값/사진/하자 규칙을 그대로 검증합니다.
// 이 함수는 운영 상태·이력·초안을 쓰지 않는 순수 preflight 입니다.
function prepareQmInspectionFinalizeDbFirst(token, payload) {
  return measureResponse_('prepareQmInspectionFinalizeDbFirst', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || user.defaultSite || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!site || !roomNo) throw new Error('QM 최종점검 식별정보가 없습니다.');

    const checklist = getQmChecklistForSubmit_();
    if (!checklist.items.length) throw new Error('사용 가능한 QM 체크리스트가 없습니다.');
    const requestedRevision = String(safe.revision || '').trim();
    if (requestedRevision && requestedRevision !== checklist.revision) {
      throw new Error('점검 중 체크리스트가 변경되었습니다. 화면을 새로고침한 뒤 다시 점검하세요.');
    }

    const normalizedDraft = normalizeQmDraftPayload_(safe, checklist, {
      answers: [],
      defects: []
    });
    const answers = validateFinalQmAnswers_(normalizedDraft.answers, checklist.items);
    const defects = validateFinalQmDefects_(normalizedDraft.defects, checklist.places);
    const itemFailCount = answers.filter(answer => String(answer.result || '').trim().toUpperCase() === 'FAIL').length;
    const resultStatus = itemFailCount || defects.length ? 'FAIL' : 'PASS';

    return {
      ok: true,
      preflight: true,
      businessDate,
      site,
      roomNo,
      revision: checklist.revision,
      answers,
      defects,
      resultStatus,
      itemFailCount,
      customDefectCount: defects.length,
      startedAt: String(safe.startedAt || '').trim(),
      qmEmployeeNo: user.employeeNo
    };
  });
}

function submitQmChecklistInspection(token, payload) { // (QM 체크리스트 최종제출·완료·재정비·실적저장)
  return measureResponse_('submitQmChecklistInspection', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || user.defaultSite || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!roomNo) throw new Error('객실번호가 없습니다.');
    // 체크리스트 조회는 읽기 작업이므로 전역 쓰기잠금 밖에서 처리한다.
    // 점검완료의 잠금 대기시간을 줄이고 다른 객실 작업을 불필요하게 막지 않는다.
    const checklist = getQmChecklistForSubmit_();
    if (!checklist.items.length) throw new Error('사용 중인 QM 체크리스트가 없습니다. 관리자 또는 오더테이커가 체크리스트를 등록해야 합니다.');
    if (safe.revision && String(safe.revision) !== checklist.revision) throw new Error('체크리스트가 변경되었습니다. 화면을 새로고침한 뒤 다시 작성하세요.');

    const writeLock = acquireWriteLock_();
    try {

    let draftInfo = null;
    if (safe.draftId) {
      draftInfo = getQmInspectionRecordById_(String(safe.draftId).trim(), safe.draftRowNumber);
      validateQmDraftOwnership_(draftInfo, user);
    }
    if (!draftInfo) {
      const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const currentRow = findCurrentRoomRow_(currentSheet, businessDate, site, roomNo);
      if (!currentRow) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
      draftInfo = { data: { '업무일자': businessDate, '사업장': site, '객실번호': roomNo, '대상사번': user.employeeNo }, rowNumber: 0 };
      draftInfo.detail = { startedAt: nowText_(), answers: [], defects: [] };
    }
    const priorDetail = draftInfo.detail || parseQmHistoryDetail_(draftInfo.data);
    const normalizedDraft = normalizeQmDraftPayload_(safe, checklist, priorDetail);
    const normalizedAnswers = validateFinalQmAnswers_(normalizedDraft.answers, checklist.items);
    const customDefects = validateFinalQmDefects_(normalizedDraft.defects, checklist.places);

    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRow_(sheet, businessDate, site, roomNo);
    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
    // QM은 본인 배정 여부와 청소상태를 잠금 안에서 다시 검증하므로, DB 미러 등 독립 변경의
    // Sheet 전체버전 증가만으로 정상 점검을 거절하지 않는다. 실제 흐름 변경은 아래 상태검증이 차단한다.
    const qmNo = String(rowInfo.data['QM사번'] || '').trim();
    if (qmNo !== user.employeeNo) throw new Error('본인에게 배정된 객실만 점검할 수 있습니다.');
    const sheetCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
    const realtimeCommitted = safe.realtimeCommitted === true;
    const allowedSubmitStatuses = realtimeCommitted
      ? ['QM_WAITING', 'COMPLETED', 'QM_CHECKING', 'QM_COMPLETED', 'REWORK']
      : ['QM_CHECKING'];
    if (!allowedSubmitStatuses.includes(sheetCleaningStatus)) throw new Error('점검중 상태의 객실에서만 체크리스트를 제출할 수 있습니다.');

    const itemDefects = normalizedAnswers.filter(item => item.result === 'FAIL').map(item => ({
      id: item.code,
      source: 'CHECKLIST',
      placeCode: item.placeCode,
      placeLabel: item.placeLabel,
      itemCode: item.code,
      itemLabel: item.label,
      note: item.note,
      photos: item.photos || []
    }));
    const defects = itemDefects.concat(customDefects);
    const passed = defects.length === 0;
    const roommaidNo = String(rowInfo.data['룸메이드사번'] || '').trim();
    const secondaryRoommaidNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
    const cleaningType = String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
    const assignmentType = String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
    const completedAt = nowText_();
    const startedAt = String(priorDetail.startedAt || draftInfo.data['등록일시'] || completedAt).trim();
    const durationMinutes = minutesBetween_(startedAt, completedAt);
    const targetCleaningStatus = 'QM_COMPLETED'; // QM_REWORK_OPERATIONAL_STATUS_V1 · FAIL은 품질자료만 기록
    const updates = { '청소상태': targetCleaningStatus, '수정일시': completedAt };
    // Realtime이 이미 같은 최종상태를 Sheet에 미러했다면 상태행을 다시 쓰지 않는다.
    // 아직 미러 전이면 기존과 동일하게 Sheet도 즉시 최종상태로 맞춘다.
    let version = Number(rowInfo.data['마지막변경버전'] || 0);
    if (sheetCleaningStatus !== targetCleaningStatus) {
      version = reserveDataVersion_({ lockHeld: true });
      updates['마지막변경버전'] = version;
      updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
      SpreadsheetApp.flush();
      publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });
    }

    const failSummary = defects.map(item => `${item.placeLabel || '기타'} · ${item.itemLabel || '하자'}${item.note ? `: ${item.note}` : ''}`).join(' / ');
    const locationSummary = buildQmDefectLocationSummary_(defects);
    const finalDetail = Object.assign({}, priorDetail, {
      revision: checklist.revision,
      result: passed ? 'PASS' : 'FAIL',
      qualityOnly: true,
      reworkRequested: false,
      startedAt,
      completedAt,
      durationMinutes,
      answers: normalizedAnswers,
      defects,
      failedCount: defects.length,
      failSummary,
      locationSummary,
      photoCount: defects.reduce((sum, defect) => sum + (defect.photos || []).length, 0),
      roommaidEmployeeNo: roommaidNo,
      secondaryRoommaidEmployeeNo: secondaryRoommaidNo,
      qmEmployeeNo: user.employeeNo,
      cleaningType,
      assignmentType,
      realtimeRequestId: String(safe.realtimeRequestId || '').trim(),
      realtimeVersion: Number(safe.realtimeVersion || 0)
    });
    let checklistRecordId = String(draftInfo.data['기록ID'] || '').trim();
    if (draftInfo.rowNumber) {
      updateRowByHeaders_(getRequiredSheet_(NOVA.SHEETS.HISTORY), draftInfo.rowNumber, {
        '처리상태': passed ? 'PASS' : 'FAIL',
        '세부내용JSON': JSON.stringify(finalDetail),
        '수정일시': completedAt,
        '처리시작일시': startedAt,
        '완료일시': completedAt,
        '변경버전': version
      });
    } else {
      checklistRecordId = `QMCL-${businessDate.replace(/-/g, '')}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;
      appendUnifiedHistory_({
        recordId: checklistRecordId,
        recordType: NOVA.RECORD_TYPES.QM_CHECKLIST,
        businessDate,
        site: String(rowInfo.data['사업장'] || site).trim(),
        roomNo,
        targetEmployeeNo: user.employeeNo,
        status: passed ? 'PASS' : 'FAIL',
        registeredBy: user.employeeNo,
        startedAt,
        completedAt,
        version,
        detail: finalDetail
      });
    }
    appendUnifiedHistory_({
      recordType: NOVA.RECORD_TYPES.QM,
      businessDate,
      site: String(rowInfo.data['사업장'] || site).trim(),
      roomNo,
      targetEmployeeNo: user.employeeNo,
      status: 'QM_COMPLETE',
      registeredBy: user.employeeNo,
      startedAt,
      completedAt,
      version,
      detail: {
        action: 'COMPLETE', role: 'QM', qualityResult: passed ? 'PASS' : 'FAIL', reason: failSummary,
        checklistRecordId, checklistRevision: checklist.revision, failedCount: defects.length,
        durationMinutes, locationSummary,
        beforeCleaningStatus: rowInfo.data['청소상태'],
        previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
        sourceRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
        roomStatus: updates['객실상태'] || rowInfo.data['객실상태'],
        cleaningStatus: updates['청소상태'], cleaningType, assignmentType,
        primaryEmployeeNo: roommaidNo, secondaryEmployeeNo: secondaryRoommaidNo,
        creditUnit: cleaningType === NOVA.CLEANING_TYPES.DS ? getCleaningCreditUnit_(NOVA.CLEANING_TYPES.DS) : 1
      }
    });

    // 체크리스트 FAIL은 품질자료 전용이며 룸메이드 재정비 알림을 생성하지 않습니다.

    const refreshed = Object.assign({}, rowInfo.data, updates);
    return {
      ok: true,
      passed,
      failedCount: defects.length,
      checklistRecordId,
      durationMinutes,
      version,
      room: {
        businessDate,
        site: String(rowInfo.data['사업장'] || site).trim(),
        roomNo,
        roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
        cleaningStatus: String(updates['청소상태'] || '').trim(),
        roommaidEmployeeNo: roommaidNo,
        secondaryRoommaidEmployeeNo: secondaryRoommaidNo,
        qmEmployeeNo: user.employeeNo,
        version
      },
      message: passed ? `QM 점검을 완료했습니다. (${durationMinutes == null ? '-' : durationMinutes}분)` : `QM 점검을 완료했습니다. (불량 ${defects.length}건 기록 · ${durationMinutes == null ? '-' : durationMinutes}분)`
    };
     } finally {
      writeLock.releaseLock();
    }
  });
}

function getQmInspectionAnalytics(token, filters) { // (QM·룸메이드 점검이력·실적 조회)
  return measureResponse_('getQmInspectionAnalytics', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER', 'QM']);
    const request = normalizeQmAnalyticsFilters_(filters, user);
    const rows = readQmChecklistHistoryRows_(request);
    const analytics = buildQmQualityAnalyticsFromHistoryRows_(rows, getUserIndex_().byEmployeeNo, request);
    return Object.assign({ ok: true, filters: request, serverTime: nowText_() }, analytics);
  });
}


function getQmChecklistForSubmit_() { // (QM 최종제출용 읽기전용 체크리스트 고속조회)
  const rows = readAllCodeRows_();
  const places = rows
    .filter(row => row.group === NOVA_QM_CHECKLIST.PLACE_GROUP && row.enabled === 'Y')
    .map(row => ({ code: row.code, label: row.label, order: Number(row.order || 9999) }))
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'ko'));
  const placeMap = {};
  places.forEach(place => { placeMap[place.code] = place; });
  const items = rows
    .filter(row => row.group === NOVA_QM_CHECKLIST.GROUP && row.enabled === 'Y')
    .map(row => qmChecklistItemFromCodeRow_(row, placeMap))
    .sort((a, b) => a.placeOrder - b.placeOrder || a.order - b.order || a.label.localeCompare(b.label, 'ko'));
  return {
    places,
    items,
    groups: places.map(place => ({ place, items: items.filter(item => item.placeCode === place.code) })).filter(group => group.items.length),
    revision: buildQmChecklistRevision_(items, places),
    maxPhotosPerTarget: NOVA_QM_CHECKLIST.MAX_PHOTOS_PER_TARGET
  };
}

function getQmChecklistForMobile_() { // (QM 모바일 장소별 체크리스트 조회)
  seedQmChecklistPlaces_();
  seedQmChecklistCodes_();
  migrateQmChecklistLocations_();
  const places = getActiveQmChecklistPlaces_();
  const items = getActiveQmChecklistItems_();
  return {
    places,
    items,
    groups: places.map(place => ({ place, items: items.filter(item => item.placeCode === place.code) })).filter(group => group.items.length),
    revision: buildQmChecklistRevision_(items, places),
    maxPhotosPerTarget: NOVA_QM_CHECKLIST.MAX_PHOTOS_PER_TARGET
  };
}

function getActiveQmChecklistPlaces_() { // (사용 중 점검 장소)
  return readAllCodeRows_()
    .filter(row => row.group === NOVA_QM_CHECKLIST.PLACE_GROUP && row.enabled === 'Y')
    .map(row => ({ code: row.code, label: row.label, order: Number(row.order || 9999) }))
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'ko'));
}

function getActiveQmChecklistItems_() { // (사용 중 체크리스트 항목)
  const places = getActiveQmChecklistPlaces_();
  const placeMap = {};
  places.forEach(place => { placeMap[place.code] = place; });
  return readAllCodeRows_()
    .filter(row => row.group === NOVA_QM_CHECKLIST.GROUP && row.enabled === 'Y')
    .map(row => qmChecklistItemFromCodeRow_(row, placeMap))
    .sort((a, b) => a.placeOrder - b.placeOrder || a.order - b.order || a.label.localeCompare(b.label, 'ko'));
}

function qmChecklistItemFromCodeRow_(row, placeMap) { // (코드설정 행을 장소 포함 체크리스트로 변환)
  const meta = parseQmChecklistNote_(row.note);
  const place = (placeMap || {})[meta.placeCode] || { code: meta.placeCode || 'OVERALL', label: '객실 전체', order: 9999 };
  return {
    code: row.code,
    label: row.label,
    order: Number(row.order || 9999),
    placeCode: place.code,
    placeLabel: place.label,
    placeOrder: Number(place.order || 9999),
    required: meta.required !== false,
    photoRequired: meta.photoRequired === true
  };
}

function parseQmChecklistNote_(note) { // (체크리스트 메타정보 해석)
  try {
    const parsed = JSON.parse(String(note || '{}'));
    return {
      placeCode: String(parsed.placeCode || 'OVERALL').trim().toUpperCase(),
      required: parsed.required !== false,
      photoRequired: parsed.photoRequired === true
    };
  } catch (error) {
    return { placeCode: 'OVERALL', required: true, photoRequired: false };
  }
}

function buildQmChecklistRevision_(items, places) { // (장소·항목 변경버전 서명)
  const canonical = {
    places: (places || []).map(place => [place.code, place.label, place.order]),
    items: (items || []).map(item => [item.code, item.label, item.placeCode, item.order, item.required ? 1 : 0, item.photoRequired ? 1 : 0])
  };
  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, JSON.stringify(canonical), Utilities.Charset.UTF_8);
  return Utilities.base64EncodeWebSafe(bytes).replace(/=+$/g, '').slice(0, 24);
}

function seedQmChecklistPlaces_() { // (기본 점검 장소 보완)
  const existing = new Set(readAllCodeRows_().filter(row => row.group === NOVA_QM_CHECKLIST.PLACE_GROUP).map(row => row.code));
  let added = 0;
  NOVA_QM_CHECKLIST.DEFAULT_PLACES.forEach(place => {
    if (existing.has(place.code)) return;
    upsertCodeRow_(NOVA_QM_CHECKLIST.PLACE_GROUP, place.code, place.label, place.order, 'Y', '');
    added += 1;
  });
  if (added) clearNovaCaches_();
  return { added };
}

function seedQmChecklistCodes_() { // (기본 QM 체크리스트 보완)
  seedQmChecklistPlaces_();
  const existing = new Set(readAllCodeRows_().filter(row => row.group === NOVA_QM_CHECKLIST.GROUP).map(row => row.code));
  let added = 0;
  NOVA_QM_CHECKLIST.DEFAULT_ITEMS.forEach(item => {
    if (existing.has(item.code)) return;
    upsertCodeRow_(NOVA_QM_CHECKLIST.GROUP, item.code, item.label, item.order, 'Y', JSON.stringify({ placeCode: item.placeCode, required: true, photoRequired: false }));
    added += 1;
  });
  if (added) clearNovaCaches_();
  return { added };
}

function migrateQmChecklistLocations_() { // (RC2 항목의 장소 자동분류)
  const rows = readAllCodeRows_().filter(row => row.group === NOVA_QM_CHECKLIST.GROUP);
  let changed = 0;
  rows.forEach(row => {
    const meta = parseQmChecklistNote_(row.note);
    let placeCode = meta.placeCode;
    const raw = String(row.note || '');
    if (!raw.includes('placeCode')) placeCode = inferQmPlaceCodeFromLabel_(row.label);
    if (raw.includes('placeCode') && placeCode) return;
    upsertCodeRow_(NOVA_QM_CHECKLIST.GROUP, row.code, row.label, row.order, row.enabled, JSON.stringify({
      placeCode: placeCode || 'OVERALL', required: meta.required !== false, photoRequired: meta.photoRequired === true
    }));
    changed += 1;
  });
  if (changed) clearNovaCaches_();
  return changed;
}

function inferQmPlaceCodeFromLabel_(label) { // (기존 항목명 장소 추론)
  const text = String(label || '');
  if (/현관|입구|신발/.test(text)) return 'ENTRANCE';
  if (/주방|싱크|식기|냉장/.test(text)) return 'KITCHEN';
  if (/욕실|화장실|배수|변기|샤워/.test(text)) return 'BATHROOM';
  if (/침구|이불|베개|침대/.test(text)) return 'BED_LINEN';
  if (/바닥|먼지|머리카락/.test(text)) return 'FLOOR';
  if (/거울|유리|가구/.test(text)) return 'FURNITURE';
  if (/소모품|비품|세팅/.test(text)) return 'AMENITY';
  if (/시설|하자|파손/.test(text)) return 'FACILITY';
  if (/냄새|환기|침실/.test(text)) return 'BEDROOM';
  return 'OVERALL';
}

function ensureQmInspectionDraft_(user, businessDate, site, roomNo, roomData, checklist) { // (진행중 초안 조회·생성)
  const existing = findActiveQmInspectionDraft_(businessDate, site, roomNo, user.employeeNo);
  if (existing) return buildQmDraftResponse_(existing, parseQmHistoryDetail_(existing.data));
  const startedAt = nowText_();
  const detail = {
    revision: checklist.revision,
    startedAt,
    savedAt: startedAt,
    answers: [],
    defects: [],
    roommaidEmployeeNo: String(roomData['룸메이드사번'] || '').trim(),
    secondaryRoommaidEmployeeNo: String(roomData['보조룸메이드사번'] || '').trim(),
    qmEmployeeNo: user.employeeNo,
    cleaningType: String(roomData['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
    assignmentType: String(roomData['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase()
  };
  const recordId = `QMDRAFT-${businessDate.replace(/-/g, '')}-${Utilities.getUuid().slice(0, 10).toUpperCase()}`;
  appendUnifiedHistory_({
    recordId,
    recordType: NOVA.RECORD_TYPES.QM_CHECKLIST,
    businessDate,
    site,
    roomNo,
    targetEmployeeNo: user.employeeNo,
    status: 'IN_PROGRESS',
    registeredBy: user.employeeNo,
    startedAt,
    detail
  });
  const created = getQmInspectionRecordById_(recordId);
  return buildQmDraftResponse_(created, detail);
}

function findActiveQmInspectionDraft_(businessDate, site, roomNo, employeeNo) { // (객실별 최근 진행중 초안)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  const headerMap = getHeaderMap_(sheet);
  const scanStart = Math.max(2, lastRow - NOVA_QM_CHECKLIST.HISTORY_SCAN_ROWS + 1);
  const count = lastRow - scanStart + 1;
  const values = sheet.getRange(scanStart, 1, count, sheet.getLastColumn()).getDisplayValues();
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const data = rowObjectFromValues_(values[index], headerMap);
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.QM_CHECKLIST) continue;
    if (String(data['처리상태'] || '').trim().toUpperCase() !== 'IN_PROGRESS') continue;
    if (String(data['업무일자'] || '').trim() !== businessDate) continue;
    if (site && String(data['사업장'] || '').trim() !== site) continue;
    if (String(data['객실번호'] || '').trim() !== roomNo) continue;
    if (String(data['대상사번'] || '').trim() !== employeeNo) continue;
    if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') continue;
    return { rowNumber: scanStart + index, data };
  }
  return null;
}

function getQmInspectionRecordById_(recordId, preferredRowNumber) { // (점검기록 ID 고속조회·직접행 검증)
  if (!recordId) throw new Error('점검기록 ID가 없습니다.');
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const headerMap = getHeaderMap_(sheet);
  const idColumn = headerMap['기록ID'];
  if (!idColumn) throw new Error('업무이력 기록ID 열이 없습니다.');
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) throw new Error('QM 점검기록을 찾을 수 없습니다.');

  const preferred = Number(preferredRowNumber || 0);
  if (preferred >= 2 && preferred <= lastRow) {
    const preferredId = String(sheet.getRange(preferred, idColumn).getDisplayValue() || '').trim();
    if (preferredId === recordId) {
      const row = sheet.getRange(preferred, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
      return { rowNumber: preferred, data: rowObjectFromValues_(row, headerMap) };
    }
  }

  const recentCount = Math.min(NOVA_QM_CHECKLIST.HISTORY_SCAN_ROWS, lastRow - 1);
  const recentStart = lastRow - recentCount + 1;
  let match = sheet.getRange(recentStart, idColumn, recentCount, 1)
    .createTextFinder(recordId).matchEntireCell(true).findNext();
  if (!match && recentStart > 2) {
    match = sheet.getRange(2, idColumn, recentStart - 2, 1)
      .createTextFinder(recordId).matchEntireCell(true).findNext();
  }
  if (!match) throw new Error('QM 점검기록을 찾을 수 없습니다.');
  const rowNumber = match.getRow();
  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
  return { rowNumber, data: rowObjectFromValues_(row, headerMap) };
}

function validateQmDraftOwnership_(draftInfo, user) { // (QM 초안 소유권 검증)
  if (!draftInfo || String(draftInfo.data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.QM_CHECKLIST) throw new Error('QM 점검기록이 아닙니다.');
  if (String(draftInfo.data['대상사번'] || '').trim() !== user.employeeNo) throw new Error('본인의 점검기록만 수정할 수 있습니다.');
}

function parseQmHistoryDetail_(data) { // (QM 이력 JSON 해석)
  try { return JSON.parse(String(data && data['세부내용JSON'] || '{}')) || {}; } catch (error) { return {}; }
}

function buildQmDraftResponse_(draftInfo, detail) { // (클라이언트용 점검 초안)
  return {
    draftId: String(draftInfo.data['기록ID'] || '').trim(),
    rowNumber: Number(draftInfo.rowNumber || 0),
    businessDate: String(draftInfo.data['업무일자'] || '').trim(),
    site: String(draftInfo.data['사업장'] || '').trim(),
    roomNo: String(draftInfo.data['객실번호'] || '').trim(),
    status: String(draftInfo.data['처리상태'] || '').trim(),
    startedAt: String(detail.startedAt || draftInfo.data['처리시작일시'] || draftInfo.data['등록일시'] || '').trim(),
    savedAt: String(detail.savedAt || draftInfo.data['수정일시'] || '').trim(),
    answers: Array.isArray(detail.answers) ? detail.answers : [],
    defects: Array.isArray(detail.defects) ? detail.defects : []
  };
}

function normalizeQmDraftPayload_(safe, checklist, priorDetail) { // (초안 답변·추가하자 정규화)
  const itemMap = {};
  (checklist.items || []).forEach(item => { itemMap[item.code] = item; });
  const previousAnswerMap = {};
  (priorDetail.answers || []).forEach(answer => { previousAnswerMap[answer.code] = answer; });
  const incoming = Array.isArray(safe.answers) ? safe.answers : (priorDetail.answers || []);
  const answers = incoming.map(answer => {
    const code = String(answer && answer.code || '').trim();
    const item = itemMap[code];
    if (!item) return null;
    const previous = previousAnswerMap[code] || {};
    const photos = sanitizeQmPhotos_(Array.isArray(answer.photos) ? answer.photos : previous.photos);
    return {
      code,
      label: item.label,
      placeCode: item.placeCode,
      placeLabel: item.placeLabel,
      order: item.order,
      required: item.required,
      photoRequired: item.photoRequired,
      result: String(answer.result || '').trim().toUpperCase(),
      note: String(answer.note || '').trim(),
      photos
    };
  }).filter(Boolean);
  const priorDefects = {};
  (priorDetail.defects || []).forEach(defect => { priorDefects[defect.id] = defect; });
  const defects = (Array.isArray(safe.defects) ? safe.defects : (priorDetail.defects || [])).map(defect => {
    const id = String(defect && defect.id || `DEF-${Utilities.getUuid().slice(0, 8).toUpperCase()}`).trim();
    const previous = priorDefects[id] || {};
    const placeCode = String(defect.placeCode || previous.placeCode || '').trim().toUpperCase();
    const place = (checklist.places || []).find(item => item.code === placeCode);
    return {
      id,
      source: 'CUSTOM',
      placeCode,
      placeLabel: place ? place.label : String(defect.placeLabel || previous.placeLabel || '기타').trim(),
      itemLabel: String(defect.itemLabel || previous.itemLabel || '추가 하자').trim(),
      note: String(defect.note || '').trim(),
      photos: sanitizeQmPhotos_(Array.isArray(defect.photos) ? defect.photos : previous.photos)
    };
  });
  return { answers, defects };
}

function validateFinalQmAnswers_(answers, checklistItems) { // (최종 체크리스트 필수값 검증)
  const answerMap = {};
  (answers || []).forEach(answer => { answerMap[answer.code] = answer; });
  return (checklistItems || []).map(item => {
    const answer = answerMap[item.code] || {};
    const result = String(answer.result || '').trim().toUpperCase();
    const allowed = item.required ? ['PASS', 'FAIL'] : ['PASS', 'FAIL', 'SKIP'];
    if (!allowed.includes(result)) throw new Error(`${item.placeLabel} · ${item.label} 항목의 점검결과를 선택하세요.`);
    const note = String(answer.note || '').trim();
    const photos = sanitizeQmPhotos_(answer.photos);
    if (result === 'FAIL' && !note) throw new Error(`${item.placeLabel} · ${item.label} 불량 내용을 입력하세요.`);
    if (item.photoRequired && !photos.length) throw new Error(`${item.placeLabel} · ${item.label} 항목의 사진을 등록하세요.`);
    return Object.assign({}, item, { result, note, photos });
  });
}

function validateFinalQmDefects_(defects, places) { // (추가 하자 검증)
  return (defects || []).map(defect => {
    const placeCode = String(defect.placeCode || '').trim().toUpperCase();
    const place = (places || []).find(item => item.code === placeCode);
    if (!place) throw new Error('추가 하자의 장소를 선택하세요.');
    const note = String(defect.note || '').trim();
    if (!note) throw new Error(`${place.label} 추가 하자 내용을 입력하세요.`);
    const photos = sanitizeQmPhotos_(defect.photos);
    if (!photos.length) throw new Error(`${place.label} 추가 하자 사진을 1장 이상 등록하세요.`);
    return {
      id: String(defect.id || `DEF-${Utilities.getUuid().slice(0, 8).toUpperCase()}`).trim(),
      source: 'CUSTOM', placeCode, placeLabel: place.label,
      itemLabel: String(defect.itemLabel || '추가 하자').trim(), note, photos
    };
  });
}

function sanitizeQmPhotos_(photos) { // (사진 메타정보 안전 정리)
  return (Array.isArray(photos) ? photos : []).slice(0, NOVA_QM_CHECKLIST.MAX_PHOTOS_PER_TARGET).map(photo => ({
    fileId: String(photo && photo.fileId || '').trim(),
    name: String(photo && photo.name || '').trim(),
    mimeType: String(photo && photo.mimeType || '').trim(),
    size: Number(photo && photo.size || 0),
    uploadedAt: String(photo && photo.uploadedAt || '').trim(),
    uploadedBy: String(photo && photo.uploadedBy || '').trim()
  })).filter(photo => photo.fileId);
}

function getQmDraftTargetPhotos_(detail, targetType, targetCode, createMissing) { // (초안 대상 사진배열 조회)
  if (!Array.isArray(detail.answers)) detail.answers = [];
  if (!Array.isArray(detail.defects)) detail.defects = [];
  if (targetType === 'ITEM') {
    let answer = detail.answers.find(item => String(item.code || '') === targetCode);
    if (!answer && createMissing) {
      const checklistItem = getActiveQmChecklistItems_().find(item => item.code === targetCode);
      if (!checklistItem) throw new Error('체크리스트 항목을 찾을 수 없습니다.');
      answer = Object.assign({}, checklistItem, { result: '', note: '', photos: [] });
      detail.answers.push(answer);
    }
    if (!answer) throw new Error('체크리스트 항목을 찾을 수 없습니다.');
    if (!Array.isArray(answer.photos)) answer.photos = [];
    return answer.photos;
  }
  let defect = detail.defects.find(item => String(item.id || '') === targetCode);
  if (!defect && createMissing) {
    defect = { id: targetCode, source: 'CUSTOM', placeCode: '', placeLabel: '', itemLabel: '추가 하자', note: '', photos: [] };
    detail.defects.push(defect);
  }
  if (!defect) throw new Error('추가 하자를 찾을 수 없습니다.');
  if (!Array.isArray(defect.photos)) defect.photos = [];
  return defect.photos;
}

function safeQmPhotoFileName_(value) { // (Drive 사진 파일명 정리)
  const base = String(value || 'qm-photo.jpg').replace(/[\\/:*?"<>|#%{}~]/g, '_').slice(0, 90);
  return `${Utilities.formatDate(new Date(), NOVA.TIMEZONE, 'HHmmss')}_${base}`;
}

function getQmInspectionPhotoFolder_(businessDate, site, roomNo) { // (점검사진 날짜·사업장·객실 폴더)
  const props = PropertiesService.getScriptProperties();
  let root = null;
  const rootId = props.getProperty(NOVA_QM_CHECKLIST.PHOTO_ROOT_PROPERTY);
  if (rootId) {
    try { root = DriveApp.getFolderById(rootId); } catch (error) { root = null; }
  }
  if (!root) {
    root = DriveApp.createFolder('NOVA_QM_점검사진');
    props.setProperty(NOVA_QM_CHECKLIST.PHOTO_ROOT_PROPERTY, root.getId());
  }
  const dateFolder = getOrCreateChildFolder_(root, businessDate || businessDateText_());
  const siteFolder = getOrCreateChildFolder_(dateFolder, String(site || '미지정').replace(/[\\/:*?"<>|]/g, '_'));
  return getOrCreateChildFolder_(siteFolder, String(roomNo || '미지정').replace(/\D/g, '') || '미지정');
}

function getOrCreateChildFolder_(parent, name) { // (Drive 하위폴더 조회·생성)
  const folders = parent.getFoldersByName(name);
  return folders.hasNext() ? folders.next() : parent.createFolder(name);
}

function findQmPhotoReference_(fileId) { // (사진 파일ID가 포함된 점검이력 조회)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  const headerMap = getHeaderMap_(sheet);
  const scanStart = Math.max(2, lastRow - NOVA_QM_CHECKLIST.HISTORY_SCAN_ROWS + 1);
  const count = lastRow - scanStart + 1;
  const detailColumn = headerMap['세부내용JSON'];
  const typeColumn = headerMap['기록구분'];
  if (!detailColumn || !typeColumn) return null;
  const details = sheet.getRange(scanStart, detailColumn, count, 1).getDisplayValues();
  const types = sheet.getRange(scanStart, typeColumn, count, 1).getDisplayValues();
  for (let index = count - 1; index >= 0; index -= 1) {
    if (String(types[index][0] || '').trim() !== NOVA.RECORD_TYPES.QM_CHECKLIST) continue;
    if (!String(details[index][0] || '').includes(fileId)) continue;
    const rowNumber = scanStart + index;
    const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
    return { rowNumber, data: rowObjectFromValues_(row, headerMap) };
  }
  return null;
}

function buildQmDefectLocationSummary_(defects) { // (장소별 하자 건수)
  const counts = {};
  (defects || []).forEach(defect => {
    const code = String(defect.placeCode || 'OTHER').trim();
    if (!counts[code]) counts[code] = { code, label: String(defect.placeLabel || '기타').trim(), count: 0 };
    counts[code].count += 1;
  });
  return Object.values(counts).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'ko'));
}

function normalizeQmAnalyticsFilters_(filters, user) { // (QM 품질실적 조회조건)
  const safe = filters || {};
  const today = businessDateText_();
  const period = String(safe.period || 'DAILY').trim().toUpperCase() === 'MONTHLY' ? 'MONTHLY' : 'DAILY';
  const date = normalizeBusinessDate_(safe.date || today);
  const year = Math.max(2020, Math.min(2100, Number(safe.year || date.slice(0, 4))));
  const month = Math.max(1, Math.min(12, Number(safe.month || date.slice(5, 7))));
  return {
    period,
    date,
    year,
    month,
    site: String(safe.site || '').trim(),
    qmEmployeeNo: String(safe.qmEmployeeNo || (String(user && user.role || '').toUpperCase() === 'QM' ? user.employeeNo : '')).trim(),
    roommaidEmployeeNo: String(safe.roommaidEmployeeNo || '').trim()
  };
}

function readQmChecklistHistoryRows_(request) { // (최종 QM 체크리스트 기간별 조회)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const rowCount = lastRow - 1;
  const typeColumn = headerMap['기록구분'];
  const dateColumn = headerMap['업무일자'];
  const statusColumn = headerMap['처리상태'];
  const deletedColumn = headerMap['삭제여부'];
  const types = sheet.getRange(2, typeColumn, rowCount, 1).getDisplayValues();
  const dates = sheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const statuses = sheet.getRange(2, statusColumn, rowCount, 1).getDisplayValues();
  const deleted = deletedColumn ? sheet.getRange(2, deletedColumn, rowCount, 1).getDisplayValues() : Array.from({ length: rowCount }, () => ['N']);
  const prefix = `${request.year}-${String(request.month).padStart(2, '0')}-`;
  const rows = [];
  for (let index = 0; index < rowCount; index += 1) {
    if (String(types[index][0] || '').trim() !== NOVA.RECORD_TYPES.QM_CHECKLIST) continue;
    if (!['PASS', 'FAIL'].includes(String(statuses[index][0] || '').trim().toUpperCase())) continue;
    const date = String(dates[index][0] || '').trim();
    if (request.period === 'DAILY' ? date !== request.date : !date.startsWith(prefix)) continue;
    if (String(deleted[index][0] || 'N').trim().toUpperCase() === 'Y') continue;
    rows.push(index + 2);
  }
  if (!rows.length) return [];
  return readRowsByNumbersForClose_(sheet, headerMap, rows);
}

function buildQmQualityAnalyticsFromHistoryRows_(historyRows, users, filters) { // (QM·룸메이드 품질실적 집계)
  const request = filters || {};
  const inspections = [];
  (historyRows || []).forEach(data => {
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.QM_CHECKLIST) return;
    const status = String(data['처리상태'] || '').trim().toUpperCase();
    if (!['PASS', 'FAIL'].includes(status)) return;
    const detail = parseQmHistoryDetail_(data);
    const qmEmployeeNo = String(detail.qmEmployeeNo || data['대상사번'] || '').trim();
    const roommaidNos = Array.from(new Set([
      String(detail.roommaidEmployeeNo || '').trim(),
      String(detail.secondaryRoommaidEmployeeNo || '').trim()
    ].filter(Boolean)));
    const site = String(data['사업장'] || '').trim();
    if (request.site && site !== request.site) return;
    if (request.qmEmployeeNo && qmEmployeeNo !== request.qmEmployeeNo) return;
    if (request.roommaidEmployeeNo && !roommaidNos.includes(request.roommaidEmployeeNo)) return;
    let defects = Array.isArray(detail.defects) ? detail.defects : [];
    if (!defects.length && Array.isArray(detail.answers)) {
      defects = detail.answers.filter(answer => answer.result === 'FAIL').map(answer => ({
        placeCode: answer.placeCode, placeLabel: answer.placeLabel, itemLabel: answer.label,
        note: answer.note, photos: answer.photos || []
      }));
    }
    inspections.push({
      recordId: String(data['기록ID'] || '').trim(),
      businessDate: String(data['업무일자'] || '').trim(),
      site,
      roomNo: String(data['객실번호'] || '').trim(),
      qmEmployeeNo,
      qmName: users[qmEmployeeNo] ? users[qmEmployeeNo].name : qmEmployeeNo,
      roommaidEmployeeNos: roommaidNos,
      roommaidNames: roommaidNos.map(no => users[no] ? users[no].name : no),
      status,
      startedAt: String(detail.startedAt || data['처리시작일시'] || '').trim(),
      completedAt: String(detail.completedAt || data['완료일시'] || data['수정일시'] || '').trim(),
      durationMinutes: Number.isFinite(Number(detail.durationMinutes)) ? Number(detail.durationMinutes) : minutesBetween_(String(detail.startedAt || data['처리시작일시'] || ''), String(detail.completedAt || data['완료일시'] || data['수정일시'] || '')),
      defectCount: defects.length,
      defects,
      photoCount: defects.reduce((sum, defect) => sum + (Array.isArray(defect.photos) ? defect.photos.length : 0), 0)
    });
  });

  const qmMap = {};
  const roommaidMap = {};
  const locationMap = {};
  inspections.forEach(inspection => {
    if (inspection.qmEmployeeNo) {
      if (!qmMap[inspection.qmEmployeeNo]) qmMap[inspection.qmEmployeeNo] = {
        employeeNo: inspection.qmEmployeeNo, name: inspection.qmName, inspections: 0,
        failedInspections: 0, defectCount: 0, durations: [], dailyCounts: {}
      };
      const qm = qmMap[inspection.qmEmployeeNo];
      qm.inspections += 1;
      if (inspection.status === 'FAIL') qm.failedInspections += 1;
      qm.defectCount += inspection.defectCount;
      if (Number.isFinite(inspection.durationMinutes)) qm.durations.push(inspection.durationMinutes);
      qm.dailyCounts[inspection.businessDate] = (qm.dailyCounts[inspection.businessDate] || 0) + 1;
    }
    inspection.roommaidEmployeeNos.forEach(employeeNo => {
      if (!roommaidMap[employeeNo]) roommaidMap[employeeNo] = {
        employeeNo, name: users[employeeNo] ? users[employeeNo].name : employeeNo,
        inspectionCount: 0, defectCount: 0, locationCounts: {}, majorDefects: []
      };
      const roommaid = roommaidMap[employeeNo];
      roommaid.inspectionCount += 1;
      roommaid.defectCount += inspection.defectCount;
      inspection.defects.forEach(defect => {
        const code = String(defect.placeCode || 'OTHER').trim();
        const label = String(defect.placeLabel || '기타').trim();
        if (!roommaid.locationCounts[code]) roommaid.locationCounts[code] = { code, label, count: 0 };
        roommaid.locationCounts[code].count += 1;
        if (roommaid.majorDefects.length < 30) roommaid.majorDefects.push({
          businessDate: inspection.businessDate, roomNo: inspection.roomNo,
          placeLabel: label, itemLabel: String(defect.itemLabel || '하자').trim(), note: String(defect.note || '').trim()
        });
      });
    });
    inspection.defects.forEach(defect => {
      const code = String(defect.placeCode || 'OTHER').trim();
      if (!locationMap[code]) locationMap[code] = { code, label: String(defect.placeLabel || '기타').trim(), count: 0 };
      locationMap[code].count += 1;
    });
  });

  const durations = inspections.map(item => item.durationMinutes).filter(Number.isFinite);
  return {
    summary: {
      inspections: inspections.length,
      passed: inspections.filter(item => item.status === 'PASS').length,
      failed: inspections.filter(item => item.status === 'FAIL').length,
      defectCount: inspections.reduce((sum, item) => sum + item.defectCount, 0),
      photoCount: inspections.reduce((sum, item) => sum + item.photoCount, 0),
      averageMinutes: durations.length ? roundQmNumber_(durations.reduce((sum, value) => sum + value, 0) / durations.length) : null
    },
    qmManagers: Object.values(qmMap).map(item => ({
      employeeNo: item.employeeNo, name: item.name,
      inspections: item.inspections, failedInspections: item.failedInspections,
      defectCount: item.defectCount,
      averageMinutes: item.durations.length ? roundQmNumber_(item.durations.reduce((sum, value) => sum + value, 0) / item.durations.length) : null,
      dailyCounts: Object.keys(item.dailyCounts).sort().map(date => ({ date, count: item.dailyCounts[date] }))
    })).sort((a, b) => b.inspections - a.inspections || a.name.localeCompare(b.name, 'ko')),
    roommaids: Object.values(roommaidMap).map(item => {
      const locations = Object.values(item.locationCounts).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'ko'));
      return {
        employeeNo: item.employeeNo, name: item.name,
        inspectionCount: item.inspectionCount, defectCount: item.defectCount,
        defectRate: item.inspectionCount ? roundQmNumber_(item.defectCount / item.inspectionCount) : 0,
        locations,
        topLocations: locations.slice(0, 5).map(row => `${row.label} ${row.count}건`).join(', '),
        majorDefects: item.majorDefects.slice(0, 10)
      };
    }).sort((a, b) => b.defectCount - a.defectCount || b.inspectionCount - a.inspectionCount || a.name.localeCompare(b.name, 'ko')),
    locations: Object.values(locationMap).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'ko')),
    inspections: inspections.sort((a, b) => String(b.completedAt).localeCompare(String(a.completedAt))).slice(0, 500)
  };
}

function roundQmNumber_(value) { // (QM 통계 소수점 1자리)
  return Math.round(Number(value || 0) * 10) / 10;
}
