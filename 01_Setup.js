function applyNovaSpecialDepartureExpansion() { // (퇴실 R/C·퇴실 H/U·객실카드 마지막 상태 적용)
  const result = seedSpecialDepartureStatusCodes_();
  const header = ensureIndicatorLastRoomStatusHeader_();
  const cycleHeaders = ensureIndicatorPreviousCycleHeaders_();
  const operationFlagHeaders = ensureRoomOperationalFlagHeaders_();
  const backfill = backfillIndicatorLastRoomStatusForDate_(businessDateText_(), '');
  const cycleBackfill = backfillIndicatorPreviousCyclesForDate_(businessDateText_(), '');
  clearNovaCaches_();
  bumpDataVersion_({ domains: ['CONFIG', 'ROOM'], businessDate: businessDateText_(), site: '' });
  return {
    ok: true,
    added: Number(result && result.added || 0),
    total: Number(result && result.total || 2),
    headerAdded: Boolean(header && header.added),
    cycleHeadersAdded: Number(cycleHeaders && cycleHeaders.added || 0),
    operationFlagHeadersAdded: Number(operationFlagHeaders && operationFlagHeaders.added || 0),
    backfilled: Number(backfill && backfill.updated || 0),
    previousCyclesBackfilled: Number(cycleBackfill && cycleBackfill.updated || 0),
    message: '퇴실R/C·퇴실H/U와 객실카드 마지막 재고·퇴실 상태 표시를 적용했습니다.'
  };
}

function applyNovaIndicatorLastRoomStatusExpansion() { // (객실카드 마지막 상태 표시만 재적용)
  return applyNovaSpecialDepartureExpansion();
}

function applyNovaIndicatorTwoCycleExpansion() { // (객실카드 당일 2개 정비주기 표시 적용)
  return applyNovaSpecialDepartureExpansion();
}

function ensureIndicatorLastRoomStatusHeader_() { // (현재객실현황 마지막객실상태 열을 맨 뒤에 안전하게 추가)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  let headerMap = getHeaderMap_(sheet);
  const header = indicatorLastRoomStatusHeader_();
  if (headerMap[header]) return { added: false, column: headerMap[header] };

  const targetColumn = Math.max(sheet.getLastColumn(), 1) + 1;
  sheet.getRange(1, targetColumn).setValue(header)
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setBackground('#f3f4f6');
  sheet.setColumnWidth(targetColumn, 120);
  if (typeof NOVA_RUNTIME_CACHE_ !== 'undefined') NOVA_RUNTIME_CACHE_.headerMaps = {};
  headerMap = getHeaderMap_(sheet);
  return { added: true, column: headerMap[header] || targetColumn };
}


function ensureIndicatorPreviousCycleHeaders_() { // (객실카드 이전 정비주기 표시 열 보장)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  let headerMap = getHeaderMap_(sheet);
  const headers = indicatorPreviousCycleHeaders_();
  let added = 0;
  headers.forEach(header => {
    if (headerMap[header]) return;
    const targetColumn = Math.max(sheet.getLastColumn(), 1) + 1;
    sheet.getRange(1, targetColumn).setValue(header)
      .setFontWeight('bold').setHorizontalAlignment('center').setBackground('#f3f4f6');
    sheet.setColumnWidth(targetColumn, 125);
    added += 1;
    if (typeof NOVA_RUNTIME_CACHE_ !== 'undefined') NOVA_RUNTIME_CACHE_.headerMaps = {};
    headerMap = getHeaderMap_(sheet);
  });
  return { added, headers };
}

