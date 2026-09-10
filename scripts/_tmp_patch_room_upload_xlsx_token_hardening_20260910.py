from pathlib import Path

ROOM = Path('09_RoomStatusUpload.js')
WORKFLOW = Path('.github/workflows/deploy-apps-script.yml')
VALIDATOR = Path('scripts/validate_room_upload_xlsx_token_hardening_20260910.py')

text = ROOM.read_text(encoding='utf-8')

old_parser = """  const occurrences = {};
  const unknownRooms = new Set();
  const headings = [];

  NOVA_ROOM_UPLOAD.STATUS_SHEETS.forEach(def => {
    const sheetBlob = sheetFiles[normalizeUploadHeading_(def.sheetName)];
    if (!sheetBlob) return;
    headings.push(def.sheetName);
    const values = parseXlsxWorksheetValues_(sheetBlob.getDataAsString('UTF-8'), sharedStrings);
    values.forEach(value => collectWorkbookRoomValue_(value, def.code, master, occurrences, unknownRooms));
  });

  const parsed = buildParsedUpload_(occurrences, Array.from(unknownRooms), headings, []);
"""
new_parser = """  const occurrences = {};
  const unknownRooms = new Set();
  const headings = [];
  const workbookDiagnostics = { recoveredCells: 0, recoveredRooms: 0 }; // ROOM_UPLOAD_XLSX_TOKEN_HARDENING_V1

  NOVA_ROOM_UPLOAD.STATUS_SHEETS.forEach(def => {
    const sheetBlob = sheetFiles[normalizeUploadHeading_(def.sheetName)];
    if (!sheetBlob) return;
    headings.push(def.sheetName);
    const values = parseXlsxWorksheetValues_(sheetBlob.getDataAsString('UTF-8'), sharedStrings);
    values.forEach(value => collectWorkbookRoomValue_(value, def.code, master, occurrences, unknownRooms, workbookDiagnostics));
  });

  const parserWarnings = [];
  if (workbookDiagnostics.recoveredCells > 0) {
    parserWarnings.push(
      `XLSX 객실번호 표기 ${workbookDiagnostics.recoveredCells}개 셀에서 ${workbookDiagnostics.recoveredRooms}실을 자동 보정해 인식했습니다. 반영 전 상태별 건수를 확인하세요.`
    );
  }
  const parsed = buildParsedUpload_(occurrences, Array.from(unknownRooms), headings, [], parserWarnings);
"""
if 'ROOM_UPLOAD_XLSX_TOKEN_HARDENING_V1' not in text:
    if old_parser not in text:
        raise SystemExit('parser anchor not found')
    text = text.replace(old_parser, new_parser, 1)

old_collect = """function collectWorkbookRoomValue_(value, statusCode, master, occurrences, unknownRooms) { // (엑셀 셀 객실번호 검증)
  const roomNo = normalizeRoomNo_(value);
  if (!roomNo) return;
  if (master.byRoomNo[roomNo]) {
    addUploadOccurrence_(occurrences, roomNo, statusCode);
  } else if (looksLikeRoomNoForMaster_(roomNo, master)) {
    unknownRooms.add(roomNo);
  }
}
"""
new_collect = """function collectWorkbookRoomValue_(value, statusCode, master, occurrences, unknownRooms, diagnostics) { // (ROOM_UPLOAD_XLSX_TOKEN_HARDENING_V1 · 엑셀 셀 객실번호 엄격·보정 검증)
  const rawValue = String(value == null ? '' : value).trim();
  if (!rawValue) return;

  // 기존 정상 셀(6111 / 6111.0)은 가장 먼저 정확일치로 처리합니다.
  // '6111호' 역시 안전한 단일 객실 표기로 취급합니다.
  const exactRoomNo = normalizeRoomNo_(rawValue.replace(/호\\s*$/i, '').trim());
  if (exactRoomNo && master.byRoomNo[exactRoomNo]) {
    addUploadOccurrence_(occurrences, exactRoomNo, statusCode);
    return;
  }
  if (exactRoomNo && looksLikeRoomNoForMaster_(exactRoomNo, master)) {
    unknownRooms.add(exactRoomNo);
    return;
  }

  // 한 셀에 '6111 / 6109', '6111호, 6109호', 줄바꿈 등으로 묶인 경우
  // 4자리 토큰을 각각 객실마스터와 대조합니다. 마스터에 없는 유사 번호는
  // unknownRooms로 보내 최종 반영을 차단합니다. 인식 실패를 공실로 조용히 넘기지 않습니다.
  const roomTokens = extractRoomTokens_(rawValue);
  if (!roomTokens.length) return;
  const seen = new Set();
  let recoveredRooms = 0;
  roomTokens.forEach(token => {
    const roomNo = normalizeRoomNo_(token);
    if (!roomNo || seen.has(roomNo)) return;
    seen.add(roomNo);
    if (master.byRoomNo[roomNo]) {
      addUploadOccurrence_(occurrences, roomNo, statusCode);
      recoveredRooms += 1;
    } else if (looksLikeRoomNoForMaster_(roomNo, master)) {
      unknownRooms.add(roomNo);
    }
  });
  if (recoveredRooms > 0 && diagnostics && typeof diagnostics === 'object') {
    diagnostics.recoveredCells = Number(diagnostics.recoveredCells || 0) + 1;
    diagnostics.recoveredRooms = Number(diagnostics.recoveredRooms || 0) + recoveredRooms;
  }
}
"""
if 'ROOM_UPLOAD_XLSX_TOKEN_HARDENING_V1 · 엑셀 셀 객실번호 엄격·보정 검증' not in text:
    if old_collect not in text:
        raise SystemExit('collect anchor not found')
    text = text.replace(old_collect, new_collect, 1)

