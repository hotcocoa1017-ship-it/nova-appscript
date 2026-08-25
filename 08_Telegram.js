/**
 * 텔레그램 ID는 사용자계정 시트에서만 조회하며, 하우스맨 신규 알림은 즉시 발송하고 실패·재알림만 업무이력 큐로 처리
 */
function prepareHousemanOrderFastTelegramRows_(sheet, order, eventName, options) { // (하우스맨 신규오더 고속응답용 텔레그램 큐·재알림 행 생성)
  const event = String(eventName || '').trim().toUpperCase();
  if (!['CREATED', 'ASSIGN'].includes(event)) {
    return { rows: [], queueRecordId: '', queueRowNumber: 0, reminderRecordId: '', reminderRowNumber: 0, reason: 'STATUS_NOTIFICATION_DISABLED' };
  }

  const recipients = resolveHousemanTelegramRecipients_(order);
  if (!recipients.length) {
    return { rows: [], queueRecordId: '', queueRowNumber: 0, reminderRecordId: '', reminderRowNumber: 0, reason: 'NO_RECIPIENT' };
  }

  const safeOptions = options || {};
  const firstRowNumber = Number(safeOptions.firstRowNumber || 0);
  const now = nowText_();
  const version = Number(order.version || getDataVersion_());
  const message = buildHousemanTelegramMessage_(order, event);
  const queueRecordId = `TG-${Utilities.getUuid()}`;
  const rows = [createRowByHeaders_(sheet, {
    '기록ID': queueRecordId,
    '기록구분': NOVA.RECORD_TYPES.TELEGRAM_QUEUE,
    '업무일자': order.businessDate || businessDateText_(),
    '사업장': order.site || '',
    '객실번호': order.roomNo || '',
    '처리상태': 'QUEUED',
    '세부내용JSON': JSON.stringify({
      recipients,
      message,
      notificationType: 'HOUSEMAN_ORDER',
      eventName: event,
      parentRecordId: order.orderId,
      fastDispatch: true
    }),
    '등록사번': order.registeredBy || '',
    '등록일시': now,
    '수정일시': now,
    '변경버전': version,
    '삭제여부': 'N'
  })];

  let reminderRecordId = '';
  let reminderRowNumber = 0;
  const sharedCandidates = String(order.statusCode || '').toUpperCase() === 'ASSIGNED' && order.routeLocked !== true
    ? (Array.isArray(order.routeCandidateEmployeeNos) ? order.routeCandidateEmployeeNos : [])
    : [];
  const targetEmployeeNos = Array.from(new Set(
    (sharedCandidates.length ? sharedCandidates : [order.assignedEmployeeNo])
      .map(String).map(value => value.trim()).filter(Boolean)
  ));
  if (targetEmployeeNos.length) {
    const users = targetEmployeeNos
      .map(employeeNo => getActiveUserByEmployeeNo_(employeeNo))
      .filter(user => user && telegramRecipientAllowed_(user, 'HOUSEMAN_ORDER'));
    const reminderRecipients = Array.from(new Set(users.map(user => String(user.telegramId || '').trim()).filter(Boolean)));
    if (reminderRecipients.length) {
      reminderRecordId = `TGR-${Utilities.getUuid()}`;
      const dueAtEpochMs = Date.now() + (Number(NOVA.HOUSEMAN_TELEGRAM_REMINDER_MINUTES || 3) * 60 * 1000);
      rows.push(createRowByHeaders_(sheet, {
        '기록ID': reminderRecordId,
        '기록구분': NOVA.RECORD_TYPES.TELEGRAM_QUEUE,
        '업무일자': order.businessDate || businessDateText_(),
        '사업장': order.site || '',
        '객실번호': order.roomNo || '',
        '대상사번': targetEmployeeNos[0] || '',
        '처리상태': 'WAITING',
        '세부내용JSON': JSON.stringify({
          recipients: reminderRecipients,
          notificationType: 'HOUSEMAN_ORDER',
          eventName: 'REMINDER',
          parentRecordId: order.orderId,
          expectedAssignedEmployeeNo: order.assignedEmployeeNo || '',
          expectedCandidateEmployeeNos: targetEmployeeNos,
          dueAtEpochMs
        }),
        '등록사번': order.registeredBy || '',
        '등록일시': now,
        '수정일시': now,
        '변경버전': version,
        '삭제여부': 'N'
      }));
      reminderRowNumber = firstRowNumber > 0 ? firstRowNumber + 1 : 0;
    }
  }

  return {
    rows,
    queueRecordId,
    queueRowNumber: firstRowNumber,
    reminderRecordId,
    reminderRowNumber,
    recipientCount: recipients.length
  };
}

function findTelegramQueueRowById_(sheet, recordId, preferredRowNumber) { // (텔레그램 큐 단건 조회)
  const id = String(recordId || '').trim();
  if (!id) return null;
  const headerMap = getHeaderMap_(sheet);
  const lastRow = sheet.getLastRow();
  const lastColumn = sheet.getLastColumn();
  const readRow = rowNumber => {
    if (!Number.isInteger(rowNumber) || rowNumber < 2 || rowNumber > lastRow) return null;
    const row = sheet.getRange(rowNumber, 1, 1, lastColumn).getDisplayValues()[0];
    const data = rowObjectFromValues_(row, headerMap);
    if (String(data['기록ID'] || '').trim() !== id || data['기록구분'] !== NOVA.RECORD_TYPES.TELEGRAM_QUEUE) return null;
    return { rowNumber, row, data, headerMap };
  };

  const direct = readRow(Number(preferredRowNumber || 0));
  if (direct) return direct;
  const idColumn = headerMap['기록ID'];
  if (!idColumn || lastRow < 2) return null;
  const match = sheet.getRange(2, idColumn, lastRow - 1, 1).createTextFinder(id).matchEntireCell(true).findNext();
  return match ? readRow(match.getRow()) : null;
}