function backfillIndicatorLastRoomStatusForDate_(businessDate, site) { // (선택 업무일자의 기존 공실카드 표시기준 일괄 보완)
  const date = normalizeBusinessDate_(businessDate);
  const normalizedSite = String(site || '').trim();
  const headerInfo = ensureIndicatorLastRoomStatusHeader_();
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const selection = getCurrentRowsForSelection_(date, normalizedSite);
  if (!selection.items.length) return { updated: 0, total: 0, businessDate: date, site: normalizedSite };

  const latestByRoom = {};
  const putLatest = (rowSite, roomNo, status, eventAt, version) => {
    const safeSite = String(rowSite || '').trim();
    const safeRoomNo = String(roomNo || '').trim();
    if (!safeRoomNo) return;
    const normalizedStatus = String(status || '').trim().toUpperCase();
    const displayStatus = isNovaRoomCleaningTargetStatus_(normalizedStatus) ? normalizedStatus : '';
    const stamp = `${String(eventAt || '').trim()}|${String(Number(version || 0)).padStart(12, '0')}`;
    const key = `${safeSite}|${safeRoomNo}`;
    if (!latestByRoom[key] || stamp >= latestByRoom[key].stamp) latestByRoom[key] = { status: displayStatus, stamp };
  };

  const historyRows = readHistoryRowsForClose_(date, normalizedSite);
  historyRows.forEach(data => {
    const type = String(data['기록구분'] || '').trim();
    const rowSite = String(data['사업장'] || '').trim();
    const roomNo = String(data['객실번호'] || '').trim();
    const eventAt = String(data['완료일시'] || data['수정일시'] || data['등록일시'] || '').trim();
    const version = Number(data['변경버전'] || 0);
    let detail = {};
    try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }

    if (type === NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD) {
      const roomsByStatus = detail.roomsByStatus && typeof detail.roomsByStatus === 'object' ? detail.roomsByStatus : {};
      Object.keys(roomsByStatus).forEach(status => {
        (Array.isArray(roomsByStatus[status]) ? roomsByStatus[status] : []).forEach(uploadedRoomNo => {
          putLatest(rowSite, uploadedRoomNo, status, eventAt, version);
        });
      });
      return;
    }

    if (type === NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE) {
      putLatest(rowSite, roomNo, detail.roomStatus || '', eventAt, version);
      return;
    }

    const sourceStatus = detail.sourceRoomStatus || detail.previousRoomStatus || '';
    if (sourceStatus) putLatest(rowSite, roomNo, sourceStatus, eventAt, version);
  });

  const rows = selection.items.slice().sort((a, b) => a.rowNumber - b.rowNumber).map(item => {
    const currentStatus = String(item.data['객실상태'] || '').trim().toUpperCase();
    const existingStatus = String(item.data[indicatorLastRoomStatusHeader_()] || '').trim().toUpperCase();
    const key = `${String(item.data['사업장'] || '').trim()}|${String(item.data['객실번호'] || '').trim()}`;
    let displayStatus = '';
    if (isNovaRoomCleaningTargetStatus_(currentStatus)) displayStatus = currentStatus;
    else if (currentStatus === 'VACANT_CLEAN') {
      const latest = latestByRoom[key] && latestByRoom[key].status || '';
      displayStatus = isNovaRoomCleaningTargetStatus_(latest)
        ? latest
        : (isNovaRoomCleaningTargetStatus_(existingStatus) ? existingStatus : '');
    }
    return { rowNumber: item.rowNumber, value: displayStatus, changed: displayStatus !== existingStatus };
  });

  const groups = [];
  rows.forEach(item => {
    const last = groups[groups.length - 1];
    if (last && last.startRow + last.values.length === item.rowNumber) {
      last.values.push([item.value]);
      last.changed += item.changed ? 1 : 0;
    } else {
      groups.push({ startRow: item.rowNumber, values: [[item.value]], changed: item.changed ? 1 : 0 });
    }
  });
  groups.forEach(group => {
    sheet.getRange(group.startRow, headerInfo.column, group.values.length, 1).setValues(group.values);
  });
  SpreadsheetApp.flush();
  return {
    updated: groups.reduce((sum, group) => sum + group.changed, 0),
    total: rows.length,
    businessDate: date,
    site: normalizedSite
  };
}

function backfillIndicatorPreviousCyclesForDate_(businessDate, site) { // (기존 당일 중복 정비의 이전 주기 1건 보완)
  const date = normalizeBusinessDate_(businessDate);
  const normalizedSite = String(site || '').trim();
  ensureIndicatorPreviousCycleHeaders_();
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const selection = getCurrentRowsForSelection_(date, normalizedSite);
  if (!selection.items.length) return { updated: 0, total: 0 };
  const completionsByRoom = {};
  readHistoryRowsForClose_(date, normalizedSite).forEach(data => {
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.CLEANING) return;
    const status = String(data['처리상태'] || '').trim().toUpperCase();
    if (!['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(status)) return;
    let detail = {};
    try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    const rowSite = String(data['사업장'] || '').trim();
    const roomNo = String(data['객실번호'] || '').trim();
    if (!roomNo) return;
    const roomStatus = String(detail.sourceRoomStatus || detail.previousRoomStatus || detail.roomStatus || '').trim().toUpperCase();
    if (!isNovaRoomCleaningTargetStatus_(roomStatus)) return;
    const key = `${rowSite}|${roomNo}`;
    if (!completionsByRoom[key]) completionsByRoom[key] = [];
    completionsByRoom[key].push({
      roomStatus,
      cleaningStatus: 'COMPLETED',
      primaryEmployeeNo: String(detail.primaryEmployeeNo || data['대상사번'] || '').trim(),
      secondaryEmployeeNo: String(detail.secondaryEmployeeNo || '').trim(),
      at: String(data['완료일시'] || data['수정일시'] || data['등록일시'] || '').trim(),
      version: Number(data['변경버전'] || 0)
    });
  });
  Object.keys(completionsByRoom).forEach(key => completionsByRoom[key].sort((a, b) => a.at.localeCompare(b.at) || a.version - b.version));
  const headerMap = getHeaderMap_(sheet);
  const writes = [];
  selection.items.forEach(item => {
    const data = item.data;
    if (String(data['이전객실상태'] || '').trim()) return;
    const key = `${String(data['사업장'] || '').trim()}|${String(data['객실번호'] || '').trim()}`;
    const completions = completionsByRoom[key] || [];
    if (!completions.length) return;
    const currentCompleted = isCleaningCompletedStatus_(data['청소상태']);
    const candidate = currentCompleted ? completions[completions.length - 2] : completions[completions.length - 1];
    if (!candidate) return;
    writes.push({ rowNumber: item.rowNumber, candidate });
  });
  writes.forEach(item => updateRowByHeaders_(sheet, item.rowNumber, {
    '이전객실상태': item.candidate.roomStatus,
    '이전청소상태': item.candidate.cleaningStatus,
    '이전룸메이드사번': item.candidate.primaryEmployeeNo,
    '이전보조룸메이드사번': item.candidate.secondaryEmployeeNo
  }));
  if (writes.length) SpreadsheetApp.flush();
  return { updated: writes.length, total: selection.items.length, businessDate: date, site: normalizedSite };
}

function seedSpecialDepartureStatusCodes_() { // (퇴실 R/C·퇴실 H/U 코드 보완)
  const sheet = getSpreadsheet_().getSheetByName(NOVA.SHEETS.CODES);
  const rows = sheet.getLastRow() > 1
    ? sheet.getRange(2, 1, sheet.getLastRow() - 1, NOVA.CODE_HEADERS.length).getDisplayValues()
    : [];
  const existingKeys = new Set(rows.map(row => `${String(row[0] || '').trim()}|${String(row[1] || '').trim()}`));
  const seeds = [
    ['객실상태', 'CHECKED_OUT_RC', '퇴실R/C', 71, 'Y', 'R/C 퇴실 정비대상'],
    ['객실상태', 'CHECKED_OUT_HU', '퇴실H/U', 72, 'Y', 'H/U 퇴실 정비대상']
  ];
  const missing = seeds.filter(row => !existingKeys.has(`${row[0]}|${row[1]}`));
  if (missing.length) {
    const startRow = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, startRow + missing.length - 1);
    sheet.getRange(startRow, 1, missing.length, NOVA.CODE_HEADERS.length).setValues(missing);
  }
  return { added: missing.length, total: seeds.length };
}

