from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)

# 1) 객실현황 업로드: 현재객실현황 전체 재작성 대신 정상 블록은 제자리 교체,
#    초기화 이력 조회는 4회 원격읽기 -> 1회 일괄읽기로 축소합니다.
room_path = Path('09_RoomStatusUpload.js')
room = room_path.read_text(encoding='utf-8')

room = replace_once(
    room,
    """    const lock = acquireWriteLock_(30000);\n    try {\n      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);""",
    """    const applyStartedMs = Date.now();\n    const lockRequestedMs = Date.now();\n    const lock = acquireWriteLock_(30000);\n    const lockAcquiredMs = Date.now();\n    try {\n      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);""",
    'apply timing start'
)

room = replace_once(
    room,
    """      const existingForTarget = {};\n      const keptRows = [];\n      let removedTargetRowCount = 0;\n\n      existingRows.forEach(row => {\n        const data = rowObjectFromValues_(row, headerMap);\n        const isTarget = String(data['업무일자'] || '').trim() === preview.businessDate\n          && String(data['사업장'] || '').trim() === preview.site;\n        if (isTarget) {\n          removedTargetRowCount += 1;\n          const roomNo = normalizeRoomNo_(data['객실번호']);\n          if (roomNo) existingForTarget[roomNo] = data;\n        } else {\n          keptRows.push(row);\n        }\n      });""",
    """      const existingForTarget = {};\n      const keptRows = [];\n      const targetRowNumbers = [];\n      let removedTargetRowCount = 0;\n\n      existingRows.forEach((row, index) => {\n        const data = rowObjectFromValues_(row, headerMap);\n        const isTarget = String(data['업무일자'] || '').trim() === preview.businessDate\n          && String(data['사업장'] || '').trim() === preview.site;\n        if (isTarget) {\n          removedTargetRowCount += 1;\n          targetRowNumbers.push(index + 2);\n          const roomNo = normalizeRoomNo_(data['객실번호']);\n          if (roomNo) existingForTarget[roomNo] = data;\n        } else {\n          keptRows.push(row);\n        }\n      });""",
    'target row tracking'
)

old_write = """      const allRows = keptRows.concat(newRows);\n      if (sheet.getLastRow() > 1) {\n        sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).clearContent();\n      }\n      if (allRows.length) {\n        ensureSheetRowCapacity_(sheet, allRows.length + 1);\n        sheet.getRange(2, 1, allRows.length, lastColumn).setValues(allRows);\n      }\n      const maintenanceReset = resetExisting\n        ? resetRoomMaintenanceHistoryForUpload_(preview.businessDate, preview.site, updatedAt)\n        : createRoomMaintenanceResetSummary_();\n      SpreadsheetApp.flush();\n      publishDataVersion_(version, {"""
new_write = """      const currentWriteStartedMs = Date.now();\n      const targetRowsContiguous = targetRowNumbers.length === newRows.length\n        && targetRowNumbers.length > 0\n        && targetRowNumbers.every((rowNumber, index) => rowNumber === targetRowNumbers[0] + index);\n      let roomWriteMode = 'FULL_REWRITE';\n      let firstWrittenRow = keptRows.length + 2;\n\n      if (targetRowsContiguous) {\n        // 정상 운영 업로드는 동일 업무일자·사업장 객실 블록을 제자리에서 한 번만 교체합니다.\n        // 다른 업무일자/사업장 행을 clear+setValues로 다시 쓰지 않아 대용량 누적 시트의 지연을 제거합니다.\n        firstWrittenRow = targetRowNumbers[0];\n        ensureSheetRowCapacity_(sheet, firstWrittenRow + newRows.length - 1);\n        sheet.getRange(firstWrittenRow, 1, newRows.length, lastColumn).setValues(newRows);\n        roomWriteMode = 'IN_PLACE_BLOCK';\n      } else {\n        // 행수 변화·비연속 블록·최초 업로드 등 예외 상황은 기존 안전한 전체 교체 방식을 유지합니다.\n        const allRows = keptRows.concat(newRows);\n        if (sheet.getLastRow() > 1) {\n          sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).clearContent();\n        }\n        if (allRows.length) {\n          ensureSheetRowCapacity_(sheet, allRows.length + 1);\n          sheet.getRange(2, 1, allRows.length, lastColumn).setValues(allRows);\n        }\n        firstWrittenRow = keptRows.length + 2;\n      }\n      const currentWriteMs = Date.now() - currentWriteStartedMs;\n\n      const maintenanceStartedMs = Date.now();\n      const maintenanceReset = resetExisting\n        ? resetRoomMaintenanceHistoryForUpload_(preview.businessDate, preview.site, updatedAt)\n        : createRoomMaintenanceResetSummary_();\n      const maintenanceMs = Date.now() - maintenanceStartedMs;\n\n      const flushStartedMs = Date.now();\n      SpreadsheetApp.flush();\n      const flushMs = Date.now() - flushStartedMs;\n      publishDataVersion_(version, {"""
room = replace_once(room, old_write, new_write, 'fast current room write')

