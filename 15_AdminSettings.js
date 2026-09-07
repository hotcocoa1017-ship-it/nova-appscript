/**
 * Sprint 9.3: 관리자 설정·자동 마감·마감취소
 * 운영 중 변경 가능한 명칭과 기준값은 코드설정 시트에서 관리합니다.
 */
const NOVA_ADMIN_SETTINGS = Object.freeze({
  OPERATION_GROUP: '운영설정',
  TELEGRAM_ROLE_GROUP: '텔레그램알림대상',
  AUTO_CLOSE_TRIGGER_HANDLER: 'processAutomaticDailyClose',
  AUTO_CLOSE_TRIGGER_MINUTES: 5,
  GROUPS: Object.freeze([
    { code: '운영설정', label: '운영 기준', addable: false, protected: true },
    { code: '사업장', label: '사업장', addable: true },
    { code: '동', label: '동', addable: true },
    { code: '객실타입', label: '객실타입', addable: true },
    { code: '직무', label: '직무', addable: true },
    { code: '권한', label: '권한', addable: true, protectedCodes: ['ADMIN', 'ORDER', 'QM', 'HOUSEMAN', 'ROOMMAID', 'PUBLIC'] },
    { code: '객실상태', label: '객실상태', addable: true, protectedCodes: ['VACANT_CLEAN', 'STOCK', 'STOCK_RC', 'STOCK_HU', 'STAY', 'DUE_OUT', 'CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU', 'RECHECKIN'] },
    { code: '청소상태', label: '청소상태', addable: true, protectedCodes: ['NOT_REQUIRED', 'WAITING', 'ASSIGNED', 'CLEANING', 'COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED', 'REWORK'] },
    { code: '정비유형', label: '정비유형', addable: true, protectedCodes: ['NORMAL', 'DS'] },
    { code: '룸메이드배정유형', label: '룸메이드 배정유형', addable: true, protectedCodes: ['SOLO', 'PAIR', 'PAIR_TRAINING'] },
    { code: '하우스맨파트', label: '하우스맨 파트', addable: true },
    { code: '하우스맨품목', label: '하우스맨 품목', addable: true },
    { code: '텔레그램알림대상', label: '텔레그램 알림대상', addable: false }
  ]),
  OPERATION_DEFINITIONS: Object.freeze([
    { code: 'DS_WEIGHT', label: 'D/S 인정 정비수', defaultValue: '0.5', type: 'number', min: 0, max: 2, step: 0.1, note: 'D/S 완료 1실당 인정 정비수' },
    { code: 'WEEKDAY_CHECKOUT', label: '주중 퇴실 기준시간', defaultValue: '12:00', type: 'time', note: '월~금 퇴실 기준' },
    { code: 'WEEKDAY_ALERT', label: '주중 지연 알림시간', defaultValue: '13:00', type: 'time', note: '월~금 퇴실지연 알림 시작' },
    { code: 'WEEKEND_CHECKOUT', label: '주말 퇴실 기준시간', defaultValue: '11:00', type: 'time', note: '토·일 퇴실 기준' },
    { code: 'WEEKEND_ALERT', label: '주말 지연 알림시간', defaultValue: '12:00', type: 'time', note: '토·일 퇴실지연 알림 시작' },
    { code: 'DEPARTURE_TRIGGER_MINUTES', label: '퇴실지연 점검주기(분)', defaultValue: '5', type: 'select', options: ['1', '5', '10', '15', '30'], note: 'Apps Script 자동 점검 간격' },
    { code: 'AUTO_CLOSE_ENABLED', label: '일일 자동마감', defaultValue: 'N', type: 'yesno', note: 'Y이면 설정시각 이후 미마감 사업장을 자동 저장' },
    { code: 'AUTO_CLOSE_TIME', label: '자동마감 실행시각', defaultValue: '23:50', type: 'time', note: '업무일자 기준 자동마감 확인시각' },
    { code: 'AUTO_CLOSE_NOTIFY_FAILURE', label: '자동마감 실패 관리자 알림', defaultValue: 'Y', type: 'yesno', note: '실패 시 관리자 텔레그램 1회 알림' }
  ])
});

