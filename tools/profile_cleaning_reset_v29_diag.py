from pathlib import Path

server_path = Path('06_Indicator.js')
client_path = Path('Client.html')
server = server_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')

start_marker = 'function resetIndicatorRoomCleaningFast_('
end_marker = 'function findIndicatorRoomActiveCleaningCompletions_('
start = server.find(start_marker)
end = server.find(end_marker, start)
if start < 0 or end < 0 or end <= start:
    raise SystemExit('PATCH_ERROR: CLEANING_RESET function markers not found')

segment = server[start:end]
if 'phaseTiming' in segment or 'resetTimingText' in client:
    raise SystemExit('PATCH_ERROR: diagnostic timing already present')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)

segment = replace_once(
    segment,
    "  let removedEmployeeNos = [];\n\n  try {",
    "  let removedEmployeeNos = [];\n  const phaseTiming = {};\n  let phaseStartedMs = Date.now();\n\n  try {",
    'phase timing init'
)

segment = replace_once(
    segment,
    "    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);\n\n    rowNumber = rowInfo.rowNumber;",
    "    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);\n    phaseTiming.currentRoomLookupMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    rowNumber = rowInfo.rowNumber;",
    'current room lookup timing'
)

segment = replace_once(
    segment,
    "    const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n    const completions = findIndicatorRoomActiveCleaningCompletions_(historySheet, businessDate, responseSite, roomNo);",
    "    phaseStartedMs = Date.now();\n    const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n    const completions = findIndicatorRoomActiveCleaningCompletions_(historySheet, businessDate, responseSite, roomNo);\n    phaseTiming.historyLookupMs = Math.max(0, Date.now() - phaseStartedMs);",
    'history lookup timing'
)

segment = replace_once(
    segment,
    "    version = reserveDataVersion_({ lockHeld: true });\n    markIndicatorRoomCleaningCompletionsDeleted_(historySheet, completions, resetAt);",
    "    phaseStartedMs = Date.now();\n    version = reserveDataVersion_({ lockHeld: true });\n    phaseTiming.reserveVersionMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    phaseStartedMs = Date.now();\n    markIndicatorRoomCleaningCompletionsDeleted_(historySheet, completions, resetAt);\n    phaseTiming.markHistoryDeletedMs = Math.max(0, Date.now() - phaseStartedMs);",
    'version/delete timing'
)

segment = replace_once(
    segment,
    "    updateRowByHeaders_(currentSheet, rowInfo.rowNumber, {",
    "    phaseStartedMs = Date.now();\n    updateRowByHeaders_(currentSheet, rowInfo.rowNumber, {",
    'current room update start'
)
segment = replace_once(
    segment,
    "      '마지막변경버전': version\n    });\n\n    appendUnifiedHistory_({",
    "      '마지막변경버전': version\n    });\n    phaseTiming.updateCurrentRoomMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    phaseStartedMs = Date.now();\n    appendUnifiedHistory_({",
    'current room update/history timing boundary'
)
segment = replace_once(
    segment,
    "      version\n    });\n\n    SpreadsheetApp.flush();\n    publishDataVersion_(version, {",
    "      version\n    });\n    phaseTiming.appendResetHistoryMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    phaseStartedMs = Date.now();\n    SpreadsheetApp.flush();\n    phaseTiming.flushMs = Math.max(0, Date.now() - phaseStartedMs);\n\n    phaseStartedMs = Date.now();\n    publishDataVersion_(version, {",
    'history/flush/publish timing boundary'
)
segment = replace_once(
    segment,
    "      lockHeld: true\n    });\n  } finally {",
    "      lockHeld: true\n    });\n    phaseTiming.publishVersionMs = Math.max(0, Date.now() - phaseStartedMs);\n  } finally {",
    'publish timing end'
)
segment = replace_once(
    segment,
    "      totalMs: Math.max(0, finishedMs - startedMs)\n    }",
    "      totalMs: Math.max(0, finishedMs - startedMs),\n      phases: phaseTiming\n    }",
    'timing response phases'
)

server = server[:start] + segment + server[end:]

client_old = """      const totalMs = Math.round(performance.now() - clickedAt);\n      const serverMs = Number(result.timing?.totalMs || result.performance?.elapsedMs || 0);\n      const duplicateIgnored = action === 'CLEANING_COMPLETE' && result.alreadyCompleted === true;\n      setSyncStatus(duplicateIgnored\n        ? `${room.roomNo}호 중복 청소완료 요청 제외 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`\n        : `${room.roomNo}호 저장 완료 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`);"""
client_new = """      const totalMs = Math.round(performance.now() - clickedAt);\n      const serverMs = Number(result.timing?.totalMs || result.performance?.elapsedMs || 0);\n      const resetPhases = action === 'CLEANING_RESET' ? (result.timing?.phases || {}) : {};\n      const resetTimingText = action === 'CLEANING_RESET'\n        ? ` · 조회${Number(resetPhases.historyLookupMs || 0)} · 삭제${Number(resetPhases.markHistoryDeletedMs || 0)} · 현재${Number(resetPhases.updateCurrentRoomMs || 0)} · 이력${Number(resetPhases.appendResetHistoryMs || 0)} · flush${Number(resetPhases.flushMs || 0)} · 발행${Number(resetPhases.publishVersionMs || 0)}`\n        : '';\n      const duplicateIgnored = action === 'CLEANING_COMPLETE' && result.alreadyCompleted === true;\n      setSyncStatus(duplicateIgnored\n        ? `${room.roomNo}호 중복 청소완료 요청 제외 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`\n        : `${room.roomNo}호 저장 완료 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}${resetTimingText}`);"""
client = replace_once(client, client_old, client_new, 'client diagnostic status')

server_path.write_text(server, encoding='utf-8')
client_path.write_text(client, encoding='utf-8')

server_check = server_path.read_text(encoding='utf-8')
client_check = client_path.read_text(encoding='utf-8')
server_segment = server_check[server_check.find(start_marker):server_check.find(end_marker, server_check.find(start_marker))]
required_server = [
    'phaseTiming.currentRoomLookupMs',
    'phaseTiming.historyLookupMs',
    'phaseTiming.reserveVersionMs',
    'phaseTiming.markHistoryDeletedMs',
    'phaseTiming.updateCurrentRoomMs',
    'phaseTiming.appendResetHistoryMs',
    'phaseTiming.flushMs',
    'phaseTiming.publishVersionMs',
    'phases: phaseTiming'
]
for token in required_server:
    if token not in server_segment:
        raise SystemExit(f'VERIFY_ERROR: missing {token}')
if 'resetTimingText' not in client_check:
    raise SystemExit('VERIFY_ERROR: client diagnostic display missing')
if 'createTextFinder(String(businessDate || \'\').trim())' not in server_check:
    raise SystemExit('VERIFY_ERROR: v28 TextFinder optimization was not preserved')

print('PATCH_OK')
print('Diagnostic only; production Apps Script NOT changed yet')
print('Changed: 06_Indicator.js, Client.html')
print('Added: CLEANING_RESET phase timing (lookup/delete/current/history/flush/publish)')
print('Preserved: v26 Sheet-version fix, v28 TextFinder lookup optimization, reset logic and permissions')
print('No Cloud Run change required')
print('VERIFY: PASS')
