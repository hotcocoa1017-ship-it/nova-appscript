from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"SKIP {label}: already applied")
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"PATCH FAIL {label}: expected 1 match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"PATCH OK {label}")


houseman = Path("07_Houseman.js")
client = Path("Client.html")

# Add low-risk timing markers to updateHousemanOrder only. No business logic changes.
replace_once(
    houseman,
    """function updateHousemanOrder(token, payload) { // (하우스맨 오더 상태·내용 수정)\n  return measureResponse_('updateHousemanOrder', () => {\n    const auth = verifyNovaToken(token);\n""",
    """function updateHousemanOrder(token, payload) { // (하우스맨 오더 상태·내용 수정)\n  return measureResponse_('updateHousemanOrder', () => {\n    const perfStartedMs = Date.now();\n    const perfTiming = { authMs: 0, lockWaitMs: 0, findMs: 0, lookupMs: 0, writeMs: 0, publishMs: 0, auditMs: 0, telegramMs: 0 };\n    const authStartedMs = Date.now();\n    const auth = verifyNovaToken(token);\n    perfTiming.authMs = Math.max(0, Date.now() - authStartedMs);\n""",
    "Houseman update auth timing"
)

replace_once(
    houseman,
    """    const writeLock = LockService.getScriptLock();\n\n    if (\n      !writeLock.tryLock(\n        Number(\n          NOVA.WRITE_LOCK_TIMEOUT_MS || 2500\n        )\n      )\n    ) {\n""",
    """    const writeLock = LockService.getScriptLock();\n    const lockStartedMs = Date.now();\n\n    if (\n      !writeLock.tryLock(\n        Number(\n          NOVA.WRITE_LOCK_TIMEOUT_MS || 2500\n        )\n      )\n    ) {\n""",
    "Houseman update lock timing start"
)

replace_once(
    houseman,
    """    try {\n      const sheet = getRequiredSheet_(\n        NOVA.SHEETS.HISTORY\n      );\n\n      const found = findHousemanOrderRow_(\n        sheet,\n        orderId,\n        payload && payload.rowNumber\n      );\n""",
    """    try {\n      perfTiming.lockWaitMs = Math.max(0, Date.now() - lockStartedMs);\n      const sheet = getRequiredSheet_(\n        NOVA.SHEETS.HISTORY\n      );\n\n      const findStartedMs = Date.now();\n      const found = findHousemanOrderRow_(\n        sheet,\n        orderId,\n        payload && payload.rowNumber\n      );\n      perfTiming.findMs = Math.max(0, Date.now() - findStartedMs);\n""",
    "Houseman update row find timing"
)

replace_once(
    houseman,
    """      const usersByEmployeeNo =\n        getUserIndex_().byEmployeeNo;\n\n      const statusCodeMap = {};\n\n      getCodes_('하우스맨상태').forEach(code => {\n        statusCodeMap[code.code] = code.label;\n      });\n""",
    """      const lookupStartedMs = Date.now();\n      const usersByEmployeeNo =\n        getUserIndex_().byEmployeeNo;\n\n      const statusCodeMap = {};\n\n      getCodes_('하우스맨상태').forEach(code => {\n        statusCodeMap[code.code] = code.label;\n      });\n      perfTiming.lookupMs = Math.max(0, Date.now() - lookupStartedMs);\n""",
    "Houseman update lookup timing"
)

replace_once(
    houseman,
    """      sheet\n        .getRange(\n          found.rowNumber,\n          1,\n          1,\n          newRow.length\n        )\n        .setValues([newRow]);\n\n      publishDataVersion_(\n        version,\n        {\n          domains: ['ORDER'],\n          businessDate:\n            current.businessDate,\n          site:\n            current.site,\n          lockHeld: true\n        }\n      );\n""",
    """      const writeStartedMs = Date.now();\n      sheet\n        .getRange(\n          found.rowNumber,\n          1,\n          1,\n          newRow.length\n        )\n        .setValues([newRow]);\n      perfTiming.writeMs = Math.max(0, Date.now() - writeStartedMs);\n\n      const publishStartedMs = Date.now();\n      publishDataVersion_(\n        version,\n        {\n          domains: ['ORDER'],\n          businessDate:\n            current.businessDate,\n          site:\n            current.site,\n          lockHeld: true\n        }\n      );\n      perfTiming.publishMs = Math.max(0, Date.now() - publishStartedMs);\n""",
    "Houseman update write/publish timing"
)

