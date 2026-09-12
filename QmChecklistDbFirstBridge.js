/** NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1 */
const NOVA_QM_CHECKLIST_DB_FIRST_V1 = Object.freeze({
  MARKER: 'NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1',
  MIRROR_PREFIX: 'NOVA_QM_CHECKLIST_DB_MIRROR_PENDING_V1_'
});

function novaQmChecklistDbRead_(token) {
  return novaDbFirstRpc_(token, 'nova_qm_checklist_codes_read_v1', {}, {
    readOnly: true,
    allowLegacyFallback: true
  });
}

function novaQmChecklistParseNote_(note) {
  try {
    const parsed = JSON.parse(String(note || '{}'));
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (ignore) {
    return {};
  }
}

function novaQmChecklistDefinitionFromDb_(db) {
  const rows = Array.isArray(db && db.items) ? db.items : [];
  const places = rows
    .filter(row => String(row && row.group || '').trim() === NOVA_QM_CHECKLIST.PLACE_GROUP)
    .filter(row => String(row && row.enabled || 'N').trim().toUpperCase() === 'Y')
    .map(row => ({
      code: String(row.code || '').trim().toUpperCase(),
      label: String(row.label || '').trim(),
      order: Number(row.order || 9999)
    }))
    .filter(place => place.code && place.label)
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'ko'));
  const placeMap = {};
  places.forEach(place => { placeMap[place.code] = place; });
  const placeSet = new Set(places.map(place => place.code));
  const items = rows
    .filter(row => String(row && row.group || '').trim() === NOVA_QM_CHECKLIST.GROUP)
    .filter(row => String(row && row.enabled || 'N').trim().toUpperCase() === 'Y')
    .map(row => {
      const meta = novaQmChecklistParseNote_(row.note);
      const placeCode = String(meta.placeCode || '').trim().toUpperCase();
      const place = placeMap[placeCode] || { code: placeCode, label: '객실 전체', order: 9999 };
      return {
        code: String(row.code || '').trim(),
        label: String(row.label || '').trim(),
        placeCode: place.code,
        placeLabel: place.label,
        placeOrder: Number(place.order || 9999),
        order: Number(row.order || 9999),
        required: meta.required !== false,
        photoRequired: meta.photoRequired === true
      };
    })
    .filter(item => item.code && item.label && placeSet.has(item.placeCode))
    .sort((a, b) => a.placeOrder - b.placeOrder || a.order - b.order || a.label.localeCompare(b.label, 'ko'));
  return {
    places,
    items,
    groups: places.map(place => ({ place, items: items.filter(item => item.placeCode === place.code) })).filter(group => group.items.length),
    revision: buildQmChecklistRevision_(items, places),
    maxPhotosPerTarget: NOVA_QM_CHECKLIST.MAX_PHOTOS_PER_TARGET,
    dbFirst: true,
    dbVersion: Number(db && db.version || 0)
  };
}

function novaQmChecklistDefinitionDbFirst_(token, legacyFactory) {
  const db = novaQmChecklistDbRead_(token);
  if (db && db.ok === true && db.confirmed === true && Array.isArray(db.items)) {
    return novaQmChecklistDefinitionFromDb_(db);
  }
  return typeof legacyFactory === 'function' ? legacyFactory() : getQmChecklistForSubmit_();
}

function getQmChecklistForSubmitDbFirst_(token) {
  // QM_FINALIZE_PREFLIGHT_SCHEMA_CACHE_BYPASS_V1
  // 최종제출/사전검증은 DB-first 관리 변경이 이미 동기화한 Sheet 정의를 사용하여
  // PostgREST schema cache 장애가 점검완료를 가로막지 않도록 합니다.
  return getQmChecklistForSubmit_();
}

function getQmChecklistForMobileDbFirst_(token) {
  return novaQmChecklistDefinitionDbFirst_(token, getQmChecklistForMobile_);
}

function novaQmChecklistMirrorKey_(group, code) {
  const digest = Utilities.base64EncodeWebSafe(Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    `${String(group || '').trim()}|${String(code || '').trim()}`
  )).replace(/=+$/g, '').slice(0, 24);
  return `${NOVA_QM_CHECKLIST_DB_FIRST_V1.MIRROR_PREFIX}${digest}`;
}

