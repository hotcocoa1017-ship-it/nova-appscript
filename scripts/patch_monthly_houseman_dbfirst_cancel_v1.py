from pathlib import Path

MARKER = 'MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1'


def patch_server():
    path = Path('RealtimeDbFirstServer.js')
    text = path.read_text(encoding='utf-8')
    if MARKER in text:
        return
    addition = r'''

function novaHousemanMonthlyDbCancelIfPresent_(token, orderId, requestId) { // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1
  const sessionToken = String(token || '').trim();
  const id = String(orderId || '').trim();
  if (!sessionToken) throw new Error('로그인이 필요합니다.');
  if (!id) throw new Error('하우스맨 오더 번호가 없습니다.');

  const props = PropertiesService.getScriptProperties();
  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() === 'Y';
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  if (!enabled || !apiBase) {
    return { ok: true, dbFirst: false, dbChecked: false, skipped: true, reason: 'REALTIME_DISABLED', orderId: id };
  }

  const requestedId = String(requestId || '').trim();
  const rid = /^[A-Za-z0-9._:-]{8,180}$/.test(requestedId)
    ? requestedId
    : `MONTHLY_HOUSEMAN_CANCEL:${Utilities.getUuid()}`;
  const response = UrlFetchApp.fetch(`${apiBase}/v1/houseman-orders/${encodeURIComponent(id)}/cancel`, {
    method: 'post',
    contentType: 'application/json; charset=utf-8',
    payload: JSON.stringify({ requestId: rid }),
    headers: {
      Authorization: `Bearer ${sessionToken}`,
      'X-Request-Id': rid
    },
    muteHttpExceptions: true,
    followRedirects: true
  });
  const status = Number(response.getResponseCode() || 0);
  let body = {};
  try { body = JSON.parse(response.getContentText() || '{}'); } catch (error) { body = {}; }
  const code = String(body.code || body.errorCode || '').trim().toUpperCase();

  // 과거 Sheet-only 오더 또는 이전 호출에서 이미 DB 삭제된 오더는 Sheet 감사이력 정리를 계속 허용합니다.
  if (status === 404 || code === 'HOUSEMAN_ORDER_NOT_FOUND') {
    return {
      ok: true,
      dbFirst: false,
      dbChecked: true,
      dbMissing: true,
      alreadyAbsent: true,
      orderId: id,
      requestId: rid
    };
  }

  if (status < 200 || status >= 300 || body.ok === false) {
    const message = String(body.message || body.error || body.code || `하우스맨 DB 취소 오류 (${status})`).trim();
    throw new Error(message || `하우스맨 DB 취소 오류 (${status})`);
  }

  return Object.assign({}, body, {
    ok: true,
    dbFirst: true,
    dbChecked: true,
    dbMissing: false,
    orderId: String(body.orderId || id),
    requestId: String(body.requestId || rid)
  });
}
'''
    path.write_text(text.rstrip() + addition + '\n', encoding='utf-8')