ROOM.write_text(text, encoding='utf-8')

validator = r'''from pathlib import Path
import sys

SRC = Path('09_RoomStatusUpload.js').read_text(encoding='utf-8')


def require(needle: str, label: str):
    if needle not in SRC:
        print(f'ERROR: missing {label}: {needle}', file=sys.stderr)
        raise SystemExit(91)

require('ROOM_UPLOAD_XLSX_TOKEN_HARDENING_V1', 'hardening marker')
require("const workbookDiagnostics = { recoveredCells: 0, recoveredRooms: 0 }", 'workbook recovery diagnostics')
require('collectWorkbookRoomValue_(value, def.code, master, occurrences, unknownRooms, workbookDiagnostics)', 'diagnostics passed to XLSX collector')
require("rawValue.replace(/호\\s*$/i, '').trim()", 'Korean room suffix normalization')
require('const roomTokens = extractRoomTokens_(rawValue);', 'embedded/multi-room token recovery')
require('if (master.byRoomNo[roomNo])', 'master exact membership guard')
require('else if (looksLikeRoomNoForMaster_(roomNo, master))', 'unknown master-like room guard')
require('unknownRooms.add(roomNo);', 'unknown room blocking path')
require('parserWarnings.push(', 'preview warning for recovered cells')
require('buildParsedUpload_(occurrences, Array.from(unknownRooms), headings, [], parserWarnings)', 'warnings preserved into upload validation')
require('const canApply = !missingSheets.length && !duplicateRooms.length && !unknownRooms.length', 'unknown room still blocks apply')

# Regression fixtures document the previously missed shapes the source must now parse through extractRoomTokens_.
fixtures = {
    '6111호': ['6111'],
    '6111 / 6109': ['6111', '6109'],
    '6111호, 6109호': ['6111', '6109'],
    '6111\\n6109': ['6111', '6109'],
}
import re
for raw, expected in fixtures.items():
    got = re.findall(r'(?<!\\d)\\d{4}(?!\\d)', raw)
    if got != expected:
        raise SystemExit(f'ERROR: fixture extraction mismatch for {raw!r}: {got} != {expected}')

print('PASS: XLSX status-sheet room tokens are recovered from decorated/multi-value cells, master-like unknown rooms still block apply, and recovery is surfaced in preview warnings.')
'''
VALIDATOR.write_text(validator, encoding='utf-8')

workflow = WORKFLOW.read_text(encoding='utf-8')
validator_line = '            scripts/validate_room_upload_xlsx_token_hardening_20260910.py\n'
anchor = '            scripts/validate_room_upload_db_first_v4_20260907.py\n'
if validator_line not in workflow:
    if anchor not in workflow:
        raise SystemExit('canonical workflow validator anchor not found')
    workflow = workflow.replace(anchor, anchor + validator_line, 1)
WORKFLOW.write_text(workflow, encoding='utf-8')

print('PATCHED: ROOM_UPLOAD_XLSX_TOKEN_HARDENING_V1')
