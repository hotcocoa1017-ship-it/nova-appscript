/** NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1 */
const NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1 = Object.freeze({
  MARKER: 'NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1',
  MIRROR_PREFIX: 'NOVA_QM_CHECKLIST_DB_MIRROR_PENDING_V1_'
});

function novaQmChecklistCodesDbRead_(token) {
  return novaDbFirstRpc_(token, 'nova_qm_checklist_codes_read_v1', {}, {
    readOnly: true,
    allowLegacyFallback: true
  });
}

function novaQmChecklistMirrorKey_(group, code) {
  const digest = Utilities.base64EncodeWebSafe(Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    `${String(group || '').trim()}|${String(code || '').trim()}`
  )).replace(/=+$/g, '').slice(0, 24);
  return `${NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1.MIRROR_PREFIX}${digest}`;
}

function novaQmChecklistMarkMirrorPending_(action, group, payload) {
  const safe = payload || {};
  PropertiesService.getScriptProperties().setProperty(
    novaQmChecklistMirrorKey_(group, safe.code),
    JSON.stringify({ action: String(action || ''), group: String(group || ''), payload: safe, markedAt: new Date().toISOString() })
  );
}

function novaQmChecklistClearMirrorPending_(group, code) {
  PropertiesService.getScriptProperties().deleteProperty(novaQmChecklistMirrorKey_(group, code));
}

function novaQmChecklistDbPlaces_(db, enabledOnly) {
  return (Array.isArray(db && db.items) ? db.items : [])
    .filter(row => String(row && row.group || '').trim() === NOVA_QM_CHECKLIST.PLACE_GROUP)
    .filter(row => enabledOnly !== true || String(row && row.enabled || 'N').trim().toUpperCase() === 'Y')
    .map(row => ({
      code: String(row.code || '').trim().toUpperCase(),
      label: String(row.label || '').trim(),
      order: Number(row.order || 9999)
    }))
    .filter(row => row.code)
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'ko'));
}

function novaQmChecklistDbItems_(db, places, enabledOnly) {
  const placeMap = {};
  (places || []).forEach(place => { placeMap[place.code] = place; });
  return (Array.isArray(db && db.items) ? db.items : [])
    .filter(row => String(row && row.group || '').trim() === NOVA_QM_CHECKLIST.GROUP)
    .filter(row => enabledOnly !== true || String(row && row.enabled || 'N').trim().toUpperCase() === 'Y')
    .map(row => qmChecklistItemFromCodeRow_({
      code: String(row.code || '').trim(),
      label: String(row.label || '').trim(),
      order: Number(row.order || 9999),
      enabled: String(row.enabled || 'N').trim().toUpperCase(),
      note: String(row.note || '')
    }, placeMap))
    .filter(row => row.code)
    .sort((a, b) => a.placeOrder - b.placeOrder || a.order - b.order || a.label.localeCompare(b.label, 'ko'));
}

function novaQmChecklistSheetPlaceApplied_(payload, enabled) {
  const safe = payload || {};
  const row = findCodeRow_(NOVA_QM_CHECKLIST.PLACE_GROUP, String(safe.code || '').trim().toUpperCase());
  if (!row) return false;
  if (enabled === false) return String(row.enabled || 'N').trim().toUpperCase() !== 'Y';
  return String(row.label || '') === String(safe.label || '')
    && Number(row.order || 9999) === Number(safe.order || 9999)
    && String(row.enabled || 'N').trim().toUpperCase() === 'Y';
}

function novaQmChecklistSheetItemApplied_(payload, enabled) {
  const safe = payload || {};
  const row = findCodeRow_(NOVA_QM_CHECKLIST.GROUP, String(safe.code || '').trim());
  if (!row) return false;
  if (enabled === false) return String(row.enabled || 'N').trim().toUpperCase() !== 'Y';
  const meta = parseQmChecklistNote_(row.note);
  const required = safe.required !== false && String(safe.required == null ? 'Y' : safe.required).trim().toUpperCase() !== 'N';
  const photoRequired = safe.photoRequired === true || String(safe.photoRequired || '').trim().toUpperCase() === 'Y';
  return String(row.label || '') === String(safe.label || '')
    && Number(row.order || 9999) === Number(safe.order || 9999)
    && String(row.enabled || 'N').trim().toUpperCase() === 'Y'
    && String(meta.placeCode || '') === String(safe.placeCode || '').trim().toUpperCase()
    && Boolean(meta.required) === Boolean(required)
    && Boolean(meta.photoRequired) === Boolean(photoRequired);
}

