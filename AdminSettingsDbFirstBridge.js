/** NOVA_OPERATION_SETTINGS_DB_FIRST_V1 */
const NOVA_OPERATION_SETTINGS_DB_FIRST_V1 = Object.freeze({
  MARKER: 'NOVA_OPERATION_SETTINGS_DB_FIRST_V1',
  MIRROR_PENDING_KEY: 'NOVA_OPERATION_SETTINGS_DB_MIRROR_PENDING_V1'
});

function novaOperationSettingsDbRead_(token) {
  return novaDbFirstRpc_(token, 'nova_operation_settings_read_v1', {}, {
    readOnly: true,
    allowLegacyFallback: true
  });
}

function novaOperationSettingsNormalize_(input, fallbackValues) {
  const source = input && typeof input === 'object' ? input : {};
  const fallback = fallbackValues && typeof fallbackValues === 'object' ? fallbackValues : {};
  const normalized = {};
  NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach(def => {
    const raw = Object.prototype.hasOwnProperty.call(source, def.code)
      ? source[def.code]
      : Object.prototype.hasOwnProperty.call(fallback, def.code)
        ? fallback[def.code]
        : getOperationSetting_(def.code, def.defaultValue);
    normalized[def.code] = validateOperationSettingValue_(def, raw);
  });
  return normalized;
}

function novaOperationSettingsMarkMirrorPending_(values) {
  PropertiesService.getScriptProperties().setProperty(
    NOVA_OPERATION_SETTINGS_DB_FIRST_V1.MIRROR_PENDING_KEY,
    JSON.stringify({ values: values || {}, markedAt: new Date().toISOString() })
  );
}

function novaOperationSettingsClearMirrorPending_() {
  PropertiesService.getScriptProperties().deleteProperty(NOVA_OPERATION_SETTINGS_DB_FIRST_V1.MIRROR_PENDING_KEY);
}

function novaOperationSettingsMirrorPending_() {
  return Boolean(PropertiesService.getScriptProperties().getProperty(NOVA_OPERATION_SETTINGS_DB_FIRST_V1.MIRROR_PENDING_KEY));
}

function novaOperationSettingsMirrorToSheet_(token, values) {
  const mirror = saveAdminOperationSettings(token, { values: values || {} });
  if (!mirror || mirror.ok !== true) throw new Error(mirror && mirror.message || '운영설정 Sheet 미러에 실패했습니다.');
  novaOperationSettingsClearMirrorPending_();
  return mirror;
}

function getAdminSettingsDataDbFirst(token) { // (운영설정 + 안정형 관리코드 DB authority, 나머지 legacy 보존)
  return measureResponse_('getAdminSettingsDataDbFirst', () => {
    requireRole_(token, ['ADMIN']);
    const legacy = getAdminSettingsData(token);
    const result = Object.assign({}, legacy);

    const operationDb = novaOperationSettingsDbRead_(token);
    const operationReady = Boolean(operationDb && !operationDb.legacyFallback && operationDb.ok === true && operationDb.confirmed === true && operationDb.values);
    let operationMirrorPending = novaOperationSettingsMirrorPending_();
    if (operationReady && operationMirrorPending) {
      try {
        novaOperationSettingsMirrorToSheet_(token, operationDb.values);
        operationMirrorPending = false;
      } catch (error) {
        console.warn('[NOVA DB] 운영설정 pending Sheet 미러 재시도 실패:', error && error.message || error);
      }
    }
    if (operationReady) {
      result.operationValues = Object.assign({}, legacy.operationValues || {}, operationDb.values || {});
      result.operationSettingsDbFirst = true;
      result.operationSettingsDbConfirmed = true;
      result.operationSettingsDbVersion = Number(operationDb.version || 0);
      result.operationSettingsSheetMirrorPending = operationMirrorPending;
    } else {
      result.operationSettingsDbFirst = false;
      result.operationSettingsDbReason = String(operationDb && operationDb.reason || 'DB_NOT_CONFIRMED');
    }

    let codeDb = null;
    try { codeDb = novaAdminCodeSettingsDbRead_(token); }
    catch (error) { codeDb = { ok: false, reason: error && error.code || 'DB_READ_FAILED' }; }
    const codeReady = Boolean(codeDb && !codeDb.legacyFallback && codeDb.ok === true && codeDb.confirmed === true && Array.isArray(codeDb.items));
    let codeMirrorPending = 0;
    if (codeReady) {
      try { codeMirrorPending = Number(novaAdminCodeRetryPendingMirrors_(token).pending || 0); }
      catch (error) { console.warn('[NOVA DB] 관리코드 pending Sheet 미러 확인 실패:', error && error.message || error); }
      result.groups = novaAdminCodeOverlayGroups_(legacy.groups, codeDb);
      result.adminCodeSettingsDbFirst = true;
      result.adminCodeSettingsDbConfirmed = true;
      result.adminCodeSettingsDbVersion = Number(codeDb.version || 0);
      result.adminCodeSettingsDbRowCount = Number(codeDb.rowCount || 0);
      result.adminCodeSettingsSheetMirrorPending = codeMirrorPending;
    } else {
      result.adminCodeSettingsDbFirst = false;
      result.adminCodeSettingsDbReason = String(codeDb && codeDb.reason || 'DB_NOT_CONFIRMED');
    }

    result.dbFirst = operationReady || codeReady;
    return result;
  });
}

function saveAdminOperationSettingsDbFirst(token, payload) { // (운영설정 DB commit -> Sheet compatibility mirror)
  return measureResponse_('saveAdminOperationSettingsDbFirst', () => {
    requireRole_(token, ['ADMIN']);
    const safe = payload || {};
    const input = safe.values && typeof safe.values === 'object' ? safe.values : safe;
    const current = novaOperationSettingsDbRead_(token);
    if (current && current.legacyFallback) {
      const error = new Error('운영설정 DB 연결을 확인할 수 없어 저장하지 않았습니다. 잠시 후 다시 시도하세요.');
      error.code = 'OPERATION_SETTINGS_DB_UNAVAILABLE';
      throw error;
    }

    const fallbackValues = current && current.ok && current.values ? current.values : {};
    const normalized = novaOperationSettingsNormalize_(input, fallbackValues);
    const requestId = String(safe.requestId || novaDbFirstRequestId_('OPERATION_SETTINGS_V1')).trim();
    const db = novaDbFirstRpc_(token, 'nova_operation_settings_save_v1', {
      p_values: normalized,
      p_request_id: requestId
    }, {});
    if (!db || db.ok !== true) throw new Error(db && db.message || '운영설정을 DB에 저장하지 못했습니다.');

    novaOperationSettingsMarkMirrorPending_(normalized);
    let mirror = null;
    let sheetMirrorPending = true;
    try {
      mirror = novaOperationSettingsMirrorToSheet_(token, normalized);
      sheetMirrorPending = false;
    } catch (error) {
      console.warn('[NOVA DB] 운영설정 DB 확정 후 Sheet 미러 지연:', error && error.message || error);
    }

    return {
      ok: true,
      dbFirst: true,
      values: normalized,
      dbVersion: Number(db.version || 0),
      requestId: String(db.requestId || requestId),
      idempotent: db.idempotent === true,
      sheetMirrorPending,
      triggers: mirror && mirror.triggers ? mirror.triggers : getAdminTriggerStatus_(),
      message: sheetMirrorPending
        ? '운영 기준은 DB에 저장됐으며 호환 설정 반영을 재시도합니다.'
        : '운영 기준과 자동 실행 트리거를 저장했습니다.'
    };
  });
}
