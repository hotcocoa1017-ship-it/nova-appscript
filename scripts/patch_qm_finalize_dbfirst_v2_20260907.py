from pathlib import Path

CLIENT = Path('Client.html')
MARKER = 'QM_FINALIZE_DB_FIRST_V2'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected=1')
    return text.replace(old, new, 1)


client = CLIENT.read_text(encoding='utf-8')
if MARKER not in client:
    anchor = "  async function submitQmInspectionDetailWithBusyRetry_(payload) { // LIVE_OPERATION_RETRY_RESILIENCE_V1 · QM 상세이력 BUSY_RETRY 전용 재시도\n"
    helper = r'''  // QM_FINALIZE_DB_FIRST_V2 · 객실 최종상태 + 점검결과 + draft 완료를 PostgreSQL 단일 트랜잭션으로 확정
  function novaQmFinalizeStableRequestId_(active) {
    const date = String(state.mobile.businessDate || '').trim();
    const site = String(state.mobile.site || '').trim();
    const roomNo = String(active?.roomNo || '').trim();
    const draftId = String(active?.draft?.draftId || '').trim() || 'NO_DRAFT';
    const key = `nova-qm-final-v2:${date}:${site}:${roomNo}:${draftId}`;
    try {
      const existing = String(sessionStorage.getItem(key) || '').trim();
      if (existing) return { key, requestId: existing };
    } catch (ignore) {}
    const requestId = novaRealtimeRequestId_('QM_FINALIZE_V2', roomNo);
    try { sessionStorage.setItem(key, requestId); } catch (ignore) {}
    return { key, requestId };
  }

  async function novaQmFinalizeDbFirstV2_(active, draft, passed, requestId) {
    let auth;
    try {
      auth = await novaQmDraftAuthBundle_();
    } catch (error) {
      // 아직 DB 요청을 전송하지 않았으므로 기존 QM_COMPLETE 경로 fallback이 안전합니다.
      console.warn('[NOVA QM] 최종제출 DB 인증 준비 실패 · 기존 경로 사용:', error?.message || error);
      return { ok: false, legacyFallback: true, reason: 'AUTH_PREP_FAILED' };
    }
    if (!auth?.token || !auth?.supabaseUrl || !auth?.publishableKey) {
      return { ok: false, legacyFallback: true, reason: 'AUTH_BUNDLE_MISSING' };
    }

    const room = (state.mobile.data?.rooms || []).find(item => String(item.roomNo || '') === String(active?.roomNo || ''));
    const draftId = String(active?.draft?.draftId || '').trim();
    const inspectionId = draftId || `QMINS-${String(requestId || '').replace(/[^A-Za-z0-9]/g, '').slice(0, 80)}`;
    const body = {
      p_payload: {
        businessDate: String(state.mobile.businessDate || ''),
        site: String(state.mobile.site || ''),
        roomNo: String(active?.roomNo || ''),
        inspectionId,
        draftId,
        checklistRevision: String(active?.checklist?.revision || ''),
        answers: Array.isArray(draft?.answers) ? draft.answers : [],
        defects: Array.isArray(draft?.defects) ? draft.defects : [],
        resultStatus: passed ? 'PASS' : 'FAIL',
        startedAt: String(active?.draft?.startedAt || ''),
        expectedVersion: Number(active?.roomVersion || room?.version || 0)
      },
      p_request_id: String(requestId || '')
    };

    const send = async attempt => {
      const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_qm_inspection_finalize_v2`;
      let response;
      try {
        response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${String(auth.token || '')}`,
            'apikey': String(auth.publishableKey || '')
          },
          body: JSON.stringify(body)
        });
      } catch (networkError) {
        if (attempt < 2) {
          await novaRealtimeSleep_([180, 480, 950][attempt] || 950);
          return send(attempt + 1);
        }
        const error = new Error('QM 최종제출 DB 처리 결과를 확인하지 못했습니다. 화면을 새로고침하여 객실상태를 확인해 주세요.');
        error.code = 'QM_FINALIZE_DB_RESULT_UNKNOWN';
        throw error;
      }

      const data = await response.json().catch(() => ({}));
      if (response.ok && data?.ok) return data;
      const code = String(data?.code || '').trim().toUpperCase();

      if (response.status === 401 && attempt < 2) {
        novaRealtime_.qmDraftAuthBundle = null;
        auth = await novaQmDraftAuthBundle_();
        await novaRealtimeSleep_(140);
        return send(attempt + 1);
      }
      if ((response.status === 429 || response.status >= 500) && attempt < 2) {
        await novaRealtimeSleep_([180, 480, 950][attempt] || 950);
        return send(attempt + 1);
      }
      if (response.status === 404 || ['PGRST202', 'PGRST205'].includes(code)) {
        // RPC 미배포는 DB mutation이 시작되지 않은 것이 명확하므로 기존 경로만 이 경우 허용합니다.
        return { ok: false, legacyFallback: true, reason: 'RPC_MISSING' };
      }

      const error = new Error(data?.message || data?.details || data?.hint || `QM 최종제출 DB 오류 (${response.status})`);
      error.status = Number(response.status || 0);
      error.code = code;
      error.data = data || null;
      throw error;
    };

    return send(0);
  }

'''
    client = replace_once(client, anchor, helper + anchor, 'QM detail retry helper')

    old_request = """    const requestId = novaRealtimeRequestId_(realtimeAction, active.roomNo);\n    const room = (state.mobile.data?.rooms || []).find(item => String(item.roomNo || '') === String(active.roomNo || ''));"""
    new_request = """    const finalizeStable = novaQmFinalizeStableRequestId_(active);\n    const requestId = finalizeStable.requestId;\n    const room = (state.mobile.data?.rooms || []).find(item => String(item.roomNo || '') === String(active.roomNo || ''));"""
    client = replace_once(client, old_request, new_request, 'stable QM finalize request id')

    old_legacy_success = """        if (!result?.ok) throw new Error(result?.message || '점검결과를 저장하지 못했습니다.');\n        state.qmChecklist.activeInspection = null;"""
    new_legacy_success = """        if (!result?.ok) throw new Error(result?.message || '점검결과를 저장하지 못했습니다.');\n        try { sessionStorage.removeItem(finalizeStable.key); } catch (ignore) {}\n        state.qmChecklist.activeInspection = null;"""
    client = replace_once(client, old_legacy_success, new_legacy_success, 'legacy finalize request cleanup')

    old_realtime = """      const realtime = await saveRoomActionRealtimeOrLegacy_('updateMobileRoomOperation', {\n        businessDate: state.mobile.businessDate,\n        site: state.mobile.site,\n        roomNo: active.roomNo,\n        action: realtimeAction,\n        requestId,\n        expectedVersion: Number(active.roomVersion || room?.version || 0),\n        expectedState: {\n          cleaningStatus: String(room?.cleaningStatus || 'QM_CHECKING'),\n          qmEmployeeNo: String(room?.qmEmployeeNo || state.bootstrap?.user?.employeeNo || '')\n        }\n      });"""
    new_realtime = """      let realtime = await novaQmFinalizeDbFirstV2_(active, draft, passed, requestId);\n      if (realtime?.legacyFallback === true) {\n        realtime = await saveRoomActionRealtimeOrLegacy_('updateMobileRoomOperation', {\n          businessDate: state.mobile.businessDate,\n          site: state.mobile.site,\n          roomNo: active.roomNo,\n          action: realtimeAction,\n          requestId,\n          expectedVersion: Number(active.roomVersion || room?.version || 0),\n          expectedState: {\n            cleaningStatus: String(room?.cleaningStatus || 'QM_CHECKING'),\n            qmEmployeeNo: String(room?.qmEmployeeNo || state.bootstrap?.user?.employeeNo || '')\n          }\n        });\n      }\n      if (!realtime?.ok) throw new Error(realtime?.message || 'QM 최종제출 DB 확정에 실패했습니다.');"""
    client = replace_once(client, old_realtime, new_realtime, 'QM realtime terminal commit')

    old_detail_success = """      void persistDetail().then(result => {\n        if (!result?.ok) throw new Error(result?.message || 'QM 상세이력 저장 실패');\n        loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 상세이력 저장 후 갱신 실패:', error));"""
    new_detail_success = """      void persistDetail().then(result => {\n        if (!result?.ok) throw new Error(result?.message || 'QM 상세이력 저장 실패');\n        try { sessionStorage.removeItem(finalizeStable.key); } catch (ignore) {}\n        loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 상세이력 저장 후 갱신 실패:', error));"""
    client = replace_once(client, old_detail_success, new_detail_success, 'QM detail mirror cleanup')

    CLIENT.write_text(client, encoding='utf-8')

print('PASS: QM final submission V2 staged as atomic DB-first with safe legacy fallback only before mutation')
