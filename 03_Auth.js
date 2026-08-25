/**
 * 로그인 기준: 아이디=이름, 비밀번호=사번
 * 별도 로그인 시트나 직원마스터를 만들지 않음
 */
function loginNova(name, employeeNo) { // (사용자 로그인)
  return measureResponse_('loginNova', () => {
    const user = authenticateNovaUser_(name, employeeNo);
    const token = createLoginToken_(user.employeeNo);
    return {
      ok: true,
      token,
      user: getPublicUser_(user)
    };
  });
}

function loginNovaBootstrap(name, employeeNo, clientType) { // (로그인·초기화 1회 통신)
  return measureResponse_('loginNovaBootstrap', () => {
    const user = authenticateNovaUser_(name, employeeNo);
    const token = createLoginToken_(user.employeeNo);
    return {
      ok: true,
      token,
      bootstrap: buildBootstrapPayload_(user, clientType)
    };
  });
}

function authenticateNovaUser_(name, employeeNo) { // (이름·사번 로그인 검증 공통)
  const safeName = String(name || '').trim();
  const safeEmployeeNo = String(employeeNo || '').trim();
  if (!safeName || !safeEmployeeNo) {
    throw new Error('이름과 사번을 입력하세요.');
  }

  const matchedByName = getActiveUsersByName_(safeName);
  const user = matchedByName.find(item => item.employeeNo === safeEmployeeNo);
  if (!user) throw new Error('이름 또는 사번이 일치하지 않습니다.');
  return user;
}

function verifyNovaToken(token) { // (로그인 토큰 검증)
  try {
    const payload = parseAndVerifyToken_(token);
    const user = getActiveUserByEmployeeNo_(payload.employeeNo);
    if (!user) return { ok: false, code: 'UNAUTHORIZED' };
    return { ok: true, user };
  } catch (error) {
    return { ok: false, code: 'UNAUTHORIZED', message: error.message };
  }
}

function createLoginToken_(employeeNo) { // (서명 로그인 토큰 생성)
  const now = Date.now();
  const payload = {
    employeeNo: String(employeeNo),
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
