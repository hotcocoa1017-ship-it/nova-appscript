/**
 * NOVA DB-first server bridge.
 * Apps Script 사용자 토큰을 Cloud Run의 기존 realtime-token 교환경로로 검증한 뒤
 * 해당 사용자의 짧은 Supabase JWT로 보호된 RPC만 호출합니다.
 * service_role key는 Apps Script/브라우저에 저장하거나 노출하지 않습니다.
 */
function novaRealtimeUserRpc_(token, rpcName, payload) { // REALTIME_DB_FIRST_SERVER_V1
  const sessionToken = String(token || '').trim();
  const name = String(rpcName || '').trim();
  if (!sessionToken) throw new Error('로그인이 필요합니다.');
  if (!/^nova_[a-z0-9_]+$/i.test(name)) throw new Error('지원하지 않는 DB 작업입니다.');

  const props = PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  if (!apiBase) throw new Error('Realtime API 주소가 설정되지 않았습니다.');

  const authResponse = UrlFetchApp.fetch(`${apiBase}/v1/auth/realtime-token`, {
    method: 'post',
    contentType: 'application/json; charset=utf-8',
    payload: '{}',
    headers: { Authorization: `Bearer ${sessionToken}` },
    muteHttpExceptions: true,
    followRedirects: true
  });
  const authStatus = Number(authResponse.getResponseCode() || 0);
  let auth = {};
  try { auth = JSON.parse(authResponse.getContentText() || '{}'); } catch (error) { auth = {}; }
  if (authStatus < 200 || authStatus >= 300) {
    throw new Error(String(auth.message || auth.error || `Realtime 인증 실패 (${authStatus})`));
  }

  const supabaseUrl = String(auth.supabaseUrl || auth.supabase_url || '').trim().replace(/\/+$/, '');
  const publishableKey = String(auth.publishableKey || auth.publishable_key || auth.anonKey || '').trim();
  const jwt = String(auth.token || auth.accessToken || auth.access_token || '').trim();
  if (!supabaseUrl || !publishableKey || !jwt) {
    throw new Error('Realtime DB 인증정보를 확인할 수 없습니다.');
  }

  const response = UrlFetchApp.fetch(`${supabaseUrl}/rest/v1/rpc/${encodeURIComponent(name)}`, {
    method: 'post',
    contentType: 'application/json; charset=utf-8',
    payload: JSON.stringify(payload || {}),
    headers: {
      apikey: publishableKey,
      Authorization: `Bearer ${jwt}`
    },
    muteHttpExceptions: true,
    followRedirects: true
  });
  const status = Number(response.getResponseCode() || 0);
  let result = {};
  try { result = JSON.parse(response.getContentText() || '{}'); } catch (error) { result = {}; }
  if (status < 200 || status >= 300 || result.ok === false) {
    const dbMessage = String(result.message || result.details || result.hint || result.error || '').trim();
    throw new Error(dbMessage || `Realtime DB 처리 오류 (${status})`);
  }
  return result;
}

function novaRoomUploadDbFirstEnabled_() { // ROOM_UPLOAD_DB_FIRST_V2
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_ROOM_UPLOAD_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaRoomUploadDbBundle_(token, businessDate, site) { // ROOM_UPLOAD_DB_FIRST_V2 · ROOM_UPLOAD_STATE_RPC_V1
  return novaRealtimeUserRpc_(token, 'nova_room_upload_state_v1', {
    p_business_date: String(businessDate || '').trim(),
    p_site: String(site || '').trim()
  });
}

function novaRoomUploadDbApply_(token, payload) { // ROOM_UPLOAD_DB_FIRST_V2
  const safe = payload || {};
  return novaRealtimeUserRpc_(token, 'nova_room_upload_apply_v2', {
    p_business_date: String(safe.businessDate || '').trim(),
    p_site: String(safe.site || '').trim(),
    p_rooms: Array.isArray(safe.rooms) ? safe.rooms : [],
    p_upload: safe.upload && typeof safe.upload === 'object' ? safe.upload : {},
    p_expected_version: Number.isFinite(Number(safe.expectedVersion)) ? Number(safe.expectedVersion) : 0,
    p_version: Number(safe.version || 0),
    p_request_id: String(safe.requestId || '').trim()
  });
}

function novaQmInspectionDbFirstEnabled_() { // QM_INSPECTION_FINALIZE_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_QM_INSPECTION_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaQmInspectionDbFinalize_(token, payload) { // QM_INSPECTION_FINALIZE_DB_FIRST_V1
  const safe = payload || {};
  return novaRealtimeUserRpc_(token, 'nova_qm_inspection_finalize_v1', {
    p_payload: safe.inspection && typeof safe.inspection === 'object' ? safe.inspection : {},
    p_request_id: String(safe.requestId || '').trim()
  });
}

function novaDailyCloseDbFirstEnabled_() { // DAILY_CLOSE_SAVE_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_DAILY_CLOSE_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaDailyCloseDbSave_(token, payload) { // DAILY_CLOSE_SAVE_DB_FIRST_V1
  const safe = payload || {};
  return novaRealtimeUserRpc_(token, 'nova_daily_close_save_v2', {
    p_business_date: String(safe.businessDate || '').trim(),
    p_site: String(safe.site || '').trim(),
    p_snapshot: safe.snapshot && typeof safe.snapshot === 'object' ? safe.snapshot : {},
    p_request_id: String(safe.requestId || '').trim()
  });
}

function novaDailyCloseDbRead_(token, payload) { // DAILY_CLOSE_READ_DB_FIRST_V1
  const safe = payload || {};
  return novaRealtimeUserRpc_(token, 'nova_daily_close_read_v1', {
    p_start_date: String(safe.startDate || '').trim(),
    p_end_date: String(safe.endDate || safe.startDate || '').trim(),
    p_site: String(safe.site || '').trim()
  });
}

function novaOperationSettingsDbFirstEnabled_() { // OPERATION_SETTINGS_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_OPERATION_SETTINGS_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaOperationSettingsDbSave_(token, values, requestId) { // OPERATION_SETTINGS_DB_FIRST_V1
  return novaRealtimeUserRpc_(token, 'nova_operation_settings_save_v1', {
    p_values: values && typeof values === 'object' ? values : {},
    p_request_id: String(requestId || '').trim()
  });
}

function novaDailyCloseDbCancel_(token, payload) { // DAILY_CLOSE_CANCEL_DB_FIRST_V1
  const safe = payload || {};
  return novaRealtimeUserRpc_(token, 'nova_daily_close_cancel_v1', {
    p_business_date: String(safe.businessDate || '').trim(),
    p_site: String(safe.site || '').trim(),
    p_reason: String(safe.reason || '').trim(),
    p_request_id: String(safe.requestId || '').trim()
  });
}
