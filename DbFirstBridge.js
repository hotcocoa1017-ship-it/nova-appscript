/**
 * NOVA whole-DB transition bridge.
 * PostgreSQL RPC is primary; existing Sheet writers are compatibility mirrors only after DB commit.
 * No service-role key is exposed or stored here. A short-lived Supabase user JWT is obtained through
 * the existing Cloud Run auth endpoint using the current NOVA login token.
 */
const NOVA_DB_FIRST_BRIDGE_V1 = Object.freeze({
  MARKER: 'NOVA_WHOLE_DB_FIRST_BRIDGE_V1',
  RETRIES: 3,
  SHIFT_MIRROR_PREFIX: 'NOVA_DB_SHIFT_MIRROR_PENDING_',
  RPCS: Object.freeze([
    'nova_houseman_shift_zone_get_v2',
    'nova_houseman_shift_zone_bootstrap_v3',
    'nova_houseman_shift_save_v2',
    'nova_houseman_zone_save_v1',
    'nova_departure_delay_dashboard_v1', // DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4
    'nova_daily_close_source_v1',
    'nova_daily_close_save_v2',
    'nova_daily_close_read_v1',
    'nova_daily_close_cancel_v1',
    'nova_daily_close_cancel_many_v1',
    'nova_roommaid_close_cancel_v1', // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1
    'nova_operation_settings_read_v1', // NOVA_OPERATION_SETTINGS_DB_FIRST_V1
    'nova_operation_settings_save_v1', // NOVA_OPERATION_SETTINGS_DB_FIRST_V1
    'nova_admin_code_settings_read_v1', // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1
    'nova_admin_code_settings_save_v1', // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1
    'nova_admin_code_settings_disable_v1', // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1
    'nova_qm_checklist_codes_read_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1
    'nova_qm_checklist_place_save_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1
    'nova_qm_checklist_item_save_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1
    'nova_qm_checklist_item_disable_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1
    'nova_qm_checklist_place_disable_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1
    'nova_monthly_history_v1',
    'nova_roommaid_performance_history_v1',
    'nova_roommaid_close_history_v1'
  ])
});

function novaDbFirstRpcAllowed_(rpc) {
  return NOVA_DB_FIRST_BRIDGE_V1.RPCS.includes(String(rpc || '').trim());
}

function novaDbFirstRealtimeAuth_(token) { // (기존 Cloud Run 인증을 서버에서도 재사용)
  const props = PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  if (!apiBase) {
    const error = new Error('Realtime API 주소가 설정되지 않았습니다.');
    error.code = 'DB_AUTH_PREP_FAILED';
    throw error;
  }
  const response = UrlFetchApp.fetch(`${apiBase}/v1/auth/realtime-token`, {
    method: 'post',
    contentType: 'application/json; charset=utf-8',
    headers: { Authorization: `Bearer ${String(token || '').trim()}` },
    payload: '{}',
    muteHttpExceptions: true,
    followRedirects: true
  });
  const status = Number(response.getResponseCode() || 0);
  let body = {};
  try { body = JSON.parse(response.getContentText('UTF-8') || '{}'); } catch (ignore) { body = {}; }
  if (status < 200 || status >= 300 || !body.ok || !body.supabaseUrl || !body.publishableKey || !body.token) {
    const error = new Error(String(body.message || body.error || `DB 인증 준비 실패 (${status || 'NO_STATUS'})`));
    error.code = 'DB_AUTH_PREP_FAILED';
    error.status = status;
    throw error;
  }
  return body;
}