function novaQmChecklistMarkMirrorPending_(action, payload) {
  const safe = payload || {};
  PropertiesService.getScriptProperties().setProperty(
    novaQmChecklistMirrorKey_(safe.group, safe.code),
    JSON.stringify({ action: String(action || ''), payload: safe, markedAt: new Date().toISOString() })
  );
}

function novaQmChecklistClearMirrorPending_(group, code) {
  PropertiesService.getScriptProperties().deleteProperty(novaQmChecklistMirrorKey_(group, code));
}

function novaQmChecklistSheetAlreadyApplied_(action, payload) {
  const safe = payload || {};
  const row = findCodeRow_(safe.group, safe.code);
  if (!row) return false;
  const upperAction = String(action || '').toUpperCase();
  if (upperAction.indexOf('DISABLE') >= 0) return row.enabled !== 'Y';
  if (safe.group === NOVA_QM_CHECKLIST.PLACE_GROUP) {
    return row.enabled === 'Y'
      && String(row.label || '') === String(safe.label || '')
      && Number(row.order || 9999) === Number(safe.order || 9999);
  }
  const expectedNote = JSON.stringify({
    placeCode: String(safe.placeCode || '').trim().toUpperCase(),
    required: safe.required !== false,
    photoRequired: safe.photoRequired === true
  });
  return row.enabled === 'Y'
    && String(row.label || '') === String(safe.label || '')
    && Number(row.order || 9999) === Number(safe.order || 9999)
    && String(row.note || '') === expectedNote;
}

function novaQmChecklistMirrorToSheet_(token, action, payload) {
  const safe = payload || {};
  if (novaQmChecklistSheetAlreadyApplied_(action, safe)) return { ok: true, alreadyApplied: true };
  switch (String(action || '').toUpperCase()) {
    case 'PLACE_SAVE':
      return saveQmChecklistPlace(token, safe);
    case 'PLACE_DISABLE':
      return deleteQmChecklistPlace(token, safe);
    case 'ITEM_SAVE':
      return saveQmChecklistItem(token, safe);
    case 'ITEM_DISABLE':
      return deleteQmChecklistItem(token, safe);
    default:
      throw new Error('QM 체크리스트 Sheet 미러 작업을 확인할 수 없습니다.');
  }
}

function novaQmChecklistRetryPendingMirrors_(token) {
  const props = PropertiesService.getScriptProperties();
  const all = props.getProperties();
  const keys = Object.keys(all).filter(key => key.indexOf(NOVA_QM_CHECKLIST_DB_FIRST_V1.MIRROR_PREFIX) === 0).slice(0, 20);
  let pending = 0;
  keys.forEach(key => {
    let record = null;
    try { record = JSON.parse(String(all[key] || '{}')); } catch (ignore) { record = null; }
    if (!record || !record.payload) { props.deleteProperty(key); return; }
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, record.action, record.payload);
      if (mirror && mirror.ok === true) props.deleteProperty(key);
      else pending += 1;
    } catch (error) {
      pending += 1;
      console.warn('[NOVA DB] QM 체크리스트 pending Sheet 미러 재시도 실패:', error && error.message || error);
    }
  });
  return { checked: keys.length, pending };
}

function novaQmChecklistRequireDbReady_(token) {
  const db = novaQmChecklistDbRead_(token);
  if (!db || db.legacyFallback || db.ok !== true || db.confirmed !== true || !Array.isArray(db.items)) {
    const error = new Error('QM 체크리스트 DB 연결을 확인할 수 없어 변경하지 않았습니다. 잠시 후 다시 시도하세요.');
    error.code = 'QM_CHECKLIST_DB_UNAVAILABLE';
    throw error;
  }
  return db;
}

