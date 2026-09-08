from pathlib import Path

p = Path('19_RoommaidCloseJournal.js')
s = p.read_text(encoding='utf-8')

MARKER = 'ROOMMAID_CLOSE_COLD_READ_V5'
if MARKER in s:
    print('V5 already applied')
    raise SystemExit(0)

old_snapshot = """    const liveSnapshot = buildDailyCloseSnapshot_(businessDate, preferredSite, {
      closedBy: saved ? saved.closedBy : '',
      closedByName: saved ? saved.closedByName : '',
      closedAt: saved ? saved.closedAt : '',
      includeRooms: false,
      currentRows,
      historyRows,
      attendanceEmployeeNos
    });"""
new_snapshot = """    const liveSnapshot = buildRoommaidCloseLiveSnapshotFast_(businessDate, preferredSite, {
      closedBy: saved ? saved.closedBy : '',
      closedByName: saved ? saved.closedByName : '',
      closedAt: saved ? saved.closedAt : '',
      currentRows,
      historyRows,
      users,
      attendanceEmployeeNos
    }); // ROOMMAID_CLOSE_COLD_READ_V5"""
if old_snapshot not in s:
    raise SystemExit('live snapshot anchor not found')
s = s.replace(old_snapshot, new_snapshot, 1)

anchor = "function readRoommaidCloseRealtimeCurrentRows_(token, businessDate, site) { // (PostgreSQL 현재객실 조회 · 조회전용·실패시 Sheet fallback)"
helper = """function buildRoommaidCloseLiveSnapshotFast_(businessDate, site, options) { // ROOMMAID_CLOSE_VIEW_SNAPSHOT_V5
  const safe = options || {};
  const currentRows = Array.isArray(safe.currentRows) ? safe.currentRows : [];
  const historyRows = Array.isArray(safe.historyRows) ? safe.historyRows : [];
  const users = safe.users || getUserIndex_().byEmployeeNo;
  const attendanceEmployeeNos = uniqueEmployeeNos_(safe.attendanceEmployeeNos || []);
  const journal = buildRoommaidCloseJournal_(businessDate, site, currentRows, historyRows, users, attendanceEmployeeNos);
  return {
    businessDate,
    site,
    closedAt: String(safe.closedAt || '').trim(),
    closedBy: String(safe.closedBy || '').trim(),
    closedByName: String(safe.closedByName || '').trim(),
    sourceUpdatedAt: latestRoommaidCloseSourceAt_(currentRows, historyRows),
    sourceSignature: roommaidCloseSourceSignature_(currentRows, historyRows, site),
    attendanceEmployeeNos: uniqueEmployeeNos_(journal && journal.attendanceEmployeeNos || attendanceEmployeeNos),
    roommaidCloseJournal: journal
  };
}

"""
if anchor not in s:
    raise SystemExit('realtime current rows anchor not found')
s = s.replace(anchor, helper + anchor, 1)

old_master = "  const master = readRoomMasterIndexForClose_(normalizedSite);"
new_master = "  const master = readRoomMasterIndexForCloseCached_(normalizedSite); // ROOMMAID_CLOSE_MASTER_SIGNATURE_CACHE_V5"
if old_master not in s:
    raise SystemExit('master signature anchor not found')
s = s.replace(old_master, new_master, 1)

old_tail = """function findRoommaidCloseTodayTailRange_(sheet, dateColumn, lastRow, businessDate) { // ROOMMAID_CLOSE_TODAY_TAIL_SCAN_V4
  const tailRows = 20000;
  const guardRows = 2000;
  const startRow = Math.max(2, lastRow - tailRows + 1);
  const rowCount = lastRow - startRow + 1;
  if (rowCount <= 0) return null;
  let values = [];
  try {
    values = sheet.getRange(startRow, dateColumn, rowCount, 1).getDisplayValues();
  } catch (error) {
    return null;
  }
  const target = String(businessDate || '').trim();
  let firstMatchOffset = -1;
  for (let index = 0; index < values.length; index += 1) {
    if (String(values[index][0] || '').trim() !== target) continue;
    firstMatchOffset = index;
    break;
  }
  if (firstMatchOffset < 0) return null;
  if (startRow > 2 && firstMatchOffset < guardRows) return null;
  return { complete: true, startRow: startRow + firstMatchOffset };
}"""
new_tail = """function findRoommaidCloseTodayTailRange_(sheet, dateColumn, lastRow, businessDate) { // ROOMMAID_CLOSE_TODAY_TAIL_SCAN_V4 · ROOMMAID_CLOSE_ADAPTIVE_TAIL_V5
  const target = String(businessDate || '').trim();
  if (!target) return null;
  const guardRows = 2000;
  const windows = [4096, 8192, 16384, 20000];
  for (const tailRows of windows) {
    const startRow = Math.max(2, lastRow - tailRows + 1);
    const rowCount = lastRow - startRow + 1;
    if (rowCount <= 0) return null;
    let values = [];
    try {
      values = sheet.getRange(startRow, dateColumn, rowCount, 1).getDisplayValues();
    } catch (error) {
      return null;
    }
    let firstMatchOffset = -1;
    for (let index = 0; index < values.length; index += 1) {
      if (String(values[index][0] || '').trim() !== target) continue;
      firstMatchOffset = index;
      break;
    }
    if (firstMatchOffset < 0) {
      if (startRow <= 2) return null;
      continue;
    }
    if (startRow <= 2 || firstMatchOffset >= guardRows) {
      return { complete: true, startRow: startRow + firstMatchOffset, scannedRows: rowCount };
    }
  }
  return null;
}"""
if old_tail not in s:
    raise SystemExit('V4 tail finder anchor not found')
s = s.replace(old_tail, new_tail, 1)

# Preserve existing V4 read-path contract for current validators/UI telemetry while marking the new implementation.
s = s.replace("      readPath = 'SHEET_TODAY_TAIL_V4';", "      readPath = 'SHEET_TODAY_TAIL_V4'; // ROOMMAID_CLOSE_ADAPTIVE_TAIL_V5", 1)

p.write_text(s, encoding='utf-8')
print('Applied roommaid close cold-read V5')
