/**
 * Sprint 8: 주중·주말 퇴실지연 자동 확인 및 텔레그램 알림
 * 별도 시트를 만들지 않고 현재객실현황과 업무이력만 사용합니다.
 */
function ensureDepartureDelayTrigger_() { // (퇴실지연 5분 자동점검 트리거 보장)
  const handler = 'processDepartureDelayAlerts';
  const triggers = ScriptApp.getProjectTriggers().filter(trigger => trigger.getHandlerFunction() === handler);
  triggers.slice(1).forEach(trigger => ScriptApp.deleteTrigger(trigger));
  if (!triggers.length) {
    ScriptApp.newTrigger(handler)
      .timeBased()
      .everyMinutes(getDepartureDelayTriggerMinutes_())
      .create();
  }
  return { ok: true, count: 1, intervalMinutes: getDepartureDelayTriggerMinutes_() };
}

// DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4
function processDepartureDelayAlerts() { // (운영 자동알림은 PostgreSQL 5분 cron + NOVA 알림센터가 소유)
  return {
    ok: true,
    dbFirst: true,
    notificationNative: true,
    skipped: true,
    reason: 'DB_CRON_NATIVE',
    businessDate: Utilities.formatDate(new Date(), NOVA.TIMEZONE, NOVA.DATE_FORMAT)
  };
}

function processDepartureDelayAlertsLegacy_() { // (기존 Sheet/Telegram 수동 호환보존 · DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4)
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(3000)) return { ok: false, skipped: true, reason: 'LOCKED' };
  try {
    const now = new Date();
    const businessDate = Utilities.formatDate(now, NOVA.TIMEZONE, NOVA.DATE_FORMAT);
    const rule = getDepartureDelayRule_(businessDate, now);
    if (!rule.reached) {
      return { ok: true, skipped: true, reason: 'BEFORE_ALERT_TIME', businessDate, rule };
    }

    const selection = getCurrentRowsForSelection_(businessDate, '');
    const dueRooms = selection.items
      .map(item => ({
        roomNo: String(item.data['객실번호'] || '').trim(),
        site: String(item.data['사업장'] || '').trim(),
        building: String(item.data['동'] || '').trim(),
        roomStatus: String(item.data['객실상태'] || '').trim()
      }))
      .filter(room => room.roomNo && room.site && room.roomStatus === 'DUE_OUT');
    if (!dueRooms.length) return { ok: true, processedSites: 0, notifiedRooms: 0, businessDate, rule };

    const notified = getDepartureDelayNotificationIndex_(businessDate);
    const bySite = {};
    dueRooms.forEach(room => {
      const key = departureDelayKey_(businessDate, room.site, room.roomNo);
      if (notified.keys.has(key)) return;
      if (!bySite[room.site]) bySite[room.site] = [];
      bySite[room.site].push(room);
    });

    const historyRows = [];
    const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const version = getDataVersion_();
    let processedSites = 0;
    let notifiedRooms = 0;

    Object.keys(bySite).sort((a, b) => a.localeCompare(b, 'ko')).forEach(site => {
      const rooms = bySite[site].sort((a, b) => compareDepartureRoomNos_(a.roomNo, b.roomNo));
      const recipients = resolveDepartureDelayTelegramRecipients_(site);
      if (!recipients.length) return;

      const queued = queueTelegramNotification_({
        notificationType: 'DEPARTURE_DELAY',
        businessDate,
        site,
        recipients,
        message: buildDepartureDelayTelegramMessage_(businessDate, site, rooms, rule),
        eventName: 'DEPARTURE_DELAY',
        parentRecordId: `DELAY-${businessDate}-${site}`,
        registeredBy: 'SYSTEM',
        version
      });
      if (!queued || !queued.queued) return;

      const registeredAt = nowText_();
      rooms.forEach(room => {
        historyRows.push(createRowByHeaders_(historySheet, {
          '기록ID': `DD-${businessDate.replaceAll('-', '')}-${Utilities.getUuid().slice(0, 10).toUpperCase()}`,
          '기록구분': NOVA.RECORD_TYPES.DEPARTURE_DELAY,
          '업무일자': businessDate,
          '사업장': site,
          '객실번호': room.roomNo,
          '처리상태': 'NOTIFIED',
          '세부내용JSON': JSON.stringify({
            notificationType: 'DEPARTURE_DELAY',
            alertTime: rule.alertTime,
            checkoutTime: rule.checkoutTime,
            dayType: rule.dayType,
            building: room.building,
            recipientCount: recipients.length
          }),
          '등록사번': 'SYSTEM',
          '등록일시': registeredAt,
          '수정일시': registeredAt,
          '변경버전': version,
          '삭제여부': 'N'
        }));
      });
      processedSites += 1;
      notifiedRooms += rooms.length;
    });

    if (historyRows.length) {
      const startRow = historySheet.getLastRow() + 1;
      ensureSheetRowCapacity_(historySheet, startRow + historyRows.length - 1);
      historySheet.getRange(startRow, 1, historyRows.length, historyRows[0].length).setValues(historyRows);
    }

    return { ok: true, businessDate, rule, processedSites, notifiedRooms };
  } finally {
    lock.releaseLock();
  }
}