function applyNovaRoommaidCleaningTypeExpansion() { // (룸메이드 정비유형 4종 추가만 적용)
  const result = seedCleaningTypeCodes_();
  clearNovaCaches_();
  return {
    ok: true,
    added: Number(result && result.added || 0),
    total: Number(result && result.total || 6),
    message: '정비유형 5S·평가원·직원숙소·딥크리닝 코드를 추가하고 캐시를 갱신했습니다.'
  };
}

function upgradeNovaV10RC641() { // (첨부 이미지형 룸메이드 마감일지 양식 적용)
  const result = upgradeNovaV10RC64();
  clearNovaCaches_();
  return Object.assign({}, result, {
    ok: true,
    version: '1.0.0-RC6.4.1',
    message: '룸메이드 마감일지의 정비현황·개인별 정비현황 화면과 Excel 양식을 첨부 이미지 구조로 변경했습니다.'
  });
}

function upgradeNovaV10RC64() { // (룸메이드 마감일지·타입별 정비현황 적용)
  const result = upgradeNovaV10RC631();
  clearNovaCaches_();
  return Object.assign({}, result, {
    ok: true,
    version: '1.0.0-RC6.4',
    message: '오더테이커·관리자 전용 룸메이드 마감일지와 동·정비타입·개인별 정비현황 구성이 완료되었습니다.'
  });
}

function upgradeNovaV10RC631() { // (운영 성과지표 조회 오류·필터 간격 수정)
  const result = upgradeNovaV10RC63();
  clearNovaCaches_();
  return Object.assign({}, result, {
    ok: true,
    version: '1.0.0-RC6.3.1',
    message: '운영 성과지표 조회 호출과 일별·월별 필터 배치 수정이 완료되었습니다.'
  });
}

function upgradeNovaV10RC63() { // (관리자 전용 운영성과지표 적용)
  const result = upgradeNovaV10RC62();
  clearNovaCaches_();
  return Object.assign({}, result, {
    ok: true,
    version: '1.0.0-RC6.3',
    message: '관리자 전용 하우스맨·룸메이드 운영성과지표 구성이 완료되었습니다.'
  });
}

/**
 * 최초 1회 실행 및 Sprint 3.4 업그레이드
 */
function setupNova() { // (NOVA 초기 구성)
  return setupNovaLite();
}

function setupNovaLite() { // (NOVA 초기 구성)
  return upgradeNovaV10RC641();
}





function upgradeNovaV10RC62() { // (NOVA v1.0 RC6.2 동시사용 안정화 적용)
  const result = upgradeNovaV10RC61();
  const properties = PropertiesService.getScriptProperties();
  if (!properties.getProperty(buildSyncVersionKey_('SYSTEM', '', ''))) {
    const version = getDataVersion_();
    properties.setProperty(buildSyncVersionKey_('SYSTEM', '', ''), String(version));
  }
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA v1.0 RC6.2 동기화 분산·업무영역별 버전·동시수정 충돌 방지 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    stabilization: ['동기화 지터·백그라운드 중지', '직무·사업장별 변경버전', '조회 자동 재시도', '객실 저장 버전 충돌 방지', '짧은 저장 잠금'],
    sheets: result.sheets
  };
}

