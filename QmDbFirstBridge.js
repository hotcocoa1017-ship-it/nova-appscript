/**
 * NOVA QM DB-first bridge v1
 *
 * DB에서 QM 점검 시작/초안을 먼저 확정한 뒤 기존 Sheet 현재객실현황·업무이력을
 * 비동기로 보완합니다. 사용자 점검 시작 응답을 Sheet 쓰기잠금에 묶지 않기 위한 브리지입니다.
 * 기존 QmMobileBrowse.js / startQmInspection 경로는 fallback으로 그대로 유지합니다.
 */
function ensureQmDbFirstDraftSheetMirror(token, payload) { // QM_BEGIN_DB_FIRST_V1
  return measureResponse_('ensureQmDbFirstDraftSheetMirror', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site);
    const roomNo = String(safe.roomNo || '').trim();
    const draftId = String(safe.draftId || (safe.draft && safe.draft.draftId) || '').trim();
    if (!site || !roomNo || !draftId) {
      throw new Error('QM DB-first 이력동기화에 사업장·객실번호·초안ID가 필요합니다.');
    }
    if (typeof novaRealtimeFinalEnabled_ !== 'function' || !novaRealtimeFinalEnabled_()
        || typeof novaRealtimeFetchCurrentRoomForQmMirror_ !== 'function') {
      throw new Error('Realtime QM 이력동기화가 준비되지 않았습니다.');
    }

    const dbRoom = novaRealtimeFetchCurrentRoomForQmMirror_(token, businessDate, site, roomNo);
    const dbQmEmployeeNo = String(dbRoom && dbRoom.qmEmployeeNo || '').trim();
    const dbCleaningStatus = String(dbRoom && dbRoom.cleaningStatus || '').trim().toUpperCase();
    if (dbQmEmployeeNo !== String(user.employeeNo || '').trim()) {
      throw new Error('DB에서 본인 QM 점검객실을 확인할 수 없습니다.');
    }
    if (!['QM_CHECKING', 'QM_COMPLETED'].includes(dbCleaningStatus)) {
      throw new Error('DB의 현재 QM 점검상태를 확인한 뒤 다시 시도하세요.');
    }

    // 체크리스트 읽기는 전역 쓰기잠금 바깥에서 수행합니다.
    const checklist = getQmChecklistForSubmit_();
    const draftPayload = safe.draft || {};
    const startedAt = String(draftPayload.startedAt || safe.startedAt || nowText_()).trim() || nowText_();
    const savedAt = String(draftPayload.savedAt || safe.savedAt || startedAt).trim() || startedAt;
    const answers = Array.isArray(draftPayload.answers) ? draftPayload.answers : [];
    const defects = Array.isArray(draftPayload.defects) ? draftPayload.defects : [];

    const lock = acquireWriteLock_(5000);
    try {
      const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const rowInfo = findCurrentRoomRowForMobileUpdate_(currentSheet, businessDate, site, roomNo, Number(safe.rowNumber || 0));
      if (!rowInfo) throw new Error('현재객실현황에서 QM 점검객실을 찾을 수 없습니다.');

      const responseSite = String(rowInfo.data['사업장'] || site).trim();
      const sheetQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
      const sheetCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
      let sheetVersion = Number(rowInfo.data['마지막변경버전'] || 0);
      let roomMirrored = false;

      // DB 확정값만 해당 객실 1행에 즉시 반영합니다. 전체 이벤트 큐는 건드리지 않습니다.
      if (sheetQmEmployeeNo !== dbQmEmployeeNo || sheetCleaningStatus !== dbCleaningStatus) {
        sheetVersion = reserveDataVersion_({ lockHeld: true });
        updateRowByHeaders_(currentSheet, rowInfo.rowNumber, {
          'QM사번': dbQmEmployeeNo,
          '청소상태': dbCleaningStatus,
          '마지막변경버전': sheetVersion,
          '수정일시': nowText_()
        });
        SpreadsheetApp.flush();
        publishDataVersion_(sheetVersion, {
          domains: ['ROOM'], businessDate, site: responseSite, lockHeld: true
        });
        roomMirrored = true;
      }

      let draftInfo = null;
      try {
        draftInfo = getQmInspectionRecordById_(draftId);
      } catch (ignore) {
        draftInfo = null;
      }

      if (!draftInfo) {
        // 전환 시점에 남아 있는 동일객실의 구 Sheet 초안은 감사기록으로 남기되 사용대상에서 제외합니다.
        const previousActive = findActiveQmInspectionDraft_(businessDate, responseSite, roomNo, user.employeeNo);
        if (previousActive && String(previousActive.data['기록ID'] || '').trim() !== draftId) {
          const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
          updateRowByHeaders_(historySheet, previousActive.rowNumber, {
            '처리상태': 'SUPERSEDED',
            '삭제여부': 'Y',
            '수정일시': nowText_()
          });
        }

        const detail = {
          revision: String(draftPayload.checklistRevision || checklist.revision || ''),
          startedAt,
          savedAt,
          answers,
          defects,
          roommaidEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
          secondaryRoommaidEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
          qmEmployeeNo: user.employeeNo,
          cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
          assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
          source: 'QM_BEGIN_DB_FIRST_V1'
        };
        appendUnifiedHistory_({
          recordId: draftId,
          recordType: NOVA.RECORD_TYPES.QM_CHECKLIST,
          businessDate,
          site: responseSite,
          roomNo,
          targetEmployeeNo: user.employeeNo,
          status: 'IN_PROGRESS',
          registeredBy: user.employeeNo,
          startedAt,
          detail
        });
        draftInfo = getQmInspectionRecordById_(draftId);
      }

      validateQmDraftOwnership_(draftInfo, user);
      const detail = parseQmHistoryDetail_(draftInfo.data);
      return {
        ok: true,
        dbFirst: true,
        roomMirrored,
        room: {
          rowNumber: rowInfo.rowNumber,
          businessDate,
          site: responseSite,
          roomNo,
          qmEmployeeNo: dbQmEmployeeNo,
          cleaningStatus: dbCleaningStatus,
          version: Number(dbRoom.version || 0),
          sheetVersion
        },
        draft: buildQmDraftResponse_(draftInfo, detail),
        checklist,
        serverTime: nowText_()
      };
    } finally {
      try { lock.releaseLock(); } catch (ignore) {}
    }
  });
}
