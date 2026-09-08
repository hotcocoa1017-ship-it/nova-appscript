from pathlib import Path

MARKER = 'ROOMMAID_CLOSE_TODAY_TAIL_SCAN_V4'

journal = Path('19_RoommaidCloseJournal.js')
text = journal.read_text(encoding='utf-8')
if MARKER not in text:
    old = """  let matches = [];
  try {
    matches = sheet.getRange(2, dateColumn, lastRow - 1, 1)
      .createTextFinder(String(businessDate || ''))
      .matchEntireCell(true)
      .findAll();
  } catch (error) {
    return readRoommaidCloseHistoryBundle_(businessDate, site);
  }
  const rowNumbers = matches.map(range => range.getRow()).filter(row => row >= 2);
  if (!rowNumbers.length) return { historyRows: [], saved: null };
  const rows = readRowsByNumbersForClose_(sheet, headerMap, rowNumbers);
"""
    new = """  let rowNumbers = [];
  let readPath = 'DATE_TEXTFINDER';
  if (String(businessDate || '').trim() === businessDateText_()) {
    const tail = findRoommaidCloseTodayTailRange_(sheet, dateColumn, lastRow, businessDate);
    if (tail && tail.complete && tail.startRow >= 2) {
      rowNumbers = Array.from({ length: lastRow - tail.startRow + 1 }, (_, index) => tail.startRow + index);
      readPath = 'SHEET_TODAY_TAIL_V4';
    }
  }
  if (!rowNumbers.length) {
    let matches = [];
    try {
      matches = sheet.getRange(2, dateColumn, lastRow - 1, 1)
        .createTextFinder(String(businessDate || ''))
        .matchEntireCell(true)
        .findAll();
    } catch (error) {
      return readRoommaidCloseHistoryBundle_(businessDate, site);
    }
    rowNumbers = matches.map(range => range.getRow()).filter(row => row >= 2);
  }
  if (!rowNumbers.length) return { historyRows: [], saved: null, readPath };
  const rows = readRowsByNumbersForClose_(sheet, headerMap, rowNumbers);
"""
    if old not in text:
        raise SystemExit('History TextFinder anchor not found')
    text = text.replace(old, new, 1)

    old_return = "  return { historyRows, saved };\n}\n\nfunction readRoommaidCloseCurrentSelection_"
    new_return = """  return { historyRows, saved, readPath };
}

function findRoommaidCloseTodayTailRange_(sheet, dateColumn, lastRow, businessDate) { // ROOMMAID_CLOSE_TODAY_TAIL_SCAN_V4
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
}

function readRoommaidCloseCurrentSelection_"""
    if old_return not in text:
        raise SystemExit('History return anchor not found')
    text = text.replace(old_return, new_return, 1)
    journal.write_text(text, encoding='utf-8')

bridge = Path('RoommaidReportingDbFirstBridge.js')
b = bridge.read_text(encoding='utf-8')
old_bridge = "      readPath: 'SHEET_TODAY_DIRECT'\n"
new_bridge = "      readPath: String(fast && fast.readPath || 'SHEET_TODAY_DIRECT') // ROOMMAID_CLOSE_TODAY_TAIL_SCAN_V4\n"
if old_bridge in b:
    b = b.replace(old_bridge, new_bridge, 1)
    bridge.write_text(b, encoding='utf-8')
elif MARKER not in b:
    raise SystemExit('Bridge readPath anchor not found')

print('ROOMMAID_CLOSE_TODAY_TAIL_SCAN_V4 patch prepared')