function novaDbFirstRpc_(token, rpc, args, options) { // (동일 body/requestId 재시도·쓰기 결과불명 fail-closed)
  const rpcName = String(rpc || '').trim();
  if (!novaDbFirstRpcAllowed_(rpcName)) throw new Error(`허용되지 않은 DB RPC입니다. (${rpcName})`);
  const safe = options || {};
  const readOnly = safe.readOnly === true;
  let auth;
  try {
    auth = novaDbFirstRealtimeAuth_(token);
  } catch (error) {
    if (readOnly || safe.allowLegacyFallback === true) {
      return { ok: false, legacyFallback: true, reason: 'AUTH_PREP_FAILED', message: error.message || '' };
    }
    throw error;
  }

  const bodyText = JSON.stringify(args && typeof args === 'object' ? args : {});
  let lastNetworkError = null;
  for (let attempt = 0; attempt < NOVA_DB_FIRST_BRIDGE_V1.RETRIES; attempt += 1) {
    let response;
    try {
      response = UrlFetchApp.fetch(`${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/${rpcName}`, {
        method: 'post',
        contentType: 'application/json; charset=utf-8',
        headers: {
          Authorization: `Bearer ${auth.token}`,
          apikey: String(auth.publishableKey || '')
        },
        payload: bodyText,
        muteHttpExceptions: true,
        followRedirects: true
      });
    } catch (networkError) {
      lastNetworkError = networkError;
      if (attempt + 1 < NOVA_DB_FIRST_BRIDGE_V1.RETRIES) {
        Utilities.sleep([140, 420, 900][attempt] || 900);
        continue;
      }
      if (readOnly) return { ok: false, legacyFallback: true, reason: 'READ_NETWORK_FAILED', message: String(networkError && networkError.message || networkError) };
      const error = new Error('DB 처리 결과를 확인할 수 없습니다. 같은 작업을 다시 저장하지 말고 화면을 새로고침해 상태를 확인하세요.');
      error.code = 'NOVA_DB_RESULT_UNKNOWN';
      throw error;
    }

    const status = Number(response.getResponseCode() || 0);
    let data = {};
    try { data = JSON.parse(response.getContentText('UTF-8') || '{}'); } catch (ignore) { data = {}; }
    if (status >= 200 && status < 300 && data && data.ok) return data;

    const code = String(data && data.code || '').trim().toUpperCase();
    if (status === 401 && attempt + 1 < NOVA_DB_FIRST_BRIDGE_V1.RETRIES) {
      auth = novaDbFirstRealtimeAuth_(token);
      Utilities.sleep(120);
      continue;
    }
    if ((status === 429 || status >= 500) && attempt + 1 < NOVA_DB_FIRST_BRIDGE_V1.RETRIES) {
      Utilities.sleep([160, 420, 900][attempt] || 900);
      continue;
    }
    if ((status === 404 || ['PGRST202', 'PGRST205'].includes(code)) && (readOnly || safe.allowLegacyFallback === true)) {
      return { ok: false, legacyFallback: true, reason: 'RPC_MISSING', status, code };
    }
    const error = new Error(String(data && (data.message || data.error || data.hint) || `DB 요청 오류 (${status || 'NO_STATUS'})`));
    error.code = code || 'NOVA_DB_RPC_FAILED';
    error.status = status;
    throw error;
  }

  if (readOnly) return { ok: false, legacyFallback: true, reason: 'READ_UNKNOWN' };
  const error = new Error(String(lastNetworkError && lastNetworkError.message || 'DB 처리 결과를 확인할 수 없습니다.'));
  error.code = 'NOVA_DB_RESULT_UNKNOWN';
  throw error;
}

function novaDbFirstRequestId_(prefix) {
  return `${String(prefix || 'NOVA')}-${Utilities.getUuid()}`.replace(/[^A-Za-z0-9._:-]/g, '-').slice(0, 176);
}

function novaDbShiftMirrorKey_(businessDate, site) {
  const digest = Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, `${businessDate}|${site}`)
  ).replace(/=+$/g, '').slice(0, 24);
  return `${NOVA_DB_FIRST_BRIDGE_V1.SHIFT_MIRROR_PREFIX}${digest}`;
}

function markShiftZoneMirrorPending_(businessDate, site) {
  PropertiesService.getScriptProperties().setProperty(novaDbShiftMirrorKey_(businessDate, site), nowText_());
}

function clearShiftZoneMirrorPending_(businessDate, site) {
  PropertiesService.getScriptProperties().deleteProperty(novaDbShiftMirrorKey_(businessDate, site));
}

function shiftZoneMirrorPending_(businessDate, site) {
  return Boolean(PropertiesService.getScriptProperties().getProperty(novaDbShiftMirrorKey_(businessDate, site)));
}

function mirrorShiftZoneDbStateToSheets_(token, dbState) { // (DB 확정상태를 기존 Sheet 구조로 재구성)
  const state = dbState || {};
  const businessDate = normalizeBusinessDate_(state.businessDate);
  const site = String(state.site || '').trim();
  if (!site) throw new Error('근무조 Sheet 미러에 사업장이 필요합니다.');
  const assignments = state.assignments || { A: [], B: [], C: [] };

  // 근무조를 먼저 맞춰야 담당동의 근무조 소속 검증이 기존 함수에서도 동일하게 통과합니다.
  const shiftMirror = saveShiftAssignments(token, { businessDate, site, assignments });
  const dbZones = state.zoneAssignments && typeof state.zoneAssignments === 'object' ? state.zoneAssignments : {};
  const sheetZones = getHousemanZoneAssignmentsForDate_(businessDate, site).byEmployeeNo || {};

  Object.keys(sheetZones).forEach(employeeNo => {
    if (dbZones[employeeNo]) return;
    saveHousemanZoneAssignment(token, { businessDate, site, employeeNo, action: 'CANCEL', buildings: [] });
  });
  Object.keys(dbZones).forEach(employeeNo => {
    const zone = dbZones[employeeNo] || {};
    const buildings = Array.isArray(zone.buildings) ? zone.buildings : [];
    if (!buildings.length) return;
    saveHousemanZoneAssignment(token, {
      businessDate,
      site,
      employeeNo,
      buildings,
      action: sheetZones[employeeNo] ? 'UPDATE' : 'SAVE'
    });
  });
  clearShiftZoneMirrorPending_(businessDate, site);
  return { ok: true, shiftMirror, businessDate, site };
}