replace_once(
    houseman,
    """      appendHousemanAudit_(\n        order,\n        action,\n        user.employeeNo,\n        version,\n        auditDetail\n      );\n\n      let telegramDispatch = {\n""",
    """      const auditStartedMs = Date.now();\n      appendHousemanAudit_(\n        order,\n        action,\n        user.employeeNo,\n        version,\n        auditDetail\n      );\n      perfTiming.auditMs = Math.max(0, Date.now() - auditStartedMs);\n\n      let telegramDispatch = {\n""",
    "Houseman update audit timing"
)

replace_once(
    houseman,
    """      if (action === 'ASSIGN') {\n        // Telegram 네트워크 발송은 사용자 저장 응답과 분리합니다.\n""",
    """      if (action === 'ASSIGN') {\n        const telegramStartedMs = Date.now();\n        // Telegram 네트워크 발송은 사용자 저장 응답과 분리합니다.\n""",
    "Houseman assignment telegram timing start"
)

replace_once(
    houseman,
    """        telegramDispatch = {\n          queued: Boolean(telegramPrepared.queueRecordId),\n          queueRecordId: telegramPrepared.queueRecordId || '',\n          queueRowNumber: Number(telegramPrepared.queueRowNumber || 0),\n          reminderScheduled: Boolean(telegramPrepared.reminderRecordId),\n          reminderRecordId: telegramPrepared.reminderRecordId || ''\n        };\n      }\n\n      return {\n        ok: true,\n        version,\n        order,\n        telegram: telegramDispatch\n      };\n""",
    """        telegramDispatch = {\n          queued: Boolean(telegramPrepared.queueRecordId),\n          queueRecordId: telegramPrepared.queueRecordId || '',\n          queueRowNumber: Number(telegramPrepared.queueRowNumber || 0),\n          reminderScheduled: Boolean(telegramPrepared.reminderRecordId),\n          reminderRecordId: telegramPrepared.reminderRecordId || ''\n        };\n        perfTiming.telegramMs = Math.max(0, Date.now() - telegramStartedMs);\n      }\n\n      return {\n        ok: true,\n        version,\n        order,\n        telegram: telegramDispatch,\n        timing: Object.assign({}, perfTiming, { totalMs: Math.max(0, Date.now() - perfStartedMs) })\n      };\n""",
    "Houseman update timing response"
)

# Surface the timing through the existing sync status line after a manager action.
replace_once(
    client,
    """      closeModal();\n      showToast(`${result.order.roomNo}호 오더: ${result.order.statusLabel}`);\n""",
    """      closeModal();\n      showToast(`${result.order.roomNo}호 오더: ${result.order.statusLabel}`);\n      if (action === 'ASSIGN' && result.timing) {\n        const t = result.timing;\n        setSyncStatus(`하우스맨 배정 성능 · 총 ${Number(t.totalMs || result.performance?.elapsedMs || 0)}ms · 인증 ${Number(t.authMs || 0)} · 잠금 ${Number(t.lockWaitMs || 0)} · 행찾기 ${Number(t.findMs || 0)} · 조회 ${Number(t.lookupMs || 0)} · 저장 ${Number(t.writeMs || 0)} · 버전 ${Number(t.publishMs || 0)} · 감사 ${Number(t.auditMs || 0)} · 알림준비 ${Number(t.telegramMs || 0)}ms`);\n      }\n""",
    "Client houseman assignment timing status"
)

houseman_text = houseman.read_text(encoding="utf-8")
client_text = client.read_text(encoding="utf-8")
for marker in [
    "const perfTiming = { authMs: 0, lockWaitMs: 0, findMs: 0",
    "perfTiming.auditMs",
    "perfTiming.telegramMs",
    "timing: Object.assign({}, perfTiming"
]:
    if marker not in houseman_text:
        raise SystemExit(f"VERIFY FAIL Houseman timing marker missing: {marker}")
if "하우스맨 배정 성능 · 총" not in client_text:
    raise SystemExit("VERIFY FAIL Client timing status marker missing")

print("VERIFY PASS houseman ASSIGN timing diagnostics; no business logic changed")
