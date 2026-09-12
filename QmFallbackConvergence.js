// QM_FALLBACK_DB_CONVERGENCE_V1
// PGRST002 circuit mode에서 Sheet QM 상태를 사용자 응답 경로 밖에서 DB에 수렴시키는 전용 브리지입니다.
// 이 함수는 Sheet를 수정하지 않습니다. 단일 객실의 현재 Sheet 상태가 기대값과 일치할 때만
// 기존 sync-current-rooms 경로에 forceSheetCleaning을 명시하고, DB 재조회로 최종 상태를 검증합니다.
function syncQmFallbackRoomToRealtime(token, payload) {
  return measureResponse_('syncQmFallbackRoomToRealtime', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site);
    const roomNo = String(safe.roomNo || '').trim();
    const expectedStatus = String(safe.expectedStatus || '').trim().toUpperCase();
    if (!site || !roomNo) throw new Error('QM fallback DB 동기화에 사업장과 객실번호가 필요합니다.');
    if (!['QM_CHECKING', 'QM_COMPLETED'].includes(expectedStatus)) {
      throw new Error('QM fallback DB 동기화 상태를 확인할 수 없습니다.');
    }
    if (typeof novaRealtimeFinalEnabled_ !== 'function' || !novaRealtimeFinalEnabled_()) {
      return { ok: true, deferred: true, reason: 'REALTIME_DISABLED', businessDate, site, roomNo, expectedStatus };
    }

    // 읽기만 수행합니다. fallback 쓰기 호출과 동일한 Sheet write lock을 잡지 않습니다.
    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
    const rowInfo = findCurrentRoomRow_(sheet, businessDate, site, roomNo);
    if (!rowInfo) throw new Error(`${roomNo}호를 현재객실현황에서 찾을 수 없습니다.`);
    const sheetStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
    const sheetQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
    if (sheetQmEmployeeNo !== String(user.employeeNo || '').trim()) {
      return { ok: true, deferred: true, reason: 'QM_OWNER_NOT_READY', businessDate, site, roomNo, expectedStatus, sheetStatus };
    }
    if (sheetStatus !== expectedStatus) {
      return { ok: true, deferred: true, reason: 'SHEET_STATUS_NOT_READY', businessDate, site, roomNo, expectedStatus, sheetStatus };
    }

    const rooms = novaRealtimeFinalBuildRooms_(businessDate, site, roomNo);
    if (rooms.length !== 1) throw new Error(`${roomNo}호 DB 동기화 원본을 정확히 1건으로 확인할 수 없습니다.`);
    const users = novaRealtimeFinalBuildUsers_([site]);
    const sync = novaRealtimeFinalSignedPost_('/v1/admin/sync-current-rooms', {
      businessDate,
      source: 'GOOGLE_SHEETS_NOVA_QM_FALLBACK_CONVERGENCE_V1',
      generatedAt: new Date().toISOString(),
      forceSheetCleaning: true,
      users,
      rooms
    });

    if (typeof novaRealtimeFetchCurrentRoomForQmMirror_ !== 'function') {
      throw new Error('QM fallback DB 동기화 검증함수가 준비되지 않았습니다.');
    }
    const dbRoom = novaRealtimeFetchCurrentRoomForQmMirror_(token, businessDate, site, roomNo);
    const dbStatus = String(dbRoom && dbRoom.cleaningStatus || '').trim().toUpperCase();
    const dbQmEmployeeNo = String(dbRoom && dbRoom.qmEmployeeNo || '').trim();
    if (dbStatus !== expectedStatus || dbQmEmployeeNo !== String(user.employeeNo || '').trim()) {
      throw new Error(`QM fallback DB 수렴 검증 실패 (${roomNo} · ${dbStatus || '-'}).`);
    }

    return {
      ok: true,
      converged: true,
      businessDate,
      site,
      roomNo,
      expectedStatus,
      sheetStatus,
      dbStatus,
      qmEmployeeNo: dbQmEmployeeNo,
      dbVersion: Number(dbRoom.version || 0),
      sync
    };
  });
}