function novaQmChecklistMirrorToSheet_(token, action, payload) {
  const safe = payload || {};
  const type = String(action || '').trim().toUpperCase();
  if (type === 'PLACE_SAVE') {
    if (novaQmChecklistSheetPlaceApplied_(safe, true)) return { ok: true, alreadyApplied: true };
    return saveQmChecklistPlace(token, safe);
  }
  if (type === 'PLACE_DISABLE') {
    if (novaQmChecklistSheetPlaceApplied_(safe, false)) return { ok: true, alreadyApplied: true };
    return deleteQmChecklistPlace(token, { code: safe.code });
  }
  if (type === 'ITEM_SAVE') {
    if (novaQmChecklistSheetItemApplied_(safe, true)) return { ok: true, alreadyApplied: true };
    return saveQmChecklistItem(token, safe);
  }
  if (type === 'ITEM_DISABLE') {
    if (novaQmChecklistSheetItemApplied_(safe, false)) return { ok: true, alreadyApplied: true };
    return deleteQmChecklistItem(token, { code: safe.code });
  }
  throw new Error('QM 체크리스트 Sheet 미러 작업을 확인할 수 없습니다.');
}

function novaQmChecklistRetryPendingMirrors_(token) {
  const props = PropertiesService.getScriptProperties();
  const all = props.getProperties();
  const keys = Object.keys(all).filter(key => key.indexOf(NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1.MIRROR_PREFIX) === 0).slice(0, 20);
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
  const db = novaQmChecklistCodesDbRead_(token);
  if (!db || db.legacyFallback || db.ok !== true || db.confirmed !== true) {
    const error = new Error('QM 체크리스트 DB 연결을 확인할 수 없어 변경하지 않았습니다. 잠시 후 다시 시도하세요.');
    error.code = 'QM_CHECKLIST_DB_UNAVAILABLE';
    throw error;
  }
  return db;
}

function getQmChecklistManagementDataDbFirst(token) {
  return measureResponse_('getQmChecklistManagementDataDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    try { novaQmChecklistRetryPendingMirrors_(token); } catch (error) {
      console.warn('[NOVA DB] QM 체크리스트 pending Sheet 미러 조회중 재시도 실패:', error && error.message || error);
    }
    const db = novaQmChecklistCodesDbRead_(token);
    if (!db || db.legacyFallback || db.ok !== true || db.confirmed !== true) return getQmChecklistManagementData(token);
    const places = novaQmChecklistDbPlaces_(db, true);
    const items = novaQmChecklistDbItems_(db, places, true);
    return {
      ok: true,
      dbFirst: true,
      dbVersion: Number(db.version || 0),
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

function saveQmChecklistPlaceDbFirst(token, payload) {
  return measureResponse_('saveQmChecklistPlaceDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const dbState = novaQmChecklistRequireDbReady_(token);
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

    const mirrorPayload = { code, label, order };
    novaQmChecklistMarkMirrorPending_('PLACE_SAVE', NOVA_QM_CHECKLIST.PLACE_GROUP, mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, 'PLACE_SAVE', mirrorPayload);
      if (mirror && mirror.ok === true) {
        novaQmChecklistClearMirrorPending_(NOVA_QM_CHECKLIST.PLACE_GROUP, code);
        sheetMirrorPending = false;
      }
    } catch (error) {
      console.warn('[NOVA DB] QM 점검장소 DB 확정 후 Sheet 미러 지연:', error && error.message || error);
    }
    return {
      ok: true, dbFirst: true, code, version: Number(db.version || 0), requestId: String(db.requestId || requestId),
      idempotent: db.idempotent === true, sheetMirrorPending,
      message: db.created === true ? '점검 장소를 추가했습니다.' : '점검 장소를 수정했습니다.'
    };
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
    if (!db || db.ok !== true) throw new Error(db && db.message || '점검 장소를 DB에서 삭제하지 못했습니다.');

    const mirrorPayload = { code };
    novaQmChecklistMarkMirrorPending_('PLACE_DISABLE', NOVA_QM_CHECKLIST.PLACE_GROUP, mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, 'PLACE_DISABLE', mirrorPayload);
      if (mirror && mirror.ok === true) {
        novaQmChecklistClearMirrorPending_(NOVA_QM_CHECKLIST.PLACE_GROUP, code);
        sheetMirrorPending = false;
      }
    } catch (error) {
      console.warn('[NOVA DB] QM 점검장소 삭제 DB 확정 후 Sheet 미러 지연:', error && error.message || error);
    }
    return {
      ok: true, dbFirst: true, code, version: Number(db.version || 0), requestId: String(db.requestId || requestId),
      idempotent: db.idempotent === true, sheetMirrorPending,
      message: '점검 장소를 삭제했습니다. 과거 점검이력은 유지됩니다.'
    };
  });
}

