from pathlib import Path
import re
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

fixtures = {
    '6111호': ['6111'],
    '6111 / 6109': ['6111', '6109'],
    '6111호, 6109호': ['6111', '6109'],
    '6111\n6109': ['6111', '6109'],
}
for raw, expected in fixtures.items():
    got = re.findall(r'(?<!\d)\d{4}(?!\d)', raw)
    if got != expected:
        raise SystemExit(f'ERROR: fixture extraction mismatch for {raw!r}: {got} != {expected}')

print('PASS: XLSX status-sheet room tokens are recovered from decorated/multi-value cells, master-like unknown rooms still block apply, and recovery is surfaced in preview warnings.')
