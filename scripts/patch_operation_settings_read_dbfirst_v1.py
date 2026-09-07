from pathlib import Path

bridge = Path('RealtimeDbFirstServer.js')
text = bridge.read_text(encoding='utf-8')
marker = "function novaOperationSettingsDbSave_(token, values, requestId) { // OPERATION_SETTINGS_DB_FIRST_V1\n  return novaRealtimeUserRpc_(token, 'nova_operation_settings_save_v1', {\n    p_values: values && typeof values === 'object' ? values : {},\n    p_request_id: String(requestId || '').trim()\n  });\n}\n"
addition = marker + "\nfunction novaOperationSettingsDbRead_(token) { // OPERATION_SETTINGS_READ_DB_FIRST_V1\n  return novaRealtimeUserRpc_(token, 'nova_operation_settings_read_v1', {});\n}\n"
if 'OPERATION_SETTINGS_READ_DB_FIRST_V1' not in text:
    if marker not in text:
        raise SystemExit('RealtimeDbFirstServer.js patch anchor not found')
    text = text.replace(marker, addition, 1)
    bridge.write_text(text, encoding='utf-8')

admin = Path('15_AdminSettings.js')
text = admin.read_text(encoding='utf-8')
old = """    const operationValues = {};
    NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach(def => {
      operationValues[def.code] = getOperationSetting_(def.code, def.defaultValue);
    });
    return {
"""
new = """    const operationValues = {};
    NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach(def => {
      operationValues[def.code] = getOperationSetting_(def.code, def.defaultValue);
    });

    // DB가 아직 confirmed=false인 초기 이행 구간에서는 기존 Sheet 설정을 유지합니다.
    // 관리자가 DB-first 저장을 1회 성공해 confirmed=true가 된 뒤에는 DB가 조회 원본입니다.
    let operationDb = null; // OPERATION_SETTINGS_READ_DB_FIRST_V1
    if (typeof novaOperationSettingsDbFirstEnabled_ === 'function'
        && novaOperationSettingsDbFirstEnabled_()
        && typeof novaOperationSettingsDbRead_ === 'function') {
      operationDb = novaOperationSettingsDbRead_(token);
      if (operationDb && operationDb.confirmed === true && operationDb.values) {
        NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach(def => {
          if (Object.prototype.hasOwnProperty.call(operationDb.values, def.code)) {
            operationValues[def.code] = validateOperationSettingValue_(def, operationDb.values[def.code]);
          }
        });
      }
    }
    return {
"""
if 'OPERATION_SETTINGS_READ_DB_FIRST_V1' not in text:
    if old not in text:
        raise SystemExit('15_AdminSettings.js patch anchor not found')
    text = text.replace(old, new, 1)
    admin.write_text(text, encoding='utf-8')

text = admin.read_text(encoding='utf-8')
old_return = """      operationDefinitions: NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS,
      operationValues,
      triggers: getAdminTriggerStatus_(),
"""
new_return = """      operationDefinitions: NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS,
      operationValues,
      operationDb: operationDb ? {
        dbFirst: Boolean(operationDb.dbFirst),
        confirmed: Boolean(operationDb.confirmed),
        version: Number(operationDb.version || 0)
      } : null,
      triggers: getAdminTriggerStatus_(),
"""
if 'operationDb: operationDb ? {' not in text:
    if old_return not in text:
        raise SystemExit('15_AdminSettings.js return anchor not found')
    text = text.replace(old_return, new_return, 1)
    admin.write_text(text, encoding='utf-8')

print('operation settings DB-first read patch OK')
