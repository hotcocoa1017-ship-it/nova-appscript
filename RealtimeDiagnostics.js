/**
 * TEMP 2026-08-29: Realtime live connectivity diagnostic.
 * Returns health/claim/status flags only. Never returns tokens, keys, employee numbers or secrets.
 */
function runNovaRealtimeLiveDiagnostic_() {
  const startedAt = Date.now();
  const result = {
    ok: false,
    realtimeEnabled: false,
    apiConfigured: false,
    cloudRunHealthOk: false,
    cloudRunHealthStatus: 0,
    cloudRunBuild: '',
    realtimeTokenOk: false,
    realtimeTokenStatus: 0,
    supabaseProjectMatch: false,
    supabaseRootStatus: 0,
    supabaseTableStatus: 0,
    supabaseJwtRejected: false,
    jwtAlg: '',
    jwtRole: '',
    jwtAudience: '',
    jwtIssuer: '',
    jwtHasExpiration: false,
    jwtSiteCount: 0,
    jwtSubjectLooksUuid: false,
    publishableKeyType: '',
    elapsedMs: 0,
    stage: 'START'
  };

  try {
    const props = PropertiesService.getScriptProperties();
    const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
    const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() === 'Y';
    result.realtimeEnabled = enabled;
    result.apiConfigured = Boolean(apiBase);
    if (!apiBase) throw new Error('NOVA_REALTIME_API_BASE_EMPTY');

    result.stage = 'CLOUD_RUN_HEALTH';
    const healthResponse = UrlFetchApp.fetch(apiBase + '/health', {
      method: 'get', muteHttpExceptions: true, followRedirects: true
    });
    result.cloudRunHealthStatus = Number(healthResponse.getResponseCode() || 0);
    let health = {};
    try { health = JSON.parse(healthResponse.getContentText() || '{}'); } catch (_) {}
    result.cloudRunHealthOk = result.cloudRunHealthStatus >= 200 && result.cloudRunHealthStatus < 300 && health.ok === true;
    result.cloudRunBuild = String(health.build || health.version || '').slice(0, 120);

    result.stage = 'NOVA_AUTH_TOKEN';
    const diagnosticUser = getActiveUsersByRole_(['ADMIN', 'ORDER'])[0];
    if (!diagnosticUser || !diagnosticUser.employeeNo) throw new Error('DIAGNOSTIC_USER_NOT_FOUND');
    const novaToken = createLoginToken_(diagnosticUser.employeeNo);

    result.stage = 'REALTIME_TOKEN';
    const tokenResponse = UrlFetchApp.fetch(apiBase + '/v1/auth/realtime-token', {
      method: 'post', contentType: 'application/json; charset=utf-8', payload: '{}',
      headers: { Authorization: 'Bearer ' + novaToken },
      muteHttpExceptions: true, followRedirects: true
    });
    result.realtimeTokenStatus = Number(tokenResponse.getResponseCode() || 0);
    let tokenBody = {};
    try { tokenBody = JSON.parse(tokenResponse.getContentText() || '{}'); } catch (_) {}
    result.realtimeTokenOk = result.realtimeTokenStatus >= 200 && result.realtimeTokenStatus < 300
      && tokenBody.ok === true && Boolean(tokenBody.token) && Boolean(tokenBody.supabaseUrl) && Boolean(tokenBody.publishableKey);
    if (!result.realtimeTokenOk) {
      result.errorCode = String(tokenBody.code || 'REALTIME_TOKEN_FAILED').slice(0, 120);
      throw new Error(result.errorCode);
    }

    const supabaseUrl = String(tokenBody.supabaseUrl || '').trim().replace(/\/+$/, '');
    const publishableKey = String(tokenBody.publishableKey || '');
    result.supabaseProjectMatch = /^https:\/\/evoetxfjmkkjptucwxsv\.supabase\.co$/i.test(supabaseUrl);
    result.publishableKeyType = publishableKey.indexOf('sb_publishable_') === 0 ? 'PUBLISHABLE' : (publishableKey.split('.').length === 3 ? 'LEGACY_JWT' : 'OTHER');

    result.stage = 'JWT_DECODE';
    try {
      const tokenParts = String(tokenBody.token || '').split('.');
      if (tokenParts.length === 3) {
        const headerText = Utilities.newBlob(Utilities.base64DecodeWebSafe(tokenParts[0])).getDataAsString('UTF-8');
        const claimText = Utilities.newBlob(Utilities.base64DecodeWebSafe(tokenParts[1])).getDataAsString('UTF-8');
        const header = JSON.parse(headerText || '{}');
        const claims = JSON.parse(claimText || '{}');
        result.jwtAlg = String(header.alg || '').slice(0, 40);
        result.jwtRole = String(claims.role || '').slice(0, 60);
        result.jwtAudience = Array.isArray(claims.aud) ? claims.aud.map(String).join(',').slice(0, 120) : String(claims.aud || '').slice(0, 120);
        result.jwtIssuer = String(claims.iss || '').slice(0, 160);
        result.jwtHasExpiration = Number(claims.exp || 0) > Math.floor(Date.now() / 1000);
        result.jwtSiteCount = Array.isArray(claims.sites) ? claims.sites.length : 0;
        result.jwtSubjectLooksUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(claims.sub || ''));
      }
    } catch (_) {}

    const headers = {
      apikey: publishableKey,
      Authorization: 'Bearer ' + String(tokenBody.token || ''),
      Accept: 'application/json'
    };

    result.stage = 'SUPABASE_JWT_VERIFY_ROOT';
    const rootResponse = UrlFetchApp.fetch(supabaseUrl + '/rest/v1/', {
      method: 'get', headers: headers, muteHttpExceptions: true, followRedirects: true
    });
    result.supabaseRootStatus = Number(rootResponse.getResponseCode() || 0);

    result.stage = 'SUPABASE_JWT_VERIFY_TABLE';
    const tableResponse = UrlFetchApp.fetch(supabaseUrl + '/rest/v1/nova_rooms_current?select=room_no&limit=1', {
      method: 'get', headers: headers, muteHttpExceptions: true, followRedirects: true
    });
    result.supabaseTableStatus = Number(tableResponse.getResponseCode() || 0);
    result.supabaseJwtRejected = result.supabaseRootStatus === 401 || result.supabaseTableStatus === 401;
    if (result.supabaseJwtRejected || result.supabaseTableStatus >= 400) {
      let restError = {};
      try { restError = JSON.parse(tableResponse.getContentText() || '{}'); } catch (_) {}
      result.supabaseErrorCode = String(restError.code || restError.error_code || '').slice(0, 120);
      result.supabaseErrorMessage = String(restError.message || restError.msg || '').slice(0, 180);
    }

    result.stage = 'DONE';
    result.ok = Boolean(
      result.realtimeEnabled && result.apiConfigured && result.cloudRunHealthOk
      && result.realtimeTokenOk && result.supabaseProjectMatch && !result.supabaseJwtRejected
      && result.jwtRole === 'authenticated' && result.jwtAudience.indexOf('authenticated') >= 0
      && result.jwtHasExpiration && result.jwtSiteCount > 0
    );
  } catch (error) {
    result.error = String(error && error.message || error || 'UNKNOWN').slice(0, 180);
  }

  result.elapsedMs = Date.now() - startedAt;
  return result;
}
