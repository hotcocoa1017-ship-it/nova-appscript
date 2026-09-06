from pathlib import Path
import re
import subprocess
import sys

MARKER = 'NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2'


def fail(message, code=160):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(code)


def replace_once(text, old, new, label, code):
    count = text.count(old)
    if count != 1:
        fail(f'{label} anchor count={count}', code)
    return text.replace(old, new, 1)


# 1) Main settings UI: personal notification settings for every role + Archive under ADMIN settings.
client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')
if MARKER not in client:
    css_anchor = '</style>\n<script>'
    css = '''
  /* NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2 */
  .notification-pref-card{display:grid;gap:16px;max-width:760px;padding:18px;border:1px solid #e5e7eb;border-radius:14px;background:#fff}
  .notification-pref-card h2{margin:0;font-size:18px}.notification-pref-card p{margin:0;color:#6b7280;font-size:12px;line-height:1.55}
  .notification-pref-row{display:grid;grid-template-columns:180px minmax(0,1fr);gap:14px;align-items:center}
  .notification-pref-row>span{font-size:13px;font-weight:800;color:#374151}.notification-pref-row select{width:100%;height:40px;border:1px solid #d1d5db;border-radius:9px;background:#fff;padding:0 10px}
  .notification-pref-toggle{display:flex;align-items:center;gap:9px;font-weight:800}.notification-pref-toggle input{width:18px;height:18px}
  .notification-pref-volume{display:grid;grid-template-columns:minmax(0,1fr) 52px;gap:10px;align-items:center}.notification-pref-volume input{width:100%}.notification-pref-volume output{text-align:right;font-weight:900}
  .notification-pref-actions{display:flex;justify-content:flex-end;gap:8px}.notification-pref-actions button{min-height:40px;padding:0 14px;border:1px solid #d1d5db;border-radius:9px;background:#fff;font-weight:800}.notification-pref-actions .primary{background:#111827;color:#fff;border-color:#111827}
  .settings-archive-host{min-width:0}.settings-archive-host .nova-archive-head h1{font-size:20px}
  @media(max-width:760px){.notification-pref-row{grid-template-columns:1fr;gap:7px}.notification-pref-actions{display:grid;grid-template-columns:1fr 1fr}.notification-pref-actions button{width:100%;min-height:44px}}
'''
    client = replace_once(client, css_anchor, css + css_anchor, 'settings preference CSS', 161)

    helper_anchor = '  function renderSystemSettingsShell_() { // (관리자 전체설정·오더테이커 사용자계정 설정 화면)\n'
    helpers = r'''  function renderNotificationPreferencesPanel_() { // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2
    const panel = $('settingsPanel');
    if (!panel) return;
    panel.innerHTML = `
      <div class="notification-pref-card">
        <div><h2>개인 알림 설정</h2><p>이 설정은 사번 기준으로 저장됩니다. 효과음과 음량은 NOVA가 실행 중일 때의 자체 알림음에 적용되며, 앱을 닫은 상태의 Web Push 소리는 휴대폰·PC 운영체제의 알림 설정을 따릅니다.</p></div>
        <div class="notification-pref-row"><span>알림음</span><label class="notification-pref-toggle"><input id="novaPrefSoundEnabled" type="checkbox"><span>앱 실행 중 알림음 사용</span></label></div>
        <div class="notification-pref-row"><span>효과음</span><select id="novaPrefSoundType"><option value="CHIME">차임 · 부드러운 3단음</option><option value="BELL">벨 · 또렷한 종소리</option><option value="DOUBLE">더블 · 짧은 2단음</option><option value="ALERT">알림 · 강한 3회음</option></select></div>
        <div class="notification-pref-row"><span>알림 음량</span><div class="notification-pref-volume"><input id="novaPrefVolume" type="range" min="0" max="100" step="5" value="70"><output id="novaPrefVolumeValue">70%</output></div></div>
        <div class="notification-pref-actions"><button id="novaPrefPreview" type="button">미리 듣기</button><button id="novaPrefSave" class="primary" type="button">저장</button></div>
      </div>`;
    const volume = $('novaPrefVolume');
    const output = $('novaPrefVolumeValue');
    volume?.addEventListener('input', () => { if (output) output.textContent = `${Number(volume.value || 0)}%`; });
    $('novaPrefPreview')?.addEventListener('click', () => {
      const prefs = readNotificationPreferencesPanel_();
      if (!prefs.soundEnabled) prefs.soundEnabled = true;
      window.NOVA_NOTIFICATION_PREFS_V2?.preview?.(prefs);
    });
    $('novaPrefSave')?.addEventListener('click', saveNotificationPreferencesSettings_);
  }

  function readNotificationPreferencesPanel_() {
    return {
      soundEnabled: Boolean($('novaPrefSoundEnabled')?.checked),
      soundType: String($('novaPrefSoundType')?.value || 'CHIME'),
      volume: Math.max(0, Math.min(100, Number($('novaPrefVolume')?.value || 70)))
    };
  }

  function applyNotificationPreferencesPanel_(prefs) {
    const enabled = $('novaPrefSoundEnabled'); if (enabled) enabled.checked = prefs?.soundEnabled !== false;
    const type = $('novaPrefSoundType'); if (type) type.value = ['CHIME','BELL','DOUBLE','ALERT'].includes(String(prefs?.soundType || '').toUpperCase()) ? String(prefs.soundType).toUpperCase() : 'CHIME';
    const volume = $('novaPrefVolume'); if (volume) volume.value = String(Math.max(0, Math.min(100, Number(prefs?.volume ?? 70))));
    const output = $('novaPrefVolumeValue'); if (output) output.textContent = `${Number(volume?.value || 70)}%`;
  }

  async function loadNotificationPreferencesSettings_() {
    try {
      const result = await callServer('getNovaNotificationPreferences', state.token);
      if (!result?.ok) throw new Error(result?.message || '알림 설정을 불러오지 못했습니다.');
      if (state.activeMenu === 'settings' && state.settings.tab === 'notifications') applyNotificationPreferencesPanel_(result);
      window.NOVA_NOTIFICATION_PREFS_V2?.apply?.(result);
    } catch (error) {
      showToast(error?.message || '알림 설정 조회 오류');
    }
  }

  async function saveNotificationPreferencesSettings_() {
    const button = $('novaPrefSave');
    if (button) { button.disabled = true; button.textContent = '저장 중'; }
    try {
      const result = await callServer('saveNovaNotificationPreferences', state.token, readNotificationPreferencesPanel_());
      if (!result?.ok) throw new Error(result?.message || '알림 설정을 저장하지 못했습니다.');
      applyNotificationPreferencesPanel_(result);
      window.NOVA_NOTIFICATION_PREFS_V2?.apply?.(result);
      showToast('개인 알림 설정을 저장했습니다.');
    } catch (error) {
      showToast(error?.message || '알림 설정 저장 오류');
    } finally {
      if (button) { button.disabled = false; button.textContent = '저장'; }
    }
  }

  function renderArchiveSettingsPanel_() {
    const panel = $('settingsPanel');
    if (!panel) return;
    panel.innerHTML = '<div class="settings-loading">Archive 관리 화면을 준비하고 있습니다.</div>';
    window.setTimeout(() => {
      if (state.activeMenu !== 'settings' || state.settings.tab !== 'archive') return;
      if (!window.NOVA_ARCHIVE_ADMIN_V2?.renderInto) {
        panel.innerHTML = '<div class="settings-loading error">Archive 화면을 불러올 수 없습니다.</div>';
        return;
      }
      panel.classList.add('settings-archive-host');
      window.NOVA_ARCHIVE_ADMIN_V2.renderInto(panel);
    }, 0);
  }

'''
    client = replace_once(client, helper_anchor, helpers + helper_anchor, 'settings helper insertion', 162)

    old_shell = '''    const role = String(state.bootstrap?.user?.role || '').trim().toUpperCase();
    const isAdmin = role === 'ADMIN';
    if (!['ADMIN', 'ORDER'].includes(role)) {
      $('content').innerHTML = '<div class=\"settings-loading error\">설정을 사용할 권한이 없습니다.</div>';
      return;
    }
    state.settings.tab = isAdmin ? 'operations' : 'users';
    const tabs = isAdmin
      ? `<button type=\"button\" data-settings-tab=\"operations\"${state.settings.tab === 'operations' ? ' class=\"active\"' : ''}>운영 기준·자동마감</button>
         <button type=\"button\" data-settings-tab=\"codes\"${state.settings.tab === 'codes' ? ' class=\"active\"' : ''}>명칭·목록 관리</button>
         <button type=\"button\" data-settings-tab=\"users\"${state.settings.tab === 'users' ? ' class=\"active\"' : ''}>사용자계정</button>
         <button type=\"button\" data-settings-tab=\"telegram\"${state.settings.tab === 'telegram' ? ' class=\"active\"' : ''}>텔레그램 연결</button>`
      : '<button type=\"button\" data-settings-tab=\"users\" class=\"active\">사용자계정</button>';
'''
    new_shell = '''    const role = String(state.bootstrap?.user?.role || '').trim().toUpperCase();
    const isAdmin = role === 'ADMIN';
    const isOrder = role === 'ORDER';
    state.settings.tab = isAdmin ? 'operations' : (isOrder ? 'users' : 'notifications');
    const notificationTab = `<button type=\"button\" data-settings-tab=\"notifications\"${state.settings.tab === 'notifications' ? ' class=\"active\"' : ''}>알림 설정</button>`;
    const tabs = isAdmin
      ? `${notificationTab}
         <button type=\"button\" data-settings-tab=\"operations\"${state.settings.tab === 'operations' ? ' class=\"active\"' : ''}>운영 기준·자동마감</button>
         <button type=\"button\" data-settings-tab=\"codes\"${state.settings.tab === 'codes' ? ' class=\"active\"' : ''}>명칭·목록 관리</button>
         <button type=\"button\" data-settings-tab=\"users\"${state.settings.tab === 'users' ? ' class=\"active\"' : ''}>사용자계정</button>
         <button type=\"button\" data-settings-tab=\"telegram\"${state.settings.tab === 'telegram' ? ' class=\"active\"' : ''}>텔레그램 연결</button>
         <button type=\"button\" data-settings-tab=\"archive\"${state.settings.tab === 'archive' ? ' class=\"active\"' : ''}>Archive 이력</button>`
      : (isOrder ? `${notificationTab}<button type=\"button\" data-settings-tab=\"users\"${state.settings.tab === 'users' ? ' class=\"active\"' : ''}>사용자계정</button>` : notificationTab);
'''
    client = replace_once(client, old_shell, new_shell, 'settings role/tabs', 163)

    client = replace_once(
        client,
        "          <div><small>${isAdmin ? '코드 수정 없이 운영기준 관리' : '현장 직원 계정 즉시 관리'}</small><h1>시스템 설정</h1></div>",
        "          <div><small>${isAdmin ? '시스템 운영과 개인 환경 설정' : (isOrder ? '사용자계정과 개인 환경 설정' : '내 NOVA 사용 환경 설정')}</small><h1>${isAdmin || isOrder ? '시스템 설정' : '개인 설정'}</h1></div>",
        'settings header copy',
        164,
    )

    client = replace_once(
        client,
        "    const allowedTabs = role === 'ADMIN' ? ['operations', 'codes', 'users', 'telegram'] : ['users'];",
        "    const allowedTabs = role === 'ADMIN' ? ['notifications', 'operations', 'codes', 'users', 'telegram', 'archive'] : (role === 'ORDER' ? ['notifications', 'users'] : ['notifications']);",
        'settings allowed tabs',
        165,
    )

    switch_anchor = "    document.querySelectorAll('[data-settings-tab]').forEach(button => button.classList.toggle('active', button.dataset.settingsTab === state.settings.tab));\n    if (state.settings.tab === 'users') {"
    switch_new = "    document.querySelectorAll('[data-settings-tab]').forEach(button => button.classList.toggle('active', button.dataset.settingsTab === state.settings.tab));\n    $('settingsPanel')?.classList.remove('settings-archive-host');\n    if (state.settings.tab === 'notifications') { renderNotificationPreferencesPanel_(); void loadNotificationPreferencesSettings_(); return; }\n    if (state.settings.tab === 'archive') { if (role === 'ADMIN') renderArchiveSettingsPanel_(); return; }\n    if (state.settings.tab === 'users') {"
    client = replace_once(client, switch_anchor, switch_new, 'settings tab switch', 166)
    client_path.write_text(client, encoding='utf-8')

