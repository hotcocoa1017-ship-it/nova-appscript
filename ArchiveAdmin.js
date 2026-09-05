/**
 * NOVA Archive 관리자 전용 서버 브리지
 * - 브라우저에는 Archive 서버키를 노출하지 않음
 * - 기존 NOVA 로그인 토큰을 서버에서 다시 검증하고 ADMIN만 허용
 * - NOVA_TOKEN_SECRET에서 Archive 전용 키를 파생하여 Supabase Edge에 서버간 호출
 */
const NOVA_ARCHIVE_ADMIN_EDGE_URL_ = 'https://evoetxfjmkkjptucwxsv.supabase.co/functions/v1/nova-archive-admin-v1';
const NOVA_ARCHIVE_ADMIN_CONTEXT_ = 'NOVA_ARCHIVE_ADMIN_KEY_V1';

function requireNovaArchiveAdmin_(token) { // (Archive 관리자 권한 검증)
  const auth = verifyNovaToken(token);
  if (!auth || !auth.ok || !auth.user) {
    const error = new Error((auth && auth.message) || '로그인이 필요합니다.');
    error.code = 'UNAUTHORIZED';
    throw error;
  }
  const role = String(auth.user.role || '').trim().toUpperCase();
  if (role !== 'ADMIN') {
    const error = new Error('관리자만 Archive 이력을 조회할 수 있습니다.');
    error.code = 'ARCHIVE_ADMIN_ONLY';
    throw error;
  }
  return auth.user;
}

function novaArchiveAdminKey_() { // (기존 NOVA 비밀키에서 Archive 전용 서버키 파생)
  const secret = String(PropertiesService.getScriptProperties().getProperty('NOVA_TOKEN_SECRET') || '').trim();
  if (!secret) {
    const error = new Error('Archive 서버 인증키를 생성할 수 없습니다.');
    error.code = 'ARCHIVE_SERVER_CONFIG';
    throw error;
  }
  const bytes = Utilities.computeHmacSha256Signature(
    NOVA_ARCHIVE_ADMIN_CONTEXT_,
    secret,
    Utilities.Charset.UTF_8
  );
  return Utilities.base64EncodeWebSafe(bytes).replace(/=+$/g, '');
}

function novaArchiveAdminPost_(token, action, payload) { // (Supabase Archive Admin Edge 서버간 호출)
  requireNovaArchiveAdmin_(token);
  const safeAction = String(action || '').trim().toLowerCase();
  if (!['status', 'query', 'restore'].includes(safeAction)) {
    const error = new Error('지원하지 않는 Archive 작업입니다.');
    error.code = 'ARCHIVE_ACTION_INVALID';
    throw error;
  }

  const body = JSON.stringify({
    action: safeAction,
    payload: payload && typeof payload === 'object' ? payload : {}
  });
  const response = UrlFetchApp.fetch(NOVA_ARCHIVE_ADMIN_EDGE_URL_, {
    method: 'post',
    contentType: 'application/json; charset=utf-8',
    headers: {
      'X-NOVA-Archive-Admin-Key': novaArchiveAdminKey_()
    },
    payload: body,
    muteHttpExceptions: true,
    followRedirects: true
  });

  const status = Number(response.getResponseCode() || 0);
  const text = response.getContentText('UTF-8');
  let result = {};
  try {
    result = text ? JSON.parse(text) : {};
  } catch (parseError) {
    const error = new Error('Archive 서버 응답을 확인할 수 없습니다.');
    error.code = 'ARCHIVE_INVALID_RESPONSE';
    throw error;
  }

  if (status >= 200 && status < 300 && result && result.ok) return result;
  const error = new Error(String(result && result.message || `Archive 요청을 처리할 수 없습니다. (${status || 'NO_STATUS'})`));
  error.code = String(result && result.code || 'ARCHIVE_REQUEST_FAILED');
  throw error;
}

function getNovaArchiveAdminStatus(token) { // (Archive 무결성 상태 조회)
  return measureResponse_('getNovaArchiveAdminStatus', () =>
    novaArchiveAdminPost_(token, 'status', {})
  );
}

function queryNovaArchiveAdmin(token, filters) { // (Archive 이력 인덱스 검색)
  return measureResponse_('queryNovaArchiveAdmin', () => {
    const source = filters && typeof filters === 'object' ? filters : {};
    return novaArchiveAdminPost_(token, 'query', {
      sourceType: String(source.sourceType || 'WORK_HISTORY').trim(),
      businessDate: String(source.businessDate || '').trim(),
      site: String(source.site || '').trim(),
      roomNo: String(source.roomNo || '').trim(),
      employeeNo: String(source.employeeNo || '').trim(),
      recordType: String(source.recordType || '').trim(),
      archiveKey: String(source.archiveKey || '').trim(),
      limit: Math.max(1, Math.min(Number(source.limit || 100) || 100, 200))
    });
  });
}

function restoreNovaArchiveAdminRecord(token, archiveKey) { // (Storage 원본 1건 복원조회)
  return measureResponse_('restoreNovaArchiveAdminRecord', () => {
    const key = String(archiveKey || '').trim();
    if (!key) throw new Error('조회할 Archive Key가 없습니다.');
    return novaArchiveAdminPost_(token, 'restore', { archiveKey: key });
  });
}