function getDepartureDelayDashboard(token, options) { // (DB 현재객실 + NOVA 알림상태 조회)
  return measureResponse_('getDepartureDelayDashboard', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const db = novaDbFirstRpc_(token, 'nova_departure_delay_dashboard_v1', {
      p_business_date: businessDate,
      p_site: site
    }, { readOnly: true, allowLegacyFallback: true });
    if (db && db.ok) return db;
    if (db && db.legacyFallback) return getDepartureDelayDashboardLegacy_(token, options);
    throw new Error(db && db.message || '퇴실지연 DB 현황을 불러오지 못했습니다.');
  });
}

function getDepartureDelayDashboardLegacy_(token, options) { // (기존 Sheet 조회 fallback · DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4)
  return measureResponse_('getDepartureDelayDashboard', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const rule = getDepartureDelayRule_(businessDate, new Date());
    const selection = getCurrentRowsForSelection_(businessDate, site);
    const notificationIndex = getDepartureDelayNotificationIndex_(businessDate);

    const items = selection.items
      .map(item => {
        const roomNo = String(item.data['객실번호'] || '').trim();
        const roomSite = String(item.data['사업장'] || '').trim();
        const status = String(item.data['객실상태'] || '').trim();
        const key = departureDelayKey_(businessDate, roomSite, roomNo);
        return {
          roomNo,
          site: roomSite,
          building: String(item.data['동'] || '').trim(),
          roomStatus: status,
          delayed: Boolean(rule.reached && status === 'DUE_OUT'),
          notified: notificationIndex.keys.has(key),
          notifiedAt: notificationIndex.times[key] || '',
          updatedAt: String(item.data['수정일시'] || '').trim()
        };
      })
      .filter(item => item.roomNo && item.roomStatus === 'DUE_OUT')
      .sort((a, b) => a.site.localeCompare(b.site, 'ko') || compareDepartureRoomNos_(a.roomNo, b.roomNo));

    const delayed = items.filter(item => item.delayed);
    const sites = getSiteList_();
    return {
      ok: true,
      businessDate,
      site,
      sites,
      rule,
      user: { employeeNo: user.employeeNo, role: user.role },
      summary: {
        dueOut: items.length,
        delayed: delayed.length,
        notified: delayed.filter(item => item.notified).length,
        waitingNotification: delayed.filter(item => !item.notified).length
      },
      items
    };
  });
}