function dispatchHousemanOrderTelegramFast(token, payload) { // (신규오더 저장응답 후 텔레그램 즉시발송·큐 폴백)
  requireRole_(token, ['ADMIN', 'ORDER']);
  const safe = payload || {};
  const recordId = String(safe.recordId || '').trim();
  if (!recordId) return { ok: true, skipped: true, reason: 'NO_QUEUE_RECORD' };

  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(Number(NOVA.WRITE_LOCK_TIMEOUT_MS || 2500))) {
    return { ok: true, queued: true, reason: 'LOCK_BUSY_QUEUE_FALLBACK' };
  }

  let found;
  let detail = {};
  try {
    found = findTelegramQueueRowById_(sheet, recordId, safe.rowNumber);
    if (!found) return { ok: true, skipped: true, reason: 'QUEUE_RECORD_NOT_FOUND' };
    const status = String(found.data['처리상태'] || '').trim().toUpperCase();
    if (status === 'SENT') return { ok: true, alreadySent: true };
    if (!['QUEUED', 'PARTIAL', 'ERROR', 'SENDING'].includes(status)) {
      return { ok: true, skipped: true, reason: `QUEUE_STATUS_${status || 'EMPTY'}` };
    }
    try { detail = JSON.parse(String(found.data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    const sendingAtEpochMs = Number(detail.sendingAtEpochMs || 0);
    if (status === 'SENDING' && sendingAtEpochMs && Date.now() - sendingAtEpochMs < 30000) {
      return { ok: true, inFlight: true };
    }
    const recipients = Array.isArray(detail.recipients) ? detail.recipients.map(String).map(value => value.trim()).filter(Boolean) : [];
    const message = String(detail.message || '');
    if (!recipients.length || !message) {
      updateRowByHeaders_(sheet, found.rowNumber, { '처리상태': 'SKIPPED', '추가내용': '발송 대상 또는 메시지 없음', '수정일시': nowText_() });
      return { ok: true, skipped: true, reason: 'NO_RECIPIENT_OR_MESSAGE' };
    }
    detail.sendingAtEpochMs = Date.now();
    updateRowByHeaders_(sheet, found.rowNumber, {
      '처리상태': 'SENDING',
      '세부내용JSON': JSON.stringify(detail),
      '수정일시': nowText_()
    });
  } finally {
    lock.releaseLock();
  }

  const recipients = Array.isArray(detail.recipients) ? detail.recipients : [];
  const message = String(detail.message || '');
  const immediate = sendTelegramImmediateMany_(recipients, message);

  const finishLock = LockService.getScriptLock();
  finishLock.waitLock(10000); // 화면 응답과 분리된 후처리이므로 발송 결과 기록은 반드시 완료
  try {
    const refreshed = findTelegramQueueRowById_(sheet, recordId, found && found.rowNumber);
    if (!refreshed) return { ok: true, queued: true, reason: 'QUEUE_RECORD_MISSING_AFTER_SEND' };
    let refreshedDetail = {};
    try { refreshedDetail = JSON.parse(String(refreshed.data['세부내용JSON'] || '{}')); } catch (error) { refreshedDetail = {}; }
    delete refreshedDetail.sendingAtEpochMs;
    const failedRecipients = Array.isArray(immediate.failedRecipients) ? immediate.failedRecipients : [];
    refreshedDetail.recipients = failedRecipients;
    const success = failedRecipients.length === 0;
    updateRowByHeaders_(sheet, refreshed.rowNumber, {
      '처리상태': success ? 'SENT' : 'QUEUED',
      '세부내용JSON': JSON.stringify(refreshedDetail),
      '추가내용': success
        ? `즉시발송 ${Number(immediate.sentCount || 0)}건`
        : `즉시발송 성공 ${Number(immediate.sentCount || 0)}건 · 실패 ${failedRecipients.length}건 큐 재시도`,
      '완료일시': success ? nowText_() : '',
      '처리불가사유': success ? '' : String(immediate.reason || ''),
      '수정일시': nowText_()
    });
    return {
      ok: true,
      queued: !success,
      immediateSent: Number(immediate.sentCount || 0),
      immediateFailed: failedRecipients.length
    };
  } finally {
    finishLock.releaseLock();
  }
}

function queueHousemanOrderTelegram_(order, eventName) { // (하우스맨 신규·직원배정 즉시 알림)
  const event = String(eventName || '').trim().toUpperCase();
  if (!['CREATED', 'ASSIGN'].includes(event)) {
    return { queued: false, reason: 'STATUS_NOTIFICATION_DISABLED' };
  }

  const recipients = resolveHousemanTelegramRecipients_(order);
  if (!recipients.length) return { queued: false, reason: 'NO_RECIPIENT' };
  const message = buildHousemanTelegramMessage_(order, event);
  const immediate = sendTelegramImmediateMany_(recipients, message);

  // 즉시 발송 실패 수신자만 기존 1분 큐에서 재시도합니다.
  if (immediate.failedRecipients.length) {
    queueTelegramNotification_({
      notificationType: 'HOUSEMAN_ORDER',
      businessDate: order.businessDate,
      site: order.site,
      roomNo: order.roomNo,
      recipients: immediate.failedRecipients,
      message,
      eventName: event,
      parentRecordId: order.orderId,
      registeredBy: order.registeredBy || '',
      version: order.version || getDataVersion_()
    });
  }

  // 3분 재알림은 실제 읽음 영수증이 아니라 담당자의 NOVA 접수 여부로 판정합니다.
  const reminder = scheduleHousemanOrderReminder_(order);
  return {
    queued: immediate.failedRecipients.length > 0,
    immediateSent: immediate.sentCount,
    immediateFailed: immediate.failedRecipients.length,
    reminderScheduled: Boolean(reminder && reminder.scheduled)
  };
}

function sendTelegramImmediateMany_(recipients, message) { // (하우스맨 오더 Telegram 즉시 발송)
  const unique = Array.from(new Set((recipients || []).map(String).map(value => value.trim()).filter(Boolean)));
  if (!unique.length || !message) return { ok: false, sentCount: 0, failedRecipients: unique };
  const token = String(PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN') || '').trim();
  if (!token) return { ok: false, sentCount: 0, failedRecipients: unique, reason: 'TOKEN_MISSING' };

  try {
    const requests = unique.map(chatId => ({
      url: `https://api.telegram.org/bot${token}/sendMessage`,
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: String(message) }),
      muteHttpExceptions: true
    }));
    const responses = UrlFetchApp.fetchAll(requests);
    const failedRecipients = [];
    responses.forEach((response, index) => {
      const code = response.getResponseCode();
      let body = {};
      try { body = JSON.parse(response.getContentText() || '{}'); } catch (error) { body = {}; }
      if (code < 200 || code >= 300 || body.ok === false) failedRecipients.push(unique[index]);
    });
    return { ok: failedRecipients.length === 0, sentCount: unique.length - failedRecipients.length, failedRecipients };
  } catch (error) {
    return { ok: false, sentCount: 0, failedRecipients: unique, reason: error.message };
  }
}

function scheduleHousemanOrderReminder_(order) { // (공동 전달 대상 전체 3분 미접수 재알림 예약)
  if (!order || !order.orderId) return { scheduled: false, reason: 'UNASSIGNED' };
  const sharedCandidates = String(order.statusCode || '').toUpperCase() === 'ASSIGNED' && order.routeLocked !== true
    ? (Array.isArray(order.routeCandidateEmployeeNos) ? order.routeCandidateEmployeeNos : [])
    : [];
  const targetEmployeeNos = Array.from(new Set(
    (sharedCandidates.length ? sharedCandidates : [order.assignedEmployeeNo])
      .map(String).map(value => value.trim()).filter(Boolean)
  ));
  if (!targetEmployeeNos.length) return { scheduled: false, reason: 'UNASSIGNED' };
  const users = targetEmployeeNos
    .map(employeeNo => getActiveUserByEmployeeNo_(employeeNo))
    .filter(user => user && telegramRecipientAllowed_(user, 'HOUSEMAN_ORDER'));
  const recipients = Array.from(new Set(users.map(user => String(user.telegramId || '').trim()).filter(Boolean)));
  if (!recipients.length) return { scheduled: false, reason: 'USER_NOT_ELIGIBLE' };

  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const version = Number(order.version || getDataVersion_());
  const recordId = `TGR-${Utilities.getUuid()}`;
  const now = nowText_();
  const dueAtEpochMs = Date.now() + (Number(NOVA.HOUSEMAN_TELEGRAM_REMINDER_MINUTES || 3) * 60 * 1000);
  const row = createRowByHeaders_(sheet, {
    '기록ID': recordId,
    '기록구분': NOVA.RECORD_TYPES.TELEGRAM_QUEUE,
    '업무일자': order.businessDate || businessDateText_(),
    '사업장': order.site || '',
    '객실번호': order.roomNo || '',
    '대상사번': targetEmployeeNos[0] || '',
    '처리상태': 'WAITING',
    '세부내용JSON': JSON.stringify({
      recipients,
      notificationType: 'HOUSEMAN_ORDER',
      eventName: 'REMINDER',
      parentRecordId: order.orderId,
      expectedAssignedEmployeeNo: order.assignedEmployeeNo || '',
      expectedCandidateEmployeeNos: targetEmployeeNos,
      dueAtEpochMs
    }),
    '등록사번': order.registeredBy || '',
    '등록일시': now,
    '수정일시': now,
    '변경버전': version,
    '삭제여부': 'N'
  });
  const rowNumber = sheet.getLastRow() + 1;
  ensureSheetRowCapacity_(sheet, rowNumber);
  sheet.getRange(rowNumber, 1, 1, row.length).setValues([row]);
  return { scheduled: true, dueAtEpochMs, targetEmployeeNos };
}

function queueTelegramNotification_(payload) { // (공통 텔레그램 비동기 큐 등록)
  const safe = payload || {};
  const notificationType = String(safe.notificationType || 'GENERAL').trim().toUpperCase();
  const allowedIds = new Set(
    getUserIndex_().active
      .filter(user => telegramRecipientAllowed_(user, notificationType))
      .map(user => String(user.telegramId || '').trim())
      .filter(Boolean)
  );
  const recipients = Array.from(new Set(
    (safe.recipients || []).map(String).map(value => value.trim()).filter(value => value && allowedIds.has(value))
  ));
  if (!recipients.length || !safe.message) return { queued: false, reason: 'NO_RECIPIENT' };
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const now = nowText_();
  const row = createRowByHeaders_(sheet, {
    '기록ID': `TG-${Utilities.getUuid()}`,
    '기록구분': NOVA.RECORD_TYPES.TELEGRAM_QUEUE,
    '업무일자': safe.businessDate || businessDateText_(),
    '사업장': safe.site || '',
    '객실번호': safe.roomNo || '',
    '처리상태': 'QUEUED',
    '세부내용JSON': JSON.stringify({
      recipients,
      message: safe.message,
      notificationType: safe.notificationType || 'GENERAL',
      eventName: safe.eventName || '',
      parentRecordId: safe.parentRecordId || ''
    }),
    '등록사번': safe.registeredBy || '',
    '등록일시': now,
    '수정일시': now,
    '변경버전': safe.version || getDataVersion_(),
    '삭제여부': 'N'
  });
  const rowNumber = sheet.getLastRow() + 1;
  ensureSheetRowCapacity_(sheet, rowNumber);
  sheet.getRange(rowNumber, 1, 1, row.length).setValues([row]);
  return { queued: true, count: recipients.length };
}

function telegramRecipientAllowed_(user, notificationType) { // (직무별 텔레그램 수신 정책)
  if (!user || !user.enabled || !user.telegramEnabled || !user.telegramId) return false;
  const role = String(user.role || '').toUpperCase();
  if (!isTelegramRoleEnabled_(role)) return false;
  if (role === 'PUBLIC') return String(notificationType || '').toUpperCase() === 'DEPARTURE_DELAY';
  return true;
}

function queueTelegramNotificationsBatch_(payloads) { // (텔레그램 알림큐 다건 일괄등록)
  const items = Array.isArray(payloads) ? payloads : [];
  if (!items.length) return { queued: false, count: 0, recipientCount: 0, reason: 'NO_PAYLOAD' };
  const activeUsers = getUserIndex_().active;
  const allowedByType = {};
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const now = nowText_();
  let recipientCount = 0;
  const rows = [];

  items.forEach(item => {
    const safe = item || {};
    const notificationType = String(safe.notificationType || 'GENERAL').trim().toUpperCase();
    if (!allowedByType[notificationType]) {
      allowedByType[notificationType] = new Set(activeUsers
        .filter(user => telegramRecipientAllowed_(user, notificationType))
        .map(user => String(user.telegramId || '').trim()).filter(Boolean));
    }
    const recipients = Array.from(new Set((safe.recipients || [])
      .map(value => String(value || '').trim())
      .filter(value => value && allowedByType[notificationType].has(value))));
    if (!recipients.length || !safe.message) return;
    recipientCount += recipients.length;
    rows.push(createRowByHeaders_(sheet, {
      '기록ID': `TG-${Utilities.getUuid()}`,
      '기록구분': NOVA.RECORD_TYPES.TELEGRAM_QUEUE,
      '업무일자': safe.businessDate || businessDateText_(),
      '사업장': safe.site || '',
      '객실번호': safe.roomNo || '',
      '처리상태': 'QUEUED',
      '세부내용JSON': JSON.stringify({
        recipients,
        message: safe.message,
        notificationType: safe.notificationType || 'GENERAL',
        eventName: safe.eventName || '',
        parentRecordId: safe.parentRecordId || ''
      }),
      '등록사번': safe.registeredBy || '',
      '등록일시': now,
      '수정일시': now,
      '변경버전': safe.version || getDataVersion_(),
      '삭제여부': 'N'
    }));
  });

  if (!rows.length) return { queued: false, count: 0, recipientCount: 0, reason: 'NO_RECIPIENT' };
  const startRow = sheet.getLastRow() + 1;
  ensureSheetRowCapacity_(sheet, startRow + rows.length - 1);
  sheet.getRange(startRow, 1, rows.length, rows[0].length).setValues(rows);
  return { queued: true, count: rows.length, recipientCount };
}

function telegramRecipientsForUsers_(users, notificationType) { // (직원목록 텔레그램 수신자 변환)
  return Array.from(new Set((Array.isArray(users) ? users : [users])
    .filter(user => telegramRecipientAllowed_(user, notificationType))
    .map(user => String(user.telegramId || '').trim()).filter(Boolean)));
}

function telegramRoomOperationFlags_(payload) { // (텔레그램 객실 중요표시 목록)
  const safe = payload || {};
  return [
    safe.preassigned ? '선배정' : '',
    safe.vip ? 'VIP' : '',
    safe.importantRoom ? '중요객실' : ''
  ].filter(Boolean);
}

function telegramRoomOperationFlagsLine_(payload) { // (텔레그램 객실 중요표시 문구)
  const flags = telegramRoomOperationFlags_(payload);
  return flags.length ? `🚨 중요표시: ${flags.join(' · ')}` : '중요표시: 없음';
}

function telegramRoomOperationFlagsSuffix_(payload) { // (텔레그램 다수객실 중요표시 축약)
  const flags = telegramRoomOperationFlags_(payload);
  return flags.length ? ` [🚨 ${flags.join('·')}]` : '';
}

function telegramUrgentTitle_(label) { // (텔레그램 긴급 제목)
  return `🚨 [NOVA ${String(label || '').trim()}]`;
}

function queueRoommaidAssignmentCancellationTelegram_(payload) { // (룸메이드 객실배정 취소 알림)
  const safe = payload || {};
  const recipients = telegramRecipientsForUsers_(safe.targetUsers, 'ROOMMAID_ASSIGNMENT_CANCEL');
  const typeLabel = getRoommaidCleaningTypeLabel_(String(safe.cleaningType || NOVA.CLEANING_TYPES.NORMAL).toUpperCase());
  const assignmentLabel = roommaidAssignmentTypeLabel_(safe.assignmentType);
  return queueTelegramNotification_({
    notificationType: 'ROOMMAID_ASSIGNMENT_CANCEL',
    businessDate: safe.businessDate, site: safe.site, roomNo: safe.roomNo, recipients,
    message: [
      telegramUrgentTitle_('객실 배정 취소'),
      `${safe.site || '-'} / ${safe.roomNo || '-'}호`,
      telegramRoomOperationFlagsLine_(safe),
      `업무: ${typeLabel}`,
      `기존 배정: ${assignmentLabel}`,
      `업무일자: ${safe.businessDate || '-'}`,
      '해당 객실의 룸메이드 배정이 취소되었습니다.'
    ].join('\n'),
    eventName: 'ROOMMAID_ASSIGNMENT_CANCELLED',
    registeredBy: safe.registeredBy || '', version: safe.version
  });
}

function queueQmAssignmentCancellationTelegram_(payload) { // (QM 객실배정 취소 알림)
  const safe = payload || {};
  const recipients = telegramRecipientsForUsers_(safe.targetUser, 'QM_ASSIGNMENT_CANCEL');
  return queueTelegramNotification_({
    notificationType: 'QM_ASSIGNMENT_CANCEL',
    businessDate: safe.businessDate, site: safe.site, roomNo: safe.roomNo, recipients,
    message: [
      telegramUrgentTitle_('QM 배정 취소'),
      `${safe.site || '-'} / ${safe.roomNo || '-'}호`,
      telegramRoomOperationFlagsLine_(safe),
      `업무일자: ${safe.businessDate || '-'}`,
      '해당 객실의 QM 점검 배정이 취소되었습니다.'
    ].join('\n'),
    eventName: 'QM_ASSIGNMENT_CANCELLED',
    registeredBy: safe.registeredBy || '', version: safe.version
  });
}

function queueRoommaidDepartureConfirmedTelegram_(payload) { // (퇴실예정에서 퇴실 전환 룸메이드 알림)
  const safe = payload || {};
  const recipients = telegramRecipientsForUsers_(safe.targetUsers, 'ROOMMAID_DEPARTURE_CONFIRMED');
  const typeLabel = getRoommaidCleaningTypeLabel_(String(safe.cleaningType || NOVA.CLEANING_TYPES.NORMAL).toUpperCase());
  return queueTelegramNotification_({
    notificationType: 'ROOMMAID_DEPARTURE_CONFIRMED',
    businessDate: safe.businessDate, site: safe.site, roomNo: safe.roomNo, recipients,
    message: [
      telegramUrgentTitle_('객실 퇴실 확인'),
      `${safe.site || '-'} / ${safe.roomNo || '-'}호`,
      telegramRoomOperationFlagsLine_(safe),
      '객실상태: 퇴실예정 → 퇴실',
      `업무: ${typeLabel}`,
      `업무일자: ${safe.businessDate || '-'}`,
      '정비 가능한 퇴실객실로 변경되었습니다.'
    ].join('\n'),
    eventName: 'DUE_OUT_TO_CHECKED_OUT',
    registeredBy: safe.registeredBy || '', version: safe.version
  });
}

function queueRoommaidOperationFlagsTelegram_(payload) { // (VIP·선배정·중요객실 변경 룸메이드 알림)
  const safe = payload || {};
  const recipients = telegramRecipientsForUsers_(safe.targetUsers, 'ROOMMAID_OPERATION_FLAGS');
  const changes = [];
  if (Boolean(safe.previousPreassigned) !== Boolean(safe.preassigned)) changes.push(`선배정 ${safe.preassigned ? '지정' : '해제'}`);
  if (Boolean(safe.previousVip) !== Boolean(safe.vip)) changes.push(`VIP ${safe.vip ? '지정' : '해제'}`);
  if (Boolean(safe.previousImportantRoom) !== Boolean(safe.importantRoom)) changes.push(`중요객실 ${safe.importantRoom ? '지정' : '해제'}`);
  if (!changes.length) return { queued: false, reason: 'NO_CHANGE' };
  return queueTelegramNotification_({
    notificationType: 'ROOMMAID_OPERATION_FLAGS',
    businessDate: safe.businessDate, site: safe.site, roomNo: safe.roomNo, recipients,
    message: [
      telegramUrgentTitle_('객실 중요정보 변경'),
      `${safe.site || '-'} / ${safe.roomNo || '-'}호`,
      `🚨 변경: ${changes.join(' · ')}`,
      telegramRoomOperationFlagsLine_(safe),
      `업무일자: ${safe.businessDate || '-'}`
    ].join('\n'),
    eventName: 'ROOM_OPERATION_FLAGS_CHANGED',
    registeredBy: safe.registeredBy || '', version: safe.version
  });
}

function queueRoommaidDepartureStatusBulkTelegrams_(items, context) { // (객실업로드 퇴실확정 룸메이드별 요약 알림)
  const safe = context || {};
  const groups = {};
  (Array.isArray(items) ? items : []).forEach(item => {
    const roomNo = String(item && item.roomNo || '').trim();
    if (!roomNo) return;
    const cleaningType = String(item.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
    Array.from(new Set((item.employeeNos || []).map(value => String(value || '').trim()).filter(Boolean))).forEach(employeeNo => {
      if (!groups[employeeNo]) groups[employeeNo] = { employeeNo, rooms: [] };
      groups[employeeNo].rooms.push({
        roomNo,
        cleaningType,
        preassigned: Boolean(item.preassigned),
        vip: Boolean(item.vip),
        importantRoom: Boolean(item.importantRoom)
      });
    });
  });

  const payloads = [];
  Object.values(groups).forEach(group => {
    const target = safe.usersByEmployeeNo && safe.usersByEmployeeNo[group.employeeNo];
    const recipients = telegramRecipientsForUsers_(target, 'ROOMMAID_DEPARTURE_CONFIRMED');
    if (!recipients.length) return;
    const rooms = group.rooms.slice().sort((a, b) => a.roomNo.localeCompare(b.roomNo, 'ko'));
    const preview = rooms.slice(0, 40).map(room => `${room.roomNo}호${telegramRoomOperationFlagsSuffix_(room)}`).join(', ');
    const more = rooms.length > 40 ? ` 외 ${rooms.length - 40}실` : '';
    payloads.push({
      notificationType: 'ROOMMAID_DEPARTURE_CONFIRMED',
      businessDate: safe.businessDate,
      site: safe.site,
      recipients,
      message: [
        telegramUrgentTitle_('퇴실예정 → 퇴실 변경'),
        `업무일자: ${safe.businessDate || '-'}`,
        `사업장: ${safe.site || '-'}`,
        `변경객실: ${rooms.length}실`,
        preview + more,
        '배정된 객실이 정비 가능한 퇴실상태로 변경되었습니다.'
      ].join('\n'),
      eventName: 'UPLOAD_DUE_OUT_TO_CHECKED_OUT',
      registeredBy: safe.registeredBy || '',
      version: safe.version
    });
  });

  const result = queueTelegramNotificationsBatch_(payloads);
  return {
    queued: Boolean(result && result.queued),
    count: Number(result && result.count || 0),
    warnings: result && result.reason && result.reason !== 'NO_PAYLOAD' && result.reason !== 'NO_RECIPIENT'
      ? [`퇴실변경 알림 일괄등록 실패: ${result.reason}`]
      : []
  };
}


function queueCleaningAssignmentTelegram_(payload) { // (룸메이드 일반정비·D/S·2인1조 배정 알림)
  const safe = payload || {};
  const target = safe.targetUser;
  const typeCode = String(safe.cleaningType || NOVA.CLEANING_TYPES.NORMAL).toUpperCase();
  const typeLabel = getRoommaidCleaningTypeLabel_(typeCode);
  const assignmentType = String(safe.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).toUpperCase();
  const assignmentLabel = roommaidAssignmentTypeLabel_(assignmentType);
  const roleLabel = safe.assignmentRole === 'SECONDARY' ? '보조담당' : '주담당';
  const recipients = telegramRecipientAllowed_(target, 'ROOMMAID_ASSIGNMENT') ? [target.telegramId] : [];
  return queueTelegramNotification_({
    notificationType: 'ROOMMAID_ASSIGNMENT', businessDate: safe.businessDate, site: safe.site, roomNo: safe.roomNo, recipients,
    message: [
      telegramUrgentTitle_('룸메이드 배정'),
      `${safe.site || '-'} / ${safe.roomNo || '-'}호`,
      telegramRoomOperationFlagsLine_(safe),
      `업무: ${typeLabel}`,
      `배정: ${assignmentLabel}${assignmentType === NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO ? '' : ` · ${roleLabel}`}`,
      `업무일자: ${safe.businessDate || '-'}`,
      `담당: ${target ? target.name : '-'}`
    ].join('\n'),
    eventName: typeCode === NOVA.CLEANING_TYPES.DS ? 'DS_ASSIGNED' : 'CLEANING_ASSIGNED',
    registeredBy: safe.registeredBy || '', version: safe.version
  });
}

function queueRoommaidBulkAssignmentTelegram_(payload) { // (최초 다수 객실 배정 요약 알림)
  const safe = payload || {};
  const roomNos = Array.from(new Set((safe.roomNos || []).map(String).map(value => value.trim()).filter(Boolean))).sort();
  if (!roomNos.length) return { queued: false, reason: 'NO_ROOMS' };
  const typeCode = String(safe.cleaningType || NOVA.CLEANING_TYPES.NORMAL).toUpperCase();
  const typeLabel = getRoommaidCleaningTypeLabel_(typeCode);
  const assignmentType = String(safe.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).toUpperCase();
  const assignmentLabel = roommaidAssignmentTypeLabel_(assignmentType);
  const preview = roomNos.slice(0, 40).join(', ');
  const more = roomNos.length > 40 ? ` 외 ${roomNos.length - 40}실` : '';
  const targets = [{ user: safe.primaryUser, roleLabel: '주담당' }, { user: safe.secondaryUser, roleLabel: '보조담당' }].filter(item => item.user);
  let queued = 0;
  targets.forEach(item => {
    const target = item.user;
    const recipients = telegramRecipientAllowed_(target, 'ROOMMAID_ASSIGNMENT') ? [target.telegramId] : [];
    const result = queueTelegramNotification_({
      notificationType: 'ROOMMAID_ASSIGNMENT', businessDate: safe.businessDate, site: safe.site, recipients,
      message: [
        telegramUrgentTitle_('룸메이드 최초 일괄배정'),
        `업무일자: ${safe.businessDate || '-'}`,
        `사업장: ${safe.site || '-'}`,
        telegramRoomOperationFlagsLine_(safe),
        `업무: ${typeLabel}`,
        `배정: ${assignmentLabel}${assignmentType === NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO ? '' : ` · ${item.roleLabel}`}`,
        `배정객실: ${roomNos.length}실`,
        preview + more
      ].join('\n'),
      eventName: 'ROOMMAID_BULK_ASSIGNED', registeredBy: safe.registeredBy || '', version: safe.version
    });
    if (result && result.queued) queued += 1;
  });
  return { queued: queued > 0, count: queued };
}

function roommaidAssignmentTypeLabel_(assignmentType) { // (룸메이드 배정유형 표시명)
  const type = String(assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).toUpperCase();
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR) return '2인1조';
  if (type === NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING) return '2인1조(교육)';
  return '1인 배정';
}

function queueQmAssignmentTelegram_(payload) { // (QM 점검 배정 알림)
  const safe = payload || {};
  const target = safe.targetUser;
  const recipients = telegramRecipientAllowed_(target, 'QM_ASSIGNMENT') ? [target.telegramId] : [];
  return queueTelegramNotification_({
    notificationType: 'QM_ASSIGNMENT', businessDate: safe.businessDate, site: safe.site, roomNo: safe.roomNo, recipients,
    message: [telegramUrgentTitle_('QM 점검 배정'), `${safe.site || '-'} / ${safe.roomNo || '-'}호`, telegramRoomOperationFlagsLine_(safe), `업무일자: ${safe.businessDate || '-'}`, `담당: ${target ? target.name : '-'}`].join('\n'),
    eventName: 'QM_ASSIGNED', registeredBy: safe.registeredBy || '', version: safe.version
  });
}

function queueQmReadyTelegram_(payload) { // (룸메이드 완료 후 QM 점검대기 알림)
  const safe = payload || {};
  const target = safe.targetUser;
  const recipients = telegramRecipientAllowed_(target, 'QM_READY') ? [target.telegramId] : [];
  return queueTelegramNotification_({
    notificationType: 'QM_READY', businessDate: safe.businessDate, site: safe.site, roomNo: safe.roomNo, recipients,
    message: [telegramUrgentTitle_('QM 점검대기'), `${safe.site || '-'} / ${safe.roomNo || '-'}호`, telegramRoomOperationFlagsLine_(safe), '룸메이드 정비가 완료되었습니다.'].join('\n'),
    eventName: 'QM_READY', registeredBy: safe.registeredBy || '', version: safe.version
  });
}

function queueRoommaidReworkTelegram_(payload) { // (QM 재정비 요청 룸메이드 알림)
  const safe = payload || {};
  const target = safe.targetUser;
  const recipients = telegramRecipientAllowed_(target, 'ROOMMAID_REWORK') ? [target.telegramId] : [];
  return queueTelegramNotification_({
    notificationType: 'ROOMMAID_REWORK', businessDate: safe.businessDate, site: safe.site, roomNo: safe.roomNo, recipients,
    message: [telegramUrgentTitle_('재정비 요청'), `${safe.site || '-'} / ${safe.roomNo || '-'}호`, telegramRoomOperationFlagsLine_(safe), safe.reason ? `사유: ${safe.reason}` : 'QM 재정비 요청이 등록되었습니다.'].join('\n'),
    eventName: 'REWORK', registeredBy: safe.registeredBy || '', version: safe.version
  });
}

function resolveHousemanTelegramRecipients_(order) { // (담당자·중요·인수인계 하우스맨 알림 대상)
  const active = getUserIndex_().active.filter(user => telegramRecipientAllowed_(user, 'HOUSEMAN_ORDER'));
  const selectedEmployeeNos = new Set();

  // 담당동 자동배정은 현재 실제 근무 중인 A·B 중첩조 포함 전체 담당자에게 공동 전달합니다.
  const routeCandidates = String(order.statusCode || '').toUpperCase() === 'ASSIGNED' && order.routeLocked !== true
    ? (Array.isArray(order.routeCandidateEmployeeNos) ? order.routeCandidateEmployeeNos : [])
    : [];
  if (routeCandidates.length) routeCandidates.forEach(employeeNo => selectedEmployeeNos.add(employeeNo));
  else if (order.assignedEmployeeNo) selectedEmployeeNos.add(order.assignedEmployeeNo);

  // 중요·인수인계 오더일 때만 근무조 데이터를 조회합니다.
  if (order.important || order.handover) {
    const shiftResult = getOrderShiftRecipients_(order);
    shiftResult.employeeNos.forEach(employeeNo => selectedEmployeeNos.add(employeeNo));
    if (!shiftResult.assignments.allEmployeeNos.length) {
      active.filter(user => user.role === 'HOUSEMAN').forEach(user => selectedEmployeeNos.add(user.employeeNo));
    }
  }

  const selected = active.filter(user => user.role === 'HOUSEMAN' && selectedEmployeeNos.has(user.employeeNo));
  const siteFiltered = order.site
    ? selected.filter(user => !user.defaultSite || user.defaultSite === order.site)
    : selected;
  return Array.from(new Set(siteFiltered.map(user => user.telegramId).filter(Boolean)));
}

function queueHousemanHandoverLoginDigest_(user, request, orders, shiftContext) { // (다음 근무조 로그인 인수인계 1회 전달)
  if (!user || !telegramRecipientAllowed_(user, 'HOUSEMAN_ORDER')) return { queued: false, reason: 'USER_NOT_ELIGIBLE' };
  const handoverOrders = (orders || []).filter(order => order.handover && !['COMPLETED', 'UNABLE'].includes(order.statusCode));
  if (!handoverOrders.length) return { queued: false, reason: 'NO_HANDOVER' };
  const shiftCodes = (shiftContext && shiftContext.shiftCodes || []).slice().sort();
  if (!shiftCodes.length) return { queued: false, reason: 'NO_SHIFT' };

  const siteKey = Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(request.site || 'ALL'))
  ).replace(/=+$/g, '').slice(0, 8);
  const recordId = `TGN-HANDOVER-${request.businessDate.replaceAll('-', '')}-${siteKey}-${shiftCodes.join('')}-${user.employeeNo}`;
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const headerMap = getHeaderMap_(sheet);
  const idColumn = headerMap['기록ID'];
  if (idColumn && sheet.getLastRow() >= 2) {
    const found = sheet.getRange(2, idColumn, sheet.getLastRow() - 1, 1)
      .createTextFinder(recordId).matchEntireCell(true).findNext();
    if (found) return { queued: false, reason: 'ALREADY_QUEUED' };
  }

  const version = getDataVersion_();
  appendUnifiedHistory_({
    recordId,
    recordType: NOVA.RECORD_TYPES.TELEGRAM_NOTICE,
    businessDate: request.businessDate,
    site: request.site,
    targetEmployeeNo: user.employeeNo,
    status: 'HANDOVER_LOGIN_NOTICE',
    detail: { shiftCodes, orderIds: handoverOrders.map(order => order.orderId) },
    registeredBy: user.employeeNo,
    version
  });
  const lines = handoverOrders.slice(0, 10).map(order => `• ${order.roomNo || '공용'}호 ${order.itemSummary || '-'} (${order.statusLabel || order.statusCode})`);
  if (handoverOrders.length > 10) lines.push(`외 ${handoverOrders.length - 10}건`);
  return queueTelegramNotification_({
    notificationType: 'HOUSEMAN_ORDER',
    businessDate: request.businessDate,
    site: request.site,
    recipients: [user.telegramId],
    message: [`[NOVA ${shiftCodes.join('·')}조 인수인계]`, `미완료 인수인계 ${handoverOrders.length}건`, ...lines].join('\n'),
    eventName: 'HANDOVER_LOGIN',
    parentRecordId: recordId,
    registeredBy: user.employeeNo,
    version
  });
}

