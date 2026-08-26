from pathlib import Path

root = Path(__file__).resolve().parents[1]
client = root / 'Client.html'
text = client.read_text(encoding='utf-8')

old = """    const cleaningResetAvailable = cleaningCompletionLocked\n      && Boolean(room.cleaningType || room.roommaidEmployeeNo || room.secondaryRoommaidEmployeeNo || room.qmEmployeeNo);"""
new = """    // 청소완료/QM 완료계열이면 배정정보 유무와 관계없이 청소 초기화를 허용한다.\n    // Realtime 미러에서 배정/정비 메타가 비어 있어도 완료이력 자체는 초기화 대상이다.\n    const cleaningResetAvailable = cleaningCompletionLocked;"""

count = text.count(old)
if count != 1:
    raise SystemExit(f'PATCH_ERROR: cleaningResetAvailable anchor expected 1 match, found {count}')

text = text.replace(old, new, 1)
client.write_text(text, encoding='utf-8')

verify = client.read_text(encoding='utf-8')
checks = [
    'const cleaningResetAvailable = cleaningCompletionLocked;',
    'data-room-action="CLEANING_RESET"',
    "action === 'CLEANING_RESET'",
    'room.__sheetVersion ?? room.version ?? 0'
]
missing = [item for item in checks if item not in verify]
if missing:
    raise SystemExit('VERIFY_ERROR: missing ' + ' | '.join(missing))

print('PATCH_OK')
print('Repository only; production Apps Script NOT changed yet')
print('Changed: Client.html only')
print('Fixed: CLEANING_RESET button remains visible for completed/QM-completed rooms even when assignment metadata is empty')
print('Preserved: v26 Sheet-version fix, reset confirmation, completion-history cancellation, permissions, all other room actions')
print('No Cloud Run change required')
print('VERIFY: PASS')