function getShiftManagementDataDbFirst(token, options) { // NOVA_SHIFT_ZONE_DB_FIRST_V3 · SHIFT_MANAGEMENT_READ_NONBLOCKING_V1
  return measureResponse_('getShiftManagementDataDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const sites = getSiteList_();
    const site = String(safe.site || user.defaultSite || sites[0] || '').trim();
    if (!site) throw new Error('사업장을 선택하세요.');

    let db = novaDbFirstRpc_(token, 'nova_houseman_shift_zone_get_v2', {
      p_business_date: businessDate,
      p_site: site
    }, { readOnly: true, allowLegacyFallback: true });

    if (db && db.ok && db.initialized === true) {
      // DB-first 조회는 이미 확정된 DB 상태를 즉시 반환해야 한다.
      // Sheet 미러 복구는 저장 경로의 best-effort 호환 작업이며 조회 응답을 절대 막지 않는다.
      const mirrorPending = shiftZoneMirrorPending_(businessDate, site);
      return Object.assign({}, db, {
        sheetMirrorPending: mirrorPending,
        readNonBlocking: true
      });
    }

    // DB RPC 자체가 아직 없는 단계에서는 현재 운영을 그대로 유지합니다.
    if (db && db.legacyFallback) return getShiftManagementData(token, options);

    // initialized=false만 1회 legacy Sheet -> DB bootstrap을 허용합니다.
    const legacy = getShiftManagementData(token, options);
    if (!legacy || !legacy.ok) return legacy;
    const requestId = novaDbFirstRequestId_('SHIFT_BOOTSTRAP_V3');
    const boot = novaDbFirstRpc_(token, 'nova_houseman_shift_zone_bootstrap_v3', {
      p_business_date: businessDate,
      p_site: site,
      p_assignments: legacy.assignments || { A: [], B: [], C: [] },
      p_zones: legacy.zoneAssignments || {},
      p_request_id: requestId
    }, { allowLegacyFallback: true });
    if (boot && boot.legacyFallback) return legacy;
    return boot;
  });
}

function saveShiftAssignmentsDbFirst(token, payload) { // NOVA_SHIFT_ZONE_DB_FIRST_V3
  return measureResponse_('saveShiftAssignmentsDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('사업장을 선택하세요.');
    const assignments = safe.assignments || {};
    const requestId = String(safe.requestId || novaDbFirstRequestId_('SHIFT_SAVE_V3')).trim();

    const db = novaDbFirstRpc_(token, 'nova_houseman_shift_save_v2', {
      p_business_date: businessDate,
      p_site: site,
      p_assignments: assignments,
      p_request_id: requestId
    }, { allowLegacyFallback: true });
    if (db && db.legacyFallback) return saveShiftAssignments(token, payload);

    let dbState = novaDbFirstRpc_(token, 'nova_houseman_shift_zone_get_v2', {
      p_business_date: businessDate,
      p_site: site
    }, { readOnly: true, allowLegacyFallback: false });
    try {
      mirrorShiftZoneDbStateToSheets_(token, dbState);
    } catch (mirrorError) {
      markShiftZoneMirrorPending_(businessDate, site);
      console.warn('[NOVA DB] 근무조 DB 확정 후 Sheet 미러 지연:', mirrorError && mirrorError.message || mirrorError);
      db.sheetMirrorPending = true;
    }
    return Object.assign({}, db, { requestedBy: user.employeeNo, dbFirst: true });
  });
}

function saveHousemanZoneAssignmentDbFirst(token, payload) { // NOVA_SHIFT_ZONE_DB_FIRST_V3
  return measureResponse_('saveHousemanZoneAssignmentDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const employeeNo = String(safe.employeeNo || '').trim();
    const action = String(safe.action || 'SAVE').trim().toUpperCase();
    if (!site || !employeeNo) throw new Error('담당동 저장정보를 확인해 주세요.');
    const requestId = String(safe.requestId || novaDbFirstRequestId_(`ZONE_${action}_V3`)).trim();

    const db = novaDbFirstRpc_(token, 'nova_houseman_zone_save_v1', {
      p_business_date: businessDate,
      p_site: site,
      p_employee_no: employeeNo,
      p_buildings: Array.isArray(safe.buildings) ? safe.buildings : [],
      p_action: action,
      p_request_id: requestId
    }, { allowLegacyFallback: true });
    if (db && db.legacyFallback) return saveHousemanZoneAssignment(token, payload);

    const dbState = novaDbFirstRpc_(token, 'nova_houseman_shift_zone_get_v2', {
      p_business_date: businessDate,
      p_site: site
    }, { readOnly: true, allowLegacyFallback: false });
    try {
      mirrorShiftZoneDbStateToSheets_(token, dbState);
    } catch (mirrorError) {
      markShiftZoneMirrorPending_(businessDate, site);
      console.warn('[NOVA DB] 담당동 DB 확정 후 Sheet 미러 지연:', mirrorError && mirrorError.message || mirrorError);
      db.sheetMirrorPending = true;
    }
    return Object.assign({}, db, { requestedBy: user.employeeNo, dbFirst: true });
  });
}