function buildHousemanTelegramMessage_(order, eventName) { // (신규·배정·미접수 재알림 문구)
  const event = String(eventName || '').trim().toUpperCase();
  const title = event === 'REMINDER'
    ? '[NOVA 하우스맨 오더 · 미접수 재알림]'
    : event === 'ASSIGN'
      ? '[NOVA 하우스맨 오더 · 직원 배정]'
      : '[NOVA 하우스맨 오더 · 신규 등록]';
  const flags = [order.important ? '중요' : '', order.handover ? `인수인계(${order.handoverTargetShift || '-'}조)` : ''].filter(Boolean).join(' · ');
  return [
    title,
    event === 'REMINDER' ? `등록 후 ${NOVA.HOUSEMAN_TELEGRAM_REMINDER_MINUTES || 3}분 동안 접수되지 않았습니다.` : '',
    `${order.site || '-'} / ${order.roomNo || '-'}호`,
    `${order.part || '-'} · ${order.itemSummary || '-'}`,
    order.routeLocked !== true && Array.isArray(order.routeCandidateNames) && order.routeCandidateNames.length > 1
      ? `공동 전달: ${order.routeCandidateNames.join(' · ')} · 접수자 1명으로 고정`
      : (order.assignedName ? `담당: ${order.assignedName}` : ''),
    order.requester ? `요청자: ${order.requester}` : '',
    flags ? `구분: ${flags}` : '',
    order.note ? `내용: ${order.note}` : '',
    'NOVA에서 오더를 확인하고 접수해 주세요.'
  ].filter(Boolean).join('\n');
}

