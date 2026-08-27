from pathlib import Path

HOUSEMAN = Path('07_Houseman.js')
CLIENT = Path('Client.html')

houseman = HOUSEMAN.read_text(encoding='utf-8')
client = CLIENT.read_text(encoding='utf-8')

marker = "\n\nfunction getHousemanOrdersForDate_("
if 'function assignHousemanOrderFast(' not in houseman:
    if marker not in houseman:
        raise SystemExit('Houseman insertion marker not found')
    fast_code = r'''

function assignHousemanOrderFast(token, payload) { // (관리자 미배정 오더 수동배정 고속 저장)
  return measureResponse_('assignHousemanOrderFast', () => {
    const startedMs = Date.now();
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');

    const user = auth.user;
    const role = String(user.role || '').trim().toUpperCase();
    if (!['ADMIN', 'ORDER'].includes(role)) {
      throw new Error('직원배정은 오더테이커만 가능합니다.');
    }

    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    const employeeNo = String(safe.employeeNo || '').trim();
    const preferredRowNumber = Number(safe.rowNumber || 0);
    if (!orderId) throw new Error('오더 번호가 없습니다.');
    if (!employeeNo) throw new Error('배정 직원을 선택하세요.');

    const assigned = getActiveUserByEmployeeNo_(employeeNo);
    if (!assigned || assigned.role !== 'HOUSEMAN') {
      throw new Error('사용 가능한 하우스맨 계정이 아닙니다.');
    }

    const lock = LockService.getScriptLock();
    const lockStartedMs = Date.now();
    if (!lock.tryLock(Number(NOVA.WRITE_LOCK_TIMEOUT_MS || 2500))) {
      const busyError = new Error('동시 오더 처리가 많습니다. 잠시 후 다시 처리하세요.');
      busyError.code = 'BUSY_RETRY';
      throw busyError;
    }
    const lockWaitMs = Math.max(0, Date.now() - lockStartedMs);

    let findMs = 0;
    let writeMs = 0;
    let versionMs = 0;
    let publishMs = 0;

    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const findStartedMs = Date.now();
      const found = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
      findMs = Math.max(0, Date.now() - findStartedMs);
      if (!found) throw new Error('하우스맨 오더를 찾을 수 없습니다.');

      const currentVersion = Number(found.data['변경버전'] || 0);
      assertExpectedVersion_(safe.expectedVersion, currentVersion, `오더 ${orderId}`);

      let detail = {};
      try {
        detail = JSON.parse(String(found.data['세부내용JSON'] || '{}'));
      } catch (_) {
        detail = {};
      }

      const now = nowText_();
      const assignDetail = Object.assign({}, detail, {
        assignmentMode: 'MANUAL',
        autoAssigned: false,
        assignedBuilding: normalizeRoomBuilding_('', found.data['객실번호']),
        assignedShiftCode: '',
        assignedShiftCodes: [],
        routeCandidateEmployeeNos: [employeeNo],
        routeCandidateNames: [assigned.name || employeeNo],
        routeLocked: true,
        acceptedByEmployeeNo: '',
        releasedCandidateEmployeeNos: []
      });

      const versionStartedMs = Date.now();
      const version = reserveDataVersion_({ lockHeld: true });
      versionMs = Math.max(0, Date.now() - versionStartedMs);

      const newRow = found.row.slice();
      const headerMap = found.headerMap;
      const updates = {
        '대상사번': employeeNo,
        '처리상태': 'ASSIGNED',
        '세부내용JSON': JSON.stringify(assignDetail),
        '수정일시': now,
        '배정사번': employeeNo,
        '변경버전': version
      };
      Object.keys(updates).forEach(header => {
        if (headerMap[header]) newRow[headerMap[header] - 1] = updates[header];
      });

      const writeStartedMs = Date.now();
      sheet.getRange(found.rowNumber, 1, 1, newRow.length).setValues([newRow]);
      writeMs = Math.max(0, Date.now() - writeStartedMs);

      const publishStartedMs = Date.now();
      publishDataVersion_(version, {
        domains: ['ORDER'],
        businessDate: String(found.data['업무일자'] || '').trim(),
        site: String(found.data['사업장'] || '').trim(),
        lockHeld: true
      });
      publishMs = Math.max(0, Date.now() - publishStartedMs);

      const users = {};
      users[employeeNo] = assigned;
      const order = housemanOrderObject_(
        rowObjectFromValues_(newRow, headerMap),
        found.rowNumber,
        users,
        { ASSIGNED: '배정' }
      );

      return {
        ok: true,
        version,
        order,
        telegram: { queued: false, deferred: true },
        timing: {
          lockWaitMs,
          findMs,
          versionMs,
          writeMs,
          publishMs,
          totalMs: Math.max(0, Date.now() - startedMs)
        }
      };
    } finally {
      lock.releaseLock();
    }
  });
}


function finalizeHousemanAssignmentAux(token, payload) { // (수동배정 감사·Telegram 후속 저장)
  const auth = verifyNovaToken(token);
  if (!auth.ok) throw new Error('로그인이 필요합니다.');

  const user = auth.user;
  const role = String(user.role || '').trim().toUpperCase();
  if (!['ADMIN', 'ORDER'].includes(role)) {
    throw new Error('직원배정 후속처리 권한이 없습니다.');
  }

  const safe = payload || {};
  const orderId = String(safe.orderId || '').trim();
  const employeeNo = String(safe.employeeNo || '').trim();
  const version = Number(safe.version || 0);
  const rowNumber = Number(safe.rowNumber || 0);
  if (!orderId || !employeeNo || !version) {
    throw new Error('배정 후속처리 정보가 부족합니다.');
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(Number(NOVA.WRITE_LOCK_TIMEOUT_MS || 2500))) {
    const busyError = new Error('배정 후속처리가 지연되고 있습니다.');
    busyError.code = 'BUSY_RETRY';
    throw busyError;
  }

  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const found = findHousemanOrderRow_(sheet, orderId, rowNumber);
    if (!found) throw new Error('하우스맨 오더를 찾을 수 없습니다.');

    const storedVersion = Number(found.data['변경버전'] || 0);
    const storedEmployeeNo = String(found.data['배정사번'] || found.data['대상사번'] || '').trim();
    const storedStatus = String(found.data['처리상태'] || '').trim().toUpperCase();
    if (storedVersion !== version || storedEmployeeNo !== employeeNo || storedStatus !== 'ASSIGNED') {
      return { ok: true, skipped: true, reason: 'STALE_ASSIGNMENT' };
    }

    const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
    const statusCodeMap = {};
    getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
    const order = housemanOrderObject_(
      found.data,
      found.rowNumber,
      usersByEmployeeNo,
      statusCodeMap
    );

    const auxStartRow = sheet.getLastRow() + 1;
    const auditRow = buildHousemanAuditRow_(
      sheet,
      order,
      'ASSIGN',
      user.employeeNo,
      version,
      { employeeNo, assignmentMode: 'MANUAL', fastAssignment: true }
    );
    const telegramPrepared = prepareHousemanOrderFastTelegramRows_(
      sheet,
      order,
      'ASSIGN',
      { firstRowNumber: auxStartRow + 1 }
    );
    const auxRows = [auditRow].concat(telegramPrepared.rows || []);
    ensureSheetRowCapacity_(sheet, auxStartRow + auxRows.length - 1);
    sheet.getRange(auxStartRow, 1, auxRows.length, sheet.getLastColumn()).setValues(auxRows);

    return {
      ok: true,
      telegram: {
        queued: Boolean(telegramPrepared.queueRecordId),
        queueRecordId: telegramPrepared.queueRecordId || '',
        queueRowNumber: Number(telegramPrepared.queueRowNumber || 0),
        reminderScheduled: Boolean(telegramPrepared.reminderRecordId),
        reminderRecordId: telegramPrepared.reminderRecordId || ''
      }
    };
  } finally {
    lock.releaseLock();
  }
}
'''
    houseman = houseman.replace(marker, fast_code + marker, 1)

