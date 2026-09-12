/**
 * QM_FINALIZE_PREFLIGHT_FAST_HOTFIX_V3
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
 * QM_FINALIZE_LEGACY_DATE_RECOVERY_V1
 *
 * Realtime 설정이 일시적으로 비활성/미초기화된 경우 Client는 기존
 * submitQmChecklistInspection 경로를 사용합니다. 이 경로는 과거에는 businessDate를 가장 먼저
 * normalize하여, 재개 세션에서 Client state가 비어 있으면 DB-first finalize까지 가지도 못하고
 * "업무일자를 확인해 주세요."로 종료됐습니다.
 *
 * 기존 제출 로직/검증은 전혀 변경하지 않고, businessDate가 없을 때만 제출에 이미 포함된
 * draftId의 업무일자를 권위값으로 복구한 뒤 원본 함수를 호출합니다. draft 소유권도 기존 QM
 * 소유권 검증으로 확인합니다. 날짜가 이미 있으면 원본 함수를 그대로 호출합니다.
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
  }
  return novaSubmitQmChecklistInspectionOriginal_(token, safe);
};