function housemanTelegramEventAllowed_(eventName) { // (하우스맨 텔레그램은 등록·배정·재알림만 허용)
  return ['CREATED', 'ASSIGN', 'REMINDER', 'HANDOVER_LOGIN'].includes(String(eventName || '').trim().toUpperCase());
}

function resolveHousemanReminderDelivery_(sheet, detail) { // (3분 후 공동 전달·미접수 상태 재확인)
  const parentRecordId = String(detail && detail.parentRecordId || '').trim();
  const expectedCandidateEmployeeNos = Array.from(new Set(
    (Array.isArray(detail && detail.expectedCandidateEmployeeNos)
      ? detail.expectedCandidateEmployeeNos
      : [detail && detail.expectedAssignedEmployeeNo])
      .map(String).map(value => value.trim()).filter(Boolean)
  ));
  if (!parentRecordId || !expectedCandidateEmployeeNos.length) return { send: false, reason: 'INVALID_REMINDER' };

  const found = findHousemanOrderRow_(sheet, parentRecordId);
  if (!found) return { send: false, reason: 'ORDER_NOT_FOUND' };
  if (String(found.data['삭제여부'] || 'N').toUpperCase() === 'Y') return { send: false, reason: 'ORDER_DELETED' };
  const order = housemanOrderObject_(found.data, found.rowNumber);
  if (order.acceptedAt || ['ACCEPTED', 'PROCESSING', 'COMPLETED', 'UNABLE'].includes(order.statusCode)) {
    return { send: false, reason: 'ORDER_ALREADY_ACCEPTED' };
  }
  if (order.statusCode !== 'ASSIGNED') return { send: false, reason: 'ORDER_NOT_ASSIGNED' };

  const currentCandidates = order.routeLocked !== true && Array.isArray(order.routeCandidateEmployeeNos) && order.routeCandidateEmployeeNos.length
    ? order.routeCandidateEmployeeNos
    : [order.assignedEmployeeNo].filter(Boolean);
  const expectedSet = new Set(expectedCandidateEmployeeNos);
  const targetEmployeeNos = Array.from(new Set(currentCandidates.filter(employeeNo => expectedSet.has(employeeNo))));
  if (!targetEmployeeNos.length) return { send: false, reason: 'ASSIGNEE_CHANGED' };
  const recipients = Array.from(new Set(targetEmployeeNos
    .map(employeeNo => getActiveUserByEmployeeNo_(employeeNo))
    .filter(user => user && telegramRecipientAllowed_(user, 'HOUSEMAN_ORDER'))
    .map(user => String(user.telegramId || '').trim())
    .filter(Boolean)));
  if (!recipients.length) return { send: false, reason: 'USER_NOT_ELIGIBLE' };
  return {
    send: true,
    recipients,
    message: buildHousemanTelegramMessage_(order, 'REMINDER')
  };
}

