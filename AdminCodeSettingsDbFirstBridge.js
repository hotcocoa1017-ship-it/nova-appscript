/** NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1 */
const NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1 = Object.freeze({
  MARKER: 'NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1',
  GROUPS: Object.freeze(['동','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목']),
  MIRROR_PREFIX: 'NOVA_ADMIN_CODE_DB_MIRROR_PENDING_V1_'
});

function novaAdminCodeSettingsIsDbGroup_(group) {
  return NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1.GROUPS.includes(String(group || '').trim());
}

function novaAdminCodeSettingsDbRead_(token) {
  return novaDbFirstRpc_(token, 'nova_admin_code_settings_read_v1', {}, {
    readOnly: true,
    allowLegacyFallback: true
  });
}

function novaAdminCodeMirrorKey_(group, code) {
  const digest = Utilities.base64EncodeWebSafe(Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    `${String(group || '').trim()}|${String(code || '').trim()}`
  )).replace(/=+$/g, '').slice(0, 24);
  return `${NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1.MIRROR_PREFIX}${digest}`;
}

function novaAdminCodeMarkMirrorPending_(action, payload) {
  const safe = payload || {};
  PropertiesService.getScriptProperties().setProperty(
    novaAdminCodeMirrorKey_(safe.group, safe.code),
    JSON.stringify({ action: String(action || 'SAVE'), payload: safe, markedAt: new Date().toISOString() })
  );
}

function novaAdminCodeClearMirrorPending_(group, code) {
  PropertiesService.getScriptProperties().deleteProperty(novaAdminCodeMirrorKey_(group, code));
}

function novaAdminCodeSheetSaveAlreadyApplied_(payload) {
  const safe = payload || {};
  const row = findCodeRow_(safe.group, safe.code);
  if (!row) return false;
  return String(row.label || '') === String(safe.label || '')
    && Number(row.order || 9999) === Number(safe.order || 9999)
    && String(row.enabled || 'N') === String(safe.enabled || 'N')
    && String(row.note || '') === String(safe.note || '');
}

function novaAdminCodeMirrorToSheet_(token, action, payload) {
  const safe = payload || {};
  if (String(action || '').toUpperCase() === 'DISABLE') {
    const row = findCodeRow_(safe.group, safe.code);
    if (row && row.enabled !== 'Y') return { ok: true, alreadyApplied: true };
    return disableAdminCodeRow(token, { group: safe.group, code: safe.code });
  }
  if (novaAdminCodeSheetSaveAlreadyApplied_(safe)) return { ok: true, alreadyApplied: true };
  return saveAdminCodeRow(token, safe);
}

function novaAdminCodeRetryPendingMirrors_(token) {
  const props = PropertiesService.getScriptProperties();
  const all = props.getProperties();
  const keys = Object.keys(all).filter(key => key.indexOf(NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1.MIRROR_PREFIX) === 0).slice(0, 20);
  let pending = 0;
  keys.forEach(key => {
    let record = null;
    try { record = JSON.parse(String(all[key] || '{}')); } catch (ignore) { record = null; }
    if (!record || !record.payload) { props.deleteProperty(key); return; }
    try {
      const mirror = novaAdminCodeMirrorToSheet_(token, record.action, record.payload);
      if (mirror && mirror.ok === true) props.deleteProperty(key);
      else pending += 1;
    } catch (error) {
      pending += 1;
      console.warn('[NOVA DB] 관리코드 pending Sheet 미러 재시도 실패:', error && error.message || error);
    }
  });
  return { checked: keys.length, pending };
}

function novaAdminCodeOverlayGroups_(legacyGroups, db) {
  const groups = Array.isArray(legacyGroups) ? legacyGroups : [];
  if (!db || db.ok !== true || db.confirmed !== true || !Array.isArray(db.items)) return groups;
  const byGroup = {};
  db.items.forEach(item => {
    const group = String(item && item.group || '').trim();
    if (!novaAdminCodeSettingsIsDbGroup_(group)) return;
    if (!byGroup[group]) byGroup[group] = [];
    byGroup[group].push(Object.assign({}, item, {
      protected: isProtectedAdminCode_(group, String(item && item.code || '').trim())
    }));
  });
  return groups.map(group => novaAdminCodeSettingsIsDbGroup_(group && group.code)
    ? Object.assign({}, group, { items: byGroup[group.code] || [] })
    : group);
}

