/**
 * 로그인 기준: 아이디=이름, 비밀번호=사번
 * 별도 로그인 시트나 직원마스터를 만들지 않음
 */
// SITE_SCOPE_INDICATOR_CLOSE_V2
const NOVA_LOGIN_SITES_ = Object.freeze(['쏘라노', '별관']);

function normalizeNovaLoginSite_(value) { // (로그인·세션 사업장 정규화)
  return String(value || '').trim();
}

function isNovaSiteScopedRole_(role) { // (관리자·오더테이커 제외 사업장 고정 역할)
  return !['ADMIN', 'ORDER'].includes(String(role || '').trim().toUpperCase());
}

function resolveNovaLoginSite_(user, selectedSite) { // (신규 로그인 사업장 검증)
  const role = String(user && user.role || '').trim().toUpperCase();
  if (!isNovaSiteScopedRole_(role)) return '';
  const site = normalizeNovaLoginSite_(selectedSite);
  if (!site) throw new Error('사업장을 선택하세요.');
  if (!NOVA_LOGIN_SITES_.includes(site)) throw new Error('사용할 수 없는 사업장입니다.');
  const configured = normalizeNovaLoginSite_(user && user.defaultSite);
  if (configured && configured !== site) {
    throw new Error(`계정 기본사업장(${configured})과 선택한 사업장(${site})이 다릅니다.`);
  }
  return site;
}

function resolveUserSessionSite_(user, requestedSite) { // (API 요청 사업장을 로그인 세션 범위로 고정)
  const role = String(user && user.role || '').trim().toUpperCase();
  const requested = normalizeNovaLoginSite_(requestedSite);
  if (!isNovaSiteScopedRole_(role)) return requested;
  const sessionSite = normalizeNovaLoginSite_(user && (user.sessionSite || user.defaultSite));
  // 배포 이전 토큰은 site가 없을 수 있으므로 기존 세션은 만료 전까지 호환합니다.
  if (!sessionSite) return requested;
  if (requested && requested !== sessionSite) {
    throw new Error(`로그인 사업장(${sessionSite})과 다른 사업장은 조회하거나 처리할 수 없습니다.`);
  }
  return sessionSite;
}

function loginNova(name, employeeNo, site) { // (사용자 로그인)
  return measureResponse_('loginNova', () => {
    const user = authenticateNovaUser_(name, employeeNo, site);
    const token = createLoginToken_(user.employeeNo, user.sessionSite);
    return {
      ok: true,
      token,
      user: getPublicUser_(user)
    };
  });
}

function loginNovaBootstrap(name, employeeNo, clientType, site) { // (로그인·초기화 1회 통신)
  return measureResponse_('loginNovaBootstrap', () => {
    const user = authenticateNovaUser_(name, employeeNo, site);
    const token = createLoginToken_(user.employeeNo, user.sessionSite);
    return {
      ok: true,
      token,
      bootstrap: buildBootstrapPayload_(user, clientType)
    };
  });
}

function authenticateNovaUser_(name, employeeNo, loginSite) { // (이름·사번·사업장 로그인 검증 공통)
  const safeName = String(name || '').trim();
  const safeEmployeeNo = String(employeeNo || '').trim();
  if (!safeName || !safeEmployeeNo) {
    throw new Error('이름과 사번을 입력하세요.');
  }

  const matchedByName = getActiveUsersByName_(safeName);
  const sourceUser = matchedByName.find(item => item.employeeNo === safeEmployeeNo);
  if (!sourceUser) throw new Error('이름 또는 사번이 일치하지 않습니다.');
  const sessionSite = resolveNovaLoginSite_(sourceUser, loginSite);
  return Object.assign({}, sourceUser, {
    sessionSite,
    siteScopeLocked: Boolean(isNovaSiteScopedRole_(sourceUser.role) && sessionSite),
    defaultSite: sessionSite || sourceUser.defaultSite
  });
}

function verifyNovaToken(token) { // (로그인 토큰 검증·사업장 세션 복원)
  try {
    const payload = parseAndVerifyToken_(token);
    const sourceUser = getActiveUserByEmployeeNo_(payload.employeeNo);
    if (!sourceUser) return { ok: false, code: 'UNAUTHORIZED' };
    const scopedRole = isNovaSiteScopedRole_(sourceUser.role);
    const tokenSite = normalizeNovaLoginSite_(payload.site);
    const configuredSite = normalizeNovaLoginSite_(sourceUser.defaultSite);
    // 신규 토큰은 tokenSite를 원본으로 사용합니다. 배포 이전 토큰(site 없음)은 기존 기본사업장으로 호환합니다.
    const sessionSite = scopedRole ? (tokenSite || configuredSite) : '';
    if (scopedRole && tokenSite && configuredSite && tokenSite !== configuredSite) {
      return { ok: false, code: 'SITE_SCOPE_CHANGED', message: '계정 사업장이 변경되었습니다. 다시 로그인하세요.' };
    }
    const user = Object.assign({}, sourceUser, {
      sessionSite,
      siteScopeLocked: Boolean(scopedRole && sessionSite),
      defaultSite: sessionSite || sourceUser.defaultSite
    });
    return { ok: true, user };
  } catch (error) {
    return { ok: false, code: 'UNAUTHORIZED', message: error.message };
  }
}

function createLoginToken_(employeeNo, site) { // (서명 로그인 토큰 생성·사업장 범위 포함)
  const now = Date.now();
  const payload = {
    employeeNo: String(employeeNo),
    site: normalizeNovaLoginSite_(site),
    issuedAt: now,
    expiresAt: now + NOVA.LOGIN_TOKEN_HOURS * 60 * 60 * 1000
  };
  const body = Utilities.base64EncodeWebSafe(JSON.stringify(payload), Utilities.Charset.UTF_8);
  const signature = signTokenBody_(body);
  return `${body}.${signature}`;
}

function parseAndVerifyToken_(token) { // (서명 로그인 토큰 해석)
  const parts = String(token || '').split('.');
  if (parts.length !== 2) throw new Error('로그인 정보가 올바르지 않습니다.');

  const [body, signature] = parts;
  if (signTokenBody_(body) !== signature) throw new Error('로그인 정보가 변경되었습니다.');

  const json = Utilities.newBlob(Utilities.base64DecodeWebSafe(body)).getDataAsString('UTF-8');
  const payload = JSON.parse(json);
  if (!payload.expiresAt || Date.now() > payload.expiresAt) {
    throw new Error('로그인 시간이 만료되었습니다.');
  }
  return payload;
}

function signTokenBody_(body) { // (로그인 토큰 서명)
  const properties = PropertiesService.getScriptProperties();
  let secret = properties.getProperty('NOVA_TOKEN_SECRET');
  if (!secret) {
    secret = Utilities.getUuid() + Utilities.getUuid();
    properties.setProperty('NOVA_TOKEN_SECRET', secret);
  }
  const bytes = Utilities.computeHmacSha256Signature(body, secret);
  return Utilities.base64EncodeWebSafe(bytes);
}
