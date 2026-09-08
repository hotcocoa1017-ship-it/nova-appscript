from pathlib import Path
import re
import subprocess
import tempfile

text = Path('Client.html').read_text(encoding='utf-8')

required = [
    'QM_MODAL_CLOSE_DRAFT_DB_FIRST_V1',
    'async function novaQmSaveDraftOnCloseDbFirst_(draft)',
    'const dbResult = await novaQmDraftDbFirstSave_(draft);',
    'novaQmScheduleLegacyDraftMirror_',
    "return callServer('saveQmInspectionDraft', state.token, {",
    'novaQmSaveDraftOnCloseDbFirst_(draft).then(result => {'
]
for needle in required:
    if needle not in text:
        raise SystemExit(f'ERROR: missing {needle}')

start = text.index('  function closeModal() { // (모달 닫기·QM 진행중 초안 보존)')
next_function = text.find('\n  function ', start + 10)
if next_function < 0:
    next_function = min(len(text), start + 5000)
block = text[start:next_function]
if "callServer('saveQmInspectionDraft', state.token" in block:
    raise SystemExit('ERROR: closeModal still writes draft directly to Sheet')
if 'novaQmSaveDraftOnCloseDbFirst_(draft)' not in block:
    raise SystemExit('ERROR: closeModal does not use DB-first close helper')

helper_start = text.index('  async function novaQmSaveDraftOnCloseDbFirst_(draft)')
helper_end = text.index('  function closeModal()', helper_start)
helper = text[helper_start:helper_end]
if helper.find('novaQmDraftDbFirstSave_(draft)') > helper.find("callServer('saveQmInspectionDraft'"):
    raise SystemExit('ERROR: Sheet fallback appears before DB-first save')

scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8', delete=False) as handle:
    handle.write('\n'.join(scripts))
    temp_js = handle.name
subprocess.run(['node', '--check', temp_js], check=True)
print('PASS: QM modal-close draft save is DB-first with legacy Sheet fallback/mirror preserved.')
