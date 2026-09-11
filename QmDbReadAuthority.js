/**
 * QM_DB_READ_AUTHORITY_V1
 * - QM 모바일 대상/추가조회에서 PostgreSQL current room 상태를 읽기 원본으로 사용합니다.
 * - 기존 Sheet 객체는 건물/층/이름/rowNumber 등 표시 메타데이터 fallback으로만 사용합니다.
 * - 읽기 전용이며 객실/초안/Sheet 상태를 변경하지 않습니다.
 */
function getQmDbReadAuthoritySnapshot(token, options) {
  return measureResponse_('getQmDbReadAuthoritySnapshot', () => {
    const user = requireRole_(token, ['QM']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site);
    const scope = String(safe.scope || 'MOBILE').trim().toUpperCase();
    const view = String(safe.view || '').trim().toUpperCase();
    if (!site) throw new Error('QM DB 조회에 사업장이 필요합니다.');
    if (!['MOBILE', 'BROWSE'].includes(scope)) throw new Error('지원하지 않는 QM DB 조회 범위입니다.');
    if (scope === 'BROWSE' && !['CLEANED', 'VACANT'].includes(view)) throw new Error('지원하지 않는 QM 조회 탭입니다.');

    const userIndex = getUserIndex_();
    const sheetRooms = getCurrentRoomsForMobile_(businessDate, site, userIndex.byEmployeeNo);
    const dbRooms = novaQmDbReadAuthorityFetchRooms_(token, businessDate, site);
    const mergedRooms = novaQmDbReadAuthorityMergeRooms_(sheetRooms, dbRooms, userIndex.byEmployeeNo, businessDate, site);

    let rooms = mergedRooms;
    if (scope === 'MOBILE') {
      rooms = mergedRooms
        .filter(room => String(room.qmEmployeeNo || '').trim() === String(user.employeeNo || '').trim())
        .sort(compareMobileQmRooms_);
      return {
        ok: true,
        dbAuthority: true,
        scope,
        businessDate,
        site,
        rooms,
        summary: buildQmSummary_(rooms),
        serverTime: nowText_()
      };
    }

    if (view === 'VACANT') {
      rooms = mergedRooms.filter(room => String(room.roomStatus || '').trim().toUpperCase() === 'VACANT_CLEAN');
    } else {
      const completedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
      rooms = mergedRooms.filter(room => {
        const cleaningStatus = String(room.cleaningStatus || '').trim().toUpperCase();
        const roomStatus = String(room.roomStatus || '').trim().toUpperCase();
        const hasRoommaid = Boolean(
          String(room.roommaidEmployeeNo || '').trim()
          || String(room.secondaryRoommaidEmployeeNo || '').trim()
        );
        return completedStatuses.has(cleaningStatus) && hasRoommaid && roomStatus !== 'VACANT_CLEAN';
      });
    }
    rooms.sort(compareRooms_);
    return {
      ok: true,
      dbAuthority: true,
      scope,
      view,
      businessDate,
      site,
      rooms: rooms.map(qmMobileBrowseRoomDto_),
      summary: { count: rooms.length },
      serverTime: nowText_()
    };
  });
}

function novaQmDbReadAuthorityFetchRooms_(token, businessDate, site) {
  const props = PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  if (!apiBase) throw new Error('Realtime API 주소를 확인할 수 없습니다.');
  const query = [
    `businessDate=${encodeURIComponent(String(businessDate || ''))}`,
    `site=${encodeURIComponent(String(site || ''))}`
  ].join('&');
  const response = UrlFetchApp.fetch(`${apiBase}/v1/rooms?${query}`, {
    method: 'get',
    headers: { Authorization: `Bearer ${String(token || '').trim()}` },
    muteHttpExceptions: true,
    followRedirects: true
  });
  const status = Number(response.getResponseCode() || 0);
  let body = {};
  try { body = JSON.parse(response.getContentText() || '{}'); } catch (error) { body = {}; }
  if (status < 200 || status >= 300 || !body.ok || !Array.isArray(body.rooms)) {
    throw new Error(String(body.message || body.error || `Realtime QM 객실조회 실패 (${status})`));
  }
  return body.rooms;
}

