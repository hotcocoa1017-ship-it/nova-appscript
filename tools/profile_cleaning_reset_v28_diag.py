from pathlib import Path

indicator_path = Path('06_Indicator.js')
client_path = Path('Client.html')

indicator = indicator_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')

start_marker = 'function resetIndicatorRoomCleaningFast_('
end_marker = 'function findIndicatorRoomActiveCleaningCompletions_('
start = indicator.find(start_marker)
end = indicator.find(end_marker)
if start < 0 or end < 0 or end <= start:
    raise SystemExit('PATCH_ERROR: CLEANING_RESET function markers not found')
block = indicator[start:end]

replacements = [
    (
        "  let removedEmployeeNos = [];\n\n  try {\n    const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);\n    const rowInfo = findCurrentRoomRowFast_(currentSheet, businessDate, site, roomNo, safe.rowNumber);\n",
        "  let removedEmployeeNos = [];\n  const phaseTiming = {};\n  let phaseStartedMs = Date.now();\n\n  try {\n    const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);\n    const rowInfo = findCurrentRoomRowFast_(currentSheet, businessDate, site, roomNo, safe.rowNumber);\n"
    ),
    (
        "    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');\n    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);\n\n    rowNumber = rowInfo.rowNumber;\n",
        "    if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');\n    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);\n    phaseTiming.currentRoomLookupMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    rowNumber = rowInfo.rowNumber;\n"
    ),
    (
        "    const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n    const completions = findIndicatorRoomActiveCleaningCompletions_(historySheet, businessDate, responseSite, roomNo);\n",
        "    phaseStartedMs = Date.now();\n    const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n    const completions = findIndicatorRoomActiveCleaningCompletions_(historySheet, businessDate, responseSite, roomNo);\n    phaseTiming.historyLookupMs = Math.max(0, Date.now() - phaseStartedMs);\n"
    ),
    (
        "    version = reserveDataVersion_({ lockHeld: true });\n    markIndicatorRoomCleaningCompletionsDeleted_(historySheet, completions, resetAt);\n",
        "    phaseStartedMs = Date.now();\n    version = reserveDataVersion_({ lockHeld: true });\n    phaseTiming.reserveVersionMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    phaseStartedMs = Date.now();\n    markIndicatorRoomCleaningCompletionsDeleted_(historySheet, completions, resetAt);\n    phaseTiming.markHistoryDeletedMs = Math.max(0, Date.now() - phaseStartedMs);\n"
    ),
    (
        "    updateRowByHeaders_(currentSheet, rowInfo.rowNumber, {\n",
        "    phaseStartedMs = Date.now();\n    updateRowByHeaders_(currentSheet, rowInfo.rowNumber, {\n"
    ),
    (
        "      '마지막변경버전': version\n    });\n\n    appendUnifiedHistory_({\n",
        "      '마지막변경버전': version\n    });\n    phaseTiming.updateCurrentRoomMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    phaseStartedMs = Date.now();\n    appendUnifiedHistory_({\n"
    ),
    (
        "      version\n    });\n\n    SpreadsheetApp.flush();\n    publishDataVersion_(version, {\n",
        "      version\n    });\n    phaseTiming.appendResetHistoryMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    phaseStartedMs = Date.now();\n    SpreadsheetApp.flush();\n    phaseTiming.flushMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    phaseStartedMs = Date.now();\n    publishDataVersion_(version, {\n"
    ),
    (
        "      lockHeld: true\n    });\n  } finally {\n",
        "      lockHeld: true\n    });\n    phaseTiming.publishVersionMs = Math.max(0, Date.now() - phaseStartedMs);\n  } finally {\n"
    ),
    (
        "      cleaningReset: true,\n      lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),\n",
        "      cleaningReset: true,\n      currentRoomLookupMs: Number(phaseTiming.currentRoomLookupMs || 0),\n      historyLookupMs: Number(phaseTiming.historyLookupMs || 0),\n      reserveVersionMs: Number(phaseTiming.reserveVersionMs || 0),\n      markHistoryDeletedMs: Number(phaseTiming.markHistoryDeletedMs || 0),\n      updateCurrentRoomMs: Number(phaseTiming.updateCurrentRoomMs || 0),\n      appendResetHistoryMs: Number(phaseTiming.appendResetHistoryMs || 0),\n      flushMs: Number(phaseTiming.flushMs || 0),\n      publishVersionMs: Number(phaseTiming.publishVersionMs || 0),\n      lockWaitMs: Math.max(0, writeLockAcquiredMs - writeLockRequestedMs),\n"
    ),
]

for old, new in replacements:
    if old not in block:
        raise SystemExit('PATCH_ERROR: CLEANING_RESET diagnostic anchor not found:\n' + old[:140])
    block = block.replace(old, new, 1)

indicator = indicator[:start] + block + indicator[end:]

old_client = """      const totalMs = Math.round(performance.now() - clickedAt);\n      const serverMs = Number(result.timing?.totalMs || result.performance?.elapsedMs || 0);\n      const duplicateIgnored = action === 'CLEANING_COMPLETE' && result.alreadyCompleted === true;\n      setSyncStatus(duplicateIgnored\n        ? `${room.roomNo}호 중복 청소완료 요청 제외 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`\n        : `${room.roomNo}호 저장 완료 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`);\n"""
new_client = """      const totalMs = Math.round(performance.now() - clickedAt);\n      const serverMs = Number(result.timing?.totalMs || result.performance?.elapsedMs || 0);\n      const duplicateIgnored = action === 'CLEANING_COMPLETE' && result.alreadyCompleted === true;\n      const resetTimingText = action === 'CLEANING_RESET' && result.timing\n        ? ` · 조회 ${Number(result.timing.historyLookupMs || 0)} · 삭제 ${Number(result.timing.markHistoryDeletedMs || 0)} · 객실 ${Number(result.timing.updateCurrentRoomMs || 0)} · 이력 ${Number(result.timing.appendResetHistoryMs || 0)} · flush ${Number(result.timing.flushMs || 0)} · 버전 ${Number(result.timing.publishVersionMs || 0)}ms`\n        : '';\n      setSyncStatus(duplicateIgnored\n        ? `${room.roomNo}호 중복 청소완료 요청 제외 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`\n        : `${room.roomNo}호 저장 완료 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}${resetTimingText}`);\n"""
if old_client not in client:
    raise SystemExit('PATCH_ERROR: Client timing status anchor not found')
client = client.replace(old_client, new_client, 1)

indicator_path.write_text(indicator, encoding='utf-8')
client_path.write_text(client, encoding='utf-8')

check_i = indicator_path.read_text(encoding='utf-8')
check_c = client_path.read_text(encoding='utf-8')
for token in ['historyLookupMs', 'markHistoryDeletedMs', 'appendResetHistoryMs', 'flushMs', 'publishVersionMs']:
    if token not in check_i:
        raise SystemExit(f'VERIFY_ERROR: {token} missing from 06_Indicator.js')
if 'resetTimingText' not in check_c:
    raise SystemExit('VERIFY_ERROR: reset timing display missing from Client.html')

print('PATCH_OK')
print('Diagnostic only; production Apps Script NOT changed yet')
print('Changed: 06_Indicator.js, Client.html')
print('Added: CLEANING_RESET phase timing (history lookup / soft delete / room update / reset history / flush / publish)')
print('Preserved: all reset logic, permissions, history rules, UI layout and other room actions')
print('No Cloud Run change required')
print('VERIFY: PASS')
