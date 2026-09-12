// QM_SCHEMA_CACHE_START_FALLBACK_V3
// PGRST002는 PostgREST schema cache 단계 실패이므로 DB RPC가 실행되기 전입니다.
// 이 경우에만 기존 Sheet QM 시작/초안 경로로 안전하게 복구합니다.
// 중요: 이 함수 안에서는 DB-first QM 체크리스트/시작 RPC를 다시 호출하지 않습니다.
// 사용자 응답 경로에서는 DB 재동기화를 기다리지 않으며, 재동기화는 클라이언트 후행 호출로 분리합니다.
function startQmInspectionSchemaCacheFallback(token, payload) {
  return measureResponse_('startQmInspectionSchemaCacheFallback', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const schemaCacheCode = String(safe.schemaCacheCode || '').trim().toUpperCase();
    if (schemaCacheCode !== 'PGRST002') throw new Error('허용되지 않은 QM 시작 복구 요청입니다.');

    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site);
    const roomNo = String(safe.roomNo || '').trim();
    const view = String(safe.view || 'TARGETS').trim().toUpperCase();
    if (!site || !roomNo) throw new Error('점검할 사업장과 객실번호가 필요합니다.');
    if (!['TARGETS', 'CLEANED', 'VACANT'].includes(view)) throw new Error('지원하지 않는 QM 점검경로입니다.');

    let rowNumber = Number(safe.rowNumber || 0);
    let responseSite = site;
    let version = 0;
    let alreadyChecking = false;
    let beforeStatus = '';
    let rowData = null;
    const lock = acquireWriteLock_(5000);
    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const rowInfo = findCurrentRoomRowForMobileUpdate_(sheet, businessDate, site, roomNo, rowNumber);
      if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
      rowNumber = rowInfo.rowNumber;
      responseSite = String(rowInfo.data['사업장'] || site).trim();

      const roomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
      const cleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
      const currentQmNo = String(rowInfo.data['QM사번'] || '').trim();
      const roommaidNo = String(rowInfo.data['룸메이드사번'] || '').trim();
      const secondaryRoommaidNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
      const operationalStatus = String(rowInfo.data['객실조치'] || rowInfo.data['운영상태'] || '').trim().toUpperCase();
      const startable = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING']);
      const hasRoommaid = Boolean(roommaidNo || secondaryRoommaidNo);
      if (!startable.has(cleaningStatus)) throw new Error('현재 QM 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.');

      if (view === 'TARGETS') {
        if (currentQmNo !== user.employeeNo) throw new Error('본인에게 배정된 QM 점검대상이 아닙니다. 목록을 새로고침해 주세요.');
        if (operationalStatus === 'REWORK') throw new Error('재정비 중인 객실은 재정비 완료 후 점검을 계속할 수 있습니다.');
      } else if (view === 'VACANT') {
        if (roomStatus !== 'VACANT_CLEAN') throw new Error('현재 공실 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.');
        if (currentQmNo && currentQmNo !== user.employeeNo) throw new Error('다른 QM에게 이미 배정되었거나 점검 중인 객실입니다.');
      } else {
        if (roomStatus === 'VACANT_CLEAN' || !hasRoommaid) throw new Error('현재 당일 청소완료 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.');
        if (currentQmNo && currentQmNo !== user.employeeNo) throw new Error('다른 QM에게 이미 배정되었거나 점검 중인 객실입니다.');
      }

      beforeStatus = cleaningStatus;
      alreadyChecking = currentQmNo === user.employeeNo && cleaningStatus === 'QM_CHECKING';
      if (alreadyChecking) {
        version = Number(rowInfo.data['마지막변경버전'] || 0);
      } else {
        version = reserveDataVersion_({ lockHeld: true });
        const startedAt = nowText_();
        const patch = {
          '청소상태': 'QM_CHECKING',
          '마지막변경버전': version,
          '수정일시': startedAt
        };
        if (view !== 'TARGETS' && !currentQmNo) patch['QM사번'] = user.employeeNo;
        updateRowByHeaders_(sheet, rowInfo.rowNumber, patch);
        SpreadsheetApp.flush();
        publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: responseSite, lockHeld: true });
        appendUnifiedHistory_({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate,
          site: responseSite,
          roomNo,
          targetEmployeeNo: user.employeeNo,
          status: 'QM_START',
          registeredBy: user.employeeNo,
          startedAt,
          version,
          detail: {
            action: 'START', role: 'QM', source: 'QM_SCHEMA_CACHE_START_FALLBACK_V3',
            browseView: view, beforeCleaningStatus: beforeStatus, cleaningStatus: 'QM_CHECKING',
            primaryEmployeeNo: roommaidNo, secondaryEmployeeNo: secondaryRoommaidNo,
            schemaCacheCode: 'PGRST002'
          }
        });
      }

      rowData = Object.assign({}, rowInfo.data, {
        '청소상태': 'QM_CHECKING',
        'QM사번': user.employeeNo,
        '마지막변경버전': version
      });
    } finally {
      try { lock.releaseLock(); } catch (ignore) {}
    }

    // 핵심 복구: 여기서는 startQmInspection()/DB-first 체크리스트를 다시 호출하지 않습니다.
    // 어제까지 사용하던 Sheet 체크리스트 + Sheet QM 초안 생성 경로만 사용합니다.
    const checklist = getQmChecklistForMobile_();
    const draft = ensureQmInspectionDraft_(user, businessDate, responseSite, roomNo, rowData || {}, checklist);
    if (!draft || !draft.draftId) throw new Error('QM 체크리스트 저장준비를 완료하지 못했습니다.');

    return {
      ok: true,
      dbFirst: false,
      schemaCacheFallback: true,
      schemaCacheCode: 'PGRST002',
      realtimeSyncDeferred: true,
      alreadyChecking,
      version,
      checklist,
      draft,
      room: {
        rowNumber,
        businessDate,
        site: responseSite,
        roomNo,
        roomStatus: String(rowData && rowData['객실상태'] || '').trim(),
        cleaningStatus: 'QM_CHECKING',
        roommaidEmployeeNo: String(rowData && rowData['룸메이드사번'] || '').trim(),
        secondaryRoommaidEmployeeNo: String(rowData && rowData['보조룸메이드사번'] || '').trim(),
        qmEmployeeNo: user.employeeNo,
        operationalStatus: String(rowData && (rowData['객실조치'] || rowData['운영상태']) || '').trim(),
        version
      },
      message: alreadyChecking ? '진행 중인 점검을 불러왔습니다.' : 'QM 점검을 시작했습니다.'
    };
  });
}
