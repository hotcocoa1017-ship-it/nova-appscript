// QM_EMERGENCY_LEGACY_START_V1
// 2026-09-12: PostgREST schema-cache(PGRST002) 장애 동안 QM 업무 중단을 막기 위한 최소 범위 복구 경로.
// DB-first 체크리스트 조회를 전혀 호출하지 않고 기존 Sheet 체크리스트/초안만으로 즉시 시작을 확정한다.
function startQmInspectionEmergencyLegacy(token, payload) {
  return measureResponse_('startQmInspectionEmergencyLegacy', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
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
    let roomData = null;
    let draft = null;
    let checklist = null;

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
      const hasRoommaid = Boolean(roommaidNo || secondaryRoommaidNo);
      if (!['COMPLETED', 'QM_WAITING', 'QM_CHECKING'].includes(cleaningStatus)) {
        throw new Error('현재 QM 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.');
      }

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

      alreadyChecking = currentQmNo === user.employeeNo && cleaningStatus === 'QM_CHECKING';
      if (alreadyChecking) {
        version = Number(rowInfo.data['마지막변경버전'] || 0);
      } else {
        version = reserveDataVersion_({ lockHeld: true });
        const startedAt = nowText_();
        const patch = { '청소상태': 'QM_CHECKING', '마지막변경버전': version, '수정일시': startedAt };
        if (view !== 'TARGETS' && !currentQmNo) patch['QM사번'] = user.employeeNo;
        updateRowByHeaders_(sheet, rowInfo.rowNumber, patch);
        SpreadsheetApp.flush();
        publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: responseSite, lockHeld: true });
        appendUnifiedHistory_({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate, site: responseSite, roomNo,
          targetEmployeeNo: user.employeeNo,
          status: 'QM_START', registeredBy: user.employeeNo, startedAt, version,
          detail: {
            action: 'START', role: 'QM', source: 'QM_EMERGENCY_LEGACY_START_V1', browseView: view,
            beforeCleaningStatus: cleaningStatus, cleaningStatus: 'QM_CHECKING',
            primaryEmployeeNo: roommaidNo, secondaryEmployeeNo: secondaryRoommaidNo
          }
        });
      }

      // 중요: DB-first getter를 호출하지 않는다. 어제까지 사용되던 Sheet 정의를 그대로 사용한다.
      checklist = getQmChecklistForSubmit_();
      roomData = Object.assign({}, rowInfo.data, {
        '청소상태': 'QM_CHECKING',
        'QM사번': user.employeeNo,
        '마지막변경버전': version
      });
      draft = ensureQmInspectionDraft_(user, businessDate, responseSite, roomNo, roomData, checklist);
      if (!draft || !draft.draftId) throw new Error('QM 체크리스트 저장준비를 완료하지 못했습니다.');
    } finally {
      try { lock.releaseLock(); } catch (ignore) {}
    }

    return {
      ok: true,
      realtime: false,
      dbFirst: false,
      emergencyLegacy: true,
      version,
      checklist,
      draft,
      alreadyChecking,
      room: {
        rowNumber, businessDate, site: responseSite, roomNo,
        roomStatus: String(roomData && roomData['객실상태'] || '').trim(),
        cleaningStatus: 'QM_CHECKING',
        roommaidEmployeeNo: String(roomData && roomData['룸메이드사번'] || '').trim(),
        secondaryRoommaidEmployeeNo: String(roomData && roomData['보조룸메이드사번'] || '').trim(),
        qmEmployeeNo: user.employeeNo,
        version
      },
      message: alreadyChecking ? '진행 중인 점검을 불러왔습니다.' : 'QM 점검을 시작했습니다.'
    };
  });
}
