from pathlib import Path
import re

MARKER = 'MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1'


def function_slice(text, name, next_name=None):
    start = text.find(f'function {name}(')
    if start < 0:
        raise SystemExit(f'function not found: {name}')
    if next_name:
        end = text.find(f'function {next_name}(', start + 1)
        if end < 0:
            raise SystemExit(f'next function not found: {next_name}')
    else:
        end = len(text)
    return start, end, text[start:end]


def sub_once(pattern, replacement, text, label, flags=0):
    result, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f'{label} replacement count={count}')
    return result


def patch_server():
    path = Path('RealtimeDbFirstServer.js')
    text = path.read_text(encoding='utf-8')
    if 'function novaHousemanMonthlyDbCancelIfPresent_(' in text:
        return

    addition = r'''

function novaHousemanMonthlyDbCancelIfPresent_(token, orderId, requestId) { // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1
  const sessionToken = String(token || '').trim();
  const id = String(orderId || '').trim();
  requireRole_(sessionToken, ['ADMIN', 'ORDER']);
  if (!id) throw new Error('하우스맨 오더 번호가 없습니다.');

  const props = PropertiesService.getScriptProperties();
  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() === 'Y';
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  if (!enabled || !apiBase) {
    return { ok: true, dbFirst: false, dbChecked: false, skipped: true, reason: 'REALTIME_DISABLED', orderId: id };
  }

  const requestedId = String(requestId || '').trim();
  const rid = requestedId || Utilities.getUuid();
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


def patch_cancel_function(text):
    start, end, part = function_slice(text, 'cancelMonthlyManagedHousemanOrder', 'deleteMonthlyHousemanOrder')
    marker = 'const dbRequestId = Utilities.getUuid(); // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1'
    if marker not in part:
        pattern = re.compile(
            r"(try\s*\{\s*detail\s*=\s*JSON\.parse\(String\(found\.data\['세부내용JSON'\]\s*\|\|\s*'\{\}'\)\);\s*\}\s*catch\s*\(error\)\s*\{\s*detail\s*=\s*\{\};\s*\})\s*(const\s+version\s*=\s*reserveDataVersion_\(\{\s*lockHeld:\s*true\s*\}\);)",
            re.S,
        )
        match = pattern.search(part)
        if not match:
            raise SystemExit('cancel DB precommit replacement count=0')
        insert = (
            match.group(1)
            + "\n\n      const dbRequestId = Utilities.getUuid(); // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1\n"
            + "      const dbResult = typeof novaHousemanMonthlyDbCancelIfPresent_ === 'function'\n"
            + "        ? novaHousemanMonthlyDbCancelIfPresent_(token, orderId, dbRequestId)\n"
            + "        : { ok: true, dbFirst: false, dbChecked: false, skipped: true };\n\n"
            + "      " + match.group(2)
        )
        part = part[:match.start()] + insert + part[match.end():]

        part = sub_once(
            r"cancelSource:\s*'MONTHLY_HISTORY'\s*\n\s*\}\);",
            "cancelSource: 'MONTHLY_HISTORY',\n        dbFirst: Boolean(dbResult && dbResult.dbFirst),\n        dbChecked: Boolean(dbResult && dbResult.dbChecked),\n        dbRequestId: String(dbResult && dbResult.requestId || dbRequestId)\n      });",
            part,
            'cancel audit metadata',
        )

        pattern = re.compile(
            r"(\n\s*orderId,\s*\n\s*version,\s*\n\s*order,)\s*\n(\s*message:\s*`\$\{String\(found\.data\['객실번호'\]\s*\|\|\s*''\)\.trim\(\)\}호 오더를 취소했습니다\.`)",
            re.S,
        )
        match = pattern.search(part)
        if not match:
            raise SystemExit('cancel return metadata replacement count=0')
        insert = (
            match.group(1)
            + "\n        dbFirst: Boolean(dbResult && dbResult.dbFirst),"
            + "\n        dbChecked: Boolean(dbResult && dbResult.dbChecked),"
            + "\n        dbRequestId: String(dbResult && dbResult.requestId || dbRequestId),\n"
            + match.group(2)
        )
        part = part[:match.start()] + insert + part[match.end():]
    return text[:start] + part + text[end:]


def patch_delete_function(text):
    start, end, part = function_slice(text, 'deleteMonthlyHousemanOrder', 'getMonthlyHousemanAutoAssignment')
    marker = 'const dbRequestId = Utilities.getUuid(); // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1'
    if marker not in part:
        pattern = re.compile(r"(\n\s*const\s+users\s*=\s*getUserIndex_\(\)\.byEmployeeNo;)")
        match = pattern.search(part)
        if not match:
            raise SystemExit('delete DB precommit replacement count=0')
        insert = (
            "\n      const dbRequestId = Utilities.getUuid(); // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1\n"
            + "      const dbResult = typeof novaHousemanMonthlyDbCancelIfPresent_ === 'function'\n"
            + "        ? novaHousemanMonthlyDbCancelIfPresent_(token, orderId, dbRequestId)\n"
            + "        : { ok: true, dbFirst: false, dbChecked: false, skipped: true };"
            + match.group(1)
        )
        part = part[:match.start()] + insert + part[match.end():]

        part = sub_once(
            r"previousStatus:\s*statusCode\s*\n\s*\}\);",
            "previousStatus: statusCode,\n        dbFirst: Boolean(dbResult && dbResult.dbFirst),\n        dbChecked: Boolean(dbResult && dbResult.dbChecked),\n        dbRequestId: String(dbResult && dbResult.requestId || dbRequestId)\n      });",
            part,
            'delete audit metadata',
        )

        pattern = re.compile(
            r"(\n\s*orderId,\s*\n\s*version,)\s*\n(\s*message:\s*`\$\{String\(found\.data\['객실번호'\]\s*\|\|\s*''\)\.trim\(\)\}호 오더를 삭제했습니다\.`)",
            re.S,
        )
        match = pattern.search(part)
        if not match:
            raise SystemExit('delete return metadata replacement count=0')
        insert = (
            match.group(1)
            + "\n        dbFirst: Boolean(dbResult && dbResult.dbFirst),"
            + "\n        dbChecked: Boolean(dbResult && dbResult.dbChecked),"
            + "\n        dbRequestId: String(dbResult && dbResult.requestId || dbRequestId),\n"
            + match.group(2)
        )
        part = part[:match.start()] + insert + part[match.end():]
    return text[:start] + part + text[end:]


def patch_monthly():
    path = Path('11_Monthly.js')
    text = path.read_text(encoding='utf-8')
    text = patch_cancel_function(text)
    text = patch_delete_function(text)
    if text.count('const dbRequestId = Utilities.getUuid(); // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1') != 2:
        raise SystemExit('monthly DB-first marker count mismatch')
    path.write_text(text, encoding='utf-8')


def patch_client():
    path = Path('Client.html')
    text = path.read_text(encoding='utf-8')
    pattern = r"^[ \t]*await\s+cancelMonthlyHousemanRealtimeIfPresent_\(item\.recordId\);[ \t]*$"
    matches = list(re.finditer(pattern, text, flags=re.M))
    if not matches:
        if text.count('DB 삭제 선확정은 Apps Script 서버가 수행합니다.') >= 2:
            return
        raise SystemExit('monthly client pre-cancel calls not found')
    if len(matches) != 2:
        raise SystemExit(f'unexpected pre-cancel count: {len(matches)}')
    text, count = re.subn(
        pattern,
        '      // DB 삭제 선확정은 Apps Script 서버가 수행합니다. // MONTHLY_HOUSEMAN_DB_FIRST_CANCEL_V1',
        text,
        flags=re.M,
    )
    if count != 2:
        raise SystemExit(f'client replacement count: {count}')
    path.write_text(text, encoding='utf-8')


patch_server()
patch_monthly()
patch_client()
print('patched monthly houseman DB-first cancel/delete v1')