function processTelegramQueue() { // (텔레그램 큐·하우스맨 3분 미접수 재알림 처리)
  const token = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
  if (!token) return { ok: false, message: 'TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.' };

  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  if (sheet.getLastRow() < 2) return { ok: true, processed: 0 };
  const headerMap = getHeaderMap_(sheet);
  const startRow = Math.max(2, sheet.getLastRow() - 1000 + 1);
  const values = sheet.getRange(startRow, 1, sheet.getLastRow() - startRow + 1, sheet.getLastColumn()).getDisplayValues();
  const nowEpochMs = Date.now();
  let processed = 0;

  values.forEach((row, offset) => {
    const rowNumber = startRow + offset;
    const data = rowObjectFromValues_(row, headerMap);
    let queueStatus = String(data['처리상태'] || '').trim().toUpperCase();
    if (data['기록구분'] !== NOVA.RECORD_TYPES.TELEGRAM_QUEUE || !['QUEUED', 'WAITING', 'SENDING'].includes(queueStatus)) return;
    let detail;
    try { detail = JSON.parse(data['세부내용JSON'] || '{}'); } catch (error) { detail = {}; }
    if (queueStatus === 'SENDING') {
      const sendingAtEpochMs = Number(detail.sendingAtEpochMs || 0);
      if (sendingAtEpochMs && nowEpochMs - sendingAtEpochMs < 30000) return;
      queueStatus = 'QUEUED'; // 즉시발송 호출이 중단된 경우 30초 후 기존 큐가 복구
    }

    const notificationType = String(detail.notificationType || '').trim().toUpperCase();
    const eventName = String(detail.eventName || '').trim().toUpperCase();
    if (notificationType === 'HOUSEMAN_ORDER' && !housemanTelegramEventAllowed_(eventName)) {
      updateRowByHeaders_(sheet, rowNumber, {
        '처리상태': 'SKIPPED',
        '추가내용': '하우스맨 처리상태 알림 비활성',
        '수정일시': nowText_()
      });
      return;
    }

    let recipients = Array.isArray(detail.recipients) ? detail.recipients : [];
    let message = String(detail.message || '');
    if (queueStatus === 'WAITING') {
      const dueAtEpochMs = Number(detail.dueAtEpochMs || 0);
      if (!dueAtEpochMs || nowEpochMs < dueAtEpochMs) return;
      const reminder = resolveHousemanReminderDelivery_(sheet, detail);
      if (!reminder.send) {
        updateRowByHeaders_(sheet, rowNumber, {
          '처리상태': 'SKIPPED',
          '추가내용': reminder.reason || '재알림 취소',
          '수정일시': nowText_()
        });
        return;
      }
      recipients = reminder.recipients;
      message = reminder.message;
    }

    if (!recipients.length || !message) {
      updateRowByHeaders_(sheet, rowNumber, { '처리상태': 'SKIPPED', '수정일시': nowText_() });
      return;
    }

    try {
      const requests = recipients.map(chatId => ({
        url: `https://api.telegram.org/bot${token}/sendMessage`,
        method: 'post',
        contentType: 'application/json',
        payload: JSON.stringify({ chat_id: chatId, text: message }),
        muteHttpExceptions: true
      }));
      const responses = UrlFetchApp.fetchAll(requests);
      const failed = responses.filter(response => response.getResponseCode() < 200 || response.getResponseCode() >= 300).length;
      updateRowByHeaders_(sheet, rowNumber, {
        '처리상태': failed ? 'PARTIAL' : 'SENT',
        '추가내용': failed ? `실패 ${failed}건` : `${queueStatus === 'WAITING' ? '3분 미접수 재알림' : '발송'} ${responses.length}건`,
        '완료일시': nowText_(),
        '수정일시': nowText_()
      });
      processed += 1;
    } catch (error) {
      updateRowByHeaders_(sheet, rowNumber, {
        '처리상태': 'ERROR',
        '처리불가사유': error.message,
        '수정일시': nowText_()
      });
    }
  });

  return { ok: true, processed };
}

