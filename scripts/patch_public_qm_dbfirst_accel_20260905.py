from pathlib import Path

MARKER = 'PUBLIC_QM_DBFIRST_ACCEL_20260905'
path = Path('Client.html')
text = path.read_text(encoding='utf-8')

if MARKER in text:
    print(f'{MARKER} already applied.')
    raise SystemExit(0)


def replace_once(source, old, new, label):
    if old not in source:
        raise SystemExit(f'{label} anchor not found')
    return source.replace(old, new, 1)


# 1) PUBLIC 하우스맨 요청: Cloud Run의 PUBLIC 403 뒤 Sheet fallback 대신
#    검증된 Postgres SECURITY DEFINER RPC로 DB를 먼저 확정합니다.
public_helper = r'''  async function novaPublicHousemanDbFirstRpc_(apiPayload) { // PUBLIC_QM_DBFIRST_ACCEL_20260905
    if (!apiPayload?.orderId || !apiPayload?.requestId) throw new Error('객실퍼블릭 하우스맨 요청 정보를 확인하세요.');
    const auth = await novaRealtimeGetAuth_();
    const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_create_public_houseman_order`;
    const send = async () => {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': String(auth.publishableKey || ''),
          'Authorization': `Bearer ${auth.token}`
        },
        body: JSON.stringify({ p_payload: apiPayload })
      });
      let data = null;
      try { data = await response.json(); } catch (_) {}
      return { response, data };
    };

    let { response, data } = await send();
    // 발급 직후 Supabase 노드 간 시각차로 PGRST303이 발생한 경우에만 같은 토큰으로 1회 재시도합니다.
    if (response.status === 401 && String(data?.code || '').trim().toUpperCase() === 'PGRST303') {
      await new Promise(resolve => window.setTimeout(resolve, 1200));
      ({ response, data } = await send());
    }
    if (!response.ok) {
      const error = new Error(data?.message || data?.details || `객실퍼블릭 DB 등록 오류 (${response.status})`);
      error.status = response.status;
      error.code = data?.code || '';
      throw error;
    }
    if (!data?.ok || !data?.order?.orderId) throw new Error('객실퍼블릭 DB 등록 응답을 확인할 수 없습니다.');
    return data;
  }

'''
anchor = "  async function novaRealtimeCreateHousemanOrder_(payload, authRetry = 0) { // (Cloud Run/PostgreSQL 등록 확정)"
if anchor not in text:
    raise SystemExit('Realtime houseman create anchor not found')
text = text.replace(anchor, public_helper + anchor, 1)

old_send = """    let result;
    try {
      result = await novaRealtimeFetch_('/v1/houseman-orders', {
        method: 'POST',
        headers: { 'X-Request-Id': requestId },
        body: JSON.stringify(apiPayload)
      });
    } catch (error) {"""
new_send = """    let result;
    try {
      const requestRole = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
      result = requestRole === 'PUBLIC'
        ? await novaPublicHousemanDbFirstRpc_(apiPayload) // PUBLIC_QM_DBFIRST_ACCEL_20260905
        : await novaRealtimeFetch_('/v1/houseman-orders', {
            method: 'POST',
            headers: { 'X-Request-Id': requestId },
            body: JSON.stringify(apiPayload)
          });
    } catch (error) {"""
text = replace_once(text, old_send, new_send, 'PUBLIC DB-first create switch')

# 2) QM 초안: 정상 요청에는 지연을 추가하지 않고, 발급 직후 PGRST303일 때만
#    동일 JWT로 1.2초 후 한 번 재시도한 다음 기존 Sheet fallback에 맡깁니다.
old_qm = r'''    const response = await fetch(`${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_save_qm_draft`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': String(auth.publishableKey || ''),
        'Authorization': `Bearer ${auth.token}`
      },
      body: JSON.stringify({
        p_draft_id: String(draft.draftId || ''),
        p_business_date: String(draft.businessDate || active.draft?.businessDate || state.mobile.businessDate || ''),
        p_site: String(draft.site || active.draft?.site || state.mobile.site || ''),
        p_room_no: String(draft.roomNo || active.draft?.roomNo || ''),
        p_checklist_revision: String(active.revision || active.draft?.revision || ''),
        p_answers: Array.isArray(draft.answers) ? draft.answers : [],
        p_defects: Array.isArray(draft.defects) ? draft.defects : [],
        p_expected_version: expectedVersion,
        p_request_id: requestId
      })
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
'''
new_qm = r'''    const send = async () => {
      const response = await fetch(`${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_save_qm_draft`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': String(auth.publishableKey || ''),
          'Authorization': `Bearer ${auth.token}`
        },
        body: JSON.stringify({
          p_draft_id: String(draft.draftId || ''),
          p_business_date: String(draft.businessDate || active.draft?.businessDate || state.mobile.businessDate || ''),
          p_site: String(draft.site || active.draft?.site || state.mobile.site || ''),
          p_room_no: String(draft.roomNo || active.draft?.roomNo || ''),
          p_checklist_revision: String(active.revision || active.draft?.revision || ''),
          p_answers: Array.isArray(draft.answers) ? draft.answers : [],
          p_defects: Array.isArray(draft.defects) ? draft.defects : [],
          p_expected_version: expectedVersion,
          p_request_id: requestId
        })
      });
      let data = null;
      try { data = await response.json(); } catch (_) {}
      return { response, data };
    };
    let { response, data } = await send(); // PUBLIC_QM_DBFIRST_ACCEL_20260905
    if (response.status === 401 && String(data?.code || '').trim().toUpperCase() === 'PGRST303') {
      await new Promise(resolve => window.setTimeout(resolve, 1200));
      ({ response, data } = await send());
    }
'''
text = replace_once(text, old_qm, new_qm, 'QM PostgREST clock-skew retry')

required = [
    MARKER,
    'nova_create_public_houseman_order',
    "requestRole === 'PUBLIC'",
    "novaRealtimeFetch_('/v1/houseman-orders'",
    "rest/v1/rpc/nova_save_qm_draft",
    "PGRST303",
    "callServer('saveQmInspectionDraft'",
    'async function submitQmInspectionFinal_',
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit('Safety validation failed: ' + ', '.join(missing))

for forbidden in ('SUPABASE_SERVICE_ROLE_KEY', 'service_role'):
    if forbidden in public_helper:
        raise SystemExit(f'Forbidden browser credential marker: {forbidden}')

path.write_text(text, encoding='utf-8')
print(f'Applied {MARKER}.')