old_call = "      const result = await callServer('updateHousemanOrder', state.token, payload);"
new_call = "      const result = action === 'ASSIGN'\n        ? await callServer('assignHousemanOrderFast', state.token, payload)\n        : await callServer('updateHousemanOrder', state.token, payload);"
if new_call not in client:
    if old_call not in client:
        raise SystemExit('Client assignment call anchor not found')
    client = client.replace(old_call, new_call, 1)

old_telegram = r'''        if (telegram.queued && telegram.queueRecordId) {
          void callServer('dispatchHousemanOrderTelegramFast', state.token, {
            recordId: telegram.queueRecordId,
            rowNumber: Number(telegram.queueRowNumber || 0)
          }).catch(error => {
            console.warn('하우스맨 배정 텔레그램 즉시발송은 큐 재시도로 전환됩니다.', error?.message || error);
          });
        }'''
new_telegram = r'''        if (telegram.deferred) {
          void callServer('finalizeHousemanAssignmentAux', state.token, {
            orderId: result.order.orderId,
            employeeNo: result.order.assignedEmployeeNo,
            rowNumber: Number(result.order.rowNumber || 0),
            version: Number(result.version || result.order.version || 0)
          }).then(aux => {
            const queued = aux?.telegram || {};
            if (queued.queued && queued.queueRecordId) {
              return callServer('dispatchHousemanOrderTelegramFast', state.token, {
                recordId: queued.queueRecordId,
                rowNumber: Number(queued.queueRowNumber || 0)
              });
            }
            return null;
          }).catch(error => {
            console.warn('하우스맨 배정 감사·텔레그램 후속처리는 큐 재확인이 필요합니다.', error?.message || error);
          });
        } else if (telegram.queued && telegram.queueRecordId) {
          void callServer('dispatchHousemanOrderTelegramFast', state.token, {
            recordId: telegram.queueRecordId,
            rowNumber: Number(telegram.queueRowNumber || 0)
          }).catch(error => {
            console.warn('하우스맨 배정 텔레그램 즉시발송은 큐 재시도로 전환됩니다.', error?.message || error);
          });
        }'''
if new_telegram not in client:
    if old_telegram not in client:
        raise SystemExit('Client telegram block anchor not found')
    client = client.replace(old_telegram, new_telegram, 1)

HOUSEMAN.write_text(houseman, encoding='utf-8')
CLIENT.write_text(client, encoding='utf-8')
print('Applied fast manual houseman assignment with deferred audit/Telegram aux processing')
