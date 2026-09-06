from pathlib import Path
import re
import subprocess
import sys

errors=[]

def req(text, needle, label):
    if needle not in text: errors.append(f'MISSING {label}: {needle}')

def forbid(text, needle, label):
    if needle in text: errors.append(f'FORBIDDEN {label}: {needle}')

api=Path('04_Api.js').read_text(encoding='utf-8')
server=Path('NotificationPreferences.js').read_text(encoding='utf-8')
client=Path('Client.html').read_text(encoding='utf-8')
center=Path('NotificationCenterV1.html').read_text(encoding='utf-8')
archive=Path('ArchiveAdminClient.html').read_text(encoding='utf-8')
rt=Path('ArchiveAdminRealtimeClient.html').read_text(encoding='utf-8')

req(api, "{ id: 'settings', label: '설정' }", 'settings menu')
forbid(api, "{ id: 'archive', label: 'Archive 이력' }", 'Archive sidebar menu')
req(server, 'function getNovaNotificationPreferences', 'preference read API')
req(server, 'function saveNovaNotificationPreferences', 'preference save API')
req(server, "['CHIME', 'BELL', 'DOUBLE', 'ALERT']", 'sound type allowlist')
req(client, 'NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2', 'settings marker')
req(client, 'data-settings-tab="notifications"', 'notification settings tab')
req(client, 'data-settings-tab="archive"', 'Archive settings tab')
req(client, "['notifications', 'operations', 'codes', 'users', 'telegram', 'archive']", 'ADMIN settings tabs')
req(client, "role === 'ORDER' ? ['notifications', 'users'] : ['notifications']", 'non-admin personal settings')
req(client, "else openSettingsTab_('notifications'); // NOVA_PERSONAL_SETTINGS_ROLE_ACCESS_V3", 'field-role personal settings route')
forbid(client, '설정을 사용할 권한이 없습니다.', 'stale field-role settings denial')
req(center, 'soundVolume', 'runtime notification volume')
req(center, 'soundType', 'runtime sound type')
req(center, 'loadSoundPrefs()', 'per-user preference sync')
req(center, 'NOVA_NOTIFICATION_PREFS_V2', 'settings runtime bridge')
req(center, "if(r==='archive')", 'Archive notification route')
req(archive, 'NOVA_ARCHIVE_ADMIN_V2', 'Archive settings renderer')
req(rt, 'return archiveRtPageVisible_();', 'Archive realtime visible-panel guard')

for source in ['NotificationPreferences.js','04_Api.js']:
    p=subprocess.run(['node','--check',source],capture_output=True,text=True)
    if p.returncode: errors.append(f'SYNTAX {source}: {(p.stderr or p.stdout).strip()}')
for name,text in [('Client.html',client),('NotificationCenterV1.html',center),('ArchiveAdminClient.html',archive),('ArchiveAdminRealtimeClient.html',rt)]:
    scripts=re.findall(r'<script[^>]*>(.*?)</script>',text,flags=re.S|re.I)
    if not scripts:
        errors.append(f'NO SCRIPT {name}')
        continue
    p=subprocess.run(['node','--check','-'],input='\n'.join(scripts),capture_output=True,text=True)
    if p.returncode: errors.append(f'SYNTAX {name}: {(p.stderr or p.stdout).strip()}')

if errors:
    print('NOVA notification preferences + Archive settings V2 validation failed',file=sys.stderr)
    for e in errors: print('- '+e,file=sys.stderr)
    sys.exit(1)
print('NOVA notification preferences + Archive settings V2 validation passed.')
