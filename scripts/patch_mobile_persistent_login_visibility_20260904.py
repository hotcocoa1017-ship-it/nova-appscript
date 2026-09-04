from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
old = """  function handleVisibilityChange_() { // (백그라운드 탭 서버요청 중지·복귀 분산)
    if (document.hidden) {
      stopIndicatorSync();
      stopMobileSync();
      return;
    }
    if (isMobileLoginClient_() && persistentSessionToken_()) {
      const expiresAt = novaTokenExpiresAt_(state.token);
      if (!expiresAt || expiresAt - Date.now() < 60 * 60 * 1000) void refreshPersistentLogin_(false);
    }
"""
new = """  async function handleVisibilityChange_() { // (백그라운드 탭 서버요청 중지·복귀 분산)
    if (document.hidden) {
      stopIndicatorSync();
      stopMobileSync();
      return;
    }
    if (isMobileLoginClient_() && persistentSessionToken_()) {
      const expiresAt = novaTokenExpiresAt_(state.token);
      if (!expiresAt || expiresAt - Date.now() < 60 * 60 * 1000) await refreshPersistentLogin_(false);
    }
"""
assert old in text, 'Persistent visibility refresh anchor not found'
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('Persistent visibility refresh guard applied.')
