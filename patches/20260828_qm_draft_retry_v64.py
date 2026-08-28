from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'


def fail(message):
    raise SystemExit(f'PATCH_ERROR: {message}')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


client = CLIENT.read_text(encoding='utf-8')
old = """    active.initPromise = promise.finally(() => {\n      if (active.initPromise === promise) active.initPromise = null;\n    });\n    return active.initPromise;\n"""
new = """    const trackedPromise = promise.finally(() => {\n      if (active.initPromise === trackedPromise) active.initPromise = null;\n    });\n    active.initPromise = trackedPromise;\n    return trackedPromise;\n"""
client = replace_once(client, old, new, 'QM background draft retry promise release')
CLIENT.write_text(client, encoding='utf-8')

script_start = client.find('<script>')
script_end = client.rfind('</script>')
if script_start < 0 or script_end <= script_start:
    fail('Client script block not found')
tmp = ROOT / '.tmp_qm_v64_client.js'
tmp.write_text(client[script_start + len('<script>'):script_end], encoding='utf-8')
try:
    subprocess.run(['node', '--check', str(tmp)], cwd=ROOT, check=True)
finally:
    if tmp.exists():
        tmp.unlink()

if 'const trackedPromise = promise.finally(() =>' not in client:
    fail('tracked promise guard missing')
if 'active.initPromise === promise' in client:
    fail('stale promise identity guard remains')
for needle in ["action: 'QM_START'", 'realtimeCommitted: true', "const realtimeAction = passed ? 'QM_COMPLETE' : 'QM_REWORK';"]:
    if needle not in client:
        fail(f'v63 realtime behavior regression: {needle}')

subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
print('QM_DRAFT_RETRY_V64_OK')
print('Changed: Client.html only')
print('Background draft init can retry after transient failure')
print('QM_START / QM_COMPLETE / QM_REWORK realtime flow preserved')
print('Syntax/scope: PASS')
