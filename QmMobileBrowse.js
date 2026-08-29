/**
 * QM 모바일 보조 조회
 * - 기존 QM 배정/점검/완료 권한과 getMobileSnapshot 구조는 변경하지 않습니다.
 * - 추가 탭을 실제로 열 때만 공실 또는 당일 실제 청소완료 객실을 조회합니다.
 * - 조회 전용이며 객실 상태/배정/점검 권한을 변경하지 않습니다.
 */
function getQmMobileBrowseRooms(token, options) { // (QM 추가탭 지연조회)
  return measureResponse_('getQmMobileBrowseRooms', () => {
    const user = requireRole_(token, ['QM']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || user.defaultSite || '').trim();
    const view = String(safe.view || '').trim().toUpperCase();
    if (!['CLEANED', 'VACANT'].includes(view)) throw new Error('지원하지 않는 QM 객실 조회입니다.');

    const userIndex = getUserIndex_();
    const rooms = getCurrentRoomsForMobile_(businessDate, site, userIndex.byEmployeeNo);
    let selectedRooms = [];

    if (view === 'VACANT') {
      selectedRooms = rooms.filter(room => String(room.roomStatus || '').trim().toUpperCase() === 'VACANT_CLEAN');
    } else {
      // 업로드 당시부터 공실이던 객실을 청소완료로 오인하지 않도록
      // 당일 업무이력의 실제 CLEANING_COMPLETE/ROOMMAID_COMPLETE 기록을 기준으로 선별합니다.
      const dailyRequest = {
        period: 'DAILY',
        date: businessDate,
        year: Number(businessDate.slice(0, 4)),
        month: Number(businessDate.slice(5, 7))
      };
      const historyRows = readMonthlyHistoryRows_(dailyRequest, [NOVA.RECORD_TYPES.CLEANING]);
      const completedRoomKeys = new Set();
      (historyRows || []).forEach(item => {
        const data = item && item.data ? item.data : item;
        if (!data) return;
        if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') return;
        const status = String(data['처리상태'] || '').trim().toUpperCase();
        if (!['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(status)) return;
        const rowSite = String(data['사업장'] || '').trim();
        const roomNo = String(data['객실번호'] || '').trim();
        if (!roomNo || (site && rowSite !== site)) return;
        completedRoomKeys.add(`${rowSite}|${roomNo}`);
      });

      // 현재 재정비/초기화된 객실은 완료목록에서 제외합니다.
      const currentCompletedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
      selectedRooms = rooms.filter(room =>
        completedRoomKeys.has(`${String(room.site || '').trim()}|${String(room.roomNo || '').trim()}`)
        && currentCompletedStatuses.has(String(room.cleaningStatus || '').trim().toUpperCase())
      );
    }

    selectedRooms.sort(compareRooms_);
    return {
      ok: true,
      view,
      selection: { businessDate, site },
      rooms: selectedRooms.map(qmMobileBrowseRoomDto_),
      summary: { count: selectedRooms.length },
      serverTime: nowText_()
    };
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