function getAdminSettingsData(token) { // (관리자 설정 전체 조회)
  return measureResponse_('getAdminSettingsData', () => {
    requireRole_(token, ['ADMIN']);
    seedAdminSettingsCodes_();
    const rows = readAllCodeRows_();
    const groups = NOVA_ADMIN_SETTINGS.GROUPS.map(meta => ({
      code: meta.code,
      label: meta.label,
      addable: Boolean(meta.addable),
      items: rows.filter(row => row.group === meta.code).map(row => Object.assign({}, row, {
        protected: isProtectedAdminCode_(meta.code, row.code)
      }))
    }));
    const operationValues = {};
    NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach(def => {
      operationValues[def.code] = getOperationSetting_(def.code, def.defaultValue);
    });

    // DB가 아직 confirmed=false인 초기 이행 구간에서는 기존 Sheet 설정을 유지합니다.
    // 관리자가 DB-first 저장을 1회 성공해 confirmed=true가 된 뒤에는 DB가 조회 원본입니다.
    let operationDb = null; // OPERATION_SETTINGS_READ_DB_FIRST_V1
    if (typeof novaOperationSettingsDbFirstEnabled_ === 'function'
        && novaOperationSettingsDbFirstEnabled_()
        && typeof novaOperationSettingsDbRead_ === 'function') {
      operationDb = novaOperationSettingsDbRead_(token);
      if (operationDb && operationDb.confirmed === true && operationDb.values) {
        NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach(def => {
          if (Object.prototype.hasOwnProperty.call(operationDb.values, def.code)) {
            operationValues[def.code] = validateOperationSettingValue_(def, operationDb.values[def.code]);
          }
        });
      }
    }
    return {
      ok: true,
      version: NOVA.VERSION,
      groups,
      operationDefinitions: NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS,
      operationValues,
      operationDb: operationDb ? {
        dbFirst: Boolean(operationDb.dbFirst),
        confirmed: Boolean(operationDb.confirmed),
        version: Number(operationDb.version || 0)
      } : null,
      triggers: getAdminTriggerStatus_(),
      autoClose: getAutomaticCloseStatus_(),
      serverTime: nowText_()
    };
  });
}

function saveAdminOperationSettings(token, payload) { // (운영 기준 일괄 저장 · OPERATION_SETTINGS_DB_FIRST_V1)
  return measureResponse_('saveAdminOperationSettings', () => {
    const user = requireRole_(token, ['ADMIN']);
    const safePayload = payload || {};
    const input = safePayload && safePayload.values ? safePayload.values : safePayload;
    const normalized = {};

    // 먼저 전체 입력값을 검증합니다. 하나라도 잘못되면 DB·Sheet 모두 변경하지 않습니다.
    NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach(def => {
      const raw = Object.prototype.hasOwnProperty.call(input, def.code)
        ? input[def.code]
        : getOperationSetting_(def.code, def.defaultValue);
      normalized[def.code] = validateOperationSettingValue_(def, raw);
    });

    let dbResult = null;
    let dbRequestId = '';
    if (typeof novaOperationSettingsDbFirstEnabled_ === 'function'
        && novaOperationSettingsDbFirstEnabled_()
        && typeof novaOperationSettingsDbSave_ === 'function') {
      const requestedId = String(safePayload.requestId || safePayload.request_id || '').trim();
      dbRequestId = /^[A-Za-z0-9._:-]{8,180}$/.test(requestedId)
        ? requestedId
        : `OPSET_V1:${Utilities.getUuid()}`;
      dbResult = novaOperationSettingsDbSave_(token, normalized, dbRequestId);
    }

    // DB-first가 켜져 있으면 여기까지 DB 저장이 성공한 뒤에만 기존 Sheet를 mirror로 갱신합니다.
    NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach(def => {
      upsertCodeRow_(
        NOVA_ADMIN_SETTINGS.OPERATION_GROUP,
        def.code,
        normalized[def.code],
        def.order || ((NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.indexOf(def) + 1) * 10),
        'Y',
        def.note
      );
    });
    clearNovaCaches_();
    bumpDataVersion_({ domains: ['CONFIG'] });
    recreateDepartureDelayTrigger_();
    ensureAutomaticDailyCloseTrigger_();
    appendUnifiedHistory_({
      recordType: 'ADMIN_SETTING',
      businessDate: businessDateText_(),
      status: 'UPDATED',
      registeredBy: user.employeeNo,
      detail: {
        category: 'OPERATION',
        values: normalized,
        dbFirst: Boolean(dbResult && dbResult.dbFirst),
        dbRequestId
      }
    });
    return {
      ok: true,
      values: normalized,
      triggers: getAdminTriggerStatus_(),
      dbFirst: Boolean(dbResult && dbResult.dbFirst),
      dbRequestId,
      message: '운영 기준과 자동 실행 트리거를 저장했습니다.'
    };
  });
}

