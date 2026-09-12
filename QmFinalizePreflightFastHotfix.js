/**
 * QM_FINALIZE_PREFLIGHT_FAST_HOTFIX_V8
 *
 * 기존 제출 검증과 DB 최종확정 규칙은 유지합니다. Realtime-disabled 최종제출은 브라우저에
 * businessDate/site/draftId가 이미 채워져 있어도 DB의 IN_PROGRESS draft를 권위값으로 확인한 뒤
 * 동일한 DB finalize 경로를 사용합니다. 재개 세션에서는 Sheet 변경버전이 아니라 DB resume context의
 * roomVersion을 optimistic concurrency 기준으로 사용합니다.
 */

function novaResolveResumedQmDbContext_(token, payload) { // QM_RESUME_CONTEXT_DB_AUTHORITY_V1
  const safe = payload || {};
  const roomNo = String(safe.roomNo || '').trim();
  const site = String(safe.site || '').trim();
  if (!roomNo) return null;

  let auth;
  try {
    auth = novaDbFirstRealtimeAuth_(token);
  } catch (error) {
    console.warn('[NOVA QM] DB 재개 문맥 인증 준비 지연:', error?.message || error);
    return null;
  }

  try {
    const origin = String(auth.supabaseUrl || '').replace(/\/+$/, '');
    if (!origin || !auth.token || !auth.publishableKey) return null;
    const response = UrlFetchApp.fetch(`${origin}/functions/v1/nova-qm-db-resilient-v1`, {
      method: 'post',
      contentType: 'application/json; charset=utf-8',
      headers: {
        Authorization: `Bearer ${auth.token}`,
        apikey: String(auth.publishableKey || '')
      },
      payload: JSON.stringify({
        rpc: 'nova_qm_resume_context_v1',
        args: { p_room_no: roomNo, p_site: site }
      }),
      muteHttpExceptions: true,
      followRedirects: true
    });
    const status = Number(response.getResponseCode() || 0);
    let data = {};
    try { data = JSON.parse(response.getContentText('UTF-8') || '{}'); } catch (ignore) {}

    if (status >= 200 && status < 300 && data?.ok === true && data?.found === true) return data;
    if (data?.ambiguous === true || String(data?.code || '') === 'QM_RESUME_CONTEXT_AMBIGUOUS') {
      const error = new Error('동일 객실의 진행 중 QM 초안이 여러 건입니다. 관리자 확인이 필요합니다.');
      error.code = 'QM_RESUME_CONTEXT_AMBIGUOUS';
      throw error;
    }
    return null;
  } catch (error) {
    if (String(error?.code || '') === 'QM_RESUME_CONTEXT_AMBIGUOUS') throw error;
    console.warn('[NOVA QM] DB 재개 문맥 복구 지연:', error?.message || error);
    return null;
  }
}

function novaApplyResumedQmDbContext_(safe, context) {
  if (!context?.found) return safe;
  safe.businessDate = String(context.businessDate || safe.businessDate || '').trim();
  safe.site = String(context.site || safe.site || '').trim();
  safe.roomNo = String(context.roomNo || safe.roomNo || '').trim();
  safe.draftId = String(context.draftId || safe.draftId || '').trim();
  if (!safe.startedAt && context.startedAt) safe.startedAt = String(context.startedAt || '').trim();
  return safe;
}