function saveQmChecklistItemDbFirst(token, payload) {
  return measureResponse_('saveQmChecklistItemDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    novaQmChecklistRequireDbReady_(token);
    const requestedCode = String(safe.code || '').trim().toUpperCase();
    const code = requestedCode || `QMCL-${Utilities.getUuid().replace(/-/g, '').slice(0, 10).toUpperCase()}`;
    const label = String(safe.label || '').trim();
    if (!label) throw new Error('점검 항목명을 입력하세요.');
    if (label.length > 120) throw new Error('점검 항목명은 120자 이내로 입력하세요.');
    const placeCode = String(safe.placeCode || '').trim().toUpperCase();
    if (!placeCode) throw new Error('점검 장소를 선택하세요.');
    const order = Math.max(0, Math.min(9999, Number(safe.order || 9999)));
    const required = safe.required !== false && String(safe.required == null ? 'Y' : safe.required).trim().toUpperCase() !== 'N';
    const photoRequired = safe.photoRequired === true || String(safe.photoRequired || '').trim().toUpperCase() === 'Y';
    const requestId = String(safe.requestId || novaDbFirstRequestId_('QM_ITEM_SAVE_V1')).trim();
    const db = novaDbFirstRpc_(token, 'nova_qm_checklist_item_save_v1', {
      p_code: code, p_label: label, p_place_code: placeCode, p_order: order,
      p_required: required, p_photo_required: photoRequired, p_request_id: requestId
    }, {});
    if (!db || db.ok !== true) throw new Error(db && db.message || '체크리스트 항목을 DB에 저장하지 못했습니다.');

    const mirrorPayload = { code, label, placeCode, order, required, photoRequired };
    novaQmChecklistMarkMirrorPending_('ITEM_SAVE', NOVA_QM_CHECKLIST.GROUP, mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, 'ITEM_SAVE', mirrorPayload);
      if (mirror && mirror.ok === true) {
        novaQmChecklistClearMirrorPending_(NOVA_QM_CHECKLIST.GROUP, code);
        sheetMirrorPending = false;
      }
    } catch (error) {
      console.warn('[NOVA DB] QM 체크리스트 DB 확정 후 Sheet 미러 지연:', error && error.message || error);
    }
    return {
      ok: true, dbFirst: true, code, version: Number(db.version || 0), requestId: String(db.requestId || requestId),
      idempotent: db.idempotent === true, sheetMirrorPending,
      message: db.created === true ? '체크리스트 항목을 추가했습니다.' : '체크리스트 항목을 수정했습니다.'
    };
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
    if (!db || db.ok !== true) throw new Error(db && db.message || '체크리스트 항목을 DB에서 삭제하지 못했습니다.');

    const mirrorPayload = { code };
    novaQmChecklistMarkMirrorPending_('ITEM_DISABLE', NOVA_QM_CHECKLIST.GROUP, mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaQmChecklistMirrorToSheet_(token, 'ITEM_DISABLE', mirrorPayload);
      if (mirror && mirror.ok === true) {
        novaQmChecklistClearMirrorPending_(NOVA_QM_CHECKLIST.GROUP, code);
        sheetMirrorPending = false;
      }
    } catch (error) {
      console.warn('[NOVA DB] QM 체크리스트 삭제 DB 확정 후 Sheet 미러 지연:', error && error.message || error);
    }
    return {
      ok: true, dbFirst: true, code, version: Number(db.version || 0), requestId: String(db.requestId || requestId),
      idempotent: db.idempotent === true, sheetMirrorPending,
      message: '체크리스트 항목을 삭제했습니다. 과거 점검이력은 유지됩니다.'
    };
  });
}
