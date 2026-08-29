/**
 * QM 모바일 보조 조회
 * - 기존 QM 배정/점검/완료 권한과 getMobileSnapshot 구조는 변경하지 않습니다.
 * - 추가 탭을 실제로 열 때만 공실 또는 당일 청소완료 객실을 조회합니다.
 * - 조회 전용이며 객실 상태/배정/점검 권한을 변경하지 않습니다.
 * - 성능보호: 업무이력 전체 재조회 없이 현재 업무일자 객실상태만으로 판별합니다.
 */
function getQmMobileBrowseRooms(token, options) { // (QM 추가탭 지연조회 · 업무이력 무스캔)
  return measureResponse_('getQmMobileBrowseRooms', () => {
    const user = requireRole_(token, ['QM']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || user.defaultSite || '').trim();
    const view = String(safe.view || '').trim().toUpperCase();
    if (!['CLEANED', 'VACANT'].includes(view)) throw new Error('지원하지 않는 QM 객실 조회입니다.');

    const cacheKey = `NOVA_QM_BROWSE_V2:${getDataVersion_()}:${businessDate}:${site || 'ALL'}:${view}`;
    const cached = getCachedJson_(cacheKey);
    if (cached) return Object.assign({}, cached, { serverTime: nowText_() });

    const userIndex = getUserIndex_();
    const rooms = getCurrentRoomsForMobile_(businessDate, site, userIndex.byEmployeeNo);
    let selectedRooms = [];

    if (view === 'VACANT') {
      selectedRooms = rooms.filter(room => String(room.roomStatus || '').trim().toUpperCase() === 'VACANT_CLEAN');
    } else {
      // 현재객실현황은 선택한 업무일자 자체의 데이터입니다.
      // 실제 당일 정비를 거친 객실만 잡기 위해 완료계열 상태 + 룸메이드 배정 존재를 함께 확인합니다.
      // 업로드 당시부터 공실인 객실은 룸메이드 배정이 없으므로 제외되고,
      // 청소초기화/재정비 객실은 완료계열 상태가 아니므로 자동 제외됩니다.
      const completedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
      selectedRooms = rooms.filter(room => {
        const cleaningStatus = String(room.cleaningStatus || '').trim().toUpperCase();
        const roomStatus = String(room.roomStatus || '').trim().toUpperCase();
        const hasRoommaid = Boolean(
          String(room.roommaidEmployeeNo || '').trim()
          || String(room.secondaryRoommaidEmployeeNo || '').trim()
        );
        return completedStatuses.has(cleaningStatus)
          && hasRoommaid
          && roomStatus !== 'VACANT_CLEAN';
      });
    }

    selectedRooms.sort(compareRooms_);
    const result = {
      ok: true,
      view,
      selection: { businessDate, site },
      rooms: selectedRooms.map(qmMobileBrowseRoomDto_),
      summary: { count: selectedRooms.length },
      serverTime: nowText_()
    };
    putCachedJson_(cacheKey, result, Math.max(6, Number(NOVA.DELTA_CACHE_SECONDS || 12)));
    return result;
  });
}

function qmMobileBrowseRoomDto_(room) { // (QM 조회전용 최소 객실정보)
  const source = room || {};
  return {
    rowNumber: Number(source.rowNumber || 0),
    businessDate: String(source.businessDate || ''),
    site: String(source.site || ''),
    roomNo: String(source.roomNo || ''),
    building: String(source.building || ''),
    floor: String(source.floor || ''),
    roomStatus: String(source.roomStatus || ''),
    cleaningStatus: String(source.cleaningStatus || ''),
    cleaningType: String(source.cleaningType || ''),
    assignmentType: String(source.assignmentType || ''),
    roommaidEmployeeNo: String(source.roommaidEmployeeNo || ''),
    roommaidName: String(source.roommaidName || ''),
    secondaryRoommaidEmployeeNo: String(source.secondaryRoommaidEmployeeNo || ''),
    secondaryRoommaidName: String(source.secondaryRoommaidName || ''),
    qmEmployeeNo: String(source.qmEmployeeNo || ''),
    qmName: String(source.qmName || ''),
    preassigned: Boolean(source.preassigned),
    vip: Boolean(source.vip),
    importantRoom: Boolean(source.importantRoom),
    operationalStatus: String(source.operationalStatus || ''),
    updatedAt: String(source.updatedAt || ''),
    version: Number(source.version || 0)
  };
}