room = replace_once(
    room,
    """      const roomObjects = newRows.map((row, index) => currentRoomObject_(\n        rowObjectFromValues_(row, headerMap),\n        keptRows.length + index + 2,\n        {},\n        usersByEmployeeNo\n      ));""",
    """      const roomObjects = newRows.map((row, index) => currentRoomObject_(\n        rowObjectFromValues_(row, headerMap),\n        firstWrittenRow + index,\n        {},\n        usersByEmployeeNo\n      ));""",
    'returned room row numbers'
)

room = replace_once(
    room,
    """        maintenanceReset,\n        message: buildRoomStatusUploadApplyMessage_(preview, newRows.length, appliedAssignments.length, skippedAssignments.length, resetExisting, removedTargetRowCount, maintenanceReset)\n      };""",
    """        maintenanceReset,\n        timing: {\n          totalMs: Date.now() - applyStartedMs,\n          lockWaitMs: lockAcquiredMs - lockRequestedMs,\n          currentWriteMs,\n          maintenanceMs,\n          flushMs,\n          roomWriteMode\n        },\n        message: buildRoomStatusUploadApplyMessage_(preview, newRows.length, appliedAssignments.length, skippedAssignments.length, resetExisting, removedTargetRowCount, maintenanceReset)\n      };""",
    'apply timing response'
)

room = replace_once(
    room,
    """  const rowCount = historySheet.getLastRow() - 1;\n  const typeValues = historySheet.getRange(2, typeColumn, rowCount, 1).getDisplayValues();\n  const dateValues = historySheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();\n  const siteValues = historySheet.getRange(2, siteColumn, rowCount, 1).getDisplayValues();\n  const deletedValues = historySheet.getRange(2, deletedColumn, rowCount, 1).getDisplayValues();\n  const matchedRows = [];\n\n  for (let index = 0; index < rowCount; index += 1) {\n    if (String(dateValues[index][0] || '').trim() !== businessDate) continue;\n    if (String(siteValues[index][0] || '').trim() !== site) continue;\n    if (String(deletedValues[index][0] || 'N').trim().toUpperCase() === 'Y') continue;\n    const recordType = String(typeValues[index][0] || '').trim();""",
    """  const rowCount = historySheet.getLastRow() - 1;\n  // 업무이력 4개 열을 각각 원격조회하지 않고 한 번의 일괄조회로 판정합니다.\n  const historyValues = historySheet.getRange(2, 1, rowCount, historySheet.getLastColumn()).getDisplayValues();\n  const matchedRows = [];\n\n  for (let index = 0; index < rowCount; index += 1) {\n    const row = historyValues[index];\n    if (String(row[dateColumn - 1] || '').trim() !== businessDate) continue;\n    if (String(row[siteColumn - 1] || '').trim() !== site) continue;\n    if (String(row[deletedColumn - 1] || 'N').trim().toUpperCase() === 'Y') continue;\n    const recordType = String(row[typeColumn - 1] || '').trim();""",
    'maintenance history single read'
)

room_path.write_text(room, encoding='utf-8')

