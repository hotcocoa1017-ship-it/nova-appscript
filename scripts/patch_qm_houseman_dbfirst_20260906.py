from pathlib import Path
import sys

CLIENT = Path('Client.html')
MARKER = 'QM_HOUSEMAN_DBFIRST_V1'


def fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(96)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly 1 anchor, found {count}')
    return text.replace(old, new, 1)


def main():
    text = CLIENT.read_text(encoding='utf-8')
    if MARKER in text:
        print('QM houseman DB-first patch already applied.')
        return

    helper_anchor = "  async function novaRealtimeCreateHousemanOrder_(payload, authRetry = 0) { // (Cloud Run/PostgreSQL 등록 확정)\n"
    if text.count(helper_anchor) != 1:
        fail(f'QM helper insertion anchor count={text.count(helper_anchor)}')

    helper = r'''  // QM_HOUSEMAN_DBFIRST_V1 · QM 하우스맨 요청 PostgreSQL 직접확정
  async function novaQmHousemanDbFirstRpc_(apiPayload) {
    if (!apiPayload?.orderId || !apiPayload?.requestId) {
      throw new Error('QM 하우스맨 요청 정보를 확인하세요.');
    }

    let auth = await novaRealtimeGetAuth_();
    let lastNetworkError = null;
    const waits = [180, 520, 1100];

    for (let attempt = 0; attempt < 3; attempt += 1) {
      const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_create_qm_houseman_order`;
      let response;
      try {
        response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'apikey': String(auth.publishableKey || ''),
            'Authorization': `Bearer ${String(auth.token || '')}`
          },
          body: JSON.stringify({ p_payload: apiPayload })
        });
      } catch (error) {
        lastNetworkError = error;
        if (attempt < 2) {
          await novaRealtimeSleep_(waits[attempt] || 520);
          continue;
        }
        const unknown = new Error('QM 하우스맨 요청의 DB 처리 결과를 확인할 수 없습니다. 같은 요청으로 다시 확인해 주세요.');
        unknown.code = 'QM_HOUSEMAN_DB_RESULT_UNKNOWN';
        unknown.status = 0;
        unknown.cause = lastNetworkError;
        throw unknown;
      }

      let data = {};
      try { data = await response.json(); } catch (ignore) {}
      if (response.ok && data?.ok && data?.order?.orderId) return data;

      const code = String(data?.code || data?.error?.code || '').trim().toUpperCase();
      if (response.status === 401 && attempt === 0) {
        auth = await novaRealtimeGetAuth_();
        continue;
      }

      if ((response.status === 429 || response.status >= 500) && attempt < 2) {
        await novaRealtimeSleep_(waits[attempt] || 520);
        continue;
      }

      const rawMessage = data?.message || data?.error?.message || data?.error || '';
      const message = typeof rawMessage === 'string' && rawMessage
        ? rawMessage
        : `QM 하우스맨 DB 등록 오류 (${response.status})`;
      const error = new Error(message);
      error.code = code;
      error.status = Number(response.status || 0);
      error.data = data;
      throw error;
    }

    const unknown = new Error('QM 하우스맨 요청의 DB 처리 결과를 확인할 수 없습니다. 같은 요청으로 다시 확인해 주세요.');
    unknown.code = 'QM_HOUSEMAN_DB_RESULT_UNKNOWN';
    unknown.status = 0;
    unknown.cause = lastNetworkError;
    throw unknown;
  }

'''
    text = text.replace(helper_anchor, helper + helper_anchor, 1)

    old_route = r'''      result = requestRole === 'PUBLIC'
        ? await novaPublicHousemanDbFirstRpc_(apiPayload) // PUBLIC_QM_DBFIRST_ACCEL_20260905
        : await novaRealtimeFetch_('/v1/houseman-orders', {
            method: 'POST',
            headers: { 'X-Request-Id': requestId },
            body: JSON.stringify(apiPayload)
          });'''
    new_route = r'''      result = requestRole === 'PUBLIC'
        ? await novaPublicHousemanDbFirstRpc_(apiPayload) // PUBLIC_QM_DBFIRST_ACCEL_20260905
        : requestRole === 'QM'
          ? await novaQmHousemanDbFirstRpc_(apiPayload) // QM_HOUSEMAN_DBFIRST_V1
          : await novaRealtimeFetch_('/v1/houseman-orders', {
              method: 'POST',
              headers: { 'X-Request-Id': requestId },
              body: JSON.stringify(apiPayload)
            });'''
    text = replace_once(text, old_route, new_route, 'route QM houseman create to direct RPC')

    old_fallback = r'''    } catch (error) {
      if (!['QM', 'PUBLIC'].includes(role)) throw error; // PUBLIC_HOUSEMAN_REQUEST_V1
      console.warn(`[NOVA ${role}] 하우스맨 DB 우선등록 실패 · 기존 모바일 요청으로 fallback`, error);
      const legacy = await callServer('createMobileHousemanRequest', state.token, Object.assign({}, payload || {}, {'''
    new_fallback = r'''    } catch (error) {
      if (!['QM', 'PUBLIC'].includes(role)) throw error; // PUBLIC_HOUSEMAN_REQUEST_V1
      if (role === 'QM') {
        const status = Number(error?.status || 0);
        const code = String(error?.code || '').trim().toUpperCase();
        const rpcUnavailable = status === 404 && ['PGRST202', 'PGRST205'].includes(code);
        // QM_HOUSEMAN_DBFIRST_V1 · 권한/검증/네트워크 결과불명은 Sheet에 이중쓰기하지 않습니다.
        // RPC 자체가 미배포된 경우에만 기존 경로로 안전하게 후퇴합니다.
        if (!rpcUnavailable) throw error;
      }
      console.warn(`[NOVA ${role}] 하우스맨 DB 우선등록 실패 · 기존 모바일 요청으로 fallback`, error);
      const legacy = await callServer('createMobileHousemanRequest', state.token, Object.assign({}, payload || {}, {'''
    text = replace_once(text, old_fallback, new_fallback, 'restrict QM legacy fallback')

    CLIENT.write_text(text, encoding='utf-8')
    print('Applied QM_HOUSEMAN_DBFIRST_V1.')


if __name__ == '__main__':
    main()
