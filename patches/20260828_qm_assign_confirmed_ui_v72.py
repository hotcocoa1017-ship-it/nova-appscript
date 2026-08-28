from pathlib import Path
p=Path(__file__).resolve().parents[1]/'Client.html'
s=p.read_text(encoding='utf-8')
old="    const fastAction = Boolean(optimisticPatch);"
new="    const fastAction = Boolean(optimisticPatch) && action !== 'QM_ASSIGN'; // QM배정은 DB+Sheet 확정 후에만 화면반영"
if s.count(old)!=1: raise SystemExit(f'PATCH_ERROR expected 1 fastAction marker, found {s.count(old)}')
s=s.replace(old,new,1)
if new not in s: raise SystemExit('PATCH_ERROR QM confirmed UI marker missing')
p.write_text(s,encoding='utf-8')
print('QM_ASSIGN_CONFIRMED_UI_V72_OK')
print('Changed: Client.html only')
