/**
 * 최소 시트 접근 계층: 사용자·코드는 캐시, 업무 데이터는 일괄 읽기
 */
var NOVA_RUNTIME_CACHE_ = typeof NOVA_RUNTIME_CACHE_ !== 'undefined'
  ? NOVA_RUNTIME_CACHE_
  : { spreadsheet: null, sheets: {}, headerMaps: {}, userIndex: null }; // NOVA_USER_INDEX_RUNTIME_CACHE_V1 · 동일 실행 내 사용자 인덱스 재사용

function getUserIndex_() { // (사용자계정 인덱스 조회)
  if (NOVA_RUNTIME_CACHE_.userIndex) return NOVA_RUNTIME_CACHE_.userIndex; // NOVA_USER_INDEX_RUNTIME_CACHE_V1
  const cache = CacheService.getScriptCache();
  const cached = cache.get('NOVA_USER_INDEX_V2');
  if (cached) {
    const parsed = JSON.parse(cached);
    NOVA_RUNTIME_CACHE_.userIndex = parsed;
    return parsed;
  }

  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  const headerMap = getHeaderMap_(sheet);
  const lastRow = sheet.getLastRow();
  const index = { byName: {}, byEmployeeNo: {}, active: [] };

  if (lastRow >= 2) {
    const values = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getDisplayValues();
    values.forEach((row, offset) => {
      const user = rowToUser_(row, offset + 2, headerMap);
      if (!user.employeeNo || !user.name) return;
      index.byEmployeeNo[user.employeeNo] = user;
      if (!index.byName[user.name]) index.byName[user.name] = [];
      index.byName[user.name].push(user);
      if (user.enabled) index.active.push(user);
    });
  }

  const serialized = JSON.stringify(index);
  if (serialized.length < 95000) {
    cache.put('NOVA_USER_INDEX_V2', serialized, NOVA.CACHE_SECONDS);
  }
  NOVA_RUNTIME_CACHE_.userIndex = index; // NOVA_USER_INDEX_RUNTIME_CACHE_V1
  return index;
}

function rowToUser_(row, rowNumber, headerMap) { // (사용자계정 행 변환)
  const value = header => String(row[(headerMap[header] || 1) - 1] || '').trim();
  return {
    rowNumber,
    employeeNo: value('사번'),
    name: value('이름'),
    job: value('직무'),
    employmentType: value('채용구분'),
    role: value('권한').toUpperCase(),
    enabled: value('사용여부').toUpperCase() === 'Y',
    telegramId: value('텔레그램ID'),
    telegramEnabled: value('텔레그램알림').toUpperCase() !== 'N',
    phone: value('연락처'),
    defaultSite: value('기본사업장'),
    defaultBuildings: value('기본담당동'),
    note: value('비고'),
    updatedAt: value('수정일시'),
    telegramConnectionKey: value('텔레그램연결키'),
    telegramConnectionLink: value('텔레그램연결링크'),
    telegramConnectionStatus: value('텔레그램연결상태'),
    telegramLinkedAt: value('텔레그램연결일시')
  };
}

function getActiveUserByEmployeeNo_(employeeNo) { // (사번 기준 활성 사용자 조회)
  const user = getUserIndex_().byEmployeeNo[String(employeeNo || '').trim()];
  return user && user.enabled ? user : null;
}

function getActiveUsersByName_(name) { // (이름 기준 활성 사용자 조회)
  const users = getUserIndex_().byName[String(name || '').trim()] || [];
  return users.filter(user => user.enabled);
}

function getActiveUsersByRole_(roles) { // (권한 기준 활성 직원 조회)
  const allowed = new Set((Array.isArray(roles) ? roles : [roles]).map(role => String(role || '').toUpperCase()));
  return getUserIndex_().active.filter(user => allowed.has(user.role));
}

function getPublicUser_(user) { // (클라이언트 전달용 사용자 정보)
  return {
    employeeNo: user.employeeNo,
    name: user.name,
    job: user.job,
    role: user.role,
    telegramLinked: Boolean(user.telegramId),
    telegramEnabled: user.telegramEnabled,
    telegramConnectionStatus: user.telegramConnectionStatus || (user.telegramId ? '연결완료' : '미연결'),
    defaultSite: user.defaultSite,
    sessionSite: String(user.sessionSite || ''),
    siteScopeLocked: Boolean(user.siteScopeLocked),
    defaultBuildings: user.defaultBuildings
    // SITE_SCOPE_INDICATOR_CLOSE_V2
  };
}