function novaFinalizeResumedQmDbFirst_(token, payload, context) { // QM_LEGACY_BRANCH_DB_FINALIZE_V1 · QM_RESUME_ROOM_VERSION_AUTHORITY_V1
  const safe = novaApplyResumedQmDbContext_(Object.assign({}, payload || {}), context);
  const preflight = prepareQmInspectionFinalizeDbFirst(token, safe);
  const draftId = String(context?.draftId || safe.draftId || '').trim();
  if (!draftId) throw new Error('QM 초안 식별정보를 확인할 수 없습니다.');

  const requestId = String(safe.realtimeRequestId || safe.requestId || `QM-LEGACY-FINALIZE-${draftId}`)
    .replace(/[^A-Za-z0-9._:-]/g, '-')
    .slice(0, 180);
  const auth = novaDbFirstRealtimeAuth_(token);
  const origin = String(auth.supabaseUrl || '').replace(/\/+$/, '');
  if (!origin || !auth.token || !auth.publishableKey) throw new Error('QM DB 인증정보를 준비할 수 없습니다.');

  const requestBody = {
    rpc: 'nova_qm_inspection_finalize_v2',
    args: {
      p_payload: {
        businessDate: String(context.businessDate || safe.businessDate || ''),
        site: String(context.site || safe.site || ''),
        roomNo: String(context.roomNo || safe.roomNo || ''),
        inspectionId: draftId,
        draftId,
        checklistRevision: String(preflight?.revision || safe.revision || ''),
        answers: Array.isArray(preflight?.answers) ? preflight.answers : [],
        defects: Array.isArray(preflight?.defects) ? preflight.defects : [],
        resultStatus: String(preflight?.resultStatus || '').trim().toUpperCase(),
        startedAt: String(preflight?.startedAt || context?.startedAt || safe.startedAt || ''),
        // Realtime-disabled Client의 active.roomVersion은 Sheet 변경버전일 수 있습니다.
        // resume context가 방금 읽은 PostgreSQL room version을 사용해 버전 도메인을 섞지 않습니다.
        expectedVersion: Number(context?.roomVersion || 0)
      },
      p_request_id: requestId
    }
  };

  let lastError = null;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const response = UrlFetchApp.fetch(`${origin}/functions/v1/nova-qm-db-resilient-v1`, {
        method: 'post',
        contentType: 'application/json; charset=utf-8',
        headers: {
          Authorization: `Bearer ${auth.token}`,
          apikey: String(auth.publishableKey || '')
        },
        payload: JSON.stringify(requestBody),
        muteHttpExceptions: true,
        followRedirects: true
      });
      const status = Number(response.getResponseCode() || 0);
      let data = {};
      try { data = JSON.parse(response.getContentText('UTF-8') || '{}'); } catch (ignore) {}
      if (status >= 200 && status < 300 && data?.ok === true) {
        return Object.assign({}, data, { requestId });
      }
      const message = String(data?.message || `QM DB 최종저장 실패 (${status})`).trim();
      const code = String(data?.code || '').trim();
      const error = new Error(message);
      error.code = code;
      if (status === 429 || status >= 500) {
        lastError = error;
        if (attempt === 0) {
          Utilities.sleep(180);
          continue;
        }
      }
      throw error;
    } catch (error) {
      lastError = error;
      if (attempt === 0 && !String(error?.code || '').trim()) {
        Utilities.sleep(180);
        continue;
      }
      throw error;
    }
  }
  throw lastError || new Error('QM DB 최종저장 결과를 확인할 수 없습니다.');
}

prepareQmInspectionFinalizeDbFirst = function(token, payload) {
  return measureResponse_('prepareQmInspectionFinalizeDbFirst', () => {
    const user = requireRole_(token, ['QM']);
    const safe = Object.assign({}, payload || {});
    const roomNoBefore = String(safe.roomNo || '').trim();
    if (roomNoBefore && (!String(safe.businessDate || '').trim() || !String(safe.site || '').trim())) {
      const dbContext = novaResolveResumedQmDbContext_(token, safe);
      if (dbContext) novaApplyResumedQmDbContext_(safe, dbContext);
    }
    const rawBusinessDate = String(safe.businessDate || '').trim();
    const businessDate = rawBusinessDate ? normalizeBusinessDate_(rawBusinessDate) : '';
    const site = String(safe.site || user.defaultSite || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!site || !roomNo) throw new Error('QM 최종점검 식별정보가 없습니다.');

    const answers = Array.isArray(safe.answers) ? safe.answers.map(answer => {
      const row = answer && typeof answer === 'object' ? Object.assign({}, answer) : {};
      row.code = String(row.code || '').trim();
      row.result = String(row.result || '').trim().toUpperCase();
      row.note = String(row.note || '').trim();
      row.photos = Array.isArray(row.photos) ? row.photos : [];
      if (!row.code) throw new Error('QM 체크리스트 항목정보를 확인해 주세요.');
      if (!['PASS', 'FAIL', 'SKIP'].includes(row.result)) throw new Error('QM 체크리스트 점검결과를 확인해 주세요.');
      if (row.result === 'FAIL' && !row.note) throw new Error('불량 항목의 내용을 입력하세요.');
      if (row.photoRequired === true && !row.photos.length) throw new Error('사진 필수 항목의 사진을 등록하세요.');
      return row;
    }) : null;
    if (!answers || !answers.length) throw new Error('QM 체크리스트 점검결과가 없습니다.');

    const defects = Array.isArray(safe.defects) ? safe.defects.map(defect => {
      const row = defect && typeof defect === 'object' ? Object.assign({}, defect) : {};
      row.id = String(row.id || '').trim();
      row.note = String(row.note || '').trim();
      row.photos = Array.isArray(row.photos) ? row.photos : [];
      if (!row.id || !row.note || !row.photos.length) throw new Error('추가 하자는 내용과 사진을 모두 등록하세요.');
      return row;
    }) : [];

    const itemFailCount = answers.filter(answer => answer.result === 'FAIL').length;
    const resultStatus = itemFailCount || defects.length ? 'FAIL' : 'PASS';

    return {
      ok: true,
      preflight: true,
      fastPreflight: true,
      businessDate,
      businessDateSource: businessDate ? (roomNoBefore && String(payload?.businessDate || '').trim() ? 'CLIENT' : 'DB_RESUME_CONTEXT') : 'DB_DRAFT_FINALIZE_FALLBACK',
      site,
      roomNo,
      revision: String(safe.revision || '').trim(),
      answers,
      defects,
      resultStatus,
      itemFailCount,
      customDefectCount: defects.length,
      startedAt: String(safe.startedAt || '').trim(),
      qmEmployeeNo: user.employeeNo
    };
  });
};

