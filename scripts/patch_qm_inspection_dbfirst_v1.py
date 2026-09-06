from pathlib import Path

MARKER = 'QM_INSPECTION_FINALIZE_DB_FIRST_V1'
path = Path('16_QmChecklist.js')
text = path.read_text(encoding='utf-8')


def replace_once(source, old, new, label):
    if old not in source:
        raise SystemExit(f'{label} anchor not found')
    return source.replace(old, new, 1)

if MARKER not in text:
    old = """    let version = Number(rowInfo.data['마지막변경버전'] || 0);\n    if (sheetCleaningStatus !== targetCleaningStatus) {\n      version = reserveDataVersion_({ lockHeld: true });\n      updates['마지막변경버전'] = version;\n      updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);\n      SpreadsheetApp.flush();\n      publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });\n    }\n\n    const failSummary = defects.map(item => `${item.placeLabel || '기타'} · ${item.itemLabel || '하자'}${item.note ? `: ${item.note}` : ''}`).join(' / ');\n"""
    new = """    let version = Number(rowInfo.data['마지막변경버전'] || 0);\n    if (sheetCleaningStatus !== targetCleaningStatus) {\n      // DB 품질결과와 Sheet 최종상태가 동일 변경버전을 공유하도록 먼저 예약만 합니다.\n      version = reserveDataVersion_({ lockHeld: true });\n      updates['마지막변경버전'] = version;\n    }\n\n    const failSummary = defects.map(item => `${item.placeLabel || '기타'} · ${item.itemLabel || '하자'}${item.note ? `: ${item.note}` : ''}`).join(' / ');\n"""
    text = replace_once(text, old, new, 'reserve version before DB finalization')

    old2 = """    let checklistRecordId = String(draftInfo.data['기록ID'] || '').trim();\n    if (draftInfo.rowNumber) {\n"""
    new2 = """    let checklistRecordId = String(draftInfo.data['기록ID'] || '').trim();\n    if (!checklistRecordId) {\n      checklistRecordId = `QMCL-${businessDate.replace(/-/g, '')}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;\n    }\n\n    let dbInspectionCommit = null; // QM_INSPECTION_FINALIZE_DB_FIRST_V1\n    const dbInspectionFirst = typeof novaQmInspectionDbFirstEnabled_ === 'function' && novaQmInspectionDbFirstEnabled_();\n    if (dbInspectionFirst) {\n      const dbRequestId = `QM_INSPECTION_V1:${checklistRecordId}`;\n      dbInspectionCommit = novaQmInspectionDbFinalize_(token, {\n        requestId: dbRequestId,\n        inspection: {\n          inspectionId: checklistRecordId,\n          businessDate,\n          site: String(rowInfo.data['사업장'] || site).trim(),\n          roomNo,\n          resultStatus: passed ? 'PASS' : 'FAIL',\n          roommaidEmployeeNo: roommaidNo,\n          secondaryRoommaidEmployeeNo: secondaryRoommaidNo,\n          qmEmployeeNo: user.employeeNo,\n          checklistRevision: checklist.revision,\n          answers: normalizedAnswers,\n          defects,\n          startedAt,\n          completedAt,\n          durationMinutes,\n          sourceVersion: version\n        }\n      });\n      if (!dbInspectionCommit || dbInspectionCommit.ok === false) {\n        throw new Error('QM 최종점검을 DB에 확정하지 못했습니다.');\n      }\n    }\n\n    // PostgreSQL 확정이 끝난 뒤 기존 Sheet 상태/이력을 후행 미러합니다.\n    if (sheetCleaningStatus !== targetCleaningStatus) {\n      updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);\n      SpreadsheetApp.flush();\n      publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });\n    }\n\n    if (draftInfo.rowNumber) {\n"""
    text = replace_once(text, old2, new2, 'DB finalize insertion')

    # checklistRecordId is now allocated before DB commit; remove duplicate generation from no-draft branch.
    old3 = """    } else {\n      checklistRecordId = `QMCL-${businessDate.replace(/-/g, '')}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;\n      appendUnifiedHistory_({\n"""
    new3 = """    } else {\n      appendUnifiedHistory_({\n"""
    text = replace_once(text, old3, new3, 'duplicate checklist id generation')

    old4 = """      durationMinutes,\n      version,\n      room: {\n"""
    new4 = """      durationMinutes,\n      version,\n      dbFirst: Boolean(dbInspectionFirst),\n      dbInspection: dbInspectionCommit ? {\n        inspectionId: String(dbInspectionCommit.inspectionId || checklistRecordId),\n        requestId: String(dbInspectionCommit.requestId || ''),\n        idempotent: Boolean(dbInspectionCommit.idempotent)\n      } : null,\n      room: {\n"""
    text = replace_once(text, old4, new4, 'DB metadata response')

for required in [
    MARKER,
    'novaQmInspectionDbFirstEnabled_',
    'novaQmInspectionDbFinalize_',
    'QM_INSPECTION_V1:',
    'dbInspectionCommit',
    'PostgreSQL 확정이 끝난 뒤'
]:
    if required not in text:
        raise SystemExit(f'missing marker: {required}')

# DB finalization must occur before the current Sheet final-status write and checklist history mirror.
start = text.index('function submitQmChecklistInspection')
end = text.index('function getQmInspectionAnalytics', start)
block = text[start:end]
db_pos = block.index('dbInspectionCommit = novaQmInspectionDbFinalize_')
sheet_pos = block.index('updateRowByHeaders_(sheet, rowInfo.rowNumber, updates)')
history_pos = block.index("'처리상태': passed ? 'PASS' : 'FAIL'")
if not (db_pos < sheet_pos < history_pos):
    raise SystemExit(f'QM DB-first ordering invalid: {db_pos}, {sheet_pos}, {history_pos}')

path.write_text(text, encoding='utf-8')
print('Applied QM_INSPECTION_FINALIZE_DB_FIRST_V1: validate -> DB finalize -> Sheet mirror.')
