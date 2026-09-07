from pathlib import Path

PATH = Path('scripts/patch_room_upload_db_first_app_v4_20260907.py')
text = PATH.read_text(encoding='utf-8')

replacements = {
    '      kind: MARKER,': "      kind: 'ROOM_UPLOAD_DB_FIRST_APP_V4',",
    '    if (!plan || plan.kind !== MARKER) {': "    if (!plan || plan.kind !== 'ROOM_UPLOAD_DB_FIRST_APP_V4') {",
    '          source: MARKER,': "          source: 'ROOM_UPLOAD_DB_FIRST_APP_V4',",
}

changed = False
for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new)
        changed = True
    elif new not in text:
        raise SystemExit(f'ERROR: generator marker anchor missing: {old}')

if changed:
    PATH.write_text(text, encoding='utf-8')

# Generated JavaScript must never depend on the Python-only MARKER symbol.
post = PATH.read_text(encoding='utf-8')
for forbidden in ['kind: MARKER', 'plan.kind !== MARKER', 'source: MARKER']:
    if forbidden in post:
        raise SystemExit(f'ERROR: unresolved Python marker leaked into generated JavaScript: {forbidden}')

print('PASS: room upload V4 generator uses JavaScript string literals for all runtime markers')
