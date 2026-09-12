/**
 * QM_FINALIZE_PREFLIGHT_FAST_HOTFIX_V4
 *
 * 최종제출 preflight가 체크리스트 정의를 다시 읽기 위해 Sheet / Cloud Run / Edge / PostgREST를
 * 왕복하면서 멈추는 경로를 제거합니다. 브라우저는 제출 직전에 이미 동일 체크리스트로
 * 필수 결과·불량 메모·사진 필수·추가하자 검증을 수행합니다. 여기서는 서버 권한/식별정보와
 * 전달된 정규 데이터의 형태를 다시 검증하고, 실제 mutation은 기존
 * nova_qm_inspection_finalize_v2의 권한·배정·QM_CHECKING·동시성·idempotency 검증에 맡깁니다.
 *
 * Client 내부 state.mobile.businessDate가 비어 있는 재개 세션에서는 preflight가 업무일자를
 * 선제 차단하지 않습니다. finalize 전송계층/DB가 draft의 실제 businessDate를 권위값으로
 * 복구할 수 있도록 빈 값은 그대로 허용합니다. 날짜가 전달된 경우에는 기존
 * normalizeBusinessDate_ 검증을 그대로 유지합니다.
 */
prepareQmInspectionFinalizeDbFirst = function(token, payload) {
  return measureResponse_('prepareQmInspectionFinalizeDbFirst', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
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
      businessDateSource: businessDate ? 'CLIENT' : 'DB_DRAFT_FINALIZE_FALLBACK',
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
 *
 * 재개된 QM 모달에서 Client state.mobile.businessDate가 비어 있고 draftId도 아직 Client에
 * 복원되지 않은 경우, 최종제출의 legacy 분기는 ensureQmInspectionDraftReady_ ->
 * beginQmInspectionDraftInit_ -> startQmInspection 순으로 들어갑니다. 원본 startQmInspection은
 * payload.businessDate를 가장 먼저 normalize하므로 이 지점에서 "업무일자를 확인해 주세요."가
 * 발생하면 submit/preflight/finalize 어느 곳에도 도달하지 못합니다.
 *
 * 이 예외적인 blank-date 재개 경로에서만, 기존 QM_CHECKLIST IN_PROGRESS 이력 중
 * 동일 사용자·사업장·객실의 가장 최근 초안 업무일자를 권위값으로 복구합니다.
 * 이력이 없을 때는 기존 CURRENT 시트의 동일 사용자·사업장·객실 QM 행을 보조값으로 사용합니다.
 * 날짜가 이미 전달되면 원본 startQmInspection을 그대로 호출합니다.
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
  if (!String(safe.businessDate || '').trim()) {
    const user = requireRole_(token, ['QM']);
    const recoveredBusinessDate = novaResolveResumedQmBusinessDate_(user, safe);
    if (recoveredBusinessDate) safe.businessDate = recoveredBusinessDate;
  }
  return novaStartQmInspectionOriginal_(token, safe);
};

/**
 * QM_FINALIZE_LEGACY_DATE_RECOVERY_V2
 *
 * Realtime 설정이 일시적으로 비활성/미초기화된 경우 Client는 기존
 * submitQmChecklistInspection 경로를 사용합니다. businessDate가 비어 있으면 먼저 draftId의
 * 업무일자를 사용하고, Client에 draftId가 아직 복원되지 않은 재개 세션이면 위와 동일한
 * IN_PROGRESS 초안 기준으로 업무일자를 복구한 뒤 원본 제출 함수를 호출합니다.
 */
const novaSubmitQmChecklistInspectionOriginal_ = submitQmChecklistInspection;
submitQmChecklistInspection = function(token, payload) {
  const safe = Object.assign({}, payload || {});
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