function getQmChecklistManagementDataDbFirst(token) {
  return measureResponse_('getQmChecklistManagementDataDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const db = novaQmChecklistDbRead_(token);
    if (!db || db.legacyFallback || db.ok !== true || db.confirmed !== true || !Array.isArray(db.items)) {
      return getQmChecklistManagementData(token);
    }
    const retry = novaQmChecklistRetryPendingMirrors_(token);
    const definition = novaQmChecklistDefinitionFromDb_(db);
    return {
      ok: true,
      places: definition.places,
      items: definition.items,
      revision: definition.revision,
      maxItems: NOVA_QM_CHECKLIST.MAX_ITEMS,
      maxPlaces: NOVA_QM_CHECKLIST.MAX_PLACES,
      sites: getSiteList_(),
      serverTime: nowText_(),
      dbFirst: true,
      dbConfirmed: true,
      dbVersion: Number(db.version || 0),
      sheetMirrorPending: Number(retry.pending || 0) > 0
    };
  });
}

function saveQmChecklistPlaceDbFirst(token, payload) {
  return measureResponse_('saveQmChecklistPlaceDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const state = novaQmChecklistRequireDbReady_(token);
    const requestedCode = String(safe.code || '').trim().toUpperCase();
    const code = requestedCode || `QMPLACE-${Utilities.getUuid().replace(/-/g, '').slice(0, 8).toUpperCase()}`;
    const label = String(safe.label || '').trim();
    if (!label) throw new Error('점검 장소명을 입력하세요.');
    if (label.length > 40) throw new Error('점검 장소명은 40자 이내로 입력하세요.');
    const order = Math.max(0, Math.min(9999, Number(safe.order || 9999)));
    const requestId = String(safe.requestId || novaDbFirstRequestId_('QM_PLACE_SAVE_V1')).trim();
    const db = novaDbFirstRpc_(token, 'nova_qm_checklist_place_save_v1', {
      p_code: code, p_label: label, p_order: order, p_request_id: requestId
    }, {});
    if (!db || db.ok !== true) throw new Error(db && db.message || '점검 장소를 DB에 저장하지 못했습니다.');
    const mirrorPayload = { group: NOVA_QM_CHECKLIST.PLACE_GROUP, code, label, order };
    novaQmChecklistMarkMirrorPending_('PLACE_SAVE', mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, 'PLACE_SAVE', mirrorPayload);
      if (mirror && mirror.ok === true) { novaQmChecklistClearMirrorPending_(mirrorPayload.group, code); sheetMirrorPending = false; }
    } catch (error) { console.warn('[NOVA DB] QM 장소 DB 확정 후 Sheet 미러 지연:', error && error.message || error); }
    return { ok: true, dbFirst: true, code, version: Number(db.version || 0), sheetMirrorPending,
      message: db.created === true ? '점검 장소를 추가했습니다.' : '점검 장소를 수정했습니다.' };
  });
}

function deleteQmChecklistPlaceDbFirst(token, payload) {
  return measureResponse_('deleteQmChecklistPlaceDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    novaQmChecklistRequireDbReady_(token);
    const code = String(safe.code || '').trim().toUpperCase();
    if (!code) throw new Error('삭제할 점검 장소가 없습니다.');
    const requestId = String(safe.requestId || novaDbFirstRequestId_('QM_PLACE_DISABLE_V1')).trim();
    const db = novaDbFirstRpc_(token, 'nova_qm_checklist_place_disable_v1', { p_code: code, p_request_id: requestId }, {});
    if (!db || db.ok !== true) throw new Error(db && db.message || '점검 장소를 DB에서 사용중지하지 못했습니다.');
    const mirrorPayload = { group: NOVA_QM_CHECKLIST.PLACE_GROUP, code };
    novaQmChecklistMarkMirrorPending_('PLACE_DISABLE', mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, 'PLACE_DISABLE', mirrorPayload);
      if (mirror && mirror.ok === true) { novaQmChecklistClearMirrorPending_(mirrorPayload.group, code); sheetMirrorPending = false; }
    } catch (error) { console.warn('[NOVA DB] QM 장소 사용중지 DB 확정 후 Sheet 미러 지연:', error && error.message || error); }
    return { ok: true, dbFirst: true, code, version: Number(db.version || 0), sheetMirrorPending,
      message: '점검 장소를 삭제했습니다. 과거 점검이력은 유지됩니다.' };
  });
}

