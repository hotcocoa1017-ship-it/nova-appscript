from pathlib import Path

MARKER = 'DAILY_CLOSE_SAVE_DB_FIRST_V1'
path = Path('14_DailyClose.js')
text = path.read_text(encoding='utf-8')


def replace_once(source, old, new, label):
    if old not in source:
        raise SystemExit(f'{label} anchor not found')
    return source.replace(old, new, 1)

if MARKER not in text:
    old = """        historyRows: allHistoryRows.filter(data => String(data['사업장'] || '').trim() === site),\n        attendanceEmployeeNos: Array.isArray(safe.attendanceEmployeeNos) ? safe.attendanceEmployeeNos : []\n"""
    new = """        historyRows: allHistoryRows.filter(data => String(data['사업장'] || '').trim() === site),\n        attendanceEmployeeNos: Array.isArray(safe.attendanceEmployeeNos) ? safe.attendanceEmployeeNos : [],\n        dbToken: token // DAILY_CLOSE_SAVE_DB_FIRST_V1 · 수동 사용자 마감만 DB-first\n"""
    text = replace_once(text, old, new, 'manual close token pass')

    old2 = """  if (!snapshot.totalRooms) throw new Error(`${businessDate} ${site} 현재객실현황이 없습니다.`);\n\n  const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n"""
    new2 = """  if (!snapshot.totalRooms) throw new Error(`${businessDate} ${site} 현재객실현황이 없습니다.`);\n\n  let dbCloseCommit = null; // DAILY_CLOSE_SAVE_DB_FIRST_V1\n  const dbCloseFirst = Boolean(preload.dbToken)\n    && typeof novaDailyCloseDbFirstEnabled_ === 'function'\n    && novaDailyCloseDbFirstEnabled_();\n  if (dbCloseFirst) {\n    const dbRequestId = dailyCloseDbRequestId_(businessDate, site, snapshot);\n    dbCloseCommit = novaDailyCloseDbSave_(preload.dbToken, {\n      businessDate,\n      site,\n      snapshot,\n      requestId: dbRequestId\n    });\n    if (!dbCloseCommit || dbCloseCommit.ok === false) {\n      throw new Error(`${site} 일일마감을 DB에 확정하지 못했습니다.`);\n    }\n    // 멱등 재시도면 최초 DB 확정시각을 그대로 Sheet 미러에도 사용합니다.\n    snapshot.closedAt = String(dbCloseCommit.closedAt || snapshot.closedAt || '').trim();\n    snapshot.closedBy = String(dbCloseCommit.closedBy || snapshot.closedBy || user.employeeNo).trim();\n    snapshot.closedByName = String(dbCloseCommit.closedByName || snapshot.closedByName || user.name || '').trim();\n  }\n\n  // PostgreSQL 확정 이후에만 기존 Sheet DAILY_CLOSE를 교체합니다.\n  const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n"""
    text = replace_once(text, old2, new2, 'DB close commit before Sheet')

    old3 = """  return Object.assign({ source: 'CLOSED', chunkCount: rows.length - 1 }, summaryDetail);\n}\n\nfunction buildDailyCloseSnapshot_"""
    new3 = """  return Object.assign({\n    source: 'CLOSED',\n    chunkCount: rows.length - 1,\n    dbFirst: Boolean(dbCloseFirst),\n    dbClose: dbCloseCommit ? {\n      version: Number(dbCloseCommit.version || 0),\n      requestId: String(dbCloseCommit.requestId || ''),\n      idempotent: Boolean(dbCloseCommit.idempotent)\n    } : null\n  }, summaryDetail);\n}\n\nfunction dailyCloseDbRequestId_(businessDate, site, snapshot) { // DAILY_CLOSE_SAVE_DB_FIRST_V1\n  const source = snapshot || {};\n  const stable = [\n    String(businessDate || ''),\n    String(site || ''),\n    String(source.sourceSignature || ''),\n    String(source.sourceUpdatedAt || ''),\n    String(source.totalRooms || 0),\n    String(source.cleaningCompleted || 0),\n    String(source.qmCompleted || 0),\n    String(source.housemanCompleted || 0)\n  ].join('|');\n  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, stable, Utilities.Charset.UTF_8);\n  const hash = Utilities.base64EncodeWebSafe(bytes).replace(/=+$/g, '').slice(0, 48);\n  return `DAILY_CLOSE_V1:${hash}`;\n}\n\nfunction buildDailyCloseSnapshot_"""
    text = replace_once(text, old3, new3, 'DB close response/helper')

for required in [MARKER, 'novaDailyCloseDbSave_', 'dailyCloseDbRequestId_', 'dbCloseCommit', 'PostgreSQL 확정 이후']:
    if required not in text:
        raise SystemExit(f'missing marker: {required}')

start = text.index('function saveDailyCloseSnapshotForSite_')
end = text.index('function buildDailyCloseSnapshot_', start)
block = text[start:end]
db_pos = block.index('dbCloseCommit = novaDailyCloseDbSave_')
mark_pos = block.index('markExistingDailyCloseDeleted_')
sheet_write_pos = block.index('historySheet.getRange(startRow')
if not (db_pos < mark_pos < sheet_write_pos):
    raise SystemExit(f'daily close DB-first ordering invalid: {db_pos}, {mark_pos}, {sheet_write_pos}')

path.write_text(text, encoding='utf-8')
print('Applied DAILY_CLOSE_SAVE_DB_FIRST_V1: build/validate -> DB close -> Sheet close mirror.')
