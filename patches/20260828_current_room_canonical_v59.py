from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INDICATOR = ROOT / '06_Indicator.js'
UPLOAD = ROOT / '09_RoomStatusUpload.js'
SYNC = ROOT / 'RealtimeDailySync.js'


def fail(message):
    raise SystemExit(f'PATCH_ERROR: {message}')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# 1) Legacy/QM single-room lookup: current-room duplicates can temporarily exist
#    from historical repeated uploads. Never take the first physical row. Use the
#    same canonical freshness rule already used by indicator display:
#    version -> updatedAt -> rowNumber.
# -----------------------------------------------------------------------------
indicator = INDICATOR.read_text(encoding='utf-8')
old = """function findCurrentRoomRow_(sheet, businessDate, site, roomNo) { // (현재 객실 행 찾기)\n  const selection = getCurrentRowsForSelection_(businessDate, site);\n  const found = selection.items.find(item => String(item.data['객실번호'] || '').trim() === roomNo);\n  return found ? { rowNumber: found.rowNumber, data: found.data } : null;\n}\n"""
new = """function findCurrentRoomRow_(sheet, businessDate, site, roomNo) { // (현재 객실 행 찾기·중복 시 최신행 선택)\n  const selection = getCurrentRowsForSelection_(businessDate, site);\n  const roomNoText = String(roomNo || '').trim();\n  const candidates = selection.items.filter(item => String(item.data['객실번호'] || '').trim() === roomNoText);\n  if (!candidates.length) return null;\n  const found = candidates.reduce((latest, item) =>\n    !latest || compareCurrentRoomRowsForDisplay_(item, latest) > 0 ? item : latest\n  , null);\n  return { rowNumber: found.rowNumber, data: found.data };\n}\n"""
indicator = replace_once(indicator, old, new, 'canonical current-room lookup')
INDICATOR.write_text(indicator, encoding='utf-8')


# -----------------------------------------------------------------------------
# 2) Room-status upload duplicate prevention. getValues() returns 업무일자 as a
#    Date object, but the old target test compared String(Date) to yyyy-MM-dd.
#    Therefore removedTargetRowCount stayed 0 and each re-upload appended another
#    full room block. Read display values so date/site/employee identifiers are
#    compared exactly as stored/displayed. Existing full-rewrite fallback will
#    collapse any old duplicate blocks on the next upload for that date/site.
# -----------------------------------------------------------------------------
upload = UPLOAD.read_text(encoding='utf-8')
old = """      const existingRows = sheet.getLastRow() > 1\n        ? sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).getValues()\n        : [];\n"""
new = """      // 업무일자는 실제 셀값(Date)이 아니라 yyyy-MM-dd 표시값으로 읽어야\n      // 동일 업무일자·사업장 기존행을 정확히 찾아 교체할 수 있다.\n      const existingRows = sheet.getLastRow() > 1\n        ? sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).getDisplayValues()\n        : [];\n"""
upload = replace_once(upload, old, new, 'room upload display-value target matching')
UPLOAD.write_text(upload, encoding='utf-8')


# -----------------------------------------------------------------------------
# 3) Realtime mirror index: align it with the exact same canonical freshness
#    rule. This prevents DB event writes and legacy/QM reads from choosing
#    different physical duplicates when versions no longer happen to follow row
#    order.
# -----------------------------------------------------------------------------
sync = SYNC.read_text(encoding='utf-8')
old = """    if (!businessDate || !site || !roomNo) return;\n    // 아래쪽 행을 최신행으로 간주한다.\n    result.set(`${businessDate}|${site}|${roomNo}`, { rowNumber: offset + 2, data });\n"""
new = """    if (!businessDate || !site || !roomNo) return;\n    const key = `${businessDate}|${site}|${roomNo}`;\n    const candidate = { rowNumber: offset + 2, data };\n    const current = result.get(key);\n    // Indicator/QM 단건조회와 동일하게 version -> 수정일시 -> 행번호 순으로\n    // 최신 원본을 선택해 Realtime 미러와 legacy 경로가 같은 행을 보게 한다.\n    if (!current || compareCurrentRoomRowsForDisplay_(candidate, current) > 0) {\n      result.set(key, candidate);\n    }\n"""
sync = replace_once(sync, old, new, 'Realtime canonical current-room index')
SYNC.write_text(sync, encoding='utf-8')


# -----------------------------------------------------------------------------
# Validation: syntax plus explicit regression guards. Full release guard runs in
# workflow after this script.
# -----------------------------------------------------------------------------
for path in [INDICATOR, UPLOAD, SYNC]:
    subprocess.run(['node', '--check', str(path)], cwd=ROOT, check=True)

indicator_check = INDICATOR.read_text(encoding='utf-8')
if "candidates.reduce" not in indicator_check or "compareCurrentRoomRowsForDisplay_(item, latest)" not in indicator_check:
    fail('canonical lookup regression guard failed')

upload_check = UPLOAD.read_text(encoding='utf-8')
needle = "sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).getDisplayValues()"
if needle not in upload_check:
    fail('upload duplicate-prevention regression guard failed')

sync_check = SYNC.read_text(encoding='utf-8')
if "compareCurrentRoomRowsForDisplay_(candidate, current) > 0" not in sync_check:
    fail('Realtime canonical index regression guard failed')

print('CURRENT_ROOM_CANONICAL_V59_OK')
print('Changed: 06_Indicator.js, 09_RoomStatusUpload.js, RealtimeDailySync.js')
print('Canonical row: version -> updatedAt -> rowNumber')
print('Upload duplicate prevention: business-date matching uses display values')
print('Existing duplicates: newest row is used immediately; next same date/site upload collapses duplicates')
print('Syntax: PASS')
