import { SupabaseRpcError } from './supabase-room-action-client.mjs';

function text(value) {
  return String(value ?? '').trim();
}

function errorResponse(status, code, message) {
  return { status, body: { ok: false, code, message } };
}

function parseBearer(authorization) {
  const match = /^Bearer\s+(.+)$/i.exec(text(authorization));
  return match ? text(match[1]) : '';
}

function mapAuthError(error) {
  if (!(error instanceof SupabaseRpcError)) {
    return errorResponse(500, 'INTERNAL_ERROR', '인증 처리 중 오류가 발생했습니다.');
  }
  const code = text(error.code).toUpperCase();
  if (error.status === 401) return errorResponse(401, 'UNAUTHORIZED', '로그인이 만료되었거나 유효하지 않습니다.');
  if (error.status === 403 || code === '42501') return errorResponse(403, 'INVALID_CREDENTIALS', error.message || '로그인 정보를 확인하세요.');
  if (code === '22023') return errorResponse(400, 'INVALID_LOGIN_INPUT', error.message || '로그인 입력값을 확인하세요.');
  if (error.status === 408 || error.status === 429 || error.status >= 500) {
    return errorResponse(503, 'AUTH_UPSTREAM_UNAVAILABLE', '인증 서비스가 일시적으로 응답하지 않습니다.');
  }
  return errorResponse(500, 'AUTH_UPSTREAM_ERROR', '인증 처리 중 오류가 발생했습니다.');
}

export function createAuthService({ authClient, tokenSigner, realtimeConfig = {} } = {}) {
  if (!authClient || typeof authClient.loginIdentity !== 'function' || typeof authClient.me !== 'function') {
    throw new Error('authClient.loginIdentity and authClient.me are required');
  }
  if (!tokenSigner || typeof tokenSigner.sign !== 'function') {
    throw new Error('tokenSigner.sign is required');
  }

  const realtimeSupabaseUrl = text(realtimeConfig.supabaseUrl);
  const realtimePublishableKey = text(realtimeConfig.publishableKey);

  async function verifyBearer(authorization) {
    const authToken = parseBearer(authorization);
    if (!authToken) return { error: errorResponse(401, 'UNAUTHORIZED', '로그인이 필요합니다.') };
    try {
      const user = await authClient.me({ authToken });
      return { authToken, user };
    } catch (error) {
      return { error: mapAuthError(error) };
    }
  }

  return {
    async login(body) {
      if (!body || typeof body !== 'object' || Array.isArray(body)) {
        return errorResponse(400, 'INVALID_BODY', '로그인 요청을 확인하세요.');
      }
      const name = text(body.name);
      const employeeNo = text(body.employeeNo);
      const site = text(body.site);
      if (!name || !employeeNo) return errorResponse(400, 'INVALID_LOGIN_INPUT', '이름과 사번을 입력하세요.');
      if (name.length > 80 || employeeNo.length > 40 || site.length > 40) {
        return errorResponse(400, 'INVALID_LOGIN_INPUT', '로그인 입력값을 확인하세요.');
      }

      try {
        const user = await authClient.loginIdentity({ name, employeeNo, site });
        const signed = tokenSigner.sign(user);
        return {
          status: 200,
          body: {
            ok: true,
            tokenType: 'Bearer',
            accessToken: signed.accessToken,
            expiresAt: signed.expiresAt,
            expiresIn: signed.expiresIn,
            user: {
              employeeNo: text(user?.employeeNo),
              name: text(user?.name),
              role: text(user?.role).toUpperCase(),
              sessionSite: text(user?.sessionSite),
              defaultSite: text(user?.defaultSite),
              allowedSites: Array.isArray(user?.allowedSites) ? user.allowedSites : [],
            },
          },
        };
      } catch (error) {
        return mapAuthError(error);
      }
    },

    async me({ authorization } = {}) {
      const verified = await verifyBearer(authorization);
      if (verified.error) return verified.error;
      return { status: 200, body: verified.user };
    },

    async realtimeConfig({ authorization } = {}) {
      const verified = await verifyBearer(authorization);
      if (verified.error) return verified.error;
      if (!realtimeSupabaseUrl || !realtimePublishableKey) {
        return errorResponse(503, 'REALTIME_CONFIG_UNAVAILABLE', 'Realtime 연결 설정을 사용할 수 없습니다.');
      }
      return {
        status: 200,
        body: {
          ok: true,
          supabaseUrl: realtimeSupabaseUrl,
          publishableKey: realtimePublishableKey,
          privateChannel: true,
          topicPattern: 'nova:site:{site}:rooms',
          sessionSite: text(verified.user?.sessionSite),
        },
      };
    },
  };
}
