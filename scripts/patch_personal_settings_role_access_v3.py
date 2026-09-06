from pathlib import Path
import sys

MARKER = 'NOVA_PERSONAL_SETTINGS_ROLE_ACCESS_V3'
path = Path('Client.html')
text = path.read_text(encoding='utf-8')

# V2 patch should already have converted the settings shell to personal settings for every role.
# Keep this patch narrowly focused: remove any stale ADMIN/ORDER-only guard and make non-admin/non-order
# roles open the notification preferences tab immediately.
old_guard = """    if (!['ADMIN', 'ORDER'].includes(role)) {
      $('content').innerHTML = '<div class=\"settings-loading error\">설정을 사용할 권한이 없습니다.</div>';
      return;
    }
"""
if old_guard in text:
    text = text.replace(old_guard, '', 1)

old_branch = """      if (role === 'ADMIN') loadAdminSettings_();
      else if (role === 'ORDER') openSettingsTab_('users');
      return;
"""
new_branch = """      if (role === 'ADMIN') loadAdminSettings_();
      else if (role === 'ORDER') openSettingsTab_('users');
      else openSettingsTab_('notifications'); // NOVA_PERSONAL_SETTINGS_ROLE_ACCESS_V3
      return;
"""
if old_branch in text:
    text = text.replace(old_branch, new_branch, 1)
elif MARKER not in text:
    print('ERROR: settings render branch anchor not found', file=sys.stderr)
    sys.exit(171)

# Postconditions: no stale role denial, and all field roles route to personal notification settings.
if "설정을 사용할 권한이 없습니다." in text:
    print('ERROR: stale settings permission denial remains', file=sys.stderr)
    sys.exit(172)
if "else openSettingsTab_('notifications'); // NOVA_PERSONAL_SETTINGS_ROLE_ACCESS_V3" not in text:
    print('ERROR: non-admin personal settings route missing', file=sys.stderr)
    sys.exit(173)
if "role === 'ADMIN' ? ['notifications', 'operations', 'codes', 'users', 'telegram', 'archive']" not in text:
    print('ERROR: V2 settings tab permissions are not present', file=sys.stderr)
    sys.exit(174)

path.write_text(text, encoding='utf-8')
print('Applied NOVA personal settings role access V3 patch.')
