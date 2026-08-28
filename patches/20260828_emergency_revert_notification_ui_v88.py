from pathlib import Path

index = Path('Index.html')
text = index.read_text(encoding='utf-8')
button = '''        <button id="appNotificationButton" class="app-notification-button hidden" type="button" aria-label="알림" title="알림">\n          <svg class="app-notification-bell" viewBox="0 0 24 24" aria-hidden="true">\n            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"></path>\n          </svg>\n          <span id="appNotificationBadge" class="app-notification-badge hidden">0</span>\n        </button>\n'''
if button not in text:
    raise SystemExit('v87 Index notification button not found')
text = text.replace(button, '', 1)
index.write_text(text, encoding='utf-8')

client = Path('Client.html')
text = client.read_text(encoding='utf-8')

style_start = '''<style>\n  .app-notification-button {'''
style_end = '''  .upload-reset-guide {'''
start = text.find(style_start)
end = text.find(style_end)
if start != 0 or end < 0:
    raise SystemExit('v87 notification CSS block not found')
text = '<style>\n' + text[end:]

state_start = '''  const novaAppNotifications_ = {'''
state_end = '''  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze(['''
start = text.find(state_start)
end = text.find(state_end)
if start < 0 or end < 0 or end <= start:
    raise SystemExit('v87 notification client block not found')
text = text[:start] + text[end:]

replacements = [
    (
        "      if (novaAppNotificationRoleEnabled_()) scheduleAppNotificationPolling_(true);\n      return true;\n",
        "      return true;\n"
    ),
    (
        "    $('userText').textContent = `${data.user.name} · ${data.user.job || data.user.role}`;\n    renderAppNotificationBadge_();\n    renderMenu(menuWithLostFoundShortcut_(data.menu || []));\n",
        "    $('userText').textContent = `${data.user.name} · ${data.user.job || data.user.role}`;\n    renderMenu(menuWithLostFoundShortcut_(data.menu || []));\n"
    ),
    (
        "    $('loginForm').addEventListener('submit', handleLogin);\n    $('logoutButton').addEventListener('click', handleLogout);\n    $('appNotificationButton').addEventListener('click', openAppNotificationModal_);\n",
        "    $('loginForm').addEventListener('submit', handleLogin);\n    $('logoutButton').addEventListener('click', handleLogout);\n"
    ),
    (
        "    stopIndicatorSync();\n    stopMobileSync();\n    stopAppNotificationPolling_();\n    novaAppNotifications_.items = [];\n    novaAppNotifications_.count = 0;\n    novaAppNotifications_.lastLoadedAt = 0;\n    renderAppNotificationBadge_();\n    void novaRealtimeDisconnect_();\n",
        "    stopIndicatorSync();\n    stopMobileSync();\n    void novaRealtimeDisconnect_();\n"
    ),
]
for old, new in replacements:
    if old not in text:
        raise SystemExit('v87 notification integration anchor not found')
    text = text.replace(old, new, 1)

for forbidden in [
    'appNotificationButton',
    'appNotificationBadge',
    'novaAppNotifications_',
    'novaAppNotificationRoleEnabled_',
    'loadAppNotifications_',
    'scheduleAppNotificationPolling_',
    'openAppNotificationModal_',
    'clearAllAppNotifications_'
]:
    if forbidden in text:
        raise SystemExit(f'notification UI residue remains in Client.html: {forbidden}')

index_text = index.read_text(encoding='utf-8')
if 'appNotificationButton' in index_text or 'appNotificationBadge' in index_text:
    raise SystemExit('notification UI residue remains in Index.html')

client.write_text(text, encoding='utf-8')
print('EMERGENCY_REVERT_NOTIFICATION_UI_V88_OK')
