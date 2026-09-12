// QM_SCHEMA_CACHE_START_FALLBACK_V2
// PGRST002는 PostgREST schema cache 단계 실패이므로 DB RPC가 실행되기 전입니다.
// 이 경우에만 기존 Sheet QM 시작/초안 경로로 안전하게 복구합니다.
// 중요: 사용자 응답 경로에서는 DB 재동기화를 기다리지 않습니다. 재동기화는 클라이언트 후행 호출로 분리합니다.
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
            action: 'START', role: 'QM', source: 'QM_SCHEMA_CACHE_START_FALLBACK_V2',
            browseView: view, beforeCleaningStatus: beforeStatus, cleaningStatus: 'QM_CHECKING',
            primaryEmployeeNo: roommaidNo, secondaryEmployeeNo: secondaryRoommaidNo,
            schemaCacheCode: 'PGRST002'
          }
        });
      }
    } finally {
      try { lock.releaseLock(); } catch (ignore) {}
    }

    const started = startQmInspection(token, {
      businessDate,
      site: responseSite,
      roomNo,
      realtimeStarted: true,
      realtimeVersion: version
    });
    if (!started || !started.ok || !started.draft || !started.draft.draftId) {
      throw new Error(started && started.message ? started.message : 'QM 체크리스트 저장준비를 완료하지 못했습니다.');
    }

    // DB 재동기화는 여기서 실행하지 않습니다.
    // PGRST002 장애 중 동기식 재동기화를 기다리면 Apps Script 응답이 12초를 넘겨
    // 클라이언트가 점검 시작 실패로 오판합니다. 사용자가 먼저 작업을 계속하고,
    // 클라이언트가 별도 후행 호출로 syncNovaRealtimeRoomForAction을 실행합니다.
    return Object.assign({}, started, {
      ok: true,
      dbFirst: false,
      schemaCacheFallback: true,
      schemaCacheCode: 'PGRST002',
      realtimeSyncDeferred: true,
      alreadyChecking,
      room: Object.assign({}, started.room || {}, {
        rowNumber, businessDate, site: responseSite, roomNo,
        qmEmployeeNo: user.employeeNo,
        cleaningStatus: 'QM_CHECKING',
        version: Number(started.room && started.room.version || version || 0)
      })
    });
  });
}
