import {
  SupabaseRpcError,
  SupabaseResultUnknownError,
} from './supabase-room-action-client.mjs';

const ALLOWED_ACTIONS = new Set(['CLEANING_START', 'CLEANING_COMPLETE']);
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function text(value) {
  return String(value ?? '').trim();
}

function errorResponse(status, code, message, extra = {}) {
  return {
    status,
    body: {
      ok: false,
      code,
      message,
      ...extra,
    },
  };
}

function parseBearer(authorization) {
  const match = /^Bearer\s+(.+)$/i.exec(text(authorization));
  return match ? text(match[1]) : '';
}

function validateCommonRead({ authorization, businessDate, site }) {
  const authToken = parseBearer(authorization);
  if (!authToken) {
    return errorResponse(401, 'UNAUTHORIZED', '로그인이 필요합니다.');
  }

  const safeBusinessDate = text(businessDate);
  const safeSite = text(site);
  if (!DATE_RE.test(safeBusinessDate)) {
    return errorResponse(400, 'INVALID_BUSINESS_DATE', '업무일자를 확인하세요.');
  }
  if (!safeSite) {
    return errorResponse(400, 'INVALID_SITE', '사업장을 확인하세요.');
  }

  return {
    authToken,
    businessDate: safeBusinessDate,
    site: safeSite,
  };
}

function validateMutation({ authorization, idempotencyKey, roomNo, body }) {
  const common = validateCommonRead({
    authorization,
    businessDate: body?.businessDate,
    site: body?.site,
  });
  if (common.status) return common;

  const requestId = text(idempotencyKey);
  if (requestId.length < 8 || requestId.length > 160) {
    return errorResponse(400, 'INVALID_IDEMPOTENCY_KEY', '유효한 Idempotency-Key가 필요합니다.');
  }

  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return errorResponse(400, 'INVALID_BODY', '요청 본문을 확인하세요.');
  }

  const safeRoomNo = text(roomNo);
  const action = text(body.action).toUpperCase();
  const expectedVersion = Number(body.expectedVersion ?? 0);

  if (!safeRoomNo) {
    return errorResponse(400, 'INVALID_ROOM', '객실번호를 확인하세요.');
  }
  if (!ALLOWED_ACTIONS.has(action)) {
    return errorResponse(400, 'UNSUPPORTED_ACTION', '현재 Core 3.0 단계에서 지원하지 않는 객실 작업입니다.');
  }
  if (!Number.isInteger(expectedVersion) || expectedVersion < 0) {
    return errorResponse(400, 'INVALID_EXPECTED_VERSION', '객실 버전을 확인하세요.');
  }

  return {
    ...common,
    requestId,
    roomNo: safeRoomNo,
    action,
    expectedVersion,
  };
}

function mapRpcError(error, { mutation = false } = {}) {
  if (error instanceof SupabaseResultUnknownError) {
    return errorResponse(
      503,
      'RESULT_UNKNOWN',
      '서버 응답이 끊겨 처리 결과를 확정할 수 없습니다. 같은 Idempotency-Key로 다시 시도하세요.',
      { retryable: true, reuseIdempotencyKey: true },
    );
  }

  if (!(error instanceof SupabaseRpcError)) {
    return errorResponse(500, 'INTERNAL_ERROR', '서버 처리 중 오류가 발생했습니다.');
  }

  const code = text(error.code).toUpperCase();
  if (error.status === 401) {
    return errorResponse(401, 'UNAUTHORIZED', '로그인이 만료되었거나 유효하지 않습니다.');
  }
  if (error.status === 403 || code === '42501') {
    return errorResponse(403, 'FORBIDDEN', error.message || '처리 권한이 없습니다.');
  }
  if (code === '22023') {
    return errorResponse(400, 'INVALID_REQUEST', error.message || '요청 값을 확인하세요.');
  }
  if (code === 'P0002') {
    return errorResponse(404, 'ROOM_NOT_FOUND', error.message || '객실을 찾을 수 없습니다.');
  }
  if (code === '23505') {
    return errorResponse(409, 'IDEMPOTENCY_KEY_REUSED', error.message || '이미 다른 요청에 사용된 요청키입니다.');
  }
  if (code === '40001') {
    return errorResponse(409, 'STATE_CHANGED', error.message || '최신 객실 상태로 다시 동기화해야 합니다.', {
      retryable: true,
    });
  }
  if (code === '55000') {
    return errorResponse(409, 'STATE_CONFLICT', error.message || '현재 객실 상태에서는 처리할 수 없습니다.');
  }
  if (error.status === 408 || error.status === 429 || error.status >= 500) {
    return errorResponse(503, 'UPSTREAM_UNAVAILABLE', 'DB 서비스가 일시적으로 응답하지 않습니다.', {
      retryable: true,
      ...(mutation ? { reuseIdempotencyKey: true } : {}),
    });
  }

  return errorResponse(500, 'UPSTREAM_ERROR', 'DB 처리 중 오류가 발생했습니다.');
}

export function createRoomActionService({ rpcClient } = {}) {
  if (!rpcClient || typeof rpcClient.executeRoommaidAction !== 'function' || typeof rpcClient.listRoommaidRooms !== 'function') {
    throw new Error('rpcClient.executeRoommaidAction and rpcClient.listRoommaidRooms are required');
  }

  return {
    async listRooms(request) {
      const validated = validateCommonRead(request);
      if (validated.status) return validated;

      try {
        const result = await rpcClient.listRoommaidRooms(validated);
        return { status: 200, body: result };
      } catch (error) {
        return mapRpcError(error, { mutation: false });
      }
    },

    async mutateRoom(request) {
      const validated = validateMutation(request);
      if (validated.status) return validated;

      try {
        const result = await rpcClient.executeRoommaidAction(validated);
        return { status: 200, body: result };
      } catch (error) {
        return mapRpcError(error, { mutation: true });
      }
    },
  };
}
