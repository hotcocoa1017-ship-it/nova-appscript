from pathlib import Path

# Targeted production patch: manager ASSIGN only.
# - Prefer known order rowNumber to avoid whole-column TextFinder on normal path.
# - Queue audit + Telegram rows in one batch and return immediately.
# - Actual Telegram network send is kicked off by the client after the ASSIGN response.
# - Non-ASSIGN houseman actions are left unchanged.

client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')
client_original = client

old_client = """  async function runOrderAction(order, action) { // (오더 상태 변경 실행)\n    if (order?.__sheetMirrorPending) {\n      showToast('오더는 저장되었습니다. 기존 이력 동기화가 완료된 뒤 처리할 수 있습니다.');\n      return;\n    }\n    const payload = { orderId: order.orderId, action, expectedVersion: Number(order.version || 0) };\n    if (action === 'ASSIGN') payload.employeeNo = $('detailAssignee').value;\n    if (action === 'UNABLE') {\n      const reason = window.prompt('처리불가 사유를 입력하세요.');\n      if (reason === null) return;\n      payload.reason = reason.trim();\n    }\n    try {\n      const result = await callServer('updateHousemanOrder', state.token, payload);\n      if (!result?.ok) throw new Error(result?.message || '오더를 변경하지 못했습니다.');\n      upsertOrderLocal_(result.order, result.version);\n      closeModal();\n      showToast(`${result.order.roomNo}호 오더: ${result.order.statusLabel}`);\n    } catch (error) {\n      showToast(error?.message || '오더 처리 오류');\n    }\n  }\n"""

new_client = """  async function runOrderAction(order, action) { // (오더 상태 변경 실행)\n    if (order?.__sheetMirrorPending) {\n      showToast('오더는 저장되었습니다. 기존 이력 동기화가 완료된 뒤 처리할 수 있습니다.');\n      return;\n    }\n    const payload = {\n      orderId: order.orderId,\n      action,\n      expectedVersion: Number(order.version || 0),\n      rowNumber: Number(order.rowNumber || 0)\n    };\n    if (action === 'ASSIGN') payload.employeeNo = $('detailAssignee').value;\n    if (action === 'UNABLE') {\n      const reason = window.prompt('처리불가 사유를 입력하세요.');\n      if (reason === null) return;\n      payload.reason = reason.trim();\n    }\n    const actionStartedAt = performance.now();\n    try {\n      const result = await callServer('updateHousemanOrder', state.token, payload);\n      if (!result?.ok) throw new Error(result?.message || '오더를 변경하지 못했습니다.');\n      upsertOrderLocal_(result.order, result.version);\n      closeModal();\n\n      if (action === 'ASSIGN') {\n        const elapsed = Math.round(performance.now() - actionStartedAt);\n        const serverElapsed = Number(result.performance?.elapsedMs || 0);\n        const telegram = result.telegram || {};\n        showToast(`${result.order.roomNo}호 배정 완료 · ${elapsed}ms${serverElapsed ? ` · 서버 ${serverElapsed}ms` : ''}`);\n        setSyncStatus(`하우스맨 배정 완료 · ${elapsed}ms${serverElapsed ? ` · 서버 ${serverElapsed}ms` : ''}`);\n        if (telegram.queued && telegram.queueRecordId) {\n          void callServer('dispatchHousemanOrderTelegramFast', state.token, {\n            recordId: telegram.queueRecordId,\n            rowNumber: Number(telegram.queueRowNumber || 0)\n          }).catch(error => {\n            console.warn('하우스맨 배정 텔레그램 즉시발송은 큐 재시도로 전환됩니다.', error?.message || error);\n          });\n        }\n      } else {\n        showToast(`${result.order.roomNo}호 오더: ${result.order.statusLabel}`);\n      }\n    } catch (error) {\n      showToast(error?.message || '오더 처리 오류');\n    }\n  }\n"""

if client.count(old_client) != 1:
    raise SystemExit(f'Client runOrderAction anchor count mismatch: {client.count(old_client)}')
