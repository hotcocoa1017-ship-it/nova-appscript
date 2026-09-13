/**
 * ROOM_UPLOAD_NETWORK_FALLBACK_V1
 *
 * Browser -> Supabase PostgREST 요청이 네트워크 단계에서 실패할 때만 사용하는
 * Apps Script 서버측 전송 브리지입니다.
 *
 * 안전 원칙:
 * - nova-realtime 프로젝트의 객실업로드 RPC 3개만 허용
 * - POST + JSON만 허용
 * - 브라우저가 이미 보유한 Supabase JWT/apikey를 그대로 전달
 * - HTTP 4xx/5xx는 정상 응답으로 되돌려 기존 Client.html 오류처리가 담당
 * - 업무규칙/DB 함수/Sheet mirror 로직은 변경하지 않음
 */
function novaRoomUploadFetchProxyV1(payload) {
  const input = payload && typeof payload === 'object' ? payload : {};
  const url = String(input.url || '').trim();
  const method = String(input.method || 'POST').trim().toUpperCase();
  const body = String(input.body || '');
  const headers = input.headers && typeof input.headers === 'object' ? input.headers : {};

  const allowedOrigin = 'https://evoetxfjmkkjptucwxsv.supabase.co';
  const allowedPaths = new Set([
    '/rest/v1/rpc/nova_room_upload_state_v3',
    '/rest/v1/rpc/nova_room_upload_apply_v5',
    '/rest/v1/rpc/nova_room_upload_mark_stage_v1'
  ]);

  let parsed;
  try {
    parsed = new URL(url);
  } catch (error) {
    throw new Error('객실업로드 네트워크 대체경로 URL이 올바르지 않습니다.');
  }

  const origin = `${parsed.protocol}//${parsed.host}`;
  if (origin !== allowedOrigin || !allowedPaths.has(parsed.pathname) || parsed.search || parsed.hash) {
    throw new Error('허용되지 않은 객실업로드 네트워크 대체경로입니다.');
  }
  if (method !== 'POST') {
    throw new Error('객실업로드 네트워크 대체경로는 POST만 허용합니다.');
  }
  if (body.length > 4 * 1024 * 1024) {
    throw new Error('객실업로드 요청 크기가 안전 한도를 초과했습니다.');
  }

  const authorization = String(headers.Authorization || headers.authorization || '').trim();
  const apiKey = String(headers.apikey || headers.apiKey || '').trim();
  if (!authorization.startsWith('Bearer ') || !apiKey) {
    throw new Error('객실업로드 네트워크 대체경로 인증정보가 없습니다.');
  }

  let response;
  try {
    response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: body,
      headers: {
        Authorization: authorization,
        apikey: apiKey,
        Accept: 'application/json'
      },
      muteHttpExceptions: true,
      followRedirects: false,
      validateHttpsCertificates: true
    });
  } catch (error) {
    throw new Error(`객실업로드 서버 대체전송 실패: ${String(error && error.message || error)}`);
  }

  const status = Number(response.getResponseCode() || 0);
  const responseHeaders = response.getAllHeaders ? response.getAllHeaders() : {};
  const contentType = String(
    responseHeaders['Content-Type'] ||
    responseHeaders['content-type'] ||
    'application/json; charset=utf-8'
  );

  return {
    ok: true,
    proxied: true,
    status,
    contentType,
    body: response.getContentText()
  };
}
