/**
 * TEMP 2026-09-14: Realtime 500 non-secret diagnostic.
 * Remove immediately after diagnosis.
 * Never returns NOVA tokens, Supabase JWTs, publishable keys, employee numbers, or secrets.
 */
function novaRuntimeRealtime500Diagnostic_() {
  const result = {
    ok: false,
    stage: 'START',
    realtimeEnabled: false,
    apiConfigured: false,
    apiHost: '',
    health: null,
    apiAuth: null,
    legacyAuth: null,
    elapsedMs: 0
  };
  const startedAt = Date.now();

  function safeProbe_(method, url, token) {
    const options = {
      method: String(method || 'get').toLowerCase(),
      muteHttpExceptions: true,
      followRedirects: false,
      headers: { Accept: 'application/json' }
    };
    if (options.method === 'post') {
      options.contentType = 'application/json; charset=utf-8';
      options.payload = '{}';
    }
    if (token) options.headers.Authorization = 'Bearer ' + token;

    try {
      const response = UrlFetchApp.fetch(url, options);
      const status = Number(response.getResponseCode() || 0);
      const contentType = String(response.getHeaders()['Content-Type'] || response.getHeaders()['content-type'] || '').slice(0, 120);
      const text = String(response.getContentText() || '');
      let body = null;
      try { body = JSON.parse(text || '{}'); } catch (_) {}
      return {
        status: status,
        contentType: contentType,
        json: Boolean(body && typeof body === 'object'),
        ok: Boolean(body && body.ok === true),
        code: String(body && (body.code || body.error_code) || '').slice(0, 120),
        message: String(body && (body.message || body.error) || '').slice(0, 180),
        hasToken: Boolean(body && body.token),
        locationHost: String(response.getHeaders().Location || response.getHeaders().location || '').replace(/^https?:\/\//i, '').split('/')[0].slice(0, 180),
        bodyPrefix: body ? '' : text.replace(/\s+/g, ' ').slice(0, 180)
      };
    } catch (error) {
      return {
        status: 0,
        contentType: '',
        json: false,
        ok: false,
        code: 'FETCH_EXCEPTION',
        message: String(error && error.message || error || 'UNKNOWN').slice(0, 180),
        hasToken: false,
        locationHost: '',
        bodyPrefix: ''
      };
    }
  }

  try {
    const props = PropertiesService.getScriptProperties();
    const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
    result.realtimeEnabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() === 'Y';
    result.apiConfigured = Boolean(apiBase);
    result.apiHost = apiBase.replace(/^https?:\/\//i, '').split('/')[0].slice(0, 180);
    if (!apiBase) throw new Error('NOVA_REALTIME_API_BASE_EMPTY');

    result.stage = 'HEALTH';
    result.health = safeProbe_('get', apiBase + '/health', '');

    result.stage = 'AUTH_TOKEN_PREP';
    const diagnosticUser = getActiveUsersByRole_(['ADMIN', 'ORDER'])[0];
    if (!diagnosticUser || !diagnosticUser.employeeNo) throw new Error('DIAGNOSTIC_USER_NOT_FOUND');
    const novaToken = createLoginToken_(diagnosticUser.employeeNo);

    result.stage = 'API_AUTH';
    result.apiAuth = safeProbe_('post', apiBase + '/api/auth/realtime-token', novaToken);

    result.stage = 'LEGACY_AUTH';
    result.legacyAuth = safeProbe_('post', apiBase + '/v1/auth/realtime-token', novaToken);

    result.stage = 'DONE';
    result.ok = true;
  } catch (error) {
    result.error = String(error && error.message || error || 'UNKNOWN').slice(0, 180);
  }

  result.elapsedMs = Date.now() - startedAt;
  return result;
}
