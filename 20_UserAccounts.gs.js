/**
 * NOVA 관리자·오더테이커 사용자계정 등록·수정·사용중지·미사용계정 삭제 관리
 * 기존 사용자계정 시트·로그인·텔레그램 연결 구조를 그대로 사용합니다.
 */
const NOVA_USER_EMPLOYMENT = Object.freeze({
  HEADER: '채용구분',
  REGULAR: '정규직',
  PART_TIME: '아르바이트',
  OUTSOURCE: '외주업체'
});

function getAdminUserAccountRegistrationData(token) { // (관리자·오더테이커 사용자계정 관리자료 조회)
  return measureResponse_('getAdminUserAccountRegistrationData', () => {
    const manager = requireRole_(token, ['ADMIN', 'ORDER']);
    const managerRole = String(manager.role || '').trim().toUpperCase();
    const operationalRoles = userAccountOperationalRoleSet_();
    const access = ensureAdminUserEmploymentHeader_();
    const sheet = access.sheet;
    const headerMap = access.headerMap;
    const users = [];

    if (sheet.getLastRow() >= 2) {
      const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getDisplayValues();
      rows.forEach((row, index) => {
        const user = rowToUser_(row, index + 2, headerMap);
        if (!user.employeeNo || !user.name) return;
        const employmentRaw = String(row[(headerMap[NOVA_USER_EMPLOYMENT.HEADER] || 1) - 1] || '').trim();
        const employment = parseAdminUserEmploymentType_(employmentRaw, user);
        const targetRole = String(user.role || '').trim().toUpperCase();
        const canManage = managerRole === 'ADMIN'
          || (managerRole === 'ORDER' && operationalRoles.has(targetRole) && user.employeeNo !== manager.employeeNo);
        users.push({
          employeeNo: user.employeeNo,
          name: user.name,
          job: user.job,
          employmentType: employment.storageValue,
          employmentCategory: employment.category,
          employmentVendor: employment.vendor,
          employmentInferred: employment.inferred,
          role: user.role,
          enabled: user.enabled,
          telegramEnabled: user.telegramEnabled,
          phone: user.phone,
          defaultSite: user.defaultSite,
          defaultBuildings: user.defaultBuildings,
          note: user.note,
          updatedAt: user.updatedAt,
          telegramLinked: Boolean(user.telegramId),
          telegramId: user.telegramId,
          telegramConnectionStatus: user.telegramConnectionStatus || (user.telegramId ? '연결완료' : (user.enabled ? '연결대기' : '사용중지')),
          canManage,
          canDelete: canManage && !user.enabled && user.employeeNo !== manager.employeeNo
        });
      });
    }

    users.sort((a, b) => {
      if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
      return a.name.localeCompare(b.name, 'ko') || a.employeeNo.localeCompare(b.employeeNo, 'ko', { numeric: true });
    });

    const roleCodes = getCodes_('권한');
    let roles = roleCodes.length
      ? roleCodes.map(item => ({ code: String(item.code || '').trim().toUpperCase(), label: String(item.label || item.code || '').trim() }))
      : [
          { code: 'ADMIN', label: '관리자' },
          { code: 'ORDER', label: '오더테이커' },
          { code: 'QM', label: '퀄리티매니저' },
          { code: 'HOUSEMAN', label: '하우스맨' },
          { code: 'ROOMMAID', label: '룸메이드' },
          { code: 'PUBLIC', label: '객실퍼블릭' }
        ];
    if (managerRole === 'ORDER') roles = roles.filter(item => operationalRoles.has(item.code));

    const jobs = Array.from(new Set(users.map(user => String(user.job || '').trim()).filter(Boolean)))
      .sort((a, b) => a.localeCompare(b, 'ko'));
    const vendors = Array.from(new Set(users
      .filter(user => user.employmentCategory === NOVA_USER_EMPLOYMENT.OUTSOURCE)
      .map(user => String(user.employmentVendor || '').trim()).filter(Boolean)))
      .sort((a, b) => a.localeCompare(b, 'ko'));

    return {
      ok: true,
      managerRole,
      users,
      roles,
      jobs,
      employmentCategories: [NOVA_USER_EMPLOYMENT.REGULAR, NOVA_USER_EMPLOYMENT.PART_TIME, NOVA_USER_EMPLOYMENT.OUTSOURCE],
      employmentVendors: vendors,
      sites: getSiteList_(),
      defaultSite: String(manager.defaultSite || '').trim(),
      serverTime: nowText_()
    };
  });
}