# 2) Notification center: per-user type/volume + server sync + preview API.
center_path = Path('NotificationCenterV1.html')
center = center_path.read_text(encoding='utf-8')
if MARKER not in center:
    old_state = "sound:localStorage.getItem('novaNotificationSound')!=='0',busy:false"
    new_state = "sound:localStorage.getItem('novaNotificationSound')!=='0',soundType:String(localStorage.getItem('novaNotificationSoundType')||'CHIME').toUpperCase(),soundVolume:Math.max(0,Math.min(100,Number(localStorage.getItem('novaNotificationSoundVolume')||70))),busy:false"
    center = replace_once(center, old_state, new_state, 'notification sound state', 167)

    sound_anchor = "function unlock(){if(U.audioReady)return;const C=window.AudioContext||window.webkitAudioContext;if(!C)return;try{U.audio=U.audio||new C();void U.audio.resume();U.audioReady=true}catch(_){}}\nfunction sound(){if(!U.sound||!U.audioReady||!U.audio)return;try{const now=U.audio.currentTime;[[740,0],[980,.12]].forEach(([f,d])=>{const o=U.audio.createOscillator(),g=U.audio.createGain();o.frequency.value=f;g.gain.setValueAtTime(.0001,now+d);g.gain.exponentialRampToValueAtTime(.075,now+d+.02);g.gain.exponentialRampToValueAtTime(.0001,now+d+.14);o.connect(g);g.connect(U.audio.destination);o.start(now+d);o.stop(now+d+.16)})}catch(_){}}\nfunction toggleSound(){unlock();U.sound=!U.sound;localStorage.setItem('novaNotificationSound',U.sound?'1':'0');render();if(U.sound)sound()}"
    sound_new = r'''function unlock(){if(U.audioReady)return;const C=window.AudioContext||window.webkitAudioContext;if(!C)return;try{U.audio=U.audio||new C();void U.audio.resume();U.audioReady=true}catch(_){}}
function normalizeSoundPrefs(p={}){const type=String(p.soundType||U.soundType||'CHIME').toUpperCase();return{soundEnabled:p.soundEnabled==null?U.sound:p.soundEnabled!==false,soundType:['CHIME','BELL','DOUBLE','ALERT'].includes(type)?type:'CHIME',volume:Math.max(0,Math.min(100,Number(p.volume??U.soundVolume??70)))}}
function applySoundPrefs(p={}){const n=normalizeSoundPrefs(p);U.sound=n.soundEnabled;U.soundType=n.soundType;U.soundVolume=n.volume;localStorage.setItem('novaNotificationSound',U.sound?'1':'0');localStorage.setItem('novaNotificationSoundType',U.soundType);localStorage.setItem('novaNotificationSoundVolume',String(U.soundVolume));render();return n}
async function loadSoundPrefs(){try{const r=await call('getNovaNotificationPreferences',tok());if(r?.ok)applySoundPrefs(r)}catch(e){console.warn('[NOVA Notification] preference load',e)}}
function tonePattern(type){if(type==='BELL')return[[880,0,.34,'sine'],[1320,.02,.42,'sine']];if(type==='DOUBLE')return[[740,0,.18,'triangle'],[980,.16,.22,'triangle']];if(type==='ALERT')return[[880,0,.16,'square'],[880,.20,.16,'square'],[1175,.40,.24,'square']];return[[659,0,.18,'sine'],[880,.13,.22,'sine'],[1047,.29,.28,'sine']]}
function playSoundPrefs(p,force=false){const n=normalizeSoundPrefs(p);if((!n.soundEnabled&&!force)||!U.audioReady||!U.audio||n.volume<=0)return;try{const now=U.audio.currentTime,peak=Math.max(.008,Math.min(.36,(n.volume/100)*.36));tonePattern(n.soundType).forEach(([f,d,len,type])=>{const o=U.audio.createOscillator(),g=U.audio.createGain();o.type=type;o.frequency.value=f;g.gain.setValueAtTime(.0001,now+d);g.gain.exponentialRampToValueAtTime(peak,now+d+.025);g.gain.exponentialRampToValueAtTime(.0001,now+d+len);o.connect(g);g.connect(U.audio.destination);o.start(now+d);o.stop(now+d+len+.03)})}catch(_){}}
function sound(){playSoundPrefs({soundEnabled:U.sound,soundType:U.soundType,volume:U.soundVolume})}
function toggleSound(){unlock();U.sound=!U.sound;const prefs=applySoundPrefs({soundEnabled:U.sound,soundType:U.soundType,volume:U.soundVolume});void call('saveNovaNotificationPreferences',tok(),prefs).catch(e=>console.warn('[NOVA Notification] preference save',e));if(U.sound)sound()}
window.NOVA_NOTIFICATION_PREFS_V2={get:()=>normalizeSoundPrefs({soundEnabled:U.sound,soundType:U.soundType,volume:U.soundVolume}),apply:p=>applySoundPrefs(p),preview:p=>{unlock();playSoundPrefs(p,true)}}; // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2'''
    center = replace_once(center, sound_anchor, sound_new, 'notification sound engine', 168)
    center = replace_once(center, 'U.employee=a.employee;', 'U.employee=a.employee;await loadSoundPrefs();', 'notification preference login load', 169)

    old_route = "function route(x){const p=x?.payload&&typeof x.payload==='object'?x.payload:{},r=String(p.route||''),map={cleaning:['오늘의 정비','룸메이드'],qm:['QM 점검'],houseman:['하우스맨 오더','하우스맨'],archive:['Archive 이력']},labels=map[r]||[],buttons=[...document.querySelectorAll('#menu button')],btn=buttons.find(b=>labels.some(l=>String(b.textContent||'').includes(l)));if(btn&&!btn.classList.contains('active'))btn.click();const room=String(p.roomNo||x.room_no||''),entity=String(p.orderId||x.entity_id||'');setTimeout(()=>focus(room,entity),700);setTimeout(()=>focus(room,entity),1400)}"
    new_route = "function route(x){const p=x?.payload&&typeof x.payload==='object'?x.payload:{},r=String(p.route||''),buttons=[...document.querySelectorAll('#menu button')];if(r==='archive'){const settings=buttons.find(b=>String(b.textContent||'').trim()==='설정');if(settings&&!settings.classList.contains('active'))settings.click();setTimeout(()=>document.querySelector('[data-settings-tab=\\\"archive\\\"]')?.click(),120);return}const map={cleaning:['오늘의 정비','룸메이드'],qm:['QM 점검'],houseman:['하우스맨 오더','하우스맨']},labels=map[r]||[],btn=buttons.find(b=>labels.some(l=>String(b.textContent||'').includes(l)));if(btn&&!btn.classList.contains('active'))btn.click();const room=String(p.roomNo||x.room_no||''),entity=String(p.orderId||x.entity_id||'');setTimeout(()=>focus(room,entity),700);setTimeout(()=>focus(room,entity),1400)}"
    center = replace_once(center, old_route, new_route, 'Archive notification route', 170)
    center_path.write_text(center, encoding='utf-8')