client = client.replace(old_client, new_client, 1)

server_path = Path('07_Houseman.js')
server = server_path.read_text(encoding='utf-8')
server_original = server

old_server = """      appendHousemanAudit_(\n        order,\n        action,\n        user.employeeNo,\n        version,\n        auditDetail\n      );\n\n      if (action === 'ASSIGN') {\n        queueHousemanOrderTelegram_(\n          order,\n          action\n        );\n      }\n\n      return {\n        ok: true,\n        version,\n        order\n      };\n"""

new_server = """      let telegramDispatch = {\n        queued: false,\n        queueRecordId: '',\n        queueRowNumber: 0,\n        reminderScheduled: false,\n        reminderRecordId: ''\n      };\n\n      if (action === 'ASSIGN') {\n        // 관리자 배정은 감사 + Telegram 큐를 한 번에 기록하고 즉시 응답합니다.\n        // Telegram 네트워크 발송은 응답 후 dispatchHousemanOrderTelegramFast에서 처리합니다.\n        const auxStartRow = sheet.getLastRow() + 1;\n        const auditRow = buildHousemanAuditRow_(\n          sheet,\n          order,\n          action,\n          user.employeeNo,\n          version,\n          auditDetail\n        );\n        const telegramPrepared = prepareHousemanOrderFastTelegramRows_(\n          sheet,\n          order,\n          action,\n          { firstRowNumber: auxStartRow + 1 }\n        );\n        const auxRows = [auditRow].concat(telegramPrepared.rows || []);\n        ensureSheetRowCapacity_(sheet, auxStartRow + auxRows.length - 1);\n        sheet.getRange(\n          auxStartRow,\n          1,\n          auxRows.length,\n          sheet.getLastColumn()\n        ).setValues(auxRows);\n        telegramDispatch = {\n          queued: Boolean(telegramPrepared.queueRecordId),\n          queueRecordId: telegramPrepared.queueRecordId || '',\n          queueRowNumber: Number(telegramPrepared.queueRowNumber || 0),\n          reminderScheduled: Boolean(telegramPrepared.reminderRecordId),\n          reminderRecordId: telegramPrepared.reminderRecordId || ''\n        };\n      } else {\n        appendHousemanAudit_(\n          order,\n          action,\n          user.employeeNo,\n          version,\n          auditDetail\n        );\n      }\n\n      return {\n        ok: true,\n        version,\n        order,\n        telegram: telegramDispatch\n      };\n"""

if server.count(old_server) != 1:
    raise SystemExit(f'07_Houseman ASSIGN post-write anchor count mismatch: {server.count(old_server)}')
server = server.replace(old_server, new_server, 1)

required_client = [
    'rowNumber: Number(order.rowNumber || 0)',
    '호 배정 완료 · ${elapsed}ms',
    "callServer('dispatchHousemanOrderTelegramFast'"
]
required_server = [
    "if (action === 'ASSIGN') {",
    'prepareHousemanOrderFastTelegramRows_(',
    'const auxRows = [auditRow].concat(telegramPrepared.rows || []);',
    'telegram: telegramDispatch'
]
for marker in required_client:
    if marker not in client:
        raise SystemExit(f'missing Client marker after patch: {marker}')
for marker in required_server:
    if marker not in server:
        raise SystemExit(f'missing server marker after patch: {marker}')

# Guard against accidentally retaining synchronous Telegram send in updateHousemanOrder's patched tail.
update_start = server.index('function updateHousemanOrder(')
update_end = server.index('function getHousemanOrdersForDate_', update_start)
update_block = server[update_start:update_end]
if 'queueHousemanOrderTelegram_(\n          order,\n          action' in update_block:
    raise SystemExit('synchronous ASSIGN Telegram call still present in updateHousemanOrder')

if client == client_original or server == server_original:
    raise SystemExit('patch did not modify both target files')

client_path.write_text(client, encoding='utf-8')
server_path.write_text(server, encoding='utf-8')
print('Applied houseman manager ASSIGN fast path + visible timing test')