function saveAdminCodeRow(token, payload) { // (관리 코드·명칭 저장)
  return measureResponse_('saveAdminCodeRow', () => {
    const user = requireRole_(token, ['ADMIN']);
    const safe = payload || {};
    const group = String(safe.group || '').trim();
    const meta = getAdminGroupMeta_(group);
    if (!meta) throw new Error('관리할 수 없는 코드그룹입니다.');
    if (group === NOVA_ADMIN_SETTINGS.OPERATION_GROUP) throw new Error('운영 기준은 운영 설정 화면에서 저장하세요.');
    const code = normalizeAdminCode_(safe.code);
    const label = String(safe.label || '').trim();
    if (!code) throw new Error('코드를 입력하세요.');
    if (!label) throw new Error('표시명을 입력하세요.');
    const existing = findCodeRow_(group, code);
    if (!existing && !meta.addable) throw new Error('이 코드그룹에는 새 항목을 추가할 수 없습니다.');
    const enabled = isProtectedAdminCode_(group, code) ? 'Y' : normalizeYesNo_(safe.enabled == null ? 'Y' : safe.enabled);
    const order = Math.max(0, Number(safe.order || 9999));
    const note = String(safe.note || '').trim();
    upsertCodeRow_(group, code, label, order, enabled, note);
    clearNovaCaches_();
    bumpDataVersion_({ domains: ['CONFIG'] });
    appendUnifiedHistory_({
      recordType: 'ADMIN_SETTING',
      businessDate: businessDateText_(),
      status: existing ? 'CODE_UPDATED' : 'CODE_CREATED',
      registeredBy: user.employeeNo,
      detail: { group, code, label, order, enabled, note }
    });
    return { ok: true, message: `${group} ${label} 항목을 저장했습니다.` };
  });
}

function disableAdminCodeRow(token, payload) { // (관리 코드 사용중지)
  return measureResponse_('disableAdminCodeRow', () => {
    const user = requireRole_(token, ['ADMIN']);
    const safe = payload || {};
    const group = String(safe.group || '').trim();
    const code = normalizeAdminCode_(safe.code);
    const meta = getAdminGroupMeta_(group);
    if (!meta || !code) throw new Error('코드정보가 올바르지 않습니다.');
    if (isProtectedAdminCode_(group, code)) throw new Error('시스템 필수코드는 사용중지할 수 없습니다. 표시명만 변경하세요.');
    const existing = findCodeRow_(group, code);
    if (!existing) throw new Error('코드 항목을 찾을 수 없습니다.');
    upsertCodeRow_(group, code, existing.label, existing.order, 'N', existing.note);
    clearNovaCaches_();
    bumpDataVersion_({ domains: ['CONFIG'] });
    appendUnifiedHistory_({
      recordType: 'ADMIN_SETTING',
      businessDate: businessDateText_(),
      status: 'CODE_DISABLED',
      registeredBy: user.employeeNo,
      detail: { group, code }
    });
    return { ok: true, message: `${existing.label} 항목을 사용중지했습니다.` };
  });
}

