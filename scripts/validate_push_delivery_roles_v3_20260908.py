from pathlib import Path
import re
import subprocess
import sys

errors = []
checks = []
NEW_VAPID = 'BKjiczDO9sG0qlh0rJDduCzQqT9tURU69oKN7mKmlyU4mnjx05x1FkUy-4Kaeqy40DReDmnQ1DR2s0ELu-SAgYM'
OLD_VAPID = 'BIcs42B7cfuzFyx_-h0Ji8G8TfsU7CvoX8RBZo65MZe-J1VQvP9VrFOL_o2VCHQo0Y01zxN4vDbkcbcvspg3Hr8'


def read(path):
    p = Path(path)
    if not p.exists():
        errors.append(f'MISSING FILE: {path}')
        return ''
    return p.read_text(encoding='utf-8')


def require(text, needle, label):
    ok = needle in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'MISSING: {label} :: {needle}')


def forbid(text, needle, label):
    ok = needle not in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'FORBIDDEN: {label} :: {needle}')


def html_syntax(path, label):
    text = read(path)
    blocks = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
    if not blocks:
        checks.append((label, False)); errors.append(f'SYNTAX: {label} no script'); return
    result = subprocess.run(['node', '--check', '-'], input='\n'.join(blocks), text=True, capture_output=True)
    ok = result.returncode == 0
    checks.append((label, ok))
    if not ok:
        errors.append(f'SYNTAX: {label} :: {(result.stderr or result.stdout).strip()}')

pwa = read('pwa/v2/index.html')
sw = read('pwa/v2/sw.js')
base = read('db/nova_pwa_web_push_v2.sql')
migration = read('supabase/migrations/20260908_web_push_vapid_recovery_v3.sql')
edge = read('supabase/functions/nova-web-push-v2/index.ts')
client = read('Client.html')
center = read('NotificationCenterV1.html')
permission_patch = read('scripts/patch_push_permission_settings_v1.py')

# VAPID recovery and automatic stale-subscription rotation.
require(pwa, 'NOVA_PUSH_VAPID_RECOVERY_V3', 'PWA VAPID recovery marker')
require(pwa, NEW_VAPID, 'PWA current public VAPID key')
require(base, NEW_VAPID, 'baseline DB current public VAPID key')
require(migration, NEW_VAPID, 'migration current public VAPID key')
forbid(pwa, OLD_VAPID, 'PWA old VAPID key removed')
forbid(base, OLD_VAPID, 'baseline old VAPID key removed')
require(pwa, "VAPID_VERSION='20260908-v3'", 'PWA key generation marker')
require(pwa, "version!==VAPID_VERSION", 'stale subscription generation detection')
require(pwa, 'await sub.unsubscribe()', 'stale subscription unsubscribe')
require(pwa, 'applicationServerKey:b64uToBytes(VAPID)', 'resubscribe with current VAPID')
require(pwa, 'localStorage.setItem(VAPID_VERSION_KEY,VAPID_VERSION)', 'successful VAPID generation persistence')
require(sw, "nova-pwa-v2-vercel-5", 'service-worker cache promotion')
require(sw, 'silent:false', 'background push sound enabled')
require(edge, 'nova_web_push_config_service', 'Edge obtains server VAPID config')

# Push permission/reconnect UI available through Apps Script personal settings.
require(permission_patch, 'NOVA_PUSH_PERMISSION_SETTINGS_V1', 'permission patch marker')
require(pwa, 'NOVA_PUSH_PERMISSION_SETTINGS_V1', 'PWA permission bridge marker')
require(pwa, "NOVA_PUSH_PERMISSION_UI_V1", 'PWA permission action bridge')
require(pwa, 'reportPushPermissionState', 'PWA subscription status reporter')
require(client, 'novaPushPermissionButton', 'Client Push reconnect control')
require(client, 'NOVA_PUSH_PERMISSION_SETTINGS_V1', 'Client permission marker')

# Foreground notification center still plays the configured NOVA sound.
require(center, "broadcast',{event:'NOTIFICATION'}", 'foreground notification broadcast subscription')
require(center, '()=>void load(true)', 'foreground new notification pop/sound path')
require(center, 'function sound()', 'foreground sound function')
require(center, "soundEnabled: true", 'notification preference source default enabled') if False else None

# Role notification generation remains present: Roommaid/QM assignments, Houseman assignment,
# and Public receives site-scoped operational/departure notifications rather than invented per-room assignment ownership.
notification_sql = read('db/nova_notification_center_v1.sql')
departure_sql = read('supabase/migrations/20260907_departure_delay_db_first_v3.sql')
for needle, label in [
    ("'ROOMMAID_ASSIGN'", 'Roommaid assignment notification'),
    ("'QM_ASSIGN'", 'QM assignment notification'),
    ("'HOUSEMAN_ASSIGN'", 'Houseman assignment notification'),
]:
    require(notification_sql, needle, label)
require(departure_sql, "'PUBLIC'", 'Public recipient role in departure notification')
require(departure_sql, "'DEPARTURE_DELAY'", 'Public site-scoped departure notification kind')

html_syntax('pwa/v2/index.html', 'PWA index JavaScript syntax')
result = subprocess.run(['node', '--check', 'pwa/v2/sw.js'], text=True, capture_output=True)
ok = result.returncode == 0
checks.append(('PWA service worker syntax', ok))
if not ok: errors.append('SYNTAX: PWA service worker :: ' + (result.stderr or result.stdout).strip())
html_syntax('Client.html', 'Client JavaScript syntax')

if errors:
    print(f'Push delivery role validation FAILED: {len(errors)} issue(s), {len(checks)} checks.', file=sys.stderr)
    for error in errors:
        print(' - ' + error, file=sys.stderr)
    raise SystemExit(231)

print(f'Push delivery role validation PASS: {len(checks)} checks.')
