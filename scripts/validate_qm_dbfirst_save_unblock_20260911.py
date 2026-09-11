from pathlib import Path

index = Path('Index.html').read_text(encoding='utf-8')
hotfix = Path('QmDbFirstControlsHotfix.html').read_text(encoding='utf-8')
client = Path('Client.html').read_text(encoding='utf-8')

client_marker = "include_('Client')"
hotfix_marker = "include_('QmDbFirstControlsHotfix')"
assert client_marker in index
assert hotfix_marker in index
assert index.index(client_marker) < index.index(hotfix_marker)
assert 'QM_DBFIRST_SAVE_UNBLOCK_V1' in hotfix
assert '#qmChecklistSubmit' in hotfix
assert '#qmInspectionSaveOnly' in hotfix
assert 'Supabase 점검 시작은 완료됐습니다. 기존 이력 동기화가 끝나면 저장할 수 있습니다.' in hotfix
assert 'active.dbFirst && !active.sheetMirrorReady' in client
assert 'Houseman' not in hotfix
for forbidden in ('google.script.run', 'fetch(', '.from(', '.update(', '.insert(', '.delete(', '#qmInspectionPhotoAdd'):
    assert forbidden not in hotfix, forbidden
print('QM DB-first save unblock validation: OK')