function upgradeNovaV10RC61() { // (NOVA v1.0 RC6.1 최초 일괄배정 미배정·동층 필터 적용)
  const result = upgradeNovaV10RC6();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA v1.0 RC6.1 최초 일괄배정 미배정 객실 전용 표시와 동·층 선택 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaV10RC6() { // (NOVA v1.0 RC6 로딩·조회 성능 최적화 적용)
  const result = upgradeNovaV10RC5();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA v1.0 RC6 로그인 통신·시트 접근·객실현황·업무이력 조회 최적화 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    optimization: ['로그인·초기화 1회 통신', '시트·헤더 실행 캐시', '현재객실현황 행 인덱스 캐시', '월·일 업무이력 행 인덱스 캐시', '연속열 일괄 기록'],
    sheets: result.sheets
  };
}

function upgradeNovaV10RC5() { // (NOVA v1.0 RC5 룸메이드 개인별 정비실적 적용)
  const result = upgradeNovaV10RC4();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA v1.0 RC5 룸메이드 개인별 일별·월별 정비실적 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaV10RC4() { // (NOVA v1.0 RC4 하우스맨 즉시알림·3분 미접수 재알림 적용)
  const result = upgradeNovaV10RC3();
  ensureTelegramQueueTrigger_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA v1.0 RC4 하우스맨 신규 오더 즉시알림과 3분 미접수 재알림 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    reminderMinutes: NOVA.HOUSEMAN_TELEGRAM_REMINDER_MINUTES,
    sheets: result.sheets
  };
}

function upgradeNovaV10RC3() { // (NOVA v1.0 RC3 장소별 실시간 QM 점검·사진·품질실적 적용)
  const result = upgradeNovaV10RC2();
  const places = seedQmChecklistPlaces_();
  const items = seedQmChecklistCodes_();
  const migrated = migrateQmChecklistLocations_();
  clearNovaCaches_();
  return {
    ok: true,
    message: `NOVA v1.0 RC3 QM 실시간 점검 구성이 완료되었습니다. 장소 ${places.added}개, 항목 ${items.added}개를 보완하고 기존 항목 ${migrated}개를 장소별로 정리했습니다.`,
    version: NOVA.VERSION,
    placesAdded: places.added,
    checklistItemsAdded: items.added,
    checklistItemsMigrated: migrated,
    sheets: result.sheets
  };
}

function upgradeNovaV10RC2() { // (NOVA v1.0 RC2 QM 체크리스트 적용)
  const result = upgradeNovaLiteSprint93();
  const seeded = seedQmChecklistCodes_();
  clearNovaCaches_();
  return {
    ok: true,
    message: `NOVA v1.0 RC2 QM 체크리스트 구성이 완료되었습니다. 기본 항목 ${seeded.added}개를 등록했습니다.`,
    version: NOVA.VERSION,
    checklistItemsAdded: seeded.added,
    sheets: result.sheets
  };
}




