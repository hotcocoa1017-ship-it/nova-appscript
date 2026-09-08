/** ROOMMAID_CLOSE_READ_PERFORMANCE_V4
 * Read-only performance helpers for the roommaid close journal.
 * Business logic remains in 19_RoommaidCloseJournal.js.
 */
var NOVA_ROOMMAID_CLOSE_MASTER_RUNTIME_ = typeof NOVA_ROOMMAID_CLOSE_MASTER_RUNTIME_ !== 'undefined'
  ? NOVA_ROOMMAID_CLOSE_MASTER_RUNTIME_
  : {};

function readRoomMasterIndexForCloseCached_(site) { // ROOMMAID_CLOSE_MASTER_CACHE_V2
  const siteText = String(site || '').trim();
  const configVersion = getSyncVersion_(['CONFIG'], '', '');
  const runtimeKey = `${siteText}|${configVersion}`;
  if (NOVA_ROOMMAID_CLOSE_MASTER_RUNTIME_[runtimeKey]) {
    return NOVA_ROOMMAID_CLOSE_MASTER_RUNTIME_[runtimeKey];
  }

  const cacheKey = buildDeltaCacheKey_('ROOMMAID_CLOSE_MASTER_V2', [
    NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION, siteText, configVersion
  ]);
  const cached = getCachedJson_(cacheKey);
  if (cached && cached.byRoomNo && cached.maintenanceTypes && cached.buildings) {
    NOVA_ROOMMAID_CLOSE_MASTER_RUNTIME_[runtimeKey] = cached;
    return cached;
  }

  const master = readRoomMasterIndexForCloseProjected_(siteText);
  // 객실마스터는 CONFIG 버전이 바뀌면 캐시키 자체가 바뀌므로 최대 6시간 재사용해도
  // 설정 변경 후 오래된 마스터가 노출되지 않습니다.
  putCachedJson_(cacheKey, master, 21600);
  NOVA_ROOMMAID_CLOSE_MASTER_RUNTIME_[runtimeKey] = master;
  return master;
}

function readRoomMasterIndexForCloseProjected_(site) { // ROOMMAID_CLOSE_MASTER_PROJECTED_READ_V1
  const sheet = getRequiredSheet_(NOVA.SHEETS.ROOMS);
  const headerMap = getHeaderMap_(sheet);
  const byRoomNo = {};
  const maintenanceTypes = new Set();
  const buildings = new Set();
  const buildingTypes = {};
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return { byRoomNo, maintenanceTypes: [], buildings: [], buildingTypes: {} };
  }

  const requiredHeaders = ['객실번호', '사업장', '동', '정비타입', '사용여부'];
  const columns = requiredHeaders.map(header => Number(headerMap[header] || 0)).filter(Boolean);
  if (columns.length !== requiredHeaders.length) {
    // 헤더 구조가 예상과 다르면 검증된 기존 구현으로 안전하게 폴백합니다.
    return readRoomMasterIndexForClose_(site);
  }
  const startColumn = Math.min.apply(null, columns);
  const endColumn = Math.max.apply(null, columns);
  const values = sheet.getRange(2, startColumn, lastRow - 1, endColumn - startColumn + 1).getDisplayValues();
  const valueAt = (row, header) => String(row[Number(headerMap[header]) - startColumn] || '').trim();

  values.forEach(row => {
    const roomSite = valueAt(row, '사업장');
    const enabled = (valueAt(row, '사용여부') || 'Y').toUpperCase();
    if (roomSite !== site || ['N', '미사용', '사용안함'].includes(enabled)) return;
    const roomNo = normalizeRoomNo_(valueAt(row, '객실번호'));
    if (!roomNo) return;
    const maintenanceType = normalizeMaintenanceTypeForClose_(valueAt(row, '정비타입'));
    const building = normalizeRoomBuilding_(valueAt(row, '동'), roomNo) || '미지정';
    byRoomNo[roomNo] = { roomNo, site: roomSite, building, maintenanceType };
    maintenanceTypes.add(maintenanceType);
    buildings.add(building);
    if (!buildingTypes[building]) buildingTypes[building] = new Set();
    buildingTypes[building].add(maintenanceType);
  });

  const normalizedBuildingTypes = {};
  Object.keys(buildingTypes).forEach(building => {
    normalizedBuildingTypes[building] = Array.from(buildingTypes[building]);
  });
  return {
    byRoomNo,
    maintenanceTypes: Array.from(maintenanceTypes),
    buildings: Array.from(buildings),
    buildingTypes: normalizedBuildingTypes
  };
}
