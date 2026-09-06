export class SupabaseRpcError extends Error {
  constructor(message, { status = 500, code = '', details = '', hint = '', body = null } = {}) {
    super(message);
    this.name = 'SupabaseRpcError';
    this.status = Number(status || 500);
    this.code = String(code || '');
    this.details = String(details || '');
    this.hint = String(hint || '');
    this.body = body;
  }
}

export class SupabaseResultUnknownError extends Error {
  constructor(message, cause) {
    super(message, cause ? { cause } : undefined);
    this.name = 'SupabaseResultUnknownError';
    this.retryable = true;
  }
}

function normalizeUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function isRetryableStatus(status) {
  return status === 408 || status === 429 || status >= 500;
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function readResponseBody(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

/**
 * Cloud Run -> Supabase RPC adapter.
 *
 * The caller's bearer token is forwarded to Supabase. The server never uses a
 * service-role key for employee mutations; DB authorization is performed from
 * the authenticated user's JWT inside nova_roommaid_action_v2.
 */
export function createSupabaseRoomActionClient({
  supabaseUrl,
  apiKey,
  fetchImpl = globalThis.fetch,
  timeoutMs = 2500,
  maxAttempts = 3,
} = {}) {
  const baseUrl = normalizeUrl(supabaseUrl);
  const safeApiKey = String(apiKey || '').trim();
  const attempts = Math.max(1, Math.min(5, Number(maxAttempts || 3)));
  const timeout = Math.max(500, Math.min(10000, Number(timeoutMs || 2500)));

  if (!baseUrl) throw new Error('SUPABASE_URL is required');
  if (!safeApiKey) throw new Error('SUPABASE_PUBLISHABLE_KEY is required');
  if (typeof fetchImpl !== 'function') throw new Error('fetch implementation is required');

  async function executeRoommaidAction({
    authToken,
    businessDate,
    site,
    roomNo,
    action,
    expectedVersion = 0,
    requestId,
  }) {
    const requestBody = JSON.stringify({
      p_business_date: businessDate,
      p_site: site,
      p_room_no: roomNo,
      p_action: action,
      p_expected_version: Number(expectedVersion || 0),
      p_request_id: requestId,
    });

    let lastNetworkError = null;

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      let response;

      try {
        response = await fetchImpl(`${baseUrl}/rest/v1/rpc/nova_roommaid_action_v2`, {
          method: 'POST',
          headers: {
            apikey: safeApiKey,
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-Client-Info': 'nova-core3-server/3.0.0-alpha.2',
          },
          body: requestBody,
          signal: controller.signal,
        });
      } catch (error) {
        lastNetworkError = error;
        if (attempt < attempts) {
          await delay(40 * attempt);
          continue;
        }
        throw new SupabaseResultUnknownError(
          'DB 처리 결과를 확인할 수 없습니다. 같은 Idempotency-Key로 재시도해야 합니다.',
          error,
        );
      } finally {
        clearTimeout(timer);
      }

      const body = await readResponseBody(response);
      if (response.ok) {
        return body;
      }

      if (isRetryableStatus(response.status) && attempt < attempts) {
        await delay(40 * attempt);
        continue;
      }

      const message = body?.message || `Supabase RPC failed (${response.status})`;
      throw new SupabaseRpcError(message, {
        status: response.status,
        code: body?.code,
        details: body?.details,
        hint: body?.hint,
        body,
      });
    }

    throw new SupabaseResultUnknownError(
      'DB 처리 결과를 확인할 수 없습니다. 같은 Idempotency-Key로 재시도해야 합니다.',
      lastNetworkError,
    );
  }

  return { executeRoommaidAction };
}