/**
 * Sprint 6.1: 사용자계정 사번 기준 텔레그램 개인 연결링크·웹훅 자동등록
 */
function setupNovaTelegramConnection() { // (텔레그램 봇·웹훅·직원 링크 초기 설정)
  const bot = getTelegramBotInfo_(true);
  const webAppUrl = String(ScriptApp.getService().getUrl() || '').trim();
  if (!webAppUrl || !/\/exec(?:$|\?)/.test(webAppUrl)) {
    throw new Error('웹앱을 먼저 새 버전으로 배포한 뒤 다시 실행하세요.');
  }

  const webhook = telegramApiRequest_('setWebhook', {
    url: webAppUrl,
    allowed_updates: ['message'],
    drop_pending_updates: false
  });
  if (!webhook.ok) throw new Error(webhook.description || '텔레그램 웹훅을 설정하지 못했습니다.');

  const props = PropertiesService.getScriptProperties();
  props.setProperties({
    TELEGRAM_BOT_USERNAME: bot.username,
    TELEGRAM_WEBHOOK_URL: webAppUrl,
    TELEGRAM_WEBHOOK_SET_AT: nowText_()
  }, false);
  ensureTelegramAccountEditTrigger_();
  const linkResult = refreshAllTelegramConnectionLinks_({ regenerateKeys: false });
  return {
    ok: true,
    message: '텔레그램 봇 연결과 직원별 개인 연결링크 생성이 완료되었습니다.',
    botUsername: bot.username,
    webhookUrl: webAppUrl,
    generated: linkResult.generated,
    linked: linkResult.linked
  };
}

function setupNovaTelegramConnectionFromApp(token) { // (관리자 설정화면 텔레그램 초기 설정)
  requireTelegramAdmin_(token);
  return setupNovaTelegramConnection();
}

function getTelegramConnectionAdminData(token) { // (관리자 텔레그램 연결현황 조회)
  requireTelegramAdmin_(token);
  const props = PropertiesService.getScriptProperties();
  const botUsername = String(props.getProperty('TELEGRAM_BOT_USERNAME') || '').trim();
  if (botUsername) refreshAllTelegramConnectionLinks_({ regenerateKeys: false, onlyMissing: true });
  clearNovaCaches_();
  const users = Object.values(getUserIndex_().byEmployeeNo)
    .sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'ko'))
    .map(user => ({
      employeeNo: user.employeeNo,
      name: user.name,
      job: user.job,
      role: user.role,
      enabled: user.enabled,
      telegramId: maskTelegramId_(user.telegramId),
      telegramLinked: Boolean(user.telegramId),
      telegramEnabled: user.telegramEnabled,
      connectionLink: user.telegramConnectionLink || '',
      connectionStatus: user.telegramConnectionStatus || (user.telegramId ? '연결완료' : '연결대기'),
      linkedAt: user.telegramLinkedAt || ''
    }));
  return {
    ok: true,
    botConfigured: Boolean(PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN')),
    botUsername,
    webhookUrl: String(props.getProperty('TELEGRAM_WEBHOOK_URL') || '').trim(),
    webhookSetAt: String(props.getProperty('TELEGRAM_WEBHOOK_SET_AT') || '').trim(),
    users
  };
}

function refreshTelegramConnectionLinks(token) { // (관리자 직원 연결링크 일괄 생성)
  requireTelegramAdmin_(token);
  const result = refreshAllTelegramConnectionLinks_({ regenerateKeys: false });
  clearNovaCaches_();
  return Object.assign({ ok: true, message: `${result.generated}명의 텔레그램 연결링크를 확인했습니다.` }, result);
}

function regenerateTelegramConnectionLink(token, employeeNo, resetConnection) { // (직원 개인 연결링크 재발급)
  requireTelegramAdmin_(token);
  const user = getUserIndex_().byEmployeeNo[String(employeeNo || '').trim()];
  if (!user) throw new Error('해당 사번의 직원을 찾지 못했습니다.');
  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  const username = getTelegramBotUsername_();
  const connectionKey = createTelegramConnectionKey_();
  const link = buildTelegramConnectionLink_(username, user.employeeNo, connectionKey);
  const values = {
    '텔레그램연결키': connectionKey,
    '텔레그램연결링크': link,
    '텔레그램연결상태': resetConnection ? '연결대기' : (user.telegramId ? '연결완료' : '연결대기'),
    '수정일시': nowText_()
  };
  if (resetConnection) {
    values['텔레그램ID'] = '';
    values['텔레그램알림'] = 'N';
    values['텔레그램연결일시'] = '';
  }
  updateRowByHeaders_(sheet, user.rowNumber, values);
  clearNovaCaches_();
  return { ok: true, message: `${user.name} 직원의 개인 연결링크를 재발급했습니다.`, link };
}

function sendTelegramConnectionTest(token, employeeNo) { // (연결된 직원 테스트 메시지 발송)
  requireTelegramAdmin_(token);
  const user = getActiveUserByEmployeeNo_(employeeNo);
  if (!user) throw new Error('사용 중인 직원을 찾지 못했습니다.');
  if (user.role === 'PUBLIC') throw new Error('객실퍼블릭은 퇴실지연 알림만 수신하므로 테스트 발송을 하지 않습니다.');
  if (!user.telegramId) throw new Error('텔레그램이 연결되지 않은 직원입니다.');
  const result = sendTelegramDirect_(user.telegramId, `[NOVA 연결 확인]\n${user.name}(${user.employeeNo})님의 텔레그램 연결이 정상입니다.`);
  if (!result.ok) throw new Error(result.description || '테스트 메시지를 발송하지 못했습니다.');
  return { ok: true, message: `${user.name} 직원에게 테스트 메시지를 발송했습니다.` };
}

function doPost(e) { // (텔레그램 웹훅 수신·업데이트 중복 차단)
  try {
    const raw = e && e.postData ? String(e.postData.contents || '') : '';
    if (!raw) return telegramWebhookResponse_('OK');
    const update = JSON.parse(raw);
    if (!claimTelegramWebhookUpdate_(update && update.update_id)) {
      return telegramWebhookResponse_('OK');
    }
    handleTelegramWebhookUpdate_(update);
  } catch (error) {
    console.error(`Telegram webhook error: ${error && error.stack ? error.stack : error}`);
  }
  return telegramWebhookResponse_('OK');
}

