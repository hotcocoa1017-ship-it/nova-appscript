from pathlib import Path

MARKER = 'DB_PRIMARY_FORWARD_GUARD_V1'

# 1) Daily close LIVE overview: when an explicit site is DB-ready, do not read Sheet current/history.
p = Path('14_DailyClose.js')
s = p.read_text(encoding='utf-8')
needle = """  const allCurrentRows = readCurrentRowsForClose_(request.date, request.site);\n  const allHistoryRows = readHistoryRowsForClose_(request.date, request.site);\n"""
replacement = """  // DB-ready 단일 사업장 LIVE 조회는 Sheet current/history를 읽지 않습니다. // DAILY_CLOSE_LIVE_DB_FIRST_V1\n  if (request.site) {\n    const dbLiveSource = tryNovaDailyCloseDbSource_(dbToken, request.date, request.site);\n    if (dbLiveSource && dbLiveSource.ready) {\n      const live = buildDailyCloseSnapshot_(request.date, request.site, {\n        closedBy: '',\n        closedAt: '',\n        includeRooms: false,\n        currentRows: dbLiveSource.currentRows,\n        historyRows: dbLiveSource.historyRows\n      });\n      return {\n        period: 'DAILY',\n        businessDate: request.date,\n        site: request.site,\n        source: 'LIVE',\n        isClosed: false,\n        closedAt: '',\n        closedBy: '',\n        summary: aggregateDailyCloseSummaries_([live]),\n        sites: [Object.assign({ source: 'LIVE', dbFirst: true }, live)],\n        dbFirst: true,\n        message: ''\n      };\n    }\n  }\n\n  const allCurrentRows = readCurrentRowsForClose_(request.date, request.site);\n  const allHistoryRows = readHistoryRowsForClose_(request.date, request.site);\n"""
if 'DAILY_CLOSE_LIVE_DB_FIRST_V1' not in s:
    if needle not in s:
        raise SystemExit('daily close insertion point not found')
    s = s.replace(needle, replacement, 1)
p.write_text(s, encoding='utf-8')

# 2) Disable Sheet -> DB forward/JIT by default in the DB-primary build.
p = Path('RealtimeDailySync.js')
s = p.read_text(encoding='utf-8')
const_end = """  FORWARD_INTERVAL_MS: 5 * 60 * 1000\n});\n\n"""
helper = """  FORWARD_INTERVAL_MS: 5 * 60 * 1000\n});\n\nfunction novaRealtimeSheetForwardSyncEnabled_() { // DB_PRIMARY_FORWARD_GUARD_V1\n  const props = PropertiesService.getScriptProperties();\n  return String(props.getProperty('NOVA_SHEET_FORWARD_SYNC_ENABLED') || 'N').trim().toUpperCase() === 'Y';\n}\n\n"""
if MARKER not in s:
    if const_end not in s:
        raise SystemExit('realtime const insertion point not found')
    s = s.replace(const_end, helper, 1)

old = """function syncNovaRealtimeCurrentBusinessDate(businessDate, site, options) { // (당일 Sheets -> PostgreSQL 증분동기화)\n  const dateText = novaRealtimeFinalBusinessDate_(businessDate);\n  const siteText = String(site || '').trim();\n  const rooms = novaRealtimeFinalBuildRooms_(dateText, siteText, '');\n"""
new = """function syncNovaRealtimeCurrentBusinessDate(businessDate, site, options) { // (레거시 Sheets -> PostgreSQL 정방향 · DB_PRIMARY_FORWARD_GUARD_V1)\n  const dateText = novaRealtimeFinalBusinessDate_(businessDate);\n  const siteText = String(site || '').trim();\n  const safeOptions = options || {};\n  if (safeOptions.forceLegacyForward !== true && !novaRealtimeSheetForwardSyncEnabled_()) {\n    return { ok: true, skipped: true, reason: 'DB_PRIMARY_SHEET_FORWARD_DISABLED', businessDate: dateText, site: siteText };\n  }\n  const rooms = novaRealtimeFinalBuildRooms_(dateText, siteText, '');\n"""
if old in s:
    s = s.replace(old, new, 1)
# remove duplicate safeOptions declaration after users
s = s.replace("""  const users = novaRealtimeFinalBuildUsers_(sites);\n  const safeOptions = options || {};\n""", """  const users = novaRealtimeFinalBuildUsers_(sites);\n""", 1)

jit_old = """  const roomNo = String(safe.roomNo || '').trim();\n  if (!site || !roomNo) throw new Error('Realtime 단건 동기화에 사업장과 객실번호가 필요합니다.');\n  const rooms = novaRealtimeFinalBuildRooms_(businessDate, site, roomNo);\n"""
jit_new = """  const roomNo = String(safe.roomNo || '').trim();\n  if (!site || !roomNo) throw new Error('Realtime 단건 동기화에 사업장과 객실번호가 필요합니다.');\n  if (!novaRealtimeSheetForwardSyncEnabled_()) {\n    return { ok: true, skipped: true, reason: 'DB_PRIMARY_JIT_SHEET_SYNC_DISABLED', businessDate, site, roomNo };\n  }\n  const rooms = novaRealtimeFinalBuildRooms_(businessDate, site, roomNo);\n"""
if 'DB_PRIMARY_JIT_SHEET_SYNC_DISABLED' not in s:
    if jit_old not in s:
        raise SystemExit('JIT insertion point not found')
    s = s.replace(jit_old, jit_new, 1)

# Keep the explicit manual test useful without reopening scheduled/JIT sync.
s = s.replace(
    "const result = syncNovaRealtimeCurrentBusinessDate(novaRealtimeFinalBusinessDate_(), '');\n  console.log(JSON.stringify(result, null, 2));",
    "const result = syncNovaRealtimeCurrentBusinessDate(novaRealtimeFinalBusinessDate_(), '', { forceLegacyForward: true });\n  console.log(JSON.stringify(result, null, 2));",
    1
)
p.write_text(s, encoding='utf-8')

print('patched DB-primary LIVE read and Sheet forward/JIT guard')