def patch_monthly():
    path = Path('11_Monthly.js')
    text = path.read_text(encoding='utf-8')
    if text.count(MARKER) >= 2:
        return

    cancel_anchor = """      let detail = {};
      try { detail = JSON.parse(String(found.data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
      const version = reserveDataVersion_({ lockHeld: true });
"""
    cancel_repl = """      let detail = {};
      try { detail = JSON.parse(String(found.data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }

      const dbRequestId = `MONTHLY_HOUSEMAN_CANCEL:${Utilities.getUuid()}`; // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1
      const dbResult = typeof novaHousemanMonthlyDbCancelIfPresent_ === 'function'
        ? novaHousemanMonthlyDbCancelIfPresent_(token, orderId, dbRequestId)
        : { ok: true, dbFirst: false, dbChecked: false, skipped: true };

      const version = reserveDataVersion_({ lockHeld: true });
"""
    if cancel_anchor not in text:
        raise SystemExit('cancel anchor not found')
    text = text.replace(cancel_anchor, cancel_repl, 1)

    detail_anchor = """        cancelledBy: user.employeeNo,
        cancelSource: 'MONTHLY_HISTORY'
      });
"""
    detail_repl = """        cancelledBy: user.employeeNo,
        cancelSource: 'MONTHLY_HISTORY',
        dbFirst: Boolean(dbResult && dbResult.dbFirst),
        dbChecked: Boolean(dbResult && dbResult.dbChecked),
        dbRequestId: String(dbResult && dbResult.requestId || dbRequestId)
      });
"""
    if detail_anchor not in text:
        raise SystemExit('cancel detail anchor not found')
    text = text.replace(detail_anchor, detail_repl, 1)

    cancel_return_anchor = """        orderId,
        version,
        order,
        message: `${String(found.data['객실번호'] || '').trim()}호 오더를 취소했습니다.`
"""
    cancel_return_repl = """        orderId,
        version,
        order,
        dbFirst: Boolean(dbResult && dbResult.dbFirst),
        dbChecked: Boolean(dbResult && dbResult.dbChecked),
        dbRequestId: String(dbResult && dbResult.requestId || dbRequestId),
        message: `${String(found.data['객실번호'] || '').trim()}호 오더를 취소했습니다.`
"""
    if cancel_return_anchor not in text:
        raise SystemExit('cancel return anchor not found')
    text = text.replace(cancel_return_anchor, cancel_return_repl, 1)

    delete_anchor = """      const users = getUserIndex_().byEmployeeNo;
      const statusCodeMap = {};
      getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
      statusCodeMap.CANCELLED = '오더취소';
      const current = housemanOrderObject_(found.data, found.rowNumber, users, statusCodeMap);
      const version = reserveDataVersion_({ lockHeld: true });
"""
    delete_repl = """      const dbRequestId = `MONTHLY_HOUSEMAN_DELETE:${Utilities.getUuid()}`; // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1
      const dbResult = typeof novaHousemanMonthlyDbCancelIfPresent_ === 'function'
        ? novaHousemanMonthlyDbCancelIfPresent_(token, orderId, dbRequestId)
        : { ok: true, dbFirst: false, dbChecked: false, skipped: true };

      const users = getUserIndex_().byEmployeeNo;
      const statusCodeMap = {};
      getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
      statusCodeMap.CANCELLED = '오더취소';
      const current = housemanOrderObject_(found.data, found.rowNumber, users, statusCodeMap);
      const version = reserveDataVersion_({ lockHeld: true });
"""
    if delete_anchor not in text:
        raise SystemExit('delete anchor not found')
    text = text.replace(delete_anchor, delete_repl, 1)

    delete_audit_anchor = """        source: 'MONTHLY_HISTORY',
        reason: 'ORDER_DELETED_BY_MANAGER',
        previousStatus: statusCode
"""
    delete_audit_repl = """        source: 'MONTHLY_HISTORY',
        reason: 'ORDER_DELETED_BY_MANAGER',
        previousStatus: statusCode,
        dbFirst: Boolean(dbResult && dbResult.dbFirst),
        dbChecked: Boolean(dbResult && dbResult.dbChecked),
        dbRequestId: String(dbResult && dbResult.requestId || dbRequestId)
"""
    if delete_audit_anchor not in text:
        raise SystemExit('delete audit anchor not found')
    text = text.replace(delete_audit_anchor, delete_audit_repl, 1)

    delete_return_anchor = """        orderId,
        version,
        message: `${String(found.data['객실번호'] || '').trim()}호 오더를 삭제했습니다.`
"""
    delete_return_repl = """        orderId,
        version,
        dbFirst: Boolean(dbResult && dbResult.dbFirst),
        dbChecked: Boolean(dbResult && dbResult.dbChecked),
        dbRequestId: String(dbResult && dbResult.requestId || dbRequestId),
        message: `${String(found.data['객실번호'] || '').trim()}호 오더를 삭제했습니다.`
"""
    if delete_return_anchor not in text:
        raise SystemExit('delete return anchor not found')
    text = text.replace(delete_return_anchor, delete_return_repl, 1)

    path.write_text(text, encoding='utf-8')


def patch_client():
    path = Path('AppJs.html')
    text = path.read_text(encoding='utf-8')
    old = "      await cancelMonthlyHousemanRealtimeIfPresent_(item.recordId);\n"
    count = text.count(old)
    if count == 0:
        return
    if count != 2:
        raise SystemExit(f'unexpected pre-cancel count: {count}')
    text = text.replace(old, "      // DB 삭제 선확정은 Apps Script 서버가 수행합니다. // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1\n")
    path.write_text(text, encoding='utf-8')


patch_server()
patch_monthly()
patch_client()
print('patched monthly houseman DB-first cancel/delete v1')