# 3) Archive renderer can target the settings panel rather than requiring a sidebar menu button.
archive_path = Path('ArchiveAdminClient.html')
archive = archive_path.read_text(encoding='utf-8')
if MARKER not in archive:
    old_header = """  function renderArchiveAdmin_() {
    const content = archiveContent_();
    const activeButton = Array.from(document.querySelectorAll('#menu button.active')).find(archiveIsMenuButton_);
    if (!content || !activeButton) return;
    content.innerHTML = `
"""
    new_header = """  function renderArchiveAdmin_() {
    const content = archiveContent_();
    const activeButton = Array.from(document.querySelectorAll('#menu button.active')).find(archiveIsMenuButton_);
    if (!content || !activeButton) return;
    renderArchiveAdminInto_(content);
  }

  function renderArchiveAdminInto_(content) { // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2
    if (!content) return;
    content.innerHTML = `
"""
    archive = replace_once(archive, old_header, new_header, 'Archive target renderer', 171)
    observer_anchor = "  const observer = new MutationObserver(bindArchiveMenu_);"
    api = "  window.NOVA_ARCHIVE_ADMIN_V2 = Object.freeze({ renderInto: target => renderArchiveAdminInto_(target) }); // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2\n\n" + observer_anchor
    archive = replace_once(archive, observer_anchor, api, 'Archive render API', 172)
    archive_path.write_text(archive, encoding='utf-8')

