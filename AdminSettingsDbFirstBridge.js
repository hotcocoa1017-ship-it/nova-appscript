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

function getAdminSettingsDataDbFirst(token) { // (관리자 설정: 코드그룹 Sheet + 운영설정 DB authority)
  return measureResponse_('getAdminSettingsDataDbFirst', () => {
    requireRole_(token, ['ADMIN']);
    const legacy = getAdminSettingsData(token);
    const db = novaOperationSettingsDbRead_(token);
    if (!db || db.legacyFallback || db.ok !== true || db.confirmed !== true || !db.values) {
      return Object.assign({}, legacy, {
        dbFirst: false,
        operationSettingsDbFirst: false,
        operationSettingsDbReason: String(db && db.reason || 'DB_NOT_CONFIRMED')
      });
    }

    let sheetMirrorPending = novaOperationSettingsMirrorPending_();
    if (sheetMirrorPending) {
      try {
        novaOperationSettingsMirrorToSheet_(token, db.values);
        sheetMirrorPending = false;
      } catch (error) {
        console.warn('[NOVA DB] 운영설정 pending Sheet 미러 재시도 실패:', error && error.message || error);
      }
    }

    return Object.assign({}, legacy, {
      operationValues: Object.assign({}, legacy.operationValues || {}, db.values || {}),
      dbFirst: true,
      operationSettingsDbFirst: true,
      operationSettingsDbConfirmed: true,
      operationSettingsDbVersion: Number(db.version || 0),
      operationSettingsSheetMirrorPending: sheetMirrorPending
    });
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