function createAdminUserAccount(token, payload) { // (관리자·오더테이커 사용자계정 신규 등록)
  return measureResponse_('createAdminUserAccount', () => {
    const manager = requireRole_(token, ['ADMIN', 'ORDER']);
    const access = ensureAdminUserEmploymentHeader_();
    const safe = normalizeAdminUserAccountPayload_(payload);
    assertUserAccountManagePermission_(manager, '', '', safe.role);
    const lock = acquireWriteLock_(5000);

    try {
      const sheet = access.sheet;
      const headerMap = getHeaderMap_(sheet);
      const lastRow = sheet.getLastRow();

      if (lastRow >= 2) {
        const employeeNoColumn = headerMap['사번'];
        if (!employeeNoColumn) throw new Error('사용자계정 시트에 사번 열이 없습니다.');
        const employeeNos = sheet.getRange(2, employeeNoColumn, lastRow - 1, 1).getDisplayValues()
          .map(row => String(row[0] || '').trim());
        if (employeeNos.includes(safe.employeeNo)) {
          throw new Error(`사번 ${safe.employeeNo}은 이미 사용자계정에 등록되어 있습니다.`);
        }
      }

      const telegram = buildNewUserTelegramFields_(safe.employeeNo, safe.enabled);
      const now = nowText_();
      const row = createRowByHeaders_(sheet, {
        '사번': safe.employeeNo,
        '이름': safe.name,
        '직무': safe.job,
        '채용구분': safe.employmentType,
        '권한': safe.role,
        '사용여부': safe.enabled,
        '텔레그램ID': '',
        '텔레그램알림': safe.telegramEnabled,
        '연락처': safe.phone,
        '기본사업장': safe.defaultSite,
        '기본담당동': safe.defaultBuildings,
        '비고': safe.note,
        '수정일시': now,
        '텔레그램연결키': telegram.key,
        '텔레그램연결링크': telegram.link,
        '텔레그램연결상태': telegram.status,
        '텔레그램연결일시': ''
      });

      const targetRow = lastRow + 1;
      ensureSheetRowCapacity_(sheet, targetRow);
      sheet.getRange(targetRow, 1, 1, row.length).setValues([row]);
      clearNovaCaches_();
      const version = bumpDataVersion_({ domains: ['CONFIG'], lockHeld: true });

      return {
        ok: true,
        version,
        user: {
          employeeNo: safe.employeeNo,
          name: safe.name,
          job: safe.job,
          employmentType: safe.employmentType,
          role: safe.role,
          enabled: safe.enabled === 'Y',
          telegramEnabled: safe.telegramEnabled === 'Y',
          phone: safe.phone,
          defaultSite: safe.defaultSite,
          defaultBuildings: safe.defaultBuildings,
          note: safe.note,
          telegramConnectionStatus: telegram.status,
          connectionLinkGenerated: Boolean(telegram.link)
        },
        message: `${safe.name}(${safe.employeeNo}) 사용자계정을 등록했습니다.${telegram.link ? ' 텔레그램 개인 연결링크도 생성했습니다.' : ''}`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function updateAdminUserAccount(token, payload) { // (관리자·오더테이커 기존 사용자계정 전체정보 수정)
  return measureResponse_('updateAdminUserAccount', () => {
    const manager = requireRole_(token, ['ADMIN', 'ORDER']);
    const access = ensureAdminUserEmploymentHeader_();
    const employeeNo = String(payload && payload.employeeNo || '').trim();
    if (!employeeNo) throw new Error('수정할 사번이 없습니다.');
    const lock = acquireWriteLock_(5000);

    try {
      const sheet = access.sheet;
      const found = findAdminUserAccountRow_(sheet, employeeNo);
      if (!found) throw new Error(`사번 ${employeeNo} 사용자계정을 찾지 못했습니다.`);
      const safe = normalizeAdminUserAccountPayload_(Object.assign({}, payload || {}, { employeeNo }));
      assertUserAccountManagePermission_(manager, found.user.role, employeeNo, safe.role);
      if (employeeNo === manager.employeeNo) {
        if (safe.enabled !== 'Y') throw new Error('현재 로그인한 본인 계정은 사용중지할 수 없습니다.');
        if (String(safe.role || '').trim().toUpperCase() !== String(manager.role || '').trim().toUpperCase()) {
          throw new Error('현재 로그인한 본인 계정의 권한은 이 화면에서 변경할 수 없습니다.');
        }
      }

      const telegram = resolveExistingUserTelegramFields_(found.data, safe.enabled);
      const updatedAt = nowText_();
      updateRowByHeaders_(sheet, found.rowNumber, {
        '이름': safe.name,
        '직무': safe.job,
        '채용구분': safe.employmentType,
        '권한': safe.role,
        '사용여부': safe.enabled,
        '텔레그램알림': safe.telegramEnabled,
        '연락처': safe.phone,
        '기본사업장': safe.defaultSite,
        '기본담당동': safe.defaultBuildings,
        '비고': safe.note,
        '수정일시': updatedAt,
        '텔레그램연결키': telegram.key,
        '텔레그램연결링크': telegram.link,
        '텔레그램연결상태': telegram.status
      });
      clearNovaCaches_();
      const version = bumpDataVersion_({ domains: ['CONFIG'], lockHeld: true });
      return {
        ok: true,
        version,
        employeeNo,
        updatedAt,
        message: `${safe.name}(${employeeNo}) 사용자계정 정보를 수정했습니다. 변경사항은 즉시 반영됩니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function setAdminUserAccountEnabled(token, payload) { // (관리자·오더테이커 사용자계정 사용·사용중지 즉시 전환)
  return measureResponse_('setAdminUserAccountEnabled', () => {
    const manager = requireRole_(token, ['ADMIN', 'ORDER']);
    const employeeNo = String(payload && payload.employeeNo || '').trim();
    const enabled = normalizeYesNo_(payload && payload.enabled || 'N');
    if (!employeeNo) throw new Error('처리할 사번이 없습니다.');
    if (employeeNo === manager.employeeNo && enabled === 'N') throw new Error('현재 로그인한 본인 계정은 사용중지할 수 없습니다.');
    const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
    const lock = acquireWriteLock_(5000);

    try {
      const found = findAdminUserAccountRow_(sheet, employeeNo);
      if (!found) throw new Error(`사번 ${employeeNo} 사용자계정을 찾지 못했습니다.`);
      assertUserAccountManagePermission_(manager, found.user.role, employeeNo, found.user.role);
      const telegram = resolveExistingUserTelegramFields_(found.data, enabled);
      const updatedAt = nowText_();
      updateRowByHeaders_(sheet, found.rowNumber, {
        '사용여부': enabled,
        '수정일시': updatedAt,
        '텔레그램연결키': telegram.key,
        '텔레그램연결링크': telegram.link,
        '텔레그램연결상태': telegram.status
      });
      clearNovaCaches_();
      const version = bumpDataVersion_({ domains: ['CONFIG'], lockHeld: true });
      return {
        ok: true,
        version,
        employeeNo,
        enabled: enabled === 'Y',
        updatedAt,
        message: enabled === 'Y'
          ? `${found.user.name}(${employeeNo}) 계정을 사용 상태로 전환했습니다.`
          : `${found.user.name}(${employeeNo}) 계정을 사용중지했습니다. 변경사항은 즉시 반영됩니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function deleteAdminUserAccount(token, payload) { // (관리자·오더테이커 이력 없는 미사용 계정 영구삭제)
  return measureResponse_('deleteAdminUserAccount', () => {
    const manager = requireRole_(token, ['ADMIN', 'ORDER']);
    const employeeNo = String(payload && payload.employeeNo || '').trim();
    if (!employeeNo) throw new Error('삭제할 사번이 없습니다.');
    if (employeeNo === manager.employeeNo) throw new Error('현재 로그인한 본인 계정은 삭제할 수 없습니다.');

    const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
    const initial = findAdminUserAccountRow_(sheet, employeeNo);
    if (!initial) throw new Error(`사번 ${employeeNo} 사용자계정을 찾지 못했습니다.`);
    assertUserAccountManagePermission_(manager, initial.user.role, employeeNo, initial.user.role);
    if (initial.user.enabled) throw new Error('사용 중인 계정은 삭제할 수 없습니다. 먼저 사용중지하세요.');

    const precheck = findUserAccountOperationalReferences_(employeeNo);
    if (precheck.current || precheck.history) {
      throw new Error('객실 배정 또는 과거 업무이력이 있는 계정은 영구삭제할 수 없습니다. 사용중지 상태로 유지하세요.');
    }

    const lock = acquireWriteLock_(5000);
    try {
      const found = findAdminUserAccountRow_(sheet, employeeNo);
      if (!found) throw new Error(`사번 ${employeeNo} 사용자계정을 찾지 못했습니다.`);
      assertUserAccountManagePermission_(manager, found.user.role, employeeNo, found.user.role);
      if (found.user.enabled) throw new Error('사용 중인 계정은 삭제할 수 없습니다. 먼저 사용중지하세요.');
      sheet.deleteRow(found.rowNumber);
      clearNovaCaches_();
      const version = bumpDataVersion_({ domains: ['CONFIG'], lockHeld: true });
      return {
        ok: true,
        version,
        employeeNo,
        message: `${found.user.name}(${employeeNo}) 미사용 계정을 삭제했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function updateAdminUserEmploymentType(token, payload) { // (관리자·오더테이커 기존 사용자 채용구분 수정)
  return measureResponse_('updateAdminUserEmploymentType', () => {
    const manager = requireRole_(token, ['ADMIN', 'ORDER']);
    const access = ensureAdminUserEmploymentHeader_();
    const safe = payload || {};
    const employeeNo = String(safe.employeeNo || '').trim();
    if (!employeeNo) throw new Error('수정할 사번이 없습니다.');
    const employment = normalizeAdminUserEmploymentInput_(safe);
    const lock = acquireWriteLock_(5000);

    try {
      const sheet = access.sheet;
      const found = findAdminUserAccountRow_(sheet, employeeNo);
      if (!found) throw new Error(`사번 ${employeeNo} 사용자계정을 찾지 못했습니다.`);
      assertUserAccountManagePermission_(manager, found.user.role, employeeNo, found.user.role);
      updateRowByHeaders_(sheet, found.rowNumber, {
        '채용구분': employment.storageValue,
        '수정일시': nowText_()
      });
      clearNovaCaches_();
      const version = bumpDataVersion_({ domains: ['CONFIG'], lockHeld: true });
      return {
        ok: true,
        version,
        employeeNo,
        employmentType: employment.storageValue,
        message: `${employeeNo} 채용구분을 ${employment.storageValue}(으)로 저장했습니다. 룸메이드 마감일지는 새 기준으로 다시 조회됩니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function userAccountOperationalRoleSet_() { // (오더테이커가 직접 관리할 수 있는 현장 직원 권한)
  return new Set(['QM', 'HOUSEMAN', 'ROOMMAID', 'PUBLIC']);
}

function assertUserAccountManagePermission_(manager, targetRole, targetEmployeeNo, nextRole) { // (사용자계정 관리자·오더테이커 권한 경계 검증)
  const managerRole = String(manager && manager.role || '').trim().toUpperCase();
  if (managerRole === 'ADMIN') return true;
  if (managerRole !== 'ORDER') throw new Error('사용자계정을 관리할 권한이 없습니다.');
  const operationalRoles = userAccountOperationalRoleSet_();
  const currentRole = String(targetRole || '').trim().toUpperCase();
  const requestedRole = String(nextRole || '').trim().toUpperCase();
  if (targetEmployeeNo && String(targetEmployeeNo) === String(manager.employeeNo || '')) {
    throw new Error('오더테이커 본인 계정은 이 화면에서 수정할 수 없습니다.');
  }
  if (currentRole && !operationalRoles.has(currentRole)) {
    throw new Error('오더테이커는 QM·하우스맨·룸메이드·객실퍼블릭 계정만 관리할 수 있습니다.');
  }
  if (requestedRole && !operationalRoles.has(requestedRole)) {
    throw new Error('오더테이커는 관리자·오더테이커 권한을 등록하거나 부여할 수 없습니다.');
  }
  return true;
}

function findAdminUserAccountRow_(sheet, employeeNo) { // (사용자계정 사번 정확일치 단건 조회)
  const safeEmployeeNo = String(employeeNo || '').trim();
  if (!safeEmployeeNo || sheet.getLastRow() < 2) return null;
  const headerMap = getHeaderMap_(sheet);
  const employeeNoColumn = headerMap['사번'];
  if (!employeeNoColumn) throw new Error('사용자계정 시트에 사번 열이 없습니다.');
  const match = sheet.getRange(2, employeeNoColumn, sheet.getLastRow() - 1, 1)
    .createTextFinder(safeEmployeeNo).matchEntireCell(true).findNext();
  if (!match) return null;
  const rowNumber = match.getRow();
  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
  return {
    rowNumber,
    row,
    data: rowObjectFromValues_(row, headerMap),
    user: rowToUser_(row, rowNumber, headerMap),
    headerMap
  };
}

function resolveExistingUserTelegramFields_(data, enabled) { // (계정 수정·재사용 시 텔레그램 연결정보 보존)
  const employeeNo = String(data && data['사번'] || '').trim();
  const telegramId = String(data && data['텔레그램ID'] || '').trim();
  let key = String(data && data['텔레그램연결키'] || '').trim();
  let link = String(data && data['텔레그램연결링크'] || '').trim();
  const useEnabled = normalizeYesNo_(enabled || data && data['사용여부'] || 'N');
  if (useEnabled === 'Y' && !telegramId && !link) {
    const generated = buildNewUserTelegramFields_(employeeNo, 'Y');
    key = generated.key || key;
    link = generated.link || link;
  }
  const status = useEnabled !== 'Y'
    ? '사용중지'
    : telegramId
      ? '연결완료'
      : link
        ? '연결대기'
        : '초기설정필요';
  return { key, link, status };
}

function findUserAccountOperationalReferences_(employeeNo) { // (영구삭제 전 객실배정·업무이력 참조 확인)
  const safeEmployeeNo = String(employeeNo || '').trim();
  if (!safeEmployeeNo) return { current: false, history: false };
  const current = userAccountSheetHasExactReference_(NOVA.SHEETS.CURRENT, safeEmployeeNo, ['룸메이드사번', '보조룸메이드사번', 'QM사번']);
  const historyExact = userAccountSheetHasExactReference_(NOVA.SHEETS.HISTORY, safeEmployeeNo, ['대상사번', '등록사번', '배정사번', '처리자사번']);
  const historyJson = userAccountSheetHasJsonReference_(NOVA.SHEETS.HISTORY, safeEmployeeNo, '세부내용JSON');
  return { current, history: historyExact || historyJson };
}

function userAccountSheetHasExactReference_(sheetName, employeeNo, headers) { // (사번 참조열 정확일치 검색)
  const sheet = getRequiredSheet_(sheetName);
  if (sheet.getLastRow() < 2) return false;
  const headerMap = getHeaderMap_(sheet);
  return (headers || []).some(header => {
    const column = headerMap[header];
    if (!column) return false;
    return Boolean(sheet.getRange(2, column, sheet.getLastRow() - 1, 1)
      .createTextFinder(employeeNo).matchEntireCell(true).findNext());
  });
}

function userAccountSheetHasJsonReference_(sheetName, employeeNo, header) { // (세부JSON 내부 사번 문자열 참조 검색)
  const sheet = getRequiredSheet_(sheetName);
  if (sheet.getLastRow() < 2) return false;
  const headerMap = getHeaderMap_(sheet);
  const column = headerMap[header];
  if (!column) return false;
  const needle = JSON.stringify(String(employeeNo || ''));
  return Boolean(sheet.getRange(2, column, sheet.getLastRow() - 1, 1)
    .createTextFinder(needle).matchCase(true).findNext());
}

function normalizeAdminUserAccountPayload_(payload) { // (사용자계정 신규·수정값 검증)
  const safe = payload || {};
  const employeeNo = String(safe.employeeNo || '').trim();
  const name = String(safe.name || '').trim();
  const job = String(safe.job || '').trim();
  const employment = normalizeAdminUserEmploymentInput_(safe);
  const requestedRole = String(safe.role || '').trim().toUpperCase();
  const role = requestedRole || defaultAdminUserRoleForJob_(job);
  const enabled = normalizeYesNo_(safe.enabled || 'Y');
  const telegramEnabled = normalizeYesNo_(safe.telegramEnabled || 'Y');
  const phone = String(safe.phone || '').trim();
  const defaultSite = String(safe.defaultSite || '').trim();
  const defaultBuildings = normalizeAdminUserBuildings_(safe.defaultBuildings);
  const note = String(safe.note || '').trim();

  if (!employeeNo) throw new Error('사번을 입력하세요.');
  if (employeeNo.length > 40 || /\s/.test(employeeNo)) throw new Error('사번은 공백 없이 40자 이내로 입력하세요.');
  if (!name) throw new Error('이름을 입력하세요.');
  if (name.length > 40) throw new Error('이름은 40자 이내로 입력하세요.');
  if (!job) throw new Error('직무를 입력하세요.');
  if (job.length > 40) throw new Error('직무는 40자 이내로 입력하세요.');
  if (phone.length > 30) throw new Error('연락처는 30자 이내로 입력하세요.');
  if (note.length > 200) throw new Error('비고는 200자 이내로 입력하세요.');

  const configuredRoles = getCodes_('권한').map(item => String(item.code || '').trim().toUpperCase()).filter(Boolean);
  const fallbackRoles = ['ADMIN', 'ORDER', 'QM', 'HOUSEMAN', 'ROOMMAID', 'PUBLIC'];
  const allowedRoles = configuredRoles.length ? configuredRoles : fallbackRoles;
  if (!allowedRoles.includes(role)) throw new Error('사용할 수 없는 권한입니다.');

  return {
    employeeNo,
    name,
    job,
    employmentType: employment.storageValue,
    role,
    enabled,
    telegramEnabled,
    phone,
    defaultSite,
    defaultBuildings,
    note
  };
}

function ensureAdminUserEmploymentHeader_() { // (사용자계정 채용구분 열 보장)
  let sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  let headerMap = getHeaderMap_(sheet);
  if (headerMap[NOVA_USER_EMPLOYMENT.HEADER]) return { sheet, headerMap };

  const lock = acquireWriteLock_(5000);
  try {
    sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
    headerMap = getHeaderMap_(sheet);
    if (!headerMap[NOVA_USER_EMPLOYMENT.HEADER]) {
      const targetColumn = Math.max(sheet.getLastColumn(), 1) + 1;
      sheet.getRange(1, targetColumn).setValue(NOVA_USER_EMPLOYMENT.HEADER)
        .setFontWeight('bold').setHorizontalAlignment('center').setBackground('#f3f4f6');
      if (typeof NOVA_RUNTIME_CACHE_ !== 'undefined') NOVA_RUNTIME_CACHE_.headerMaps = {};
      clearNovaCaches_();
      sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
      headerMap = getHeaderMap_(sheet);
    }
    return { sheet, headerMap };
  } finally {
    lock.releaseLock();
  }
}

function normalizeAdminUserEmploymentInput_(payload) { // (채용구분 입력값 정리)
  const safe = payload || {};
  const direct = String(safe.employmentType || '').trim();
  if (direct) {
    const parsed = parseAdminUserEmploymentType_(direct, null, false);
    if (parsed.category === NOVA_USER_EMPLOYMENT.OUTSOURCE && !parsed.vendor) throw new Error('외주업체명을 입력하세요.');
    return parsed;
  }
  const category = String(safe.employmentCategory || NOVA_USER_EMPLOYMENT.REGULAR).trim();
  const vendor = String(safe.employmentVendor || '').trim();
  if (![NOVA_USER_EMPLOYMENT.REGULAR, NOVA_USER_EMPLOYMENT.PART_TIME, NOVA_USER_EMPLOYMENT.OUTSOURCE].includes(category)) {
    throw new Error('사용할 수 없는 채용구분입니다.');
  }
  if (category === NOVA_USER_EMPLOYMENT.OUTSOURCE) {
    if (!vendor) throw new Error('외주업체명을 입력하세요.');
    if (vendor.length > 40) throw new Error('외주업체명은 40자 이내로 입력하세요.');
    return { category, vendor, storageValue: `${NOVA_USER_EMPLOYMENT.OUTSOURCE}: ${vendor}`, inferred: false };
  }
  return { category, vendor: '', storageValue: category, inferred: false };
}

function parseAdminUserEmploymentType_(value, user, allowInference) { // (저장 채용구분 해석·기존자료 보조판정)
  const raw = String(value || '').trim();
  if (raw === NOVA_USER_EMPLOYMENT.REGULAR) return { category: NOVA_USER_EMPLOYMENT.REGULAR, vendor: '', storageValue: NOVA_USER_EMPLOYMENT.REGULAR, inferred: false };
  if (raw === NOVA_USER_EMPLOYMENT.PART_TIME) return { category: NOVA_USER_EMPLOYMENT.PART_TIME, vendor: '', storageValue: NOVA_USER_EMPLOYMENT.PART_TIME, inferred: false };
  const outsourceMatch = raw.match(/^외주업체\s*[:：\-]?\s*(.*)$/i);
  if (outsourceMatch) {
    const vendor = String(outsourceMatch[1] || '').trim();
    return { category: NOVA_USER_EMPLOYMENT.OUTSOURCE, vendor, storageValue: vendor ? `${NOVA_USER_EMPLOYMENT.OUTSOURCE}: ${vendor}` : NOVA_USER_EMPLOYMENT.OUTSOURCE, inferred: false };
  }

  if (allowInference !== false) {
    const text = [user && user.name, user && user.job, user && user.note].map(item => String(item || '').trim()).join(' ').toLowerCase();
    if (text.includes('아르바이트') || text.includes('알바')) {
      return { category: NOVA_USER_EMPLOYMENT.PART_TIME, vendor: '', storageValue: NOVA_USER_EMPLOYMENT.PART_TIME, inferred: true };
    }
    if (text.includes('하이브넷')) return { category: NOVA_USER_EMPLOYMENT.OUTSOURCE, vendor: '하이브넷', storageValue: '외주업체: 하이브넷', inferred: true };
    if (text.includes('금광')) return { category: NOVA_USER_EMPLOYMENT.OUTSOURCE, vendor: '금광', storageValue: '외주업체: 금광', inferred: true };
  }
  return { category: NOVA_USER_EMPLOYMENT.REGULAR, vendor: '', storageValue: NOVA_USER_EMPLOYMENT.REGULAR, inferred: !raw };
}

function defaultAdminUserRoleForJob_(job) { // (직무명 기준 기본 권한 보조)
  const text = String(job || '').trim().toUpperCase();
  if (text.includes('관리자') || text.includes('ADMIN')) return 'ADMIN';
  if (text.includes('오더') || text.includes('ORDER')) return 'ORDER';
  if (text === 'QM' || text.includes('퀄리티')) return 'QM';
  if (text.includes('하우스맨') || text.includes('HOUSEMAN')) return 'HOUSEMAN';
  if (text.includes('룸메이드') || text.includes('ROOMMAID')) return 'ROOMMAID';
  if (text.includes('퍼블릭') || text.includes('PUBLIC')) return 'PUBLIC';
  return '';
}

function normalizeAdminUserBuildings_(value) { // (기본담당동 표기 정리)
  const tokens = String(value || '').split(/[,;|/\s]+/).map(item => item.trim()).filter(Boolean);
  const normalized = [];
  tokens.forEach(token => {
    const match = token.match(/^0?([1-9])(?:동)?$/);
    const text = match ? `${Number(match[1])}동` : token;
    if (!normalized.includes(text)) normalized.push(text);
  });
  return normalized.join(',');
}

function buildNewUserTelegramFields_(employeeNo, enabled) { // (신규 사용자 텔레그램 연결정보 준비)
  let key = '';
  let link = '';
  let status = enabled === 'Y' ? '연결대기' : '사용중지';

  try {
    if (typeof createTelegramConnectionKey_ === 'function') key = createTelegramConnectionKey_();
    if (enabled === 'Y'
      && key
      && typeof getTelegramBotUsername_ === 'function'
      && typeof buildTelegramConnectionLink_ === 'function') {
      const username = getTelegramBotUsername_();
      if (username) link = buildTelegramConnectionLink_(username, employeeNo, key);
    }
  } catch (error) {
    status = enabled === 'Y' ? '초기설정필요' : '사용중지';
  }

  if (enabled !== 'Y') status = '사용중지';
  else if (!link) status = '초기설정필요';

  return { key, link, status };
}