function runDepartureDelayCheckNow(token) { // (DB cron 운영현황 수동 조회 · DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4)
  requireRole_(token, ['ADMIN', 'ORDER']);
  const businessDate = Utilities.formatDate(new Date(), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
  const result = getDepartureDelayDashboard(token, { businessDate, site: '' });
  return Object.assign({}, result, {
    message: '퇴실지연 자동점검은 DB에서 5분 주기로 실행됩니다. 현재 DB 현황을 조회했습니다.'
  });
}

function getDepartureDelayRule_(businessDate, now) { // (주중·주말 퇴실·알림 기준 계산)
  const dateText = normalizeBusinessDate_(businessDate);
  const day = new Date(`${dateText}T12:00:00+09:00`).getUTCDay();
  const weekend = day === 0 || day === 6;
  const checkoutTime = weekend
    ? getDepartureDelaySetting_('WEEKEND_CHECKOUT', NOVA.DEPARTURE_DELAY.WEEKEND_CHECKOUT)
    : getDepartureDelaySetting_('WEEKDAY_CHECKOUT', NOVA.DEPARTURE_DELAY.WEEKDAY_CHECKOUT);
  const alertTime = weekend
    ? getDepartureDelaySetting_('WEEKEND_ALERT', NOVA.DEPARTURE_DELAY.WEEKEND_ALERT)
    : getDepartureDelaySetting_('WEEKDAY_ALERT', NOVA.DEPARTURE_DELAY.WEEKDAY_ALERT);
  const today = Utilities.formatDate(now || new Date(), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
  let reached = false;
  if (dateText < today) reached = true;
  else if (dateText === today) {
    const current = Utilities.formatDate(now || new Date(), NOVA.TIMEZONE, 'HH:mm');
    reached = current >= alertTime;
  }
  return {
    businessDate: dateText,
    weekend,
    dayType: weekend ? '주말' : '주중',
    checkoutTime,
    alertTime,
    reached
  };
}

function resolveDepartureDelayTelegramRecipients_(site) { // (퇴실지연 알림 대상 선정)
  const allowedRoles = new Set(['ADMIN', 'ORDER', 'PUBLIC']);
  return Array.from(new Set(
    getUserIndex_().active
      .filter(user => allowedRoles.has(String(user.role || '').toUpperCase()))
      .filter(user => {
        const role = String(user.role || '').toUpperCase();
        return ['ADMIN', 'ORDER'].includes(role) || !site || !user.defaultSite || user.defaultSite === site;
      })
      .filter(user => telegramRecipientAllowed_(user, 'DEPARTURE_DELAY'))
      .map(user => String(user.telegramId || '').trim())
      .filter(Boolean)
  ));
}

function getDepartureDelayNotificationIndex_(businessDate) { // (업무일자별 퇴실지연 발송기록 조회)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const keys = new Set();
  const times = {};
  if (sheet.getLastRow() < 2) return { keys, times };
  const headerMap = getHeaderMap_(sheet);
  const rowCount = Math.min(sheet.getLastRow() - 1, NOVA.DEPARTURE_DELAY.HISTORY_SCAN_ROWS);
  const startRow = sheet.getLastRow() - rowCount + 1;
  const values = sheet.getRange(startRow, 1, rowCount, sheet.getLastColumn()).getDisplayValues();
  values.forEach(row => {
    const data = rowObjectFromValues_(row, headerMap);
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.DEPARTURE_DELAY) return;
    if (String(data['업무일자'] || '').trim() !== businessDate) return;
    if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') return;
    const key = departureDelayKey_(businessDate, data['사업장'], data['객실번호']);
    keys.add(key);
    times[key] = String(data['등록일시'] || '').trim();
  });
  return { keys, times };
}

function buildDepartureDelayTelegramMessage_(businessDate, site, rooms, rule) { // (퇴실지연 텔레그램 문구)
  const roomNos = rooms.map(room => room.roomNo);
  const preview = roomNos.slice(0, 120).join(', ');
  const more = roomNos.length > 120 ? ` 외 ${roomNos.length - 120}실` : '';
  return [
    '[NOVA 퇴실지연 알림]',
    '',
    `업무일자: ${businessDate}`,
    `사업장: ${site}`,
    `${rule.dayType} 퇴실기준: ${rule.checkoutTime}`,
    `지연 확인시간: ${rule.alertTime}`,
    '',
    `퇴실 미확인: ${rooms.length}실`,
    preview + more,
    '',
    '통합 인디케이터에서 퇴실 여부를 확인해 주세요.'
  ].join('\n');
}

function departureDelayKey_(businessDate, site, roomNo) { // (퇴실지연 중복방지 키)
  return [String(businessDate || '').trim(), String(site || '').trim(), String(roomNo || '').trim()].join('|');
}

function compareDepartureRoomNos_(a, b) { // (퇴실지연 객실번호 정렬)
  const an = Number(String(a || '').replace(/\D/g, ''));
  const bn = Number(String(b || '').replace(/\D/g, ''));
  if (Number.isFinite(an) && Number.isFinite(bn) && an !== bn) return an - bn;
  return String(a || '').localeCompare(String(b || ''), 'ko');
}

function departureDelayCheckMessage_(result) { // (수동 점검 결과 문구)
  if (!result || !result.ok) return '퇴실지연 점검을 실행하지 못했습니다.';
  if (result.reason === 'BEFORE_ALERT_TIME') return `${result.rule.dayType} 알림 기준 ${result.rule.alertTime} 이전입니다.`;
  if (result.reason === 'LOCKED') return '다른 퇴실지연 점검이 진행 중입니다.';
  if (!result.notifiedRooms) return '새로 알림할 퇴실지연 객실이 없습니다.';
  return `퇴실지연 ${result.notifiedRooms}실의 알림을 등록했습니다.`;
}