function saveQmChecklistItemDbFirst(token, payload) {
  return measureResponse_('saveQmChecklistItemDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const state = novaQmChecklistRequireDbReady_(token);
    const requestedCode = String(safe.code || '').trim().toUpperCase();
    const code = requestedCode || `QMCL-${Utilities.getUuid().replace(/-/g, '').slice(0, 10).toUpperCase()}`;
    const label = String(safe.label || '').trim();
    if (!label) throw new Error('점검 항목명을 입력하세요.');
    if (label.length > 120) throw new Error('점검 항목명은 120자 이내로 입력하세요.');
    const definition = novaQmChecklistDefinitionFromDb_(state);
    const placeCode = String(safe.placeCode || '').trim().toUpperCase();
    if (!definition.places.some(place => place.code === placeCode)) throw new Error('점검 장소를 선택하세요.');
    const order = Math.max(0, Math.min(9999, Number(safe.order || 9999)));
    const required = safe.required !== false && String(safe.required || 'Y').toUpperCase() !== 'N';
    const photoRequired = safe.photoRequired === true || String(safe.photoRequired || '').toUpperCase() === 'Y';
    const requestId = String(safe.requestId || novaDbFirstRequestId_('QM_ITEM_SAVE_V1')).trim();
    const db = novaDbFirstRpc_(token, 'nova_qm_checklist_item_save_v1', {
      p_code: code, p_label: label, p_place_code: placeCode, p_order: order,
      p_required: required, p_photo_required: photoRequired, p_request_id: requestId
    }, {});
    if (!db || db.ok !== true) throw new Error(db && db.message || '체크리스트 항목을 DB에 저장하지 못했습니다.');
    const mirrorPayload = { group: NOVA_QM_CHECKLIST.GROUP, code, label, placeCode, order, required, photoRequired };
    novaQmChecklistMarkMirrorPending_('ITEM_SAVE', mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, 'ITEM_SAVE', mirrorPayload);
      if (mirror && mirror.ok === true) { novaQmChecklistClearMirrorPending_(mirrorPayload.group, code); sheetMirrorPending = false; }
    } catch (error) { console.warn('[NOVA DB] QM 항목 DB 확정 후 Sheet 미러 지연:', error && error.message || error); }
    return { ok: true, dbFirst: true, code, version: Number(db.version || 0), sheetMirrorPending,
      message: db.created === true ? '체크리스트 항목을 추가했습니다.' : '체크리스트 항목을 수정했습니다.' };
  });
}

function deleteQmChecklistItemDbFirst(token, payload) {
  return measureResponse_('deleteQmChecklistItemDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    novaQmChecklistRequireDbReady_(token);
    const code = String(safe.code || '').trim().toUpperCase();
    if (!code) throw new Error('삭제할 체크리스트 항목이 없습니다.');
    const requestId = String(safe.requestId || novaDbFirstRequestId_('QM_ITEM_DISABLE_V1')).trim();
    const db = novaDbFirstRpc_(token, 'nova_qm_checklist_item_disable_v1', { p_code: code, p_request_id: requestId }, {});
    if (!db || db.ok !== true) throw new Error(db && db.message || '체크리스트 항목을 DB에서 사용중지하지 못했습니다.');
    const mirrorPayload = { group: NOVA_QM_CHECKLIST.GROUP, code };
    novaQmChecklistMarkMirrorPending_('ITEM_DISABLE', mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, 'ITEM_DISABLE', mirrorPayload);
      if (mirror && mirror.ok === true) { novaQmChecklistClearMirrorPending_(mirrorPayload.group, code); sheetMirrorPending = false; }
    } catch (error) { console.warn('[NOVA DB] QM 항목 사용중지 DB 확정 후 Sheet 미러 지연:', error && error.message || error); }
    return { ok: true, dbFirst: true, code, version: Number(db.version || 0), sheetMirrorPending,
      message: '체크리스트 항목을 삭제했습니다. 과거 점검이력은 유지됩니다.' };
  });
}