from pathlib import Path

path = Path('19_RoommaidCloseJournal.js')
text = path.read_text(encoding='utf-8')

old = """    // 업무이력은 날짜 TextFinder로 후보행만 읽습니다. 전체 업무이력 열 스캔을 제거합니다.\n    let dbSaved = null; // DAILY_CLOSE_READ_DB_FIRST_V1\n    try {\n      dbSaved = readDailyCloseDbSnapshots_(token, businessDate, businessDate, preferredSite)[0] || null;\n    } catch (error) {\n      dbSaved = null;\n    }\n    const historyBundle = readRoommaidCloseHistoryBundleFast_(businessDate, preferredSite);\n    const historyRows = historyBundle.historyRows;\n    const saved = dbSaved || historyBundle.saved;\n"""
new = """    // DB-native 업무일자/사업장은 PostgreSQL history를 원본으로 사용하고 Sheet TextFinder를 건너뜁니다.\n    // 과거·미완전 업무일자는 기존 Sheet 후보행 조회를 그대로 유지합니다.\n    const historyBundle = readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, preferredSite); // ROOMMAID_CLOSE_HISTORY_DB_FIRST_V1\n    const historyRows = historyBundle.historyRows;\n    const dbSaved = historyBundle.dbSaved || null;\n    const saved = historyBundle.saved;\n"""
if old in text:
    text = text.replace(old, new, 1)
elif 'readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, preferredSite)' not in text:
    raise SystemExit('history source block not found')

old2 = """        savedSource: dbSaved ? 'REALTIME_DB' : (historyBundle.saved ? 'SHEET' : 'NONE'), // DAILY_CLOSE_READ_DB_FIRST_V1\n        currentRowCount: currentRows.length,\n        historyRowCount: historyRows.length,\n        historyLookup: 'DATE_TEXTFINDER'\n"""
new2 = """        savedSource: dbSaved ? 'REALTIME_DB' : (historyBundle.saved ? 'SHEET' : 'NONE'), // DAILY_CLOSE_READ_DB_FIRST_V1\n        currentRowCount: currentRows.length,\n        historyRowCount: historyRows.length,\n        historyLookup: historyBundle.dbFirst ? 'REALTIME_DB' : 'DATE_TEXTFINDER', // ROOMMAID_CLOSE_HISTORY_DB_FIRST_V1\n        historyDbFirst: Boolean(historyBundle.dbFirst),\n        historyStateVersion: Number(historyBundle.stateVersion || 0)\n"""
if old2 in text:
    text = text.replace(old2, new2, 1)
elif "historyLookup: historyBundle.dbFirst ? 'REALTIME_DB' : 'DATE_TEXTFINDER'" not in text:
    raise SystemExit('optimization block not found')

path.write_text(text, encoding='utf-8')
