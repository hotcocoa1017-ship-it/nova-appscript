from pathlib import Path

# Patch daily close save path.
p14 = Path('14_DailyClose.js')
t14 = p14.read_text(encoding='utf-8')
old14 = """      const allCurrentRows = readCurrentRowsForClose_(businessDate, requestedSite);\n      const allHistoryRows = readHistoryRowsForClose_(businessDate, requestedSite);\n      const results = sites.map(site => saveDailyCloseSnapshotForSite_(businessDate, site, user, {\n        currentRows: allCurrentRows.filter(data => String(data['사업장'] || '').trim() === site),\n        historyRows: allHistoryRows.filter(data => String(data['사업장'] || '').trim() === site),\n        attendanceEmployeeNos: Array.isArray(safe.attendanceEmployeeNos) ? safe.attendanceEmployeeNos : [],\n        dbToken: token // DAILY_CLOSE_SAVE_DB_FIRST_V1 · 수동 사용자 마감만 DB-first\n      }));\n"""
new14 = """      const dbSources = {}; // DAILY_CLOSE_SOURCE_DB_FIRST_V1\n      sites.forEach(site => {\n        const source = tryNovaDailyCloseDbSource_(token, businessDate, site);\n        if (source && source.ready) dbSources[site] = source;\n      });\n      const needsSheetFallback = sites.some(site => !dbSources[site]);\n      const allCurrentRows = needsSheetFallback ? readCurrentRowsForClose_(businessDate, requestedSite) : [];\n      const allHistoryRows = needsSheetFallback ? readHistoryRowsForClose_(businessDate, requestedSite) : [];\n      const results = sites.map(site => {\n        const source = dbSources[site] || null;\n        return saveDailyCloseSnapshotForSite_(businessDate, site, user, {\n          currentRows: source ? source.currentRows : allCurrentRows.filter(data => String(data['사업장'] || '').trim() === site),\n          historyRows: source ? source.historyRows : allHistoryRows.filter(data => String(data['사업장'] || '').trim() === site),\n          attendanceEmployeeNos: Array.isArray(safe.attendanceEmployeeNos) ? safe.attendanceEmployeeNos : [],\n          dbToken: token, // DAILY_CLOSE_SAVE_DB_FIRST_V1 · 수동 사용자 마감만 DB-first\n          dbSource: Boolean(source) // DAILY_CLOSE_SOURCE_DB_FIRST_V1\n        });\n      });\n"""
if old14 in t14:
    t14 = t14.replace(old14, new14, 1)
elif 'const dbSources = {}; // DAILY_CLOSE_SOURCE_DB_FIRST_V1' not in t14:
    raise SystemExit('14_DailyClose save source block not found')
p14.write_text(t14, encoding='utf-8')

# Patch roommaid close save path.
p19 = Path('19_RoommaidCloseJournal.js')
t19 = p19.read_text(encoding='utf-8')
old19 = """      const currentRows = readCurrentRowsForClose_(businessDate, site);\n      if (!currentRows.length) throw new Error(`${businessDate} ${site} 현재객실현황이 없습니다.`);\n      const historyRows = readHistoryRowsForClose_(businessDate, site);\n      const result = saveDailyCloseSnapshotForSite_(businessDate, site, user, {\n        currentRows,\n        historyRows,\n        attendanceEmployeeNos\n      });\n"""
new19 = """      const dbSource = tryNovaDailyCloseDbSource_(token, businessDate, site); // DAILY_CLOSE_SOURCE_DB_FIRST_V1\n      const currentRows = dbSource ? dbSource.currentRows : readCurrentRowsForClose_(businessDate, site);\n      if (!currentRows.length) throw new Error(`${businessDate} ${site} 현재객실현황이 없습니다.`);\n      const historyRows = dbSource ? dbSource.historyRows : readHistoryRowsForClose_(businessDate, site);\n      const result = saveDailyCloseSnapshotForSite_(businessDate, site, user, {\n        currentRows,\n        historyRows,\n        attendanceEmployeeNos,\n        dbToken: token, // DAILY_CLOSE_SAVE_DB_FIRST_V1\n        dbSource: Boolean(dbSource)\n      });\n"""
if old19 in t19:
    t19 = t19.replace(old19, new19, 1)
elif 'const dbSource = tryNovaDailyCloseDbSource_(token, businessDate, site)' not in t19:
    raise SystemExit('19_RoommaidCloseJournal save source block not found')
p19.write_text(t19, encoding='utf-8')