# 2) 클라이언트: 배정 초기화는 최종 목표가 "미배정"이므로 stale DB version에 막히지 않게 하고,
#    업로드 완료 후 불필요한 동기 전체 재조회를 사용자 응답 경로에서 분리합니다.
client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')

client = replace_once(
    client,
    """      // Realtime 요청은 DB version을 사용하고, Realtime 비활성/장애 시 legacy CLEANING_RESET만\n      // 별도로 보존한 Sheet version을 사용한다. 두 버전 도메인을 섞지 않는다.\n      expectedVersion: Number(room.version || 0),\n      sheetExpectedVersion: action === 'CLEANING_RESET'""",
    """      // Realtime 요청은 DB version을 사용하고, Realtime 비활성/장애 시 legacy CLEANING_RESET만\n      // 별도로 보존한 Sheet version을 사용한다. 두 버전 도메인을 섞지 않는다.\n      // CLEAR_ASSIGNMENT는 관리자가 현재 배정을 '없음'으로 만드는 멱등 작업이므로\n      // 지연된 Realtime version 때문에 초기화가 거절되지 않도록 version 충돌검사를 사용하지 않는다.\n      expectedVersion: action === 'CLEAR_ASSIGNMENT' ? 0 : Number(room.version || 0),\n      sheetExpectedVersion: action === 'CLEANING_RESET'""",
    'clear assignment version handling'
)

client = replace_once(
    client,
    """    let result;\n    try {\n      result = await send();\n    } catch (error) {\n      const code = String(error?.code || '').trim().toUpperCase();\n      if (!['ROOM_NOT_FOUND', 'FORBIDDEN', 'INVALID_STATE', 'ROOMMAID_NOT_AVAILABLE', 'QM_NOT_AVAILABLE'].includes(code)) throw error;\n      // 업무일 생성/최근 배정·QM 변경이 DB에 아직 없을 때 해당 객실만 Sheets->DB 보정 후 동일 requestId로 1회 재시도.\n      await callServer('syncNovaRealtimeRoomForAction', state.token, {\n        businessDate: safe.businessDate,\n        site: safe.site,\n        roomNo: safe.roomNo,\n        action: mappedAction\n      });\n      result = await send();\n    }""",
    """    let result;\n    try {\n      result = await send();\n    } catch (error) {\n      const code = String(error?.code || '').trim().toUpperCase();\n\n      // 권한/상태 오류는 DB 보정으로 해결되지 않으므로 느린 Sheets JIT 동기화를 실행하지 않습니다.\n      // 누락 객실 또는 배정대상 사용자 누락처럼 실제 DB 보정이 필요한 경우에만 1회 동기화합니다.\n      const jitCodes = mappedAction === 'ASSIGN_ROOMMAID'\n        ? ['ROOM_NOT_FOUND', 'ROOMMAID_NOT_AVAILABLE']\n        : mappedAction === 'QM_ASSIGN'\n          ? ['ROOM_NOT_FOUND', 'QM_NOT_AVAILABLE']\n          : ['ROOM_NOT_FOUND'];\n      if (!jitCodes.includes(code)) throw error;\n\n      await callServer('syncNovaRealtimeRoomForAction', state.token, {\n        businessDate: safe.businessDate,\n        site: safe.site,\n        roomNo: safe.roomNo,\n        action: mappedAction\n      });\n      if (mappedAction === 'CLEAR_ASSIGNMENT') safe.expectedVersion = 0;\n      result = await send();\n    }""",
    'realtime JIT narrowing'
)

client = replace_once(
    client,
    """  function handleRoomUploadPreview(event) { // (업로드 파일 서버 검증)\n    event.preventDefault();\n    const form = event.currentTarget;""",
    """  function handleRoomUploadPreview(event) { // (업로드 파일 서버 검증)\n    event.preventDefault();\n    const previewStartedAt = performance.now();\n    const form = event.currentTarget;""",
    'preview client timer start'
)