/**
 * QM_RESUMED_DRAFT_DATE_RECOVERY_V1
 * Sheet 복구는 DB 문맥 조회가 사용할 수 없을 때만 기존 호환 경로로 유지합니다.
 */
function novaResolveResumedQmBusinessDate_(user, payload) {
  const safe = payload || {};
  const site = String(safe.site || user.defaultSite || '').trim();
  const roomNo = String(safe.roomNo || '').trim();
  const employeeNo = String(user.employeeNo || '').trim();
  if (!roomNo || !employeeNo) return '';

  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const lastRow = sheet.getLastRow();
    if (lastRow >= 2) {
      const headerMap = getHeaderMap_(sheet);
      const scanStart = Math.max(2, lastRow - NOVA_QM_CHECKLIST.HISTORY_SCAN_ROWS + 1);
      const values = sheet.getRange(scanStart, 1, lastRow - scanStart + 1, sheet.getLastColumn()).getDisplayValues();
      for (let index = values.length - 1; index >= 0; index -= 1) {
        const data = rowObjectFromValues_(values[index], headerMap);
        if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.QM_CHECKLIST) continue;
        if (String(data['처리상태'] || '').trim().toUpperCase() !== 'IN_PROGRESS') continue;
        if (site && String(data['사업장'] || '').trim() !== site) continue;
        if (String(data['객실번호'] || '').trim() !== roomNo) continue;
        if (String(data['대상사번'] || '').trim() !== employeeNo) continue;
        if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') continue;
        const businessDate = String(data['업무일자'] || '').trim();
        if (businessDate) return normalizeBusinessDate_(businessDate);
      }
    }
  } catch (error) {
    console.warn('[NOVA QM] 재개 초안 업무일자 이력 복구 지연:', error?.message || error);
  }

  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const lastRow = sheet.getLastRow();
    if (lastRow >= 2) {
      const headerMap = getHeaderMap_(sheet);
      const values = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getDisplayValues();
      for (let index = values.length - 1; index >= 0; index -= 1) {
        const data = rowObjectFromValues_(values[index], headerMap);
        if (site && String(data['사업장'] || '').trim() !== site) continue;
        if (String(data['객실번호'] || '').trim() !== roomNo) continue;
        if (String(data['QM사번'] || '').trim() !== employeeNo) continue;
        const status = String(data['청소상태'] || '').trim().toUpperCase();
        if (!['QM_WAITING', 'COMPLETED', 'QM_CHECKING'].includes(status)) continue;
        const businessDate = String(data['업무일자'] || '').trim();
        if (businessDate) return normalizeBusinessDate_(businessDate);
      }
    }
  } catch (error) {
    console.warn('[NOVA QM] 재개 초안 업무일자 CURRENT 복구 지연:', error?.message || error);
  }

  return '';
}

const novaStartQmInspectionOriginal_ = startQmInspection;
startQmInspection = function(token, payload) {
  const safe = Object.assign({}, payload || {});
  let dbContext = null;
  if (String(safe.roomNo || '').trim()) {
    dbContext = novaResolveResumedQmDbContext_(token, safe);
    if (dbContext) novaApplyResumedQmDbContext_(safe, dbContext);
  }

  // QM_RESUME_DRAFT_READY_DB_AUTHORITY_V2
  // Client의 ensureQmInspectionDraftReady_가 최종제출 전에 background start를 다시 호출하더라도,
  // 이미 DB에 존재하는 본인 IN_PROGRESS draft와 authoritative DB room version을 그대로 돌려줍니다.
  if (safe.realtimeStarted === true && dbContext?.draftId) {
    return {
      ok: true,
      realtime: true,
      dbFirst: true,
      recoveredExistingDraft: true,
      version: Number(dbContext.roomVersion || 0),
      draft: {
        draftId: String(dbContext.draftId || ''),
        businessDate: String(dbContext.businessDate || ''),
        site: String(dbContext.site || ''),
        roomNo: String(dbContext.roomNo || ''),
        checklistRevision: String(dbContext.checklistRevision || ''),
        answers: Array.isArray(dbContext.answers) ? dbContext.answers : [],
        defects: Array.isArray(dbContext.defects) ? dbContext.defects : [],
        status: 'IN_PROGRESS',
        version: Number(dbContext.draftVersion || 0),
        dbVersion: Number(dbContext.draftVersion || 0),
        rowNumber: 0,
        startedAt: String(dbContext.startedAt || ''),
        savedAt: String(dbContext.savedAt || '')
      }
    };
  }

  if (!String(safe.businessDate || '').trim()) {
    const user = requireRole_(token, ['QM']);
    const recoveredBusinessDate = novaResolveResumedQmBusinessDate_(user, safe);
    if (recoveredBusinessDate) safe.businessDate = recoveredBusinessDate;
  }
  return novaStartQmInspectionOriginal_(token, safe);
};

