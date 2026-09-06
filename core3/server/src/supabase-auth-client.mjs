import { SupabaseRpcError } from './supabase-room-action-client.mjs';

function normalizeUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function text(value) {
  return String(value ?? '').trim();
}

async function parseBody(response) {
  const raw = await response.text();
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return { message: raw }; }
}

export function createSupabaseAuthClient({ supabaseUrl, apiKey, fetchImpl = globalThis.fetch, timeoutMs = 2500 } = {}) {
  const baseUrl = normalizeUrl(supabaseUrl);
  const safeApiKey = text(apiKey);
  const timeout = Math.max(500, Math.min(10000, Number(timeoutMs || 2500)));
  if (!baseUrl) throw new Error('SUPABASE_URL is required');
  if (!safeApiKey) throw new Error('SUPABASE_PUBLISHABLE_KEY is required');
  if (typeof fetchImpl !== 'function') throw new Error('fetch implementation is required');

  async function rpc(name, body, authToken = '') {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    let response;
    try {
      const headers = {
        apikey: safeApiKey,
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Client-Info': 'nova-core3-server/3.0.0-alpha.3',
      };
      if (text(authToken)) headers.Authorization = `Bearer ${text(authToken)}`;
      response = await fetchImpl(`${baseUrl}/rest/v1/rpc/${name}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body || {}),
        signal: controller.signal,
      });
    } catch (error) {
      throw new SupabaseRpcError('인증 DB 응답을 받을 수 없습니다.', {
        status: 503,
        code: error?.name === 'AbortError' ? 'TIMEOUT' : 'NETWORK_ERROR',
      });
    } finally {
      clearTimeout(timer);
    }

    const parsed = await parseBody(response);
    if (response.ok) return parsed;
    throw new SupabaseRpcError(parsed?.message || `Supabase auth RPC failed (${response.status})`, {
      status: response.status,
      code: parsed?.code,
      details: parsed?.details,
      hint: parsed?.hint,
      body: parsed,
    });
  }

  return {
    loginIdentity({ name, employeeNo, site }) {
      return rpc('nova_core_login_identity_v1', {
        p_name: text(name),
        p_employee_no: text(employeeNo),
        p_site: text(site),
      });
    },
    me({ authToken }) {
      return rpc('nova_core_me_v1', {}, authToken);
    },
  };
}