client = replace_once(
    client,
    """        state.indicator.uploadPreviewId = result.previewId || '';\n        renderRoomUploadPreview_(result);""",
    """        state.indicator.uploadPreviewId = result.previewId || '';\n        renderRoomUploadPreview_(result);\n        const totalMs = Math.round(performance.now() - previewStartedAt);\n        const serverMs = Number(result.performance?.elapsedMs || 0);\n        setSyncStatus(`객실현황 검증 완료 · 총 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`);""",
    'preview client timer result'
)

client = replace_once(
    client,
    """  async function applyRoomUploadPreview_(resetExisting) { // (검증된 객실현황 유지 반영·초기화 후 교체)\n    const previewId = state.indicator.uploadPreviewId;""",
    """  async function applyRoomUploadPreview_(resetExisting) { // (검증된 객실현황 유지 반영·초기화 후 교체)\n    const clickedAt = performance.now();\n    const previewId = state.indicator.uploadPreviewId;""",
    'apply client timer start'
)

client = replace_once(
    client,
    """      showToast(result.message || '객실현황을 반영했습니다.');\n      await loadIndicatorSnapshot({ silent: true, force: true });""",
    """      showToast(result.message || '객실현황을 반영했습니다.');\n      const totalMs = Math.round(performance.now() - clickedAt);\n      const serverMs = Number(result.performance?.elapsedMs || result.timing?.totalMs || 0);\n      const writeMs = Number(result.timing?.currentWriteMs || 0);\n      const lockMs = Number(result.timing?.lockWaitMs || 0);\n      const flushMs = Number(result.timing?.flushMs || 0);\n      setSyncStatus(\n        `객실현황 반영 완료 · 총 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`\n        + `${writeMs ? ` · 저장 ${writeMs}ms` : ''}${lockMs ? ` · 잠금 ${lockMs}ms` : ''}${flushMs ? ` · flush ${flushMs}ms` : ''}`\n      );\n\n      // 서버가 이미 최신 객실목록을 반환했으므로 완료 응답 직후 동일 자료를 다시 전체조회하지 않습니다.\n      // 보조 재조회는 사용자 응답 경로 밖에서 수행해 업로드 완료 체감을 지연시키지 않습니다.\n      window.setTimeout(() => {\n        if (state.activeMenu !== 'indicator' || !state.indicator.loaded) return;\n        void loadIndicatorSnapshot({ silent: true, force: true })\n          .catch(error => console.error('[NOVA] 업로드 후 보조 동기화 실패:', error));\n      }, 1200);""",
    'defer post-upload snapshot'
)

client_path.write_text(client, encoding='utf-8')

# Guardrails
room_check = room_path.read_text(encoding='utf-8')
client_check = client_path.read_text(encoding='utf-8')
required = [
    ('09_RoomStatusUpload.js', 'roomWriteMode = \'IN_PLACE_BLOCK\'', room_check),
    ('09_RoomStatusUpload.js', 'const historyValues = historySheet.getRange(2, 1, rowCount, historySheet.getLastColumn()).getDisplayValues();', room_check),
    ('09_RoomStatusUpload.js', 'timing: {\n          totalMs: Date.now() - applyStartedMs', room_check),
    ('Client.html', "expectedVersion: action === 'CLEAR_ASSIGNMENT' ? 0", client_check),
    ('Client.html', "const jitCodes = mappedAction === 'ASSIGN_ROOMMAID'", client_check),
    ('Client.html', '객실현황 반영 완료 · 총 ${totalMs}ms', client_check),
]
for file_name, marker, text in required:
    if marker not in text:
        raise SystemExit(f'{file_name}: guard marker missing: {marker}')

# Existing protected paths must remain present.
if 'function resetIndicatorRoomCleaningFast_' not in Path('06_Indicator.js').read_text(encoding='utf-8'):
    raise SystemExit('Protected cleaning reset fast path missing')
if 'SCHEMA_VERSION: 28' not in Path('19_RoommaidCloseJournal.js').read_text(encoding='utf-8'):
    raise SystemExit('Protected roommaid close schema 28 missing')

print('Room upload fast block write + assignment clear stabilization patch applied')