/**
 * QM_FINALIZE_LEGACY_DATE_RECOVERY_V5
 *
 * Client의 Realtime-disabled 분기는 DB finalize helper를 거치지 않고 이 함수로 직접 들어옵니다.
 * 이 분기는 Client 필드가 모두 채워져 있어도 DB의 IN_PROGRESS draft 문맥을 먼저 확인하고
 * 동일한 nova_qm_inspection_finalize_v2를 실행합니다. DB 문맥이 없을 때만 기존 호환 경로를 유지합니다.
 * DB 커밋 후 Sheet 상세미러 경로는 기존 동작을 유지합니다.
 */
const novaSubmitQmChecklistInspectionOriginal_ = submitQmChecklistInspection;
submitQmChecklistInspection = function(token, payload) {
  const safe = Object.assign({}, payload || {});
  const needsDbResumeContext = !String(safe.businessDate || '').trim()
    || !String(safe.site || '').trim()
    || !String(safe.draftId || '').trim();
  const shouldResolveDbContext = safe.realtimeCommitted !== true || needsDbResumeContext;

  let dbContext = null;
  if (shouldResolveDbContext && String(safe.roomNo || '').trim()) {
    dbContext = novaResolveResumedQmDbContext_(token, safe);
    if (dbContext) novaApplyResumedQmDbContext_(safe, dbContext);
  }

  if (safe.realtimeCommitted === true) {
    if (dbContext) {
      const mirrorSafe = Object.assign({}, safe, { draftId: '', draftRowNumber: 0 });
      return novaSubmitQmChecklistInspectionOriginal_(token, mirrorSafe);
    }
    return novaSubmitQmChecklistInspectionOriginal_(token, safe);
  }

  if (dbContext) {
    const dbResult = novaFinalizeResumedQmDbFirst_(token, safe, dbContext);
    let sheetMirrorPending = false;
    let mirrorDraftId = '';
    try {
      if (safe.draftId) {
        const sheetDraft = getQmInspectionRecordById_(String(safe.draftId || '').trim(), safe.draftRowNumber);
        if (sheetDraft) mirrorDraftId = String(safe.draftId || '').trim();
      }
    } catch (ignore) {}

    try {
      const mirrorSafe = Object.assign({}, safe, {
        businessDate: String(dbContext.businessDate || ''),
        site: String(dbContext.site || ''),
        roomNo: String(dbContext.roomNo || ''),
        draftId: mirrorDraftId,
        draftRowNumber: mirrorDraftId ? Number(safe.draftRowNumber || 0) : 0,
        realtimeCommitted: true,
        realtimeRequestId: String(dbResult.requestId || ''),
        realtimeVersion: Number(dbResult.version || dbResult.room?.version || 0)
      });
      novaSubmitQmChecklistInspectionOriginal_(token, mirrorSafe);
    } catch (mirrorError) {
      sheetMirrorPending = true;
      console.warn('[NOVA QM] DB 최종완료 후 Sheet 상세미러 지연:', mirrorError?.message || mirrorError);
    }

    return Object.assign({}, dbResult, {
      ok: true,
      dbFirst: true,
      sheetMirrorPending,
      message: '점검결과를 저장했습니다.'
    });
  }

  if (!String(safe.businessDate || '').trim()) {
    const user = requireRole_(token, ['QM']);
    const draftId = String(safe.draftId || '').trim();
    if (draftId) {
      const draftInfo = getQmInspectionRecordById_(draftId, safe.draftRowNumber);
      validateQmDraftOwnership_(draftInfo, user);
      safe.businessDate = String(draftInfo?.data?.['업무일자'] || '').trim();
      if (!safe.site) safe.site = String(draftInfo?.data?.['사업장'] || '').trim();
      if (!safe.roomNo) safe.roomNo = String(draftInfo?.data?.['객실번호'] || '').trim();
    }
    if (!String(safe.businessDate || '').trim()) {
      const recoveredBusinessDate = novaResolveResumedQmBusinessDate_(user, safe);
      if (recoveredBusinessDate) safe.businessDate = recoveredBusinessDate;
    }
  }
  return novaSubmitQmChecklistInspectionOriginal_(token, safe);
};