# 4) Archive realtime follows the visible Archive panel, not the removed sidebar item.
rt_path = Path('ArchiveAdminRealtimeClient.html')
rt = rt_path.read_text(encoding='utf-8')
if MARKER not in rt:
    old_guard = """  function archiveRtAdminMenuPresent_() {
    return Array.from(document.querySelectorAll('#menu button')).some(button =>
      String(button.textContent || '').trim() === 'Archive 이력'
    );
  }
"""
    new_guard = """  function archiveRtAdminMenuPresent_() { // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2
    return archiveRtPageVisible_();
  }
"""
    rt = replace_once(rt, old_guard, new_guard, 'Archive realtime visible-page guard', 173)
    rt_path.write_text(rt, encoding='utf-8')

# Syntax checks for modified browser/server sources.
for source in ['NotificationCenterV1.html', 'ArchiveAdminClient.html', 'ArchiveAdminRealtimeClient.html']:
    text = Path(source).read_text(encoding='utf-8')
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
    if not scripts:
        fail(f'no script block in {source}', 174)
    result = subprocess.run(['node', '--check', '-'], input='\n'.join(scripts), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        fail(f'{source} syntax: {(result.stderr or result.stdout).strip()}', 175)

print('Applied personal notification preferences + Archive settings V2 patch.')
