from pathlib import Path
import re
import subprocess
import sys

MARKER = 'NOVA_NOTIFICATION_PREVIEW_CLIENT_FALLBACK_V2'


def fail(message, code=197):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(code)


def replace_once(text, old, new, label, code):
    count = text.count(old)
    if count != 1:
        fail(f'{label} anchor count={count}', code)
    return text.replace(old, new, 1)

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
if MARKER in text:
    print('NOVA notification preview client fallback V2 already applied.')
    sys.exit(0)

anchor = "  function renderNotificationPreferencesPanel_() { // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2\n"
helper = r'''  let novaNotificationPreviewAudio_ = null; // NOVA_NOTIFICATION_PREVIEW_CLIENT_FALLBACK_V2

  async function previewNotificationSoundLocal_(prefs = {}) {
    const AudioCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtor) throw new Error('이 기기는 NOVA 알림음 미리듣기를 지원하지 않습니다.');
    try {
      novaNotificationPreviewAudio_ = novaNotificationPreviewAudio_ || new AudioCtor();
      if (novaNotificationPreviewAudio_.state !== 'running') await novaNotificationPreviewAudio_.resume();
      if (novaNotificationPreviewAudio_.state !== 'running') {
        throw new Error('오디오 재생이 차단되어 있습니다. 기기 미디어 음량과 브라우저 소리 권한을 확인해 주세요.');
      }
      const type = String(prefs.soundType || 'CHIME').toUpperCase();
      const volume = Math.max(0, Math.min(100, Number(prefs.volume ?? 70)));
      if (volume <= 0) throw new Error('알림 음량이 0%입니다. 음량을 올린 뒤 다시 눌러주세요.');
      const patterns = {
        CHIME: [[659, 0, .18, 'sine'], [880, .13, .22, 'sine'], [1047, .29, .28, 'sine']],
        BELL: [[880, 0, .34, 'sine'], [1320, .02, .42, 'sine']],
        DOUBLE: [[740, 0, .18, 'triangle'], [980, .16, .22, 'triangle']],
        ALERT: [[880, 0, .16, 'square'], [880, .20, .16, 'square'], [1175, .40, .24, 'square']]
      };
      const now = novaNotificationPreviewAudio_.currentTime;
      const peak = Math.max(.008, Math.min(.36, (volume / 100) * .36));
      (patterns[type] || patterns.CHIME).forEach(([frequency, delay, length, wave]) => {
        const oscillator = novaNotificationPreviewAudio_.createOscillator();
        const gain = novaNotificationPreviewAudio_.createGain();
        oscillator.type = wave;
        oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(.0001, now + delay);
        gain.gain.exponentialRampToValueAtTime(peak, now + delay + .025);
        gain.gain.exponentialRampToValueAtTime(.0001, now + delay + length);
        oscillator.connect(gain);
        gain.connect(novaNotificationPreviewAudio_.destination);
        oscillator.start(now + delay);
        oscillator.stop(now + delay + length + .03);
      });
      return true;
    } catch (error) {
      if (error?.message) throw error;
      throw new Error('알림음을 재생하지 못했습니다.');
    }
  }

'''
text = replace_once(text, anchor, helper + anchor, 'preview fallback helper', 198)

old = """        const preview = window.NOVA_NOTIFICATION_PREFS_V2?.preview;
        if (typeof preview !== 'function') throw new Error('알림음 엔진을 준비하고 있습니다. 잠시 후 다시 눌러주세요.');
        if (button) { button.disabled = true; button.textContent = '재생 중'; }
        await preview(prefs);
"""
new = """        const preview = window.NOVA_NOTIFICATION_PREFS_V2?.preview;
        if (button) { button.disabled = true; button.textContent = '재생 중'; }
        if (typeof preview === 'function') await preview(prefs);
        else await previewNotificationSoundLocal_(prefs); // NOVA_NOTIFICATION_PREVIEW_CLIENT_FALLBACK_V2
"""
text = replace_once(text, old, new, 'preview fallback call', 199)
path.write_text(text, encoding='utf-8')

scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
if not scripts:
    fail('no Client script block', 200)
result = subprocess.run(['node', '--check', '-'], input='\n'.join(scripts), text=True, capture_output=True, check=False)
if result.returncode != 0:
    fail(f'Client syntax: {(result.stderr or result.stdout).strip()}', 201)

print('Applied NOVA notification preview client fallback V2 patch.')