function getPublicStaffList_(roles) { // (선택 목록용 직원 정보)
  return getActiveUsersByRole_(roles)
    .map(user => ({
      employeeNo: user.employeeNo,
      name: user.name,
      job: user.job,
      role: user.role,
      defaultSite: user.defaultSite,
      defaultBuildings: user.defaultBuildings
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'ko'));
}

function getCodeIndex_() { // (코드설정 인덱스 조회)
  const cache = CacheService.getScriptCache();
  const cached = cache.get('NOVA_CODE_INDEX_V2');
  if (cached) return JSON.parse(cached);

  const sheet = getRequiredSheet_(NOVA.SHEETS.CODES);
  const headerMap = getHeaderMap_(sheet);
  const index = {};
  if (sheet.getLastRow() >= 2) {
    const values = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getDisplayValues();
    values.forEach(row => {
      const get = header => String(row[(headerMap[header] || 1) - 1] || '').trim();
      if (get('사용여부').toUpperCase() !== 'Y') return;
      const group = get('코드그룹');
      if (!group) return;
      if (!index[group]) index[group] = [];
      index[group].push({
        code: get('코드'),
        label: get('표시명'),
        order: Number(get('정렬순서') || 9999),
        note: get('비고')
      });
    });
  }
  Object.keys(index).forEach(group => index[group].sort((a, b) => a.order - b.order));
  cache.put('NOVA_CODE_INDEX_V2', JSON.stringify(index), NOVA.CODE_CACHE_SECONDS);
  return index;
}

function getCodes_(group) { // (특정 코드그룹 조회)
  return getCodeIndex_()[String(group || '').trim()] || [];
}

function getRequiredSheet_(name) { // (필수 시트 조회·동일 실행 내 재사용)
  const key = String(name || '').trim();
  if (NOVA_RUNTIME_CACHE_.sheets[key]) return NOVA_RUNTIME_CACHE_.sheets[key];
  const sheet = getSpreadsheet_().getSheetByName(key);
  if (!sheet) throw new Error(`${key} 시트가 없습니다. setupNovaLite()를 먼저 실행하세요.`);
  NOVA_RUNTIME_CACHE_.sheets[key] = sheet;
  return sheet;
}

function getHeaderMap_(sheet) { // (시트 헤더-열번호 매핑·동일 실행 내 재사용)
  const lastColumn = Math.max(sheet.getLastColumn(), 1);
  const cacheKey = `${sheet.getSheetId()}:${lastColumn}`;
  if (NOVA_RUNTIME_CACHE_.headerMaps[cacheKey]) return NOVA_RUNTIME_CACHE_.headerMaps[cacheKey];
  const headers = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0];
  const map = {};
  headers.forEach((header, index) => {
    const key = String(header || '').trim();
    if (key) map[key] = index + 1;
  });
  NOVA_RUNTIME_CACHE_.headerMaps[cacheKey] = map;
  return map;
}

function rowObjectFromValues_(row, headerMap) { // (행 배열을 헤더 객체로 변환)
  const result = {};
  Object.keys(headerMap).forEach(header => {
    result[header] = row[headerMap[header] - 1];
  });
  return result;
}

function createRowByHeaders_(sheet, valuesByHeader) { // (헤더 기준 신규 행 생성)
  const headerMap = getHeaderMap_(sheet);
  const row = new Array(sheet.getLastColumn()).fill('');
  Object.keys(valuesByHeader).forEach(header => {
    if (headerMap[header]) row[headerMap[header] - 1] = valuesByHeader[header];
  });
  return row;
}

function updateRowByHeaders_(sheet, rowNumber, valuesByHeader) { // (헤더 기준 행 일부 수정·연속열 일괄 기록)
  const headerMap = getHeaderMap_(sheet);
  const entries = Object.keys(valuesByHeader)
    .map(header => ({ column: headerMap[header], value: valuesByHeader[header] == null ? '' : valuesByHeader[header] }))
    .filter(entry => Boolean(entry.column))
    .sort((a, b) => a.column - b.column);
  if (!entries.length) return;

  const groups = [];
  entries.forEach(entry => {
    const last = groups[groups.length - 1];
    if (last && last.startColumn + last.values.length === entry.column) {
      last.values.push(entry.value);
    } else {
      groups.push({ startColumn: entry.column, values: [entry.value] });
    }
  });
  groups.forEach(group => {
    sheet.getRange(rowNumber, group.startColumn, 1, group.values.length).setValues([group.values]);
  });
}


function ensureSheetRowCapacity_(sheet, requiredLastRow) { // (대량 기록 전 시트 행수 확보)
  const required = Math.max(1, Number(requiredLastRow || 1));
  const current = sheet.getMaxRows();
  if (current < required) sheet.insertRowsAfter(current, required - current);
}

function clearNovaCaches_() { // (공통 캐시 초기화)
  CacheService.getScriptCache().removeAll([
    'NOVA_USER_INDEX_V1',
    'NOVA_CODE_INDEX_V1',
    'NOVA_USER_INDEX_V2',
    'NOVA_CODE_INDEX_V2',
    'NOVA_SITE_LIST_V1',
    'NOVA_TELEGRAM_ROLE_POLICY_V1'
  ]);
  NOVA_RUNTIME_CACHE_.spreadsheet = null;
  NOVA_RUNTIME_CACHE_.sheets = {};
  NOVA_RUNTIME_CACHE_.headerMaps = {};
  NOVA_RUNTIME_CACHE_.userIndex = null; // NOVA_USER_INDEX_RUNTIME_CACHE_V1
}