function claimTelegramWebhookUpdate_(updateId) { // (동일 Telegram update_id 재처리 방지)
  const id = String(updateId === null || updateId === undefined ? '' : updateId).trim();
  if (!id) return true;
  const cache = CacheService.getScriptCache();
  const key = `NOVA_TG_UPDATE_${id}`;
  if (cache.get(key)) return false;

  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(3000);
    if (cache.get(key)) return false;
    cache.put(key, '1', 21600);
    return true;
  } catch (error) {
    // 잠금 경합 중에도 이미 처리 표시가 있으면 중복으로 간주한다.
    if (cache.get(key)) return false;
    cache.put(key, '1', 21600);
    return true;
  } finally {
    try {
      if (lock.hasLock()) lock.releaseLock();
    } catch (ignore) {}
  }
}

function handleTelegramWebhookUpdate_(update) { // (텔레그램 /start 개인링크 처리)
  const message = update && update.message;
  if (!message || !message.chat || !message.text) return;
  const chatId = String(message.chat.id || '').trim();
  if (!chatId) return;
  if (String(message.chat.type || '').toLowerCase() !== 'private') {
    sendTelegramDirect_(chatId, 'NOVA 직원 연결은 텔레그램 개인 대화에서만 가능합니다.');
    return;
  }

  const text = String(message.text || '').trim();
  const match = text.match(/^\/start(?:@\w+)?(?:\s+([A-Za-z0-9_-]+))?$/i);
  if (!match) return;
  const payload = String(match[1] || '').trim();
  if (!payload) {
    sendTelegramDirect_(chatId, 'NOVA에서 발급한 개인 연결링크를 통해 다시 시작해 주세요.');
    return;
  }

  let verified;
  try {
    verified = verifyTelegramLinkPayload_(payload);
  } catch (error) {
    sendTelegramDirect_(chatId, `연결링크를 확인하지 못했습니다.\n${error.message}`);
    return;
  }

  clearNovaCaches_();
  const index = getUserIndex_();
  const user = index.byEmployeeNo[verified.employeeNo];
  if (!user || !user.enabled) {
    sendTelegramDirect_(chatId, '사용 중인 직원계정을 찾지 못했습니다. 관리자에게 문의해 주세요.');
    return;
  }
  if (!user.telegramConnectionKey || user.telegramConnectionKey !== verified.connectionKey) {
    sendTelegramDirect_(chatId, '만료되었거나 재발급된 연결링크입니다. 최신 링크를 받아 다시 연결해 주세요.');
    return;
  }

  const duplicate = index.active.find(item => item.employeeNo !== user.employeeNo && String(item.telegramId || '') === chatId);
  if (duplicate) {
    sendTelegramDirect_(chatId, `이 텔레그램 계정은 이미 ${duplicate.name}(${duplicate.employeeNo}) 직원에게 연결되어 있습니다.`);
    return;
  }
  if (user.telegramId && String(user.telegramId) !== chatId) {
    sendTelegramDirect_(chatId, '이 직원계정은 다른 텔레그램 계정에 연결되어 있습니다. 관리자에게 연결링크 재발급을 요청해 주세요.');
    return;
  }

  // 같은 직원·같은 chat_id가 이미 연결 완료된 경우 Telegram 재시도나 재클릭으로
  // 연결 완료 메시지를 반복 발송하지 않는다.
  const alreadyConnected = String(user.telegramId || '') === chatId
    && String(user.telegramConnectionStatus || '').trim() === '연결완료'
    && user.telegramEnabled;
  if (alreadyConnected) return;

  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  updateRowByHeaders_(sheet, user.rowNumber, {
    '텔레그램ID': chatId,
    '텔레그램알림': 'Y',
    '텔레그램연결상태': '연결완료',
    '텔레그램연결일시': nowText_(),
    '수정일시': nowText_()
  });
  clearNovaCaches_();
  logTelegramConnection_(user, chatId, message.from || {});
  sendTelegramDirect_(chatId, [
    '[NOVA 텔레그램 연결 완료]',
    `${user.name}(${user.employeeNo})님으로 연결되었습니다.`,
    '앞으로 담당 업무 알림이 이 대화로 전달됩니다.'
  ].join('\n'));
}

function refreshAllTelegramConnectionLinks_(options) { // (사용자계정 전체 개인링크 생성)
  const safe = options || {};
  const username = getTelegramBotUsername_();
  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  const map = getHeaderMap_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { generated: 0, linked: 0 };

  const rows = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getDisplayValues();
  const keyValues = sheet.getRange(2, map['텔레그램연결키'], lastRow - 1, 1).getDisplayValues();
  const linkValues = sheet.getRange(2, map['텔레그램연결링크'], lastRow - 1, 1).getDisplayValues();
  const statusValues = sheet.getRange(2, map['텔레그램연결상태'], lastRow - 1, 1).getDisplayValues();
  let generated = 0;
  let linked = 0;

  rows.forEach((row, index) => {
    const employeeNo = String(row[(map['사번'] || 1) - 1] || '').trim();
    const name = String(row[(map['이름'] || 1) - 1] || '').trim();
    const enabled = String(row[(map['사용여부'] || 1) - 1] || '').trim().toUpperCase() === 'Y';
    const telegramId = String(row[(map['텔레그램ID'] || 1) - 1] || '').trim();
    if (!employeeNo || !name) return;
    if (!enabled) {
      statusValues[index][0] = '사용중지';
      return;
    }
    let key = String(keyValues[index][0] || '').trim();
    let link = String(linkValues[index][0] || '').trim();
    if (safe.regenerateKeys || !key) key = createTelegramConnectionKey_();
    if (safe.regenerateKeys || !link || !link.includes(`t.me/${username}`)) {
      link = buildTelegramConnectionLink_(username, employeeNo, key);
    }
    keyValues[index][0] = key;
    linkValues[index][0] = link;
    statusValues[index][0] = telegramId ? '연결완료' : '연결대기';
    if (telegramId) linked += 1;
    generated += 1;
  });

  sheet.getRange(2, map['텔레그램연결키'], lastRow - 1, 1).setValues(keyValues);
  sheet.getRange(2, map['텔레그램연결링크'], lastRow - 1, 1).setValues(linkValues);
  sheet.getRange(2, map['텔레그램연결상태'], lastRow - 1, 1).setValues(statusValues);
  clearNovaCaches_();
  return { generated, linked };
}

function handleNovaUserAccountEdit(e) { // (사용자계정 직원 등록 시 연결링크 자동 생성)
  try {
    if (!e || !e.range) return refreshAllTelegramConnectionLinks_({ regenerateKeys: false, onlyMissing: true });
    const sheet = e.range.getSheet();
    if (sheet.getName() !== NOVA.SHEETS.USERS || e.range.getRow() < 2) return;
    const username = String(PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_USERNAME') || '').trim();
    if (!username) return;
    const map = getHeaderMap_(sheet);
    const startRow = Math.max(2, e.range.getRow());
    const endRow = e.range.getLastRow();
    for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
      const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
      const employeeNo = String(row[(map['사번'] || 1) - 1] || '').trim();
      const name = String(row[(map['이름'] || 1) - 1] || '').trim();
      const enabled = String(row[(map['사용여부'] || 1) - 1] || '').trim().toUpperCase() === 'Y';
      const telegramId = String(row[(map['텔레그램ID'] || 1) - 1] || '').trim();
      if (!employeeNo || !name) continue;
      if (!enabled) {
        updateRowByHeaders_(sheet, rowNumber, { '텔레그램연결상태': '사용중지', '수정일시': nowText_() });
        continue;
      }
      let key = String(row[(map['텔레그램연결키'] || 1) - 1] || '').trim();
      if (!key) key = createTelegramConnectionKey_();
      updateRowByHeaders_(sheet, rowNumber, {
        '텔레그램연결키': key,
        '텔레그램연결링크': buildTelegramConnectionLink_(username, employeeNo, key),
        '텔레그램연결상태': telegramId ? '연결완료' : '연결대기',
        '수정일시': nowText_()
      });
    }
    clearNovaCaches_();
    bumpDataVersion_({ domains: ['CONFIG'] });
  } catch (error) {
    console.error(`User telegram link edit error: ${error && error.stack ? error.stack : error}`);
  }
}

function configureTelegramUserAccountColumns_() { // (사용자계정 텔레그램 연결열 서식)
  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  const map = getHeaderMap_(sheet);
  if (map['텔레그램연결키']) {
    sheet.setColumnWidth(map['텔레그램연결키'], 90);
    try { sheet.hideColumns(map['텔레그램연결키']); } catch (error) {}
  }
  if (map['텔레그램연결링크']) sheet.setColumnWidth(map['텔레그램연결링크'], 360);
  if (map['텔레그램연결상태']) sheet.setColumnWidth(map['텔레그램연결상태'], 100);
  if (map['텔레그램연결일시']) sheet.setColumnWidth(map['텔레그램연결일시'], 150);
}

function ensureTelegramAccountEditTrigger_() { // (사용자계정 자동링크 설치형 수정 트리거 보장)
  const exists = ScriptApp.getProjectTriggers().some(trigger => trigger.getHandlerFunction() === 'handleNovaUserAccountEdit');
  if (!exists) {
    ScriptApp.newTrigger('handleNovaUserAccountEdit').forSpreadsheet(getSpreadsheet_()).onEdit().create();
  }
}