function novaQmDbReadAuthorityMergeRooms_(sheetRooms, dbRooms, userIndex, businessDate, site) {
  const sheetList = Array.isArray(sheetRooms) ? sheetRooms : [];
  const dbList = Array.isArray(dbRooms) ? dbRooms : [];
  const byKey = new Map();
  sheetList.forEach(room => {
    const key = `${String(room.site || site).trim()}|${String(room.roomNo || '').trim()}`;
    if (String(room.roomNo || '').trim()) byKey.set(key, Object.assign({}, room));
  });

  dbList.forEach(dbRoom => {
    const roomNo = String(dbRoom && dbRoom.roomNo || '').trim();
    const roomSite = String(dbRoom && dbRoom.site || site).trim();
    if (!roomNo || !roomSite) return;
    const key = `${roomSite}|${roomNo}`;
    const base = Object.assign({ businessDate, site: roomSite, roomNo }, byKey.get(key) || {});
    const qmEmployeeNo = String(dbRoom.qmEmployeeNo || '').trim();
    const roommaidEmployeeNo = String(dbRoom.roommaidEmployeeNo || '').trim();
    const secondaryRoommaidEmployeeNo = String(dbRoom.secondaryRoommaidEmployeeNo || '').trim();
    const qmUser = qmEmployeeNo && userIndex ? userIndex[qmEmployeeNo] : null;
    const roommaidUser = roommaidEmployeeNo && userIndex ? userIndex[roommaidEmployeeNo] : null;
    const secondaryUser = secondaryRoommaidEmployeeNo && userIndex ? userIndex[secondaryRoommaidEmployeeNo] : null;

    Object.assign(base, {
      businessDate: String(dbRoom.businessDate || base.businessDate || businessDate),
      site: roomSite,
      roomNo,
      building: String(dbRoom.building || base.building || ''),
      roomStatus: String(dbRoom.roomStatus || base.roomStatus || ''),
      cleaningStatus: String(dbRoom.cleaningStatus || base.cleaningStatus || ''),
      cleaningType: String(dbRoom.cleaningType || base.cleaningType || ''),
      assignmentType: String(dbRoom.assignmentType || base.assignmentType || ''),
      roommaidEmployeeNo,
      roommaidName: String(roommaidUser && roommaidUser.name || base.roommaidName || ''),
      secondaryRoommaidEmployeeNo,
      secondaryRoommaidName: String(secondaryUser && secondaryUser.name || base.secondaryRoommaidName || ''),
      qmEmployeeNo,
      qmName: String(qmUser && qmUser.name || base.qmName || ''),
      operationalStatus: String(dbRoom.operationalStatus || ''),
      preassigned: Boolean(dbRoom.preassigned),
      vip: Boolean(dbRoom.vip),
      importantRoom: Boolean(dbRoom.importantRoom),
      lastRoomStatus: String(dbRoom.lastRoomStatus || base.lastRoomStatus || ''),
      previousRoomStatus: String(dbRoom.previousRoomStatus || base.previousRoomStatus || ''),
      previousCleaningStatus: String(dbRoom.previousCleaningStatus || base.previousCleaningStatus || ''),
      previousRoommaidEmployeeNo: String(dbRoom.previousRoommaidEmployeeNo || base.previousRoommaidEmployeeNo || ''),
      previousSecondaryRoommaidEmployeeNo: String(dbRoom.previousSecondaryRoommaidEmployeeNo || base.previousSecondaryRoommaidEmployeeNo || ''),
      lastQmBusinessDate: String(dbRoom.lastQmBusinessDate || base.lastQmBusinessDate || ''),
      lastQmEmployeeNo: String(dbRoom.lastQmEmployeeNo || base.lastQmEmployeeNo || ''),
      cleaningStartedAt: String(dbRoom.cleaningStartedAt || base.cleaningStartedAt || ''),
      cleaningCompletedAt: String(dbRoom.cleaningCompletedAt || base.cleaningCompletedAt || ''),
      version: Number(dbRoom.version || 0),
      updatedAt: String(dbRoom.updatedAt || base.updatedAt || '')
    });
    byKey.set(key, base);
  });

  return Array.from(byKey.values());
}