function cancelDailyCloseSnapshot(token, payload) { // (저장된 일일 마감 취소·DB-first/Sheet mirror)
  return measureResponse_('cancelDailyCloseSnapshot', () => {
    const user = requireRole_(token, ['ADMIN']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const requestedSite = String(safe.site || '').trim();
    const reason = String(safe.reason || '').trim();
    const writeLock = acquireWriteLock_(10000);
    try {
      const active = readDailyCloseSummaries_(businessDate, requestedSite);
      const sites = requestedSite
        ? [requestedSite]
        : Array.from(new Set(active.map(item => item.site).filter(Boolean)));
      if (!sites.length) throw new Error('취소할 마감자료가 없습니다.');

      let dbResult = null;
      let dbRequestId = '';
      let dbSites = [];
      if (typeof novaDailyCloseDbFirstEnabled_ === 'function'
          && novaDailyCloseDbFirstEnabled_()
          && typeof novaDailyCloseDbRead_ === 'function'
          && typeof novaDailyCloseDbCancelMany_ === 'function') {
        const dbRead = novaDailyCloseDbRead_(token, {
          startDate: businessDate,
          endDate: businessDate,
          site: requestedSite
        });
        const requestedSet = new Set(sites);
        dbSites = Array.from(new Set(
          (Array.isArray(dbRead && dbRead.items) ? dbRead.items : [])
            .filter(item => String(item && item.businessDate || '').trim() === businessDate)
            .map(item => String(item && item.site || '').trim())
            .filter(site => site && requestedSet.has(site))
        ));

        if (dbSites.length && dbSites.length !== sites.length) {
          throw new Error('일부 사업장만 DB 마감으로 전환된 상태입니다. 사업장을 하나씩 선택해 취소해 주세요.');
        }
        if (dbSites.length === sites.length) {
          const requestedId = String(safe.requestId || safe.request_id || '').trim();
          dbRequestId = /^[A-Za-z0-9._:-]{8,180}$/.test(requestedId)
            ? requestedId
            : `DCANCEL_V1:${Utilities.getUuid()}`;
          dbResult = novaDailyCloseDbCancelMany_(token, {
            businessDate,
            sites,
            reason,
            requestId: dbRequestId
          });
        }
      }

      // DB-native 마감은 DB 취소가 성공한 뒤에만 Sheet 이력을 mirror로 소프트삭제합니다.
      // DB에 없는 과거 Sheet-only 마감은 기존 취소 방식을 유지합니다.
      const version = reserveDataVersion_({ lockHeld: true });
      const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const updatedAt = nowText_();
      let cancelledRows = 0;
      sites.forEach(site => {
        cancelledRows += markExistingDailyCloseDeleted_(historySheet, businessDate, site, updatedAt);
      });
      appendUnifiedHistory_({
        recordType: NOVA.RECORD_TYPES.DAILY_CLOSE,
        businessDate,
        site: requestedSite,
        status: 'CANCEL_AUDIT',
        registeredBy: user.employeeNo,
        version,
        detail: {
          sites,
          cancelledRows,
          reason,
          dbFirst: Boolean(dbResult && dbResult.dbFirst),
          dbRequestId
        }
      });
      sites.forEach(site => publishDataVersion_(version, {
        domains: ['REPORT'],
        businessDate,
        site,
        lockHeld: true
      }));
      return {
        ok: true,
        businessDate,
        sites,
        cancelledRows,
        version,
        dbFirst: Boolean(dbResult && dbResult.dbFirst),
        dbRequestId,
        dbCancelledCount: Number(dbResult && dbResult.cancelledCount || 0),
        message: `${businessDate} ${sites.length}개 사업장의 마감을 취소했습니다.`
      };
    } finally {
      writeLock.releaseLock();
    }
  });
}

function runAutomaticDailyCloseNow(token) { // (관리자 자동마감 즉시 시험 · AUTO_CLOSE_DB_FIRST_GUARD_V1)
  requireRole_(token, ['ADMIN']);
  return processAutomaticDailyClose({ force: true, invokedBy: 'ADMIN_TEST', dbToken: token });
}

function processAutomaticDailyClose(options) { // (설정시각 기준 미마감 사업장 자동 저장 · AUTO_CLOSE_DB_FIRST_GUARD_V1)
  const safe = options || {};
  const force = safe.force === true;
  const enabled = getOperationSetting_('AUTO_CLOSE_ENABLED', 'N') === 'Y';
  if (!enabled && !force) return { ok: true, skipped: true, reason: 'DISABLED' };
  const now = new Date();
  const businessDate = businessDateText_(); // 공통 09:00 업무일자 기준
  const currentTime = Utilities.formatDate(now, NOVA.TIMEZONE, 'HH:mm');
  const closeTime = getOperationSetting_('AUTO_CLOSE_TIME', '23:50');
  if (!force && currentTime < closeTime) return { ok: true, skipped: true, reason: 'BEFORE_TIME', businessDate, currentTime, closeTime };

  const dbFirstRequired = typeof novaDailyCloseDbFirstEnabled_ === 'function' && novaDailyCloseDbFirstEnabled_();
  const dbToken = String(safe.dbToken || '').trim();

  // DB-primary에서는 무인 시간트리거가 Sheet만 단독 마감해 split-brain을 만들지 못하게 합니다.
  // 관리자 즉시시험은 로그인 토큰을 전달하므로 DB source -> DB close -> Sheet mirror 경로를 그대로 사용합니다.
  if (dbFirstRequired && !dbToken) {
    const error = new Error('DB-primary 자동마감은 안전한 system DB endpoint가 연결되기 전까지 무인 실행을 차단합니다. 관리자 즉시시험 또는 수동 마감을 사용해 주세요.');
    notifyAutomaticCloseFailure_(businessDate, error);
    return { ok: false, skipped: true, reason: 'DB_SYSTEM_ENDPOINT_REQUIRED', businessDate, closeTime, message: error.message };
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return { ok: false, skipped: true, reason: 'LOCKED' };
  try {
    if (dbFirstRequired && dbToken) {
      const configuredSites = getSiteList_();
      const dbSources = {};
      configuredSites.forEach(site => {
        const source = tryNovaDailyCloseDbSource_(dbToken, businessDate, site);
        if (source && source.ready) dbSources[site] = source;
      });
      const sourceSites = Object.keys(dbSources);
      if (!sourceSites.length) throw new Error(`${businessDate} DB에 자동마감 가능한 사업장이 없습니다.`);

      const savedDb = readDailyCloseDbSnapshots_(dbToken, businessDate, businessDate, '');
      const closedSites = new Set(savedDb.map(item => String(item.site || '').trim()).filter(Boolean));
      const pendingSites = sourceSites.filter(site => !closedSites.has(site));
      if (!pendingSites.length) return { ok: true, skipped: true, reason: 'ALREADY_CLOSED', businessDate, sites: sourceSites, dbFirst: true };

      const systemUser = { employeeNo: 'SYSTEM', name: '자동마감', role: 'ADMIN' };
      const results = pendingSites.map(site => saveDailyCloseSnapshotForSite_(businessDate, site, systemUser, {
        currentRows: dbSources[site].currentRows,
        historyRows: dbSources[site].historyRows,
        dbToken,
        dbSource: true
      }));
      PropertiesService.getScriptProperties().deleteProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_KEY');
      PropertiesService.getScriptProperties().deleteProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_TEXT');
      return { ok: true, businessDate, closeTime, sites: results, dbFirst: true, message: `${businessDate} ${results.length}개 사업장을 DB-first로 자동 마감했습니다.` };
    }

    // Realtime/DB-first가 꺼진 레거시 모드에서만 기존 Sheet 자동마감을 유지합니다.
    const sites = getCurrentSitesForDate_(businessDate);
    if (!sites.length) throw new Error(`${businessDate} 현재객실현황에 자동마감할 사업장이 없습니다.`);
    const saved = readDailyCloseSummaries_(businessDate, '');
    const closedSites = new Set(saved.map(item => item.site));
    const pendingSites = sites.filter(site => !closedSites.has(site));
    if (!pendingSites.length) return { ok: true, skipped: true, reason: 'ALREADY_CLOSED', businessDate, sites };
    const allCurrentRows = readCurrentRowsForClose_(businessDate, '');
    const allHistoryRows = readHistoryRowsForClose_(businessDate, '');
    const systemUser = { employeeNo: 'SYSTEM', name: '자동마감', role: 'ADMIN' };
    const results = pendingSites.map(site => saveDailyCloseSnapshotForSite_(businessDate, site, systemUser, {
      currentRows: allCurrentRows.filter(data => String(data['사업장'] || '').trim() === site),
      historyRows: allHistoryRows.filter(data => String(data['사업장'] || '').trim() === site)
    }));
    PropertiesService.getScriptProperties().deleteProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_KEY');
    PropertiesService.getScriptProperties().deleteProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_TEXT');
    return { ok: true, businessDate, closeTime, sites: results, dbFirst: false, message: `${businessDate} ${results.length}개 사업장을 자동 마감했습니다.` };
  } catch (error) {
    notifyAutomaticCloseFailure_(businessDate, error);
    throw error;
  } finally {
    lock.releaseLock();
  }
}

function ensureAutomaticDailyCloseTrigger_() { // (자동마감 점검 트리거 보장)
  const handler = NOVA_ADMIN_SETTINGS.AUTO_CLOSE_TRIGGER_HANDLER;
  const triggers = ScriptApp.getProjectTriggers().filter(trigger => trigger.getHandlerFunction() === handler);
  triggers.slice(1).forEach(trigger => ScriptApp.deleteTrigger(trigger));
  if (!triggers.length) ScriptApp.newTrigger(handler).timeBased().everyMinutes(NOVA_ADMIN_SETTINGS.AUTO_CLOSE_TRIGGER_MINUTES).create();
  return { handler, count: 1, intervalMinutes: NOVA_ADMIN_SETTINGS.AUTO_CLOSE_TRIGGER_MINUTES };
}

function recreateDepartureDelayTrigger_() { // (설정된 간격으로 퇴실지연 트리거 재생성)
  const handler = 'processDepartureDelayAlerts';
  ScriptApp.getProjectTriggers().filter(trigger => trigger.getHandlerFunction() === handler).forEach(trigger => ScriptApp.deleteTrigger(trigger));
  const minutes = getDepartureDelayTriggerMinutes_();
  ScriptApp.newTrigger(handler).timeBased().everyMinutes(minutes).create();
  return { handler, count: 1, intervalMinutes: minutes };
}

function getAdminTriggerStatus_() { // (관리 트리거 설치상태)
  const counts = {};
  ScriptApp.getProjectTriggers().forEach(trigger => {
    const handler = trigger.getHandlerFunction();
    counts[handler] = (counts[handler] || 0) + 1;
  });
  return {
    departureDelay: { handler: 'processDepartureDelayAlerts', count: counts.processDepartureDelayAlerts || 0, intervalMinutes: getDepartureDelayTriggerMinutes_() },
    automaticClose: { handler: NOVA_ADMIN_SETTINGS.AUTO_CLOSE_TRIGGER_HANDLER, count: counts[NOVA_ADMIN_SETTINGS.AUTO_CLOSE_TRIGGER_HANDLER] || 0, intervalMinutes: NOVA_ADMIN_SETTINGS.AUTO_CLOSE_TRIGGER_MINUTES },
    telegramQueue: { handler: 'processTelegramQueue', count: counts.processTelegramQueue || 0, intervalMinutes: 1 }
  };
}

function getAutomaticCloseStatus_() { // (자동마감 현재 설정 요약)
  return {
    enabled: getOperationSetting_('AUTO_CLOSE_ENABLED', 'N') === 'Y',
    closeTime: getOperationSetting_('AUTO_CLOSE_TIME', '23:50'),
    notifyFailure: getOperationSetting_('AUTO_CLOSE_NOTIFY_FAILURE', 'Y') === 'Y',
    lastFailure: PropertiesService.getScriptProperties().getProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_TEXT') || ''
  };
}

function notifyAutomaticCloseFailure_(businessDate, error) { // (자동마감 실패 관리자 1회 알림)
  if (getOperationSetting_('AUTO_CLOSE_NOTIFY_FAILURE', 'Y') !== 'Y') return;
  const messageText = String(error && error.message || error || '알 수 없는 오류').slice(0, 500);
  const key = `${businessDate}|${messageText}`;
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_KEY') === key) return;
  props.setProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_KEY', key);
  props.setProperty('NOVA_AUTO_CLOSE_LAST_FAILURE_TEXT', `${nowText_()} · ${messageText}`);
  const recipients = getActiveUsersByRole_('ADMIN')
    .filter(user => telegramRecipientAllowed_(user, 'AUTO_CLOSE_FAILURE'))
    .map(user => user.telegramId)
    .filter(Boolean);
  queueTelegramNotification_({
    notificationType: 'AUTO_CLOSE_FAILURE',
    businessDate,
    recipients,
    message: ['[NOVA 자동마감 실패]', `업무일자: ${businessDate}`, `오류: ${messageText}`, '관리자 설정과 현재객실현황을 확인해 주세요.'].join('\n'),
    eventName: 'AUTO_CLOSE_FAILURE',
    registeredBy: 'SYSTEM',
    version: getDataVersion_()
  });
}

function seedAdminSettingsCodes_() { // (관리자 설정용 코드·운영값 일괄 보완)
  const existingRows = readAllCodeRows_();
  const existingKeys = new Set(existingRows.map(row => `${row.group}|${row.code}`));
  const seeds = [];
  NOVA_ADMIN_SETTINGS.OPERATION_DEFINITIONS.forEach((def, index) => {
    seeds.push([NOVA_ADMIN_SETTINGS.OPERATION_GROUP, def.code, def.defaultValue, (index + 1) * 10, 'Y', def.note]);
  });
  ['ADMIN', 'ORDER', 'QM', 'HOUSEMAN', 'ROOMMAID', 'PUBLIC'].forEach((role, index) => {
    const label = ({ ADMIN: '관리자', ORDER: '오더테이커', QM: 'QM', HOUSEMAN: '하우스맨', ROOMMAID: '룸메이드', PUBLIC: '객실퍼블릭' })[role];
    seeds.push([NOVA_ADMIN_SETTINGS.TELEGRAM_ROLE_GROUP, role, label, (index + 1) * 10, 'Y', role === 'PUBLIC' ? '퇴실지연 알림만 허용' : '직무별 NOVA 알림 허용']);
  });
  for (let building = 1; building <= 9; building += 1) {
    seeds.push(['동', `${building}`, `${building}동`, building * 10, 'Y', '객실번호 첫 자리 기준']);
  }
  collectDistinctAdminSeedRows_().forEach(row => seeds.push(row));
  const missing = seeds.filter(row => !existingKeys.has(`${row[0]}|${row[1]}`));
  if (missing.length) {
    const sheet = getRequiredSheet_(NOVA.SHEETS.CODES);
    const startRow = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, startRow + missing.length - 1);
    sheet.getRange(startRow, 1, missing.length, NOVA.CODE_HEADERS.length).setValues(missing);
    clearNovaCaches_();
  }
  return { added: missing.length };
}

function collectDistinctAdminSeedRows_() { // (현재 데이터의 사업장·객실타입·직무 시드 수집)
  const ss = getSpreadsheet_();
  const targets = [
    { sheet: NOVA.SHEETS.ROOMS, header: '사업장', group: '사업장' },
    { sheet: NOVA.SHEETS.CURRENT, header: '사업장', group: '사업장' },
    { sheet: NOVA.SHEETS.USERS, header: '기본사업장', group: '사업장' },
    { sheet: NOVA.SHEETS.ROOMS, header: '객실타입', group: '객실타입' },
    { sheet: NOVA.SHEETS.USERS, header: '직무', group: '직무' }
  ];
  const valuesByGroup = {};
  targets.forEach(target => {
    const sheet = ss.getSheetByName(target.sheet);
    if (!sheet || sheet.getLastRow() < 2) return;
    const map = getHeaderMap_(sheet);
    const column = map[target.header];
    if (!column) return;
    if (!valuesByGroup[target.group]) valuesByGroup[target.group] = new Set();
    sheet.getRange(2, column, sheet.getLastRow() - 1, 1).getDisplayValues().forEach(row => {
      const value = String(row[0] || '').trim();
      if (value) valuesByGroup[target.group].add(value);
    });
  });
  const rows = [];
  Object.keys(valuesByGroup).forEach(group => {
    Array.from(valuesByGroup[group]).sort((a, b) => a.localeCompare(b, 'ko')).forEach((label, index) => {
      rows.push([group, makeAdminListCode_(label), label, (index + 1) * 10, 'Y', '기존 데이터에서 자동등록']);
    });
  });
  return rows;
}

function getOperationSetting_(code, fallback) { // (운영설정 값 조회)
  const item = getCodes_(NOVA_ADMIN_SETTINGS.OPERATION_GROUP).find(row => row.code === String(code || '').trim());
  return item && item.label !== '' ? String(item.label) : String(fallback == null ? '' : fallback);
}

function getCleaningCreditUnit_(cleaningType) { // (정비유형별 인정 정비수)
  return String(cleaningType || '').trim().toUpperCase() === NOVA.CLEANING_TYPES.DS
    ? Number(getOperationSetting_('DS_WEIGHT', '0.5')) || 0.5
    : 1;
}

function getDepartureDelayTriggerMinutes_() { // (퇴실지연 점검 간격)
  const value = Number(getOperationSetting_('DEPARTURE_TRIGGER_MINUTES', String(NOVA.DEPARTURE_DELAY.TRIGGER_MINUTES)));
  return [1, 5, 10, 15, 30].includes(value) ? value : NOVA.DEPARTURE_DELAY.TRIGGER_MINUTES;
}

function getDepartureDelaySetting_(code, fallback) { // (퇴실지연 시간 설정)
  const value = getOperationSetting_(code, fallback);
  return /^\d{2}:\d{2}$/.test(value) ? value : fallback;
}

function isTelegramRoleEnabled_(role) { // (직무별 텔레그램 알림 허용)
  const normalized = String(role || '').trim().toUpperCase();
  if (!normalized) return false;
  const cache = CacheService.getScriptCache();
  let policy = null;
  const cached = cache.get('NOVA_TELEGRAM_ROLE_POLICY_V1');
  if (cached) {
    try { policy = JSON.parse(cached); } catch (error) { policy = null; }
  }
  if (!policy) {
    policy = {};
    readAllCodeRows_().filter(row => row.group === NOVA_ADMIN_SETTINGS.TELEGRAM_ROLE_GROUP)
      .forEach(row => { policy[String(row.code || '').toUpperCase()] = row.enabled === 'Y'; });
    cache.put('NOVA_TELEGRAM_ROLE_POLICY_V1', JSON.stringify(policy), NOVA.CODE_CACHE_SECONDS);
  }
  return Object.prototype.hasOwnProperty.call(policy, normalized) ? policy[normalized] : true;
}

function readAllCodeRows_() { // (코드설정 전체 행 조회·비활성 포함)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CODES);
  if (sheet.getLastRow() < 2) return [];
  const map = getHeaderMap_(sheet);
  return sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getDisplayValues().map((row, index) => ({
    rowNumber: index + 2,
    group: String(row[(map['코드그룹'] || 1) - 1] || '').trim(),
    code: String(row[(map['코드'] || 1) - 1] || '').trim(),
    label: String(row[(map['표시명'] || 1) - 1] || '').trim(),
    order: Number(row[(map['정렬순서'] || 1) - 1] || 9999),
    enabled: String(row[(map['사용여부'] || 1) - 1] || 'N').trim().toUpperCase() === 'Y' ? 'Y' : 'N',
    note: String(row[(map['비고'] || 1) - 1] || '').trim()
  })).filter(row => row.group && row.code).sort((a, b) => a.group.localeCompare(b.group, 'ko') || a.order - b.order || a.label.localeCompare(b.label, 'ko'));
}

function findCodeRow_(group, code) { // (코드설정 단일 행 조회)
  return readAllCodeRows_().find(row => row.group === String(group || '').trim() && row.code === String(code || '').trim()) || null;
}

function upsertCodeRow_(group, code, label, order, enabled, note) { // (코드설정 행 추가·수정)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CODES);
  const existing = findCodeRow_(group, code);
  const values = { '코드그룹': group, '코드': code, '표시명': label, '정렬순서': Number(order || 9999), '사용여부': normalizeYesNo_(enabled), '비고': note || '' };
  if (existing) updateRowByHeaders_(sheet, existing.rowNumber, values);
  else {
    const row = createRowByHeaders_(sheet, values);
    const rowNumber = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, rowNumber);
    sheet.getRange(rowNumber, 1, 1, row.length).setValues([row]);
  }
}