function getTelegramBotInfo_(refresh) { // (BotFather 봇 계정정보 조회)
  const props = PropertiesService.getScriptProperties();
  const cached = String(props.getProperty('TELEGRAM_BOT_USERNAME') || '').trim();
  if (cached && !refresh) return { username: cached };
  const result = telegramApiRequest_('getMe', {});
  if (!result.ok || !result.result || !result.result.username) {
    throw new Error(result.description || '텔레그램 봇 정보를 확인하지 못했습니다. TELEGRAM_BOT_TOKEN을 확인하세요.');
  }
  props.setProperty('TELEGRAM_BOT_USERNAME', String(result.result.username));
  return { username: String(result.result.username), id: result.result.id, firstName: result.result.first_name || '' };
}

function getTelegramBotUsername_() { // (연결링크용 봇 사용자명 조회)
  return getTelegramBotInfo_(false).username;
}

function telegramApiRequest_(method, payload) { // (텔레그램 Bot API 공통 호출)
  const token = String(PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN') || '').trim();
  if (!token) throw new Error('스크립트 속성 TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.');
  const response = UrlFetchApp.fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload || {}),
    muteHttpExceptions: true
  });
  let parsed;
  try { parsed = JSON.parse(response.getContentText() || '{}'); } catch (error) { parsed = {}; }
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    return { ok: false, description: parsed.description || `Telegram API ${response.getResponseCode()}` };
  }
  return parsed;
}

function sendTelegramDirect_(chatId, text) { // (연결 처리용 즉시 텔레그램 발송)
  try {
    return telegramApiRequest_('sendMessage', { chat_id: String(chatId), text: String(text || '') });
  } catch (error) {
    return { ok: false, description: error.message };
  }
}

function createTelegramConnectionKey_() { // (직원별 연결키 생성)
  return Utilities.base64EncodeWebSafe(Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    `${Utilities.getUuid()}|${Date.now()}|${Math.random()}`,
    Utilities.Charset.UTF_8
  )).replace(/=+$/g, '').slice(0, 12);
}

function getTelegramLinkSecret_() { // (연결링크 서명 비밀키)
  const props = PropertiesService.getScriptProperties();
  let secret = String(props.getProperty('TELEGRAM_LINK_SECRET') || '').trim();
  if (!secret) {
    secret = `${Utilities.getUuid()}${Utilities.getUuid()}`.replace(/-/g, '');
    props.setProperty('TELEGRAM_LINK_SECRET', secret);
  }
  return secret;
}

function buildTelegramConnectionLink_(username, employeeNo, connectionKey) { // (사번 기준 개인 딥링크 생성)
  const payload = buildTelegramLinkPayload_(employeeNo, connectionKey);
  return `https://t.me/${String(username || '').replace(/^@/, '')}?start=${payload}`;
}

function computeTelegramLinkSignature_(employeeNo, connectionKey) { // (사번·연결키 HMAC 서명 계산)
  const message = `${String(employeeNo || '')}|${String(connectionKey || '')}`;
  return Utilities.base64EncodeWebSafe(
    Utilities.computeHmacSha256Signature(message, getTelegramLinkSecret_(), Utilities.Charset.UTF_8)
  ).replace(/=+$/g, '').slice(0, 18);
}

function buildTelegramLinkPayload_(employeeNo, connectionKey) { // (사번·연결키 서명 토큰 생성)
  const empEncoded = Utilities.base64EncodeWebSafe(String(employeeNo || ''), Utilities.Charset.UTF_8).replace(/=+$/g, '');
  const signature = computeTelegramLinkSignature_(employeeNo, connectionKey);
  const payload = `n_${empEncoded}_${connectionKey}_${signature}`;
  if (payload.length > 64) throw new Error('사번이 너무 길어 텔레그램 연결링크를 생성하지 못했습니다.');
  return payload;
}

function verifyTelegramLinkPayload_(payload) { // (개인 연결토큰 고정길이 역방향 검증)
  const token = String(payload || '').trim();
  const prefix = 'n_';
  const connectionKeyLength = 12;
  const signatureLength = 18;
  const minimumLength = prefix.length + 1 + connectionKeyLength + 1 + signatureLength;
  if (!token.startsWith(prefix) || token.length < minimumLength) {
    throw new Error('올바른 NOVA 개인 연결링크가 아닙니다.');
  }

  const signatureSeparator = token.length - signatureLength - 1;
  const keyStart = signatureSeparator - connectionKeyLength;
  const keySeparator = keyStart - 1;
  if (token.charAt(signatureSeparator) !== '_' || token.charAt(keySeparator) !== '_') {
    throw new Error('올바른 NOVA 개인 연결링크가 아닙니다.');
  }

  const empEncoded = token.slice(prefix.length, keySeparator);
  const connectionKey = token.slice(keyStart, signatureSeparator);
  const signature = token.slice(signatureSeparator + 1);
  if (!/^[A-Za-z0-9_-]+$/.test(empEncoded)
      || !/^[A-Za-z0-9_-]{12}$/.test(connectionKey)
      || !/^[A-Za-z0-9_-]{18}$/.test(signature)) {
    throw new Error('올바른 NOVA 개인 연결링크가 아닙니다.');
  }

  let employeeNo;
  try {
    employeeNo = Utilities.newBlob(Utilities.base64DecodeWebSafe(empEncoded)).getDataAsString('UTF-8');
  } catch (error) {
    throw new Error('연결링크의 사번 정보를 읽지 못했습니다.');
  }
  if (!employeeNo) throw new Error('연결링크의 사번 정보가 비어 있습니다.');

  const expected = computeTelegramLinkSignature_(employeeNo, connectionKey);
  if (!safeTelegramTokenEquals_(expected, signature)) throw new Error('연결링크 서명이 올바르지 않습니다.');
  return { employeeNo, connectionKey };
}

function safeTelegramTokenEquals_(left, right) { // (서명 문자열 일정시간 비교)
  const a = String(left || '');
  const b = String(right || '');
  let diff = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    diff |= (a.charCodeAt(index % Math.max(1, a.length)) || 0) ^ (b.charCodeAt(index % Math.max(1, b.length)) || 0);
  }
  return diff === 0;
}

function requireTelegramAdmin_(token) { // (텔레그램 관리자 API 권한 확인)
  const auth = verifyNovaToken(token);
  if (!auth.ok || String(auth.user.role || '').toUpperCase() !== 'ADMIN') throw new Error('관리자 권한이 필요합니다.');
  return auth.user;
}

function getMyTelegramConnectionLink(token) { // (로그인 본인 텔레그램 연결링크 조회)
  const auth = verifyNovaToken(token);
  if (!auth.ok || !auth.user) {
    return { ok: false, code: 'UNAUTHORIZED', connectionLink: '', message: '다시 로그인해 주세요.' };
  }

  clearNovaCaches_();
  const employeeNo = String(auth.user.employeeNo || '').trim();
  const user = getUserIndex_().byEmployeeNo[employeeNo];
  if (!user || !user.enabled) {
    return { ok: false, connectionLink: '', message: '사용 중인 본인 사용자계정을 찾지 못했습니다.' };
  }
  if (user.telegramId) {
    return { ok: false, alreadyLinked: true, connectionLink: '', message: '이미 텔레그램 연결이 완료된 계정입니다.' };
  }

  const connectionLink = String(user.telegramConnectionLink || '').trim();
  if (!connectionLink) {
    return { ok: false, connectionLink: '', message: '본인 텔레그램 연결링크가 없습니다. 관리자에게 링크 재발급을 요청해 주세요.' };
  }
  if (!/^https:\/\/t\.me\/[A-Za-z0-9_]+\?start=[A-Za-z0-9_-]+$/i.test(connectionLink)) {
    return { ok: false, connectionLink: '', message: '본인 텔레그램 연결링크 형식이 올바르지 않습니다. 관리자에게 재발급을 요청해 주세요.' };
  }

  return { ok: true, connectionLink };
}

function maskTelegramId_(value) { // (화면용 텔레그램 ID 마스킹)
  const text = String(value || '').trim();
  if (!text) return '';
  if (text.length <= 5) return `${text.slice(0, 1)}***`;
  return `${text.slice(0, 3)}***${text.slice(-2)}`;
}

function logTelegramConnection_(user, chatId, from) { // (텔레그램 자동연결 이력 기록)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const row = createRowByHeaders_(sheet, {
    '기록ID': `TGLINK-${Utilities.getUuid()}`,
    '기록구분': NOVA.RECORD_TYPES.TELEGRAM_NOTICE,
    '업무일자': businessDateText_(),
    '대상사번': user.employeeNo,
    '처리상태': 'CONNECTED',
    '세부내용JSON': JSON.stringify({
      telegramChatId: String(chatId),
      telegramUserId: String(from.id || ''),
      username: from.username || '',
      firstName: from.first_name || '',
      lastName: from.last_name || ''
    }),
    '등록사번': user.employeeNo,
    '등록일시': nowText_(),
    '수정일시': nowText_(),
    '변경버전': getDataVersion_(),
    '삭제여부': 'N'
  });
  const rowNumber = sheet.getLastRow() + 1;
  ensureSheetRowCapacity_(sheet, rowNumber);
  sheet.getRange(rowNumber, 1, 1, row.length).setValues([row]);
}

function telegramWebhookResponse_(text) { // (텔레그램 웹훅 응답)
  return ContentService.createTextOutput(String(text || 'OK')).setMimeType(ContentService.MimeType.TEXT);
}