function upgradeNovaLiteSprint93() { // (Sprint 9.3 관리자 설정·자동 마감 적용)
  const result = upgradeNovaLiteSprint92();
  seedAdminSettingsCodes_();
  recreateDepartureDelayTrigger_();
  ensureAutomaticDailyCloseTrigger_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 9.3 관리자 설정 및 자동 마감 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint92() { // (Sprint 9.2 일일 마감통계·스냅샷 적용)
  const result = upgradeNovaLiteSprint912();
  configureMonthlyViewV3_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 9.2 일일 마감통계 및 마감 스냅샷 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}


function upgradeNovaLiteSprint912() { // (Sprint 9.1.2 하우스맨 담당동·자동배정 적용)
  const result = upgradeNovaLiteSprint91();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 9.1.2 하우스맨 담당동 및 자동 오더배정 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}


function upgradeNovaLiteSprint91() { // (Sprint 9.1 월별·일별 통합조회 적용)
  const result = upgradeNovaLiteSprint85();
  configureMonthlyViewV3_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 9.1 월별·일별 통합조회 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}



function upgradeNovaLiteSprint85() { // (Sprint 8.5 객실번호 기준 동·층 필터 정합 적용)
  const result = upgradeNovaLiteSprint84();
  const repaired = repairRoomBuildingValues_();
  if (repaired.total > 0) bumpDataVersion_({ domains: ['ROOM'] });
  clearNovaCaches_();
  return {
    ok: true,
    message: `NOVA Sprint 8.5 동·층 정합 구성이 완료되었습니다. 객실마스터 ${repaired.roomMaster}건, 현재객실현황 ${repaired.currentRooms}건을 바로잡았습니다.`,
    version: NOVA.VERSION,
    repairedBuildings: repaired,
    sheets: result.sheets
  };
}


function upgradeNovaLiteSprint84() { // (Sprint 8.4 객실퍼블릭 1~9동 자동보완 적용)
  const result = upgradeNovaLiteSprint83();
  const repaired = repairRoomBuildingValues_();
  if (repaired.total > 0) bumpDataVersion_({ domains: ['ROOM'] });
  clearNovaCaches_();
  return {
    ok: true,
    message: `NOVA Sprint 8.4 동 정보 구성이 완료되었습니다. 객실마스터 ${repaired.roomMaster}건, 현재객실현황 ${repaired.currentRooms}건을 보완했습니다.`,
    version: NOVA.VERSION,
    repairedBuildings: repaired,
    sheets: result.sheets
  };
}


function upgradeNovaLiteSprint83() { // (Sprint 8.3 재입실 청소상태 강제정합 적용)
  const result = upgradeNovaLiteSprint82();
  const repairedRooms = repairRecheckinCleaningStatus_();
  clearNovaCaches_();
  return {
    ok: true,
    message: `NOVA Sprint 8.3 재입실 청소상태 구성이 완료되었습니다. 기존 오류 ${repairedRooms}실을 복구했습니다.`,
    version: NOVA.VERSION,
    repairedRooms,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint82() { // (Sprint 8.2 객실·청소상태 자동전환 적용)
  const result = upgradeNovaLiteSprint8();
  updateVacantRoomStatusLabel_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 8.2 객실·청소상태 자동전환 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint8() { // (Sprint 8 퇴실지연 자동알림 적용)
  const result = upgradeNovaLiteSprint71();
  ensureDepartureDelayTrigger_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 8 퇴실지연 자동알림 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint71() { // (Sprint 7.1 룸메이드 일괄·2인1조 배정 적용)
  const result = upgradeNovaLiteSprint7();
  ensureSheet_(getSpreadsheet_(), NOVA.SHEETS.CURRENT, NOVA.CURRENT_HEADERS);
  seedRoommaidAssignmentTypeCodes_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 7.1 룸메이드 일괄·2인1조 배정 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint7() { // (Sprint 7 A·B·C 근무조·인수인계 적용)
  const result = upgradeNovaLiteSprint61();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 7 근무조 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint61() { // (Sprint 6.1 사번 기준 텔레그램 자동 연결 적용)
  const result = upgradeNovaLiteSprint6();
  ensureSheet_(getSpreadsheet_(), NOVA.SHEETS.USERS, NOVA.USER_HEADERS);
  configureTelegramUserAccountColumns_();
  ensureTelegramAccountEditTrigger_();
  try {
    const props = PropertiesService.getScriptProperties();
    if (props.getProperty('TELEGRAM_BOT_TOKEN') && props.getProperty('TELEGRAM_BOT_USERNAME')) {
      refreshAllTelegramConnectionLinks_({ regenerateKeys: false, onlyMissing: true });
    }
  } catch (error) {
    console.warn(`Telegram link refresh skipped: ${error.message}`);
  }
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 6.1 텔레그램 자동 연결 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint6() { // (Sprint 6 D/S 배정·텔레그램 통합 적용)
  const result = upgradeNovaLiteSprint5();
  seedCleaningTypeCodes_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 6 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint5() { // (Sprint 5 월별 이력조회·집계 적용)
  const result = upgradeNovaLiteSprint4();
  configureMonthlyViewV2_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 5 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint4() { // (Sprint 4 직원 스마트폰 전용 화면 적용)
  const result = upgradeNovaLiteSprint36();
  seedMobileCodes_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 4 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}
function upgradeNovaLiteSprint36() { // (Sprint 3.6 인디케이터 대량 객실 조회 성능 개선)
  const result = upgradeNovaLiteSprint34();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 3.6 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint34() { // (Sprint 3.4 객실상태 정상 중첩 처리 적용)
  const result = upgradeNovaLiteSprint32();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 3.4 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint32() { // (Sprint 3.2 XLSX 직접 분석 수정 적용)
  const result = upgradeNovaLiteSprint31();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 3.2 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint31() { // (Sprint 3.1 Drive 변환 수정 적용)
  const result = upgradeNovaLiteSprint3();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 3.1 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint3() { // (Sprint 3 구조 업그레이드)
  const result = upgradeNovaLiteSprint2();
  seedUploadCodes_();
  clearNovaCaches_();
  return {
    ok: true,
    message: 'NOVA Sprint 3 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: result.sheets
  };
}

function upgradeNovaLiteSprint2() { // (Sprint 2 구조 업그레이드)
  const ss = getSpreadsheet_();
  const definitions = [
    [NOVA.SHEETS.USERS, NOVA.USER_HEADERS],
    [NOVA.SHEETS.ROOMS, NOVA.ROOM_HEADERS],
    [NOVA.SHEETS.CURRENT, NOVA.CURRENT_HEADERS],
    [NOVA.SHEETS.HISTORY, NOVA.HISTORY_HEADERS],
    [NOVA.SHEETS.CODES, NOVA.CODE_HEADERS],
    [NOVA.SHEETS.MONTHLY, NOVA.MONTHLY_HEADERS]
  ];

  definitions.forEach(([name, headers]) => ensureSheet_(ss, name, headers));
  seedCodes_();
  configureMonthlyView_();
  formatCoreSheets_();
  clearNovaCaches_();
  ensureTelegramQueueTrigger_();

  return {
    ok: true,
    message: 'NOVA Sprint 2 구성이 완료되었습니다.',
    version: NOVA.VERSION,
    sheets: definitions.map(([name]) => name)
  };
}

function ensureSheet_(ss, name, headers) { // (시트 생성 및 헤더 확장)
  let sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);

  const currentLastColumn = Math.max(sheet.getLastColumn(), 1);
  const currentHeaders = sheet.getRange(1, 1, 1, currentLastColumn).getDisplayValues()[0];
  const existing = {};
  currentHeaders.forEach((header, index) => {
    const key = String(header || '').trim();
    if (key) existing[key] = index + 1;
  });

  let nextColumn = currentLastColumn + 1;
  headers.forEach((header, index) => {
    if (!existing[header]) {
      const targetColumn = currentHeaders.every(value => !String(value || '').trim()) && index === 0 ? 1 : nextColumn++;
      sheet.getRange(1, targetColumn).setValue(header);
      existing[header] = targetColumn;
    }
  });

  // 신규 시트 또는 빈 헤더는 정의 순서대로 배치합니다.
  if (sheet.getLastRow() <= 1 && currentHeaders.every(value => !String(value || '').trim())) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }

  sheet.setFrozenRows(1);
  const lastColumn = Math.max(sheet.getLastColumn(), headers.length);
  sheet.getRange(1, 1, 1, lastColumn)
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setBackground('#f3f4f6');
  return sheet;
}

function updateVacantRoomStatusLabel_() { // (공실·청소상태 표시 분리)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CODES);
  const headerMap = getHeaderMap_(sheet);
  const groupColumn = headerMap['코드그룹'];
  const codeColumn = headerMap['코드'];
  const labelColumn = headerMap['표시명'];
  const memoColumn = headerMap['비고'];
  if (!groupColumn || !codeColumn || !labelColumn) return;

  const rowCount = Math.max(0, sheet.getLastRow() - 1);
  if (!rowCount) return;
  const values = sheet.getRange(2, 1, rowCount, sheet.getLastColumn()).getValues();
  const index = values.findIndex(row =>
    String(row[groupColumn - 1] || '').trim() === '객실상태'
    && String(row[codeColumn - 1] || '').trim() === 'VACANT_CLEAN'
  );
  if (index < 0) return;
  const rowNumber = index + 2;
  sheet.getRange(rowNumber, labelColumn).setValue('공실');
  if (memoColumn) sheet.getRange(rowNumber, memoColumn).setValue('미등록 또는 정비완료 객실');
}

function seedCodes_() { // (필수 공통 코드 보완)
  const sheet = getSpreadsheet_().getSheetByName(NOVA.SHEETS.CODES);
  const rows = sheet.getLastRow() > 1
    ? sheet.getRange(2, 1, sheet.getLastRow() - 1, NOVA.CODE_HEADERS.length).getDisplayValues()
    : [];
  const existingKeys = new Set(rows.map(row => `${row[0]}|${row[1]}`));

  const seeds = [
    ['권한', 'ADMIN', '관리자', 10, 'Y', '전체 기능'],
    ['권한', 'ORDER', '오더테이커', 20, 'Y', '데스크톱 통합 운영'],
    ['권한', 'QM', '퀄리티매니저', 30, 'Y', 'QM 점검'],
    ['권한', 'HOUSEMAN', '하우스맨', 40, 'Y', '하우스맨 오더'],
    ['권한', 'ROOMMAID', '룸메이드', 50, 'Y', '객실 정비'],
    ['권한', 'PUBLIC', '객실퍼블릭', 60, 'Y', '퇴실 여부 조회'],

    ['객실상태', 'VACANT_CLEAN', '공실', 10, 'Y', '미등록 또는 정비완료 객실'],
    ['객실상태', 'STOCK', '재고', 20, 'Y', ''],
    ['객실상태', 'STOCK_RC', '재고 R/C', 30, 'Y', ''],
    ['객실상태', 'STOCK_HU', '재고 H/U', 40, 'Y', ''],
    ['객실상태', 'STAY', '투숙', 50, 'Y', ''],
    ['객실상태', 'DUE_OUT', '퇴실예정', 60, 'Y', ''],
    ['객실상태', 'CHECKED_OUT', '퇴실', 70, 'Y', ''],
    ['객실상태', 'CHECKED_OUT_RC', '퇴실R/C', 71, 'Y', 'R/C 퇴실 정비대상'],
    ['객실상태', 'CHECKED_OUT_HU', '퇴실H/U', 72, 'Y', 'H/U 퇴실 정비대상'],
    ['객실상태', 'RECHECKIN', '재입실', 80, 'Y', ''],

    ['청소상태', 'WAITING', '대기', 10, 'Y', ''],
    ['청소상태', 'ASSIGNED', '배정', 20, 'Y', ''],
    ['청소상태', 'CLEANING', '청소중', 30, 'Y', ''],
    ['청소상태', 'COMPLETED', '청소완료', 40, 'Y', ''],
    ['청소상태', 'QM_WAITING', 'QM대기', 50, 'Y', ''],
    ['청소상태', 'REWORK', '재정비', 60, 'Y', ''],

    ['하우스맨상태', 'REGISTERED', NOVA.ORDER_STATUS.REGISTERED, 10, 'Y', '미배정'],
    ['하우스맨상태', 'ASSIGNED', NOVA.ORDER_STATUS.ASSIGNED, 20, 'Y', '직원 배정'],
    ['하우스맨상태', 'ACCEPTED', NOVA.ORDER_STATUS.ACCEPTED, 30, 'Y', '담당자 접수'],
    ['하우스맨상태', 'PROCESSING', NOVA.ORDER_STATUS.PROCESSING, 40, 'Y', '처리 진행'],
    ['하우스맨상태', 'COMPLETED', NOVA.ORDER_STATUS.COMPLETED, 50, 'Y', '처리 완료'],
    ['하우스맨상태', 'UNABLE', NOVA.ORDER_STATUS.UNABLE, 60, 'Y', '처리 불가'],

    ['하우스맨파트', 'AMENITY', '비품', 10, 'Y', '직원배정 가능'],
    ['하우스맨파트', 'LINEN', '린넨', 20, 'Y', '직원배정 가능'],
    ['하우스맨파트', 'FACILITY', '시설', 30, 'Y', '타 파트 처리 가능'],
    ['하우스맨파트', 'INQUIRY', '문의', 40, 'Y', '타 파트 처리 가능'],
    ['하우스맨파트', 'OTHER', '기타', 50, 'Y', '']
  ];

  const missing = seeds.filter(row => !existingKeys.has(`${row[0]}|${row[1]}`));
  if (missing.length) {
    const startRow = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, startRow + missing.length - 1);
    sheet.getRange(startRow, 1, missing.length, NOVA.CODE_HEADERS.length).setValues(missing);
  }
}


function seedUploadCodes_() { // (객실현황 업로드용 코드 보완)
  const sheet = getSpreadsheet_().getSheetByName(NOVA.SHEETS.CODES);
  const rows = sheet.getLastRow() > 1
    ? sheet.getRange(2, 1, sheet.getLastRow() - 1, NOVA.CODE_HEADERS.length).getDisplayValues()
    : [];
  const exists = rows.some(row => String(row[0] || '').trim() === '청소상태' && String(row[1] || '').trim() === 'NOT_REQUIRED');
  if (!exists) {
    const rowNumber = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, rowNumber);
    sheet.getRange(rowNumber, 1, 1, NOVA.CODE_HEADERS.length)
      .setValues([['청소상태', 'NOT_REQUIRED', '정비대상 아님', 5, 'Y', '투숙·퇴실예정 기본상태']]);
  }
}

function configureMonthlyView_() { // (월별조회 선택 영역 구성)
  configureMonthlyViewV2_();
}

function formatCoreSheets_() { // (핵심 시트 기본 서식)
  const ss = getSpreadsheet_();
  const users = ss.getSheetByName(NOVA.SHEETS.USERS);
  const current = ss.getSheetByName(NOVA.SHEETS.CURRENT);
  const history = ss.getSheetByName(NOVA.SHEETS.HISTORY);
  if (users) users.setFrozenColumns(2);
  if (current) current.setFrozenColumns(3);
  if (history) history.setFrozenColumns(5);
}

function ensureTelegramQueueTrigger_() { // (텔레그램 큐 처리 트리거 보장)
  const exists = ScriptApp.getProjectTriggers().some(trigger => trigger.getHandlerFunction() === 'processTelegramQueue');
  if (!exists) {
    ScriptApp.newTrigger('processTelegramQueue').timeBased().everyMinutes(1).create();
  }
}


function seedMobileCodes_() { // (모바일 룸메이드·QM 상태코드 보완)
  const sheet = getSpreadsheet_().getSheetByName(NOVA.SHEETS.CODES);
  const rows = sheet.getLastRow() > 1
    ? sheet.getRange(2, 1, sheet.getLastRow() - 1, NOVA.CODE_HEADERS.length).getDisplayValues()
    : [];
  const existingKeys = new Set(rows.map(row => `${String(row[0] || '').trim()}|${String(row[1] || '').trim()}`));
  const seeds = [
    ['청소상태', 'QM_CHECKING', 'QM점검중', 55, 'Y', 'QM 모바일 점검 시작'],
    ['청소상태', 'QM_COMPLETED', 'QM완료', 70, 'Y', 'QM 최종 점검 완료']
  ];
  const missing = seeds.filter(row => !existingKeys.has(`${row[0]}|${row[1]}`));
  if (missing.length) {
    const startRow = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, startRow + missing.length - 1);
    sheet.getRange(startRow, 1, missing.length, NOVA.CODE_HEADERS.length).setValues(missing);
  }
}


function seedCleaningTypeCodes_() { // (룸메이드 정비유형 6종 코드 보완)
  const sheet = getSpreadsheet_().getSheetByName(NOVA.SHEETS.CODES);
  const rows = sheet.getLastRow() > 1
    ? sheet.getRange(2, 1, sheet.getLastRow() - 1, NOVA.CODE_HEADERS.length).getDisplayValues()
    : [];

  const existingKeys = new Set(rows.map(row => `${String(row[0] || '').trim()}|${String(row[1] || '').trim()}`));
  const seeds = [
    ['정비유형', NOVA.CLEANING_TYPES.NORMAL, '일반정비', 10, 'Y', '기본 인정정비수 × 1.0 · 마감 재고 차감'],
    ['정비유형', NOVA.CLEANING_TYPES.DS, 'D/S', 20, 'Y', '데일리서비스 · 인정정비수 0.5 · 마감 재고 미차감'],
    ['정비유형', NOVA.CLEANING_TYPES.FIVE_S, '5S', 30, 'Y', '기본 인정정비수 × 1.5 · 마감 재고 차감'],
    ['정비유형', NOVA.CLEANING_TYPES.EVALUATION, '평가원', 40, 'Y', '기본 인정정비수 × 1.5 · 마감 재고 차감'],
    ['정비유형', NOVA.CLEANING_TYPES.STAFF_DORM, '직원숙소', 50, 'Y', '기본 인정정비수 × 1.5 · 마감 재고 차감'],
    ['정비유형', NOVA.CLEANING_TYPES.DEEP_CLEANING, '딥크리닝', 60, 'Y', '기본 인정정비수 × 1.5 · 마감 재고 차감']
  ];
  const missing = seeds.filter(row => !existingKeys.has(`${row[0]}|${row[1]}`));
  if (missing.length) {
    const startRow = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, startRow + missing.length - 1);
    sheet.getRange(startRow, 1, missing.length, NOVA.CODE_HEADERS.length).setValues(missing);
  }
  return { added: missing.length, total: seeds.length };
}


function seedRoommaidAssignmentTypeCodes_() { // (룸메이드 1인·2인1조 배정유형 코드 보완)
  const sheet = getSpreadsheet_().getSheetByName(NOVA.SHEETS.CODES);
  const rows = sheet.getLastRow() > 1
    ? sheet.getRange(2, 1, sheet.getLastRow() - 1, NOVA.CODE_HEADERS.length).getDisplayValues()
    : [];
  const existingKeys = new Set(rows.map(row => `${String(row[0] || '').trim()}|${String(row[1] || '').trim()}`));
  const seeds = [
    ['룸메이드배정유형', 'SOLO', '1인 배정', 10, 'Y', '룸메이드 1명이 여러 객실을 담당'],
    ['룸메이드배정유형', 'PAIR', '2인1조', 20, 'Y', '두 명이 공동 정비'],
    ['룸메이드배정유형', 'PAIR_TRAINING', '2인1조(교육)', 30, 'Y', '교육 목적 공동 정비']
  ];
  const missing = seeds.filter(row => !existingKeys.has(`${row[0]}|${row[1]}`));
  if (missing.length) {
    const startRow = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, startRow + missing.length - 1);
    sheet.getRange(startRow, 1, missing.length, NOVA.CODE_HEADERS.length).setValues(missing);
  }
}


function repairRoomBuildingValues_() { // (객실번호 첫 자리 기준 1~9동 누락값 복구)
  const spreadsheet = getSpreadsheet_();
  const result = { roomMaster: 0, currentRooms: 0, total: 0 };
  [
    { sheetName: NOVA.SHEETS.ROOMS, resultKey: 'roomMaster' },
    { sheetName: NOVA.SHEETS.CURRENT, resultKey: 'currentRooms' }
  ].forEach(target => {
    const sheet = spreadsheet.getSheetByName(target.sheetName);
    if (!sheet || sheet.getLastRow() < 2) return;
    const headerMap = getHeaderMap_(sheet);
    const roomColumn = headerMap['객실번호'];
    const buildingColumn = headerMap['동'];
    if (!roomColumn || !buildingColumn) return;
    const rowCount = sheet.getLastRow() - 1;
    const rooms = sheet.getRange(2, roomColumn, rowCount, 1).getDisplayValues();
    const buildings = sheet.getRange(2, buildingColumn, rowCount, 1).getDisplayValues();
    let changed = 0;
    const output = buildings.map((row, index) => {
      const current = String(row[0] || '').trim();
      const normalized = normalizeRoomBuilding_(current, rooms[index][0]);
      if (normalized !== current) changed += 1;
      return [normalized];
    });
    if (changed > 0) sheet.getRange(2, buildingColumn, rowCount, 1).setValues(output);
    result[target.resultKey] = changed;
    result.total += changed;
  });
  return result;
}


function roomOperationalFlagHeaders_() { // (객실 선배정·VIP·중요 표시 열)
  return ['선배정여부', 'VIP여부', '중요객실여부'];
}

function ensureRoomOperationalFlagHeaders_() { // (현재객실현황 운영표시 열을 끝에 안전하게 추가)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  let headerMap = getHeaderMap_(sheet);
  let added = 0;
  roomOperationalFlagHeaders_().forEach(header => {
    if (headerMap[header]) return;
    const targetColumn = Math.max(sheet.getLastColumn(), 1) + 1;
    sheet.getRange(1, targetColumn).setValue(header)
      .setFontWeight('bold')
      .setHorizontalAlignment('center')
      .setBackground('#f3f4f6');
    sheet.setColumnWidth(targetColumn, 95);
    added += 1;
    if (typeof NOVA_RUNTIME_CACHE_ !== 'undefined') NOVA_RUNTIME_CACHE_.headerMaps = {};
    headerMap = getHeaderMap_(sheet);
  });
  return { added, headers: roomOperationalFlagHeaders_() };
}

function applyNovaRoomOperationalFlagsExpansion() { // (선배정·VIP·중요객실 표시 기능 적용)
  const result = ensureRoomOperationalFlagHeaders_();
  clearNovaCaches_();
  bumpDataVersion_({ domains: ['CONFIG', 'ROOM'], businessDate: businessDateText_(), site: '' });
  return {
    ok: true,
    added: Number(result && result.added || 0),
    headers: roomOperationalFlagHeaders_(),
    message: '선배정·VIP·중요객실 표시 기능을 적용했습니다.'
  };
}