function validateOperationSettingValue_(definition, value) { // (운영설정 입력 검증)
  const text = String(value == null ? '' : value).trim();
  if (definition.type === 'time') {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(text)) throw new Error(`${definition.label}을 HH:mm 형식으로 입력하세요.`);
    return text;
  }
  if (definition.type === 'yesno') return normalizeYesNo_(text);
  if (definition.type === 'select') {
    if (!(definition.options || []).includes(text)) throw new Error(`${definition.label} 값이 올바르지 않습니다.`);
    return text;
  }
  if (definition.type === 'number') {
    const number = Number(text);
    if (!Number.isFinite(number) || number < definition.min || number > definition.max) throw new Error(`${definition.label}은 ${definition.min}~${definition.max} 범위로 입력하세요.`);
    return String(Math.round(number * 100) / 100);
  }
  if (!text) throw new Error(`${definition.label} 값을 입력하세요.`);
  return text;
}

function getAdminGroupMeta_(group) { // (관리 코드그룹 메타 조회)
  return NOVA_ADMIN_SETTINGS.GROUPS.find(item => item.code === String(group || '').trim()) || null;
}

function isProtectedAdminCode_(group, code) { // (시스템 필수코드 판정)
  const meta = getAdminGroupMeta_(group);
  if (!meta) return true;
  if (meta.protected) return true;
  return Array.isArray(meta.protectedCodes) && meta.protectedCodes.includes(String(code || '').trim());
}

function normalizeAdminCode_(value) { // (관리코드 안전 정리)
  return String(value || '').trim().toUpperCase().replace(/\s+/g, '_').replace(/[^0-9A-Z가-힣_\-]/g, '').slice(0, 60);
}

function makeAdminListCode_(label) { // (기존 표시명에서 안정적 코드 생성)
  const normalized = normalizeAdminCode_(label);
  if (normalized) return normalized;
  return `ITEM_${Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(label || ''))).replace(/=+$/g, '').slice(0, 12)}`;
}
