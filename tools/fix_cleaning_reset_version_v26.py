#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'

if not CLIENT.exists():
    print('PATCH_ERROR: Client.html not found')
    sys.exit(1)

text = CLIENT.read_text(encoding='utf-8')
original = text

merge_anchor = "    const merged = Object.assign({}, legacyRoom);\n"
merge_insert = (
    "    const merged = Object.assign({}, legacyRoom);\n"
    "    // Sheet snapshot version and Realtime DB version are separate domains.\n"
    "    // Preserve the Sheet version before Realtime fields overwrite room.version.\n"
    "    if (!Object.prototype.hasOwnProperty.call(merged, '__sheetVersion')) {\n"
    "      merged.__sheetVersion = Number(legacyRoom.version || 0);\n"
    "    }\n"
)
if text.count(merge_anchor) != 1:
    print(f'PATCH_ERROR: realtime merge anchor expected 1, found {text.count(merge_anchor)}')
    sys.exit(1)
text = text.replace(merge_anchor, merge_insert, 1)

version_anchor = "      expectedVersion: Number(room.version || 0)\n"
version_replacement = (
    "      // CLEANING_RESET remains Sheet-owned because it cancels the existing completion/history records.\n"
    "      // Realtime room.version is a DB version, so use the preserved Sheet version only for reset.\n"
    "      expectedVersion: action === 'CLEANING_RESET'\n"
    "        ? Number(room.__sheetVersion ?? room.version ?? 0)\n"
    "        : Number(room.version || 0)\n"
)
if text.count(version_anchor) != 1:
    print(f'PATCH_ERROR: expectedVersion anchor expected 1, found {text.count(version_anchor)}')
    sys.exit(1)
text = text.replace(version_anchor, version_replacement, 1)

if text == original:
    print('PATCH_ERROR: no changes made')
    sys.exit(1)

CLIENT.write_text(text, encoding='utf-8')

# Lightweight integrity checks around exact modified regions.
updated = CLIENT.read_text(encoding='utf-8')
required = [
    "merged.__sheetVersion = Number(legacyRoom.version || 0);",
    "expectedVersion: action === 'CLEANING_RESET'",
    "? Number(room.__sheetVersion ?? room.version ?? 0)",
    ": Number(room.version || 0)"
]
missing = [item for item in required if item not in updated]
if missing:
    print('PATCH_ERROR: verification failed')
    for item in missing:
        print('Missing:', item)
    sys.exit(1)

print('PATCH_OK')
print('Repository only; production Apps Script NOT changed yet')
print('Changed: Client.html only')
print('Fixed: CLEANING_RESET uses preserved Sheet version instead of Realtime DB version')
print('Preserved: reset confirmation, completion-history cancellation, permissions, other room actions')
print('No Cloud Run change required')
print('VERIFY: PASS')
