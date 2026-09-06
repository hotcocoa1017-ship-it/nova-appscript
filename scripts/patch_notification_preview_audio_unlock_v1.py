from pathlib import Path
import re
import subprocess
import sys

MARKER = 'NOVA_NOTIFICATION_PREVIEW_AUDIO_UNLOCK_V1'


def fail(message, code=190):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(code)


def replace_once(text, old, new, label, code):
    count = text.count(old)
    if count != 1:
        fail(f'{label} anchor count={count}', code)
    return text.replace(old, new, 1)

# Client settings preview must await the browser audio unlock result.
client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')
if MARKER not in client:
    old = """    $('novaPrefPreview')?.addEventListener('click', () => {
      const prefs = readNotificationPreferencesPanel_();
      if (!prefs.soundEnabled) prefs.soundEnabled = true;
      window.NOVA_NOTIFICATION_PREFS_V2?.preview?.(prefs);
    });
"""
    new = """    $('novaPrefPreview')?.addEventListener('click', async () => {
      const button = $('novaPrefPreview');
      const prefs = readNotificationPreferencesPanel_();
      if (!prefs.soundEnabled) prefs.soundEnabled = true;
      try {
        const preview = window.NOVA_NOTIFICATION_PREFS_V2?.preview;
        if (typeof preview !== 'function') throw new Error('알림음 엔진을 준비하고 있습니다. 잠시 후 다시 눌러주세요.');
        if (button) { button.disabled = true; button.textContent = '재생 중'; }
        await preview(prefs);
      } catch (error) {
        showToast(error?.message || '알림음을 재생하지 못했습니다.');
      } finally {
        if (button) { button.disabled = false; button.textContent = '미리 듣기'; }
      }
    }); // NOVA_NOTIFICATION_PREVIEW_AUDIO_UNLOCK_V1
"""
    client = replace_once(client, old, new, 'settings preview click', 191)
    client_path.write_text(client, encoding='utf-8')

# Notification engine must wait for AudioContext.resume() and verify running state.
center_path = Path('NotificationCenterV1.html')
center = center_path.read_text(encoding='utf-8')
if MARKER not in center:
    old_unlock = "function unlock(){if(U.audioReady)return;const C=window.AudioContext||window.webkitAudioContext;if(!C)return;try{U.audio=U.audio||new C();void U.audio.resume();U.audioReady=true}catch(_){}}"
    new_unlock = "function unlock(){const C=window.AudioContext||window.webkitAudioContext;if(!C)return Promise.resolve(false);try{U.audio=U.audio||new C();if(U.audio.state==='running'){U.audioReady=true;return Promise.resolve(true)}return Promise.resolve(U.audio.resume()).then(()=>{U.audioReady=U.audio?.state==='running';return U.audioReady}).catch(e=>{U.audioReady=false;console.warn('[NOVA Notification] audio unlock',e);return false})}catch(e){U.audioReady=false;console.warn('[NOVA Notification] audio init',e);return Promise.resolve(false)}}"
    center = replace_once(center, old_unlock, new_unlock, 'audio unlock', 192)

    old_toggle = "function toggleSound(){unlock();U.sound=!U.sound;const prefs=applySoundPrefs({soundEnabled:U.sound,soundType:U.soundType,volume:U.soundVolume});void call('saveNovaNotificationPreferences',tok(),prefs).catch(e=>console.warn('[NOVA Notification] preference save',e));if(U.sound)sound()}"
    new_toggle = "async function toggleSound(){await unlock();U.sound=!U.sound;const prefs=applySoundPrefs({soundEnabled:U.sound,soundType:U.soundType,volume:U.soundVolume});void call('saveNovaNotificationPreferences',tok(),prefs).catch(e=>console.warn('[NOVA Notification] preference save',e));if(U.sound)sound()}"
    center = replace_once(center, old_toggle, new_toggle, 'sound toggle unlock', 193)

    old_api = "window.NOVA_NOTIFICATION_PREFS_V2={get:()=>normalizeSoundPrefs({soundEnabled:U.sound,soundType:U.soundType,volume:U.soundVolume}),apply:p=>applySoundPrefs(p),preview:p=>{unlock();playSoundPrefs(p,true)}}; // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2"
    new_api = "window.NOVA_NOTIFICATION_PREFS_V2={get:()=>normalizeSoundPrefs({soundEnabled:U.sound,soundType:U.soundType,volume:U.soundVolume}),apply:p=>applySoundPrefs(p),preview:async p=>{const ready=await unlock();if(!ready)throw new Error('기기에서 오디오 재생을 시작할 수 없습니다. 미디어 음량과 브라우저 소리 권한을 확인해 주세요.');playSoundPrefs(p,true);return true}}; // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2 NOVA_NOTIFICATION_PREVIEW_AUDIO_UNLOCK_V1"
    center = replace_once(center, old_api, new_api, 'preview audio API', 194)
    center_path.write_text(center, encoding='utf-8')

# Validate browser JavaScript syntax.
for source in ['Client.html', 'NotificationCenterV1.html']:
    text = Path(source).read_text(encoding='utf-8')
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
    if not scripts:
        fail(f'no script block in {source}', 195)
    result = subprocess.run(['node', '--check', '-'], input='\n'.join(scripts), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        fail(f'{source} syntax: {(result.stderr or result.stdout).strip()}', 196)

print('Applied NOVA notification preview audio unlock V1 patch.')
