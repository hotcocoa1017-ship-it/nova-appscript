/**
 * QM_FINALIZE_CALLSERVER_DB_AUTHORITY_V1
 *
 * Realtime 연결여부와 무관하게 기존 진행중 QM 초안의 최종제출만 DB 권위 경로로 확정합니다.
 * 기존 체크리스트 검증, 권한, 동시성, Sheet 상세이력 미러는 그대로 유지합니다.
 */
function submitQmChecklistInspectionDbAuthority(token, payload) {
  return measureResponse_('submitQmChecklistInspectionDbAuthority', () => {
    requireRole_(token, ['QM']);
    const safe = Object.assign({}, payload || {});
    const roomNo = String(safe.roomNo || '').trim();
    const requestedSite = String(safe.site || '').trim();
    if (!roomNo) throw new Error('QM 최종제출 객실번호가 없습니다.');

    // 기존 NOVA 로그인 토큰으로 Cloud Run에서 단기 Supabase JWT를 발급받습니다.
    // 이 단계가 실패하면 Sheet-only 완료로 후퇴하지 않고 중단해 DB/Sheet 분기를 만들지 않습니다.
    const auth = novaDbFirstRealtimeAuth_(token);
    const origin = String(auth && auth.supabaseUrl || '').trim().replace(/\/+$/, '');
    if (!origin || !auth.token || !auth.publishableKey) {
      throw new Error('QM DB 인증정보를 준비할 수 없습니다.');
    }

    const edgeUrl = `${origin}/functions/v1/nova-qm-db-resilient-v1`;
    const edgeHeaders = {
      Authorization: `Bearer ${auth.token}`,
      apikey: String(auth.publishableKey || '')
    };

    // 화면/Sheet 버전에 의존하지 않고 DB의 본인 IN_PROGRESS 초안과 roomVersion을 권위값으로 읽습니다.
    const resumeResponse = UrlFetchApp.fetch(edgeUrl, {
      method: 'post',
      contentType: 'application/json; charset=utf-8',
      headers: edgeHeaders,
      payload: JSON.stringify({
        rpc: 'nova_qm_resume_context_v1',
        args: { p_room_no: roomNo, p_site: requestedSite }
      }),
      muteHttpExceptions: true,
      followRedirects: true
    });
    const resumeStatus = Number(resumeResponse.getResponseCode() || 0);
    let context = {};
    try { context = JSON.parse(resumeResponse.getContentText('UTF-8') || '{}'); } catch (ignore) { context = {}; }
    if (resumeStatus < 200 || resumeStatus >= 300 || context?.ok !== true || context?.found !== true) {
      const message = context?.ambiguous === true
        ? '동일 객실의 진행 중 QM 초안이 여러 건입니다. 관리자 확인이 필요합니다.'
        : String(context?.message || '진행 중인 QM DB 초안을 확인할 수 없습니다.');
      const error = new Error(message);
      error.code = String(context?.code || 'QM_RESUME_CONTEXT_REQUIRED');
      throw error;
    }

    safe.businessDate = String(context.businessDate || safe.businessDate || '').trim();
    safe.site = String(context.site || safe.site || '').trim();
    safe.roomNo = String(context.roomNo || safe.roomNo || '').trim();
    safe.draftId = String(context.draftId || safe.draftId || '').trim();
    if (!safe.startedAt && context.startedAt) safe.startedAt = String(context.startedAt || '').trim();

    // 현재 운영 중인 preflight를 그대로 재사용해 PASS/FAIL/메모/사진/하자 규칙을 보존합니다.
    const preflight = prepareQmInspectionFinalizeDbFirst(token, safe);
    if (!preflight?.ok) throw new Error(preflight?.message || 'QM 최종제출 사전검증에 실패했습니다.');

    const draftId = String(context.draftId || safe.draftId || '').trim();
    if (!draftId) throw new Error('QM 초안 식별정보를 확인할 수 없습니다.');
    const requestId = String(safe.realtimeRequestId || safe.requestId || `QM-DBAUTH-FINALIZE-${draftId}`)
      .replace(/[^A-Za-z0-9._:-]/g, '-')
      .slice(0, 180);
    const requestBody = {
      rpc: 'nova_qm_inspection_finalize_v2',
      args: {
        p_payload: {
          businessDate: String(context.businessDate || safe.businessDate || ''),
          site: String(context.site || safe.site || ''),
          roomNo: String(context.roomNo || safe.roomNo || ''),
          inspectionId: draftId,
          draftId,
          checklistRevision: String(preflight.revision || safe.revision || ''),
          answers: Array.isArray(preflight.answers) ? preflight.answers : [],
          defects: Array.isArray(preflight.defects) ? preflight.defects : [],
          resultStatus: String(preflight.resultStatus || '').trim().toUpperCase(),
          startedAt: String(preflight.startedAt || context.startedAt || safe.startedAt || ''),
          expectedVersion: Number(context.roomVersion || 0)
        },
        p_request_id: requestId
      }
    };

    let dbResult = null;
    let lastError = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const response = UrlFetchApp.fetch(edgeUrl, {
          method: 'post',
          contentType: 'application/json; charset=utf-8',
          headers: edgeHeaders,
          payload: JSON.stringify(requestBody),
          muteHttpExceptions: true,
          followRedirects: true
        });
        const status = Number(response.getResponseCode() || 0);
        let data = {};
        try { data = JSON.parse(response.getContentText('UTF-8') || '{}'); } catch (ignore) { data = {}; }
        if (status >= 200 && status < 300 && data?.ok === true) {
          dbResult = data;
          break;
        }
        const error = new Error(String(data?.message || `QM DB 최종저장 실패 (${status})`));
        error.code = String(data?.code || 'QM_DB_FINALIZE_FAILED');
        error.status = status;
        lastError = error;
        if ((status === 429 || status >= 500) && attempt === 0) {
          Utilities.sleep(180);
          continue;
        }
        throw error;
      } catch (error) {
        lastError = error;
        if (attempt === 0 && !Number(error?.status || 0) && !String(error?.code || '').trim()) {
          Utilities.sleep(180);
          continue;
        }
        throw error;
      }
    }
    if (!dbResult?.ok) throw lastError || new Error('QM DB 최종저장 결과를 확인할 수 없습니다.');

    // DB 확정 후에만 기존 Sheet 상세이력을 보완합니다. 미러 실패는 DB 완료를 되돌리지 않습니다.
    let sheetMirrorPending = false;
    try {
      const mirrorSafe = Object.assign({}, safe, {
        businessDate: String(context.businessDate || ''),
        site: String(context.site || ''),
        roomNo: String(context.roomNo || ''),
        draftId,
        realtimeCommitted: true,
        realtimeRequestId: requestId,
        realtimeVersion: Number(dbResult.version || dbResult.room?.version || 0)
      });
      const mirror = submitQmChecklistInspection(token, mirrorSafe);
      if (!mirror?.ok) throw new Error(mirror?.message || 'QM Sheet 상세이력 미러 실패');
    } catch (mirrorError) {
      sheetMirrorPending = true;
      console.warn('[NOVA QM] DB 권위 최종완료 후 Sheet 상세미러 지연:', mirrorError?.message || mirrorError);
    }

    return Object.assign({}, dbResult, {
      ok: true,
      dbFirst: true,
      dbAuthorityFinalize: true,
      sheetMirrorPending,
      requestId,
      message: '점검결과를 저장했습니다.'
    });
  });
}
