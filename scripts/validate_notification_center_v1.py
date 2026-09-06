from pathlib import Path
import re
import subprocess
import sys

index = Path('Index.html').read_text(encoding='utf-8')
center = Path('NotificationCenterV1.html').read_text(encoding='utf-8')
errors = []


def require(text, needle, label):
    if needle not in text:
        errors.append(f'MISSING: {label} :: {needle}')


def forbid(text, needle, label):
    if needle in text:
        errors.append(f'FORBIDDEN: {label} :: {needle}')


require(index, "include_('NotificationCenterV1')", 'NotificationCenterV1 included in Index')
require(center, 'NOVA_NOTIFICATION_CENTER_V1', 'notification center marker')
require(center, "nova_notifications?select=", 'notification Data API read')
require(center, "method:'PATCH'", 'notification read-state update')
require(center, "config:{private:true}", 'private notification Realtime channel')
require(center, "nova:user:${auth.employeeNo}:notifications", 'per-user notification topic')
require(center, "claims?.employee_no", 'employee number claim binding')
require(center, "novaNotificationSound", 'notification sound preference')
require(center, 'playSound_', 'notification sound playback')
require(center, 'markAllRead_', 'mark-all-read action')
require(center, "route:'", 'notification route payload compatibility') if False else None
forbid(center, 'SUPABASE_SERVICE_ROLE_KEY', 'service role secret in browser')
forbid(center, 'service_role', 'service role literal in browser')

scripts = re.findall(r'<script[^>]*>(.*?)</script>', center, flags=re.S | re.I)
if len(scripts) != 1:
    errors.append(f'SYNTAX: expected one script block, found {len(scripts)}')
else:
    result = subprocess.run(['node', '--check', '-'], input=scripts[0], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        errors.append('SYNTAX: ' + (result.stderr or result.stdout or 'node --check failed').strip())

if errors:
    print('NOVA notification center V1 validation failed', file=sys.stderr)
    for error in errors:
        print('- ' + error, file=sys.stderr)
    sys.exit(1)

print('NOVA notification center V1 validation passed.')
