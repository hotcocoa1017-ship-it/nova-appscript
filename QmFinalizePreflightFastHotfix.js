/**
 * QM_FINALIZE_PREFLIGHT_FAST_HOTFIX_V2
 *
 * 최종제출 preflight가 체크리스트 정의를 다시 읽기 위해 Sheet / Cloud Run / Edge / PostgREST를
 * 왕복하면서 멈추는 경로를 제거합니다. 브라우저는 제출 직전에 이미 동일 체크리스트로
 * 필수 결과·불량 메모·사진 필수·추가하자 검증을 수행합니다. 여기서는 서버 권한/식별정보와
 * 전달된 정규 데이터의 형태를 다시 검증하고, 실제 mutation은 기존
 * nova_qm_inspection_finalize_v2의 권한·배정·QM_CHECKING·동시성·idempotency 검증에 맡깁니다.
 *
 * Client 내부 state.mobile.businessDate가 비어 있는 재개 세션에서는 preflight가 업무일자를
 * 선제 차단하지 않습니다. 운영 Edge v5가 finalize 직전 draftId로 실제 businessDate를 조회해
 * payload.businessDate를 보정하므로, DB의 기존 초안 날짜를 권위값으로 사용합니다.
 * 날짜가 전달된 경우에는 기존 normalizeBusinessDate_ 검증을 그대로 유지합니다.
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