function saveAdminCodeRowDbFirst(token, payload) {
  return measureResponse_('saveAdminCodeRowDbFirst', () => {
    requireRole_(token, ['ADMIN']);
    const safe = payload || {};
    const group = String(safe.group || '').trim();
    if (!novaAdminCodeSettingsIsDbGroup_(group)) return saveAdminCodeRow(token, payload);

    const dbState = novaAdminCodeSettingsDbRead_(token);
    if (!dbState || dbState.legacyFallback || dbState.ok !== true || dbState.confirmed !== true) {
      const error = new Error('관리 코드 DB 연결을 확인할 수 없어 저장하지 않았습니다. 잠시 후 다시 시도하세요.');
      error.code = 'ADMIN_CODE_DB_UNAVAILABLE';
      throw error;
    }

    const meta = getAdminGroupMeta_(group);
    if (!meta) throw new Error('관리할 수 없는 코드그룹입니다.');
    const code = normalizeAdminCode_(safe.code);
    const label = String(safe.label || '').trim();
    if (!code) throw new Error('코드를 입력하세요.');
    if (!label) throw new Error('표시명을 입력하세요.');
    const existing = (dbState.items || []).find(item => String(item.group || '') === group && String(item.code || '') === code) || null;
    if (!existing && !meta.addable) throw new Error('이 코드그룹에는 새 항목을 추가할 수 없습니다.');
    const enabled = isProtectedAdminCode_(group, code) ? 'Y' : normalizeYesNo_(safe.enabled == null ? 'Y' : safe.enabled);
    const order = Math.max(0, Number(safe.order || 9999));
    const note = String(safe.note || '').trim();
    const requestId = String(safe.requestId || novaDbFirstRequestId_(`ADMIN_CODE_SAVE_${group}`)).trim();

    const db = novaDbFirstRpc_(token, 'nova_admin_code_settings_save_v1', {
      p_group: group, p_code: code, p_label: label, p_order: order,
      p_enabled: enabled, p_note: note, p_request_id: requestId
    }, {});
    if (!db || db.ok !== true) throw new Error(db && db.message || '관리 코드를 DB에 저장하지 못했습니다.');

    const mirrorPayload = { group, code, label, order, enabled, note };
    novaAdminCodeMarkMirrorPending_('SAVE', mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaAdminCodeMirrorToSheet_(token, 'SAVE', mirrorPayload);
      if (mirror && mirror.ok === true) {
        novaAdminCodeClearMirrorPending_(group, code);
        sheetMirrorPending = false;
      }
    } catch (error) {
      console.warn('[NOVA DB] 관리코드 DB 확정 후 Sheet 미러 지연:', error && error.message || error);
    }
    return {
      ok: true, dbFirst: true, group, code, version: Number(db.version || 0),
      requestId: String(db.requestId || requestId), idempotent: db.idempotent === true,
      sheetMirrorPending,
      message: `${group} ${label} 항목을 저장했습니다.`
    };
  });
}

function disableAdminCodeRowDbFirst(token, payload) {
  return measureResponse_('disableAdminCodeRowDbFirst', () => {
    requireRole_(token, ['ADMIN']);
    const safe = payload || {};
    const group = String(safe.group || '').trim();
    if (!novaAdminCodeSettingsIsDbGroup_(group)) return disableAdminCodeRow(token, payload);

    const dbState = novaAdminCodeSettingsDbRead_(token);
    if (!dbState || dbState.legacyFallback || dbState.ok !== true || dbState.confirmed !== true) {
      const error = new Error('관리 코드 DB 연결을 확인할 수 없어 변경하지 않았습니다. 잠시 후 다시 시도하세요.');
      error.code = 'ADMIN_CODE_DB_UNAVAILABLE';
      throw error;
    }
    const code = normalizeAdminCode_(safe.code);
    if (!code) throw new Error('코드정보가 올바르지 않습니다.');
    if (isProtectedAdminCode_(group, code)) throw new Error('시스템 필수코드는 사용중지할 수 없습니다. 표시명만 변경하세요.');
    const existing = (dbState.items || []).find(item => String(item.group || '') === group && String(item.code || '') === code) || null;
    if (!existing || String(existing.enabled || 'N') !== 'Y') throw new Error('코드 항목을 찾을 수 없습니다.');
    const requestId = String(safe.requestId || novaDbFirstRequestId_(`ADMIN_CODE_DISABLE_${group}`)).trim();

    const db = novaDbFirstRpc_(token, 'nova_admin_code_settings_disable_v1', {
      p_group: group, p_code: code, p_request_id: requestId
    }, {});
    if (!db || db.ok !== true) throw new Error(db && db.message || '관리 코드를 DB에서 사용중지하지 못했습니다.');

    const mirrorPayload = { group, code };
    novaAdminCodeMarkMirrorPending_('DISABLE', mirrorPayload);
    let sheetMirrorPending = true;
    try {
      const mirror = novaAdminCodeMirrorToSheet_(token, 'DISABLE', mirrorPayload);
      if (mirror && mirror.ok === true) {
        novaAdminCodeClearMirrorPending_(group, code);
        sheetMirrorPending = false;
      }
    } catch (error) {
      console.warn('[NOVA DB] 관리코드 사용중지 DB 확정 후 Sheet 미러 지연:', error && error.message || error);
    }
    return {
      ok: true, dbFirst: true, group, code, version: Number(db.version || 0),
      requestId: String(db.requestId || requestId), idempotent: db.idempotent === true,
      sheetMirrorPending,
      message: `${String(existing.label || code)} 항목을 사용중지했습니다.`
    };
  });
}
