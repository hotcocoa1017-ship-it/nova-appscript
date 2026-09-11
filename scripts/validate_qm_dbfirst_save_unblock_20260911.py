from pathlib import Path

index = Path('Index.html').read_text(encoding='utf-8')
hotfix = Path('QmDbFirstControlsHotfix.html').read_text(encoding='utf-8')

assert "include_('Client')" in index
assert "include_('QmDbFirstControlsHotfix')" in index
assert index.index("include_('Client')") < index.index("include_('QmDbFirstControlsHotfix')")
assert 'QM_DBFIRST_SAVE_UNBLOCK_V1' in hotfix
assert '#qmChecklistSubmit' in hotfix
assert '#qmInspectionSaveOnly' in hotfix
assert 'Supabase 점검 시작은 완료됐습니다. 기존 이력 동기화가 끝나면 저장할 수 있습니다.' in hotfix
assert "점검 시작 처리 중입니다." in Path('Client.html').read_text(encoding='utf-8')
assert 'Houseman' not in hotfix
assert 'google.script.run' not in hotfix
assert 'fetch(' not in hotfix
assert '.from(' not in hotfix
assert '.update(' not in hotfix
assert '.insert(' not in hotfix
assert '.delete(' not in hotfix
assert '#qmInspectionPhotoAdd' not in hotfix
print('QM DB-first save unblock validation: OK')
