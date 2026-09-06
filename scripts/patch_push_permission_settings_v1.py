from pathlib import Path
import re
import subprocess
import sys

MARKER = 'NOVA_PUSH_PERMISSION_SETTINGS_V1'
PWA_ORIGIN = 'https://nova-pwa-hotcocoa1017-3826.vercel.app'


def fail(message, code=210):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(code)


def replace_once(text, old, new, label, code):
    count = text.count(old)
    if count != 1:
        fail(f'{label} anchor count={count}', code)
    return text.replace(old, new, 1)


client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')
if MARKER not in client:
    css_old = "  .notification-pref-actions{display:flex;justify-content:flex-end;gap:8px}.notification-pref-actions button{min-height:40px;padding:0 14px;border:1px solid #d1d5db;border-radius:9px;background:#fff;font-weight:800}.notification-pref-actions .primary{background:#111827;color:#fff;border-color:#111827}\n  .settings-archive-host{min-width:0}.settings-archive-host .nova-archive-head h1{font-size:20px}\n"
    css_new = "  .notification-pref-actions{display:flex;justify-content:flex-end;gap:8px}.notification-pref-actions button{min-height:40px;padding:0 14px;border:1px solid #d1d5db;border-radius:9px;background:#fff;font-weight:800}.notification-pref-actions .primary{background:#111827;color:#fff;border-color:#111827}\n  .notification-push-card{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 14px;border:1px solid #dbeafe;border-radius:11px;background:#f8fbff}.notification-push-card>div{display:grid;gap:3px;min-width:0}.notification-push-card strong{font-size:13px;color:#111827}.notification-push-card small{color:#64748b;font-size:11px;line-height:1.4}.notification-push-card button{flex:0 0 auto;min-height:38px;padding:0 12px;border:1px solid #bfdbfe;border-radius:9px;background:#fff;color:#1d4ed8;font-weight:900}.notification-push-card button:disabled{opacity:.6}\n  .settings-archive-host{min-width:0}.settings-archive-host .nova-archive-head h1{font-size:20px}\n"
    client = replace_once(client, css_old, css_new, 'notification push settings CSS', 211)

    helper_anchor = "  function renderNotificationPreferencesPanel_() { // NOVA_PERSONAL_NOTIFICATION_SETTINGS_V2\n"
    helpers = f"""  const NOVA_PWA_PUSH_PERMISSION_ORIGIN_ = '{PWA_ORIGIN}'; // {MARKER}\n\n  function applyNovaPushPermissionState_(detail = {{}}) {{\n    const status = $('novaPushPermissionStatus');\n    const button = $('novaPushPermissionButton');\n    if (!status || !button) return;\n    const permission = String(detail.permission || 'unknown').toLowerCase();\n    const subscribed = Boolean(detail.subscribed);\n    if (permission === 'granted' && subscribed) {{ status.textContent = '허용됨 · 이 기기 Push 연결 완료'; button.textContent = 'Push 연결 확인'; button.disabled = false; return; }}\n    if (permission === 'granted') {{ status.textContent = '알림 권한 허용됨 · Push 기기 등록 확인 필요'; button.textContent = 'Push 다시 연결'; button.disabled = false; return; }}\n    if (permission === 'denied') {{ status.textContent = '알림 권한이 차단되어 있습니다.'; button.textContent = '권한 설정 안내'; button.disabled = false; return; }}\n    if (permission === 'unsupported') {{ status.textContent = '이 실행환경에서는 Web Push 알림을 사용할 수 없습니다.'; button.textContent = '지원 안 됨'; button.disabled = true; return; }}\n    if (permission === 'standalone-required') {{ status.textContent = 'iPhone은 홈 화면에 설치한 NOVA에서 알림을 켜야 합니다.'; button.textContent = '설치 후 사용'; button.disabled = false; return; }}\n    status.textContent = window.top === window ? '설치된 NOVA PWA에서 Push 알림을 설정할 수 있습니다.' : '알림 권한이 아직 설정되지 않았습니다.';\n    button.textContent = 'Push 알림 켜기';\n    button.disabled = window.top === window;\n  }}\n\n  function requestNovaPushPermissionUi_(action = 'STATUS') {{\n    if (window.top === window) {{ applyNovaPushPermissionState_({{ permission: 'unsupported' }}); return; }}\n    try {{\n      window.top.postMessage({{ type: 'NOVA_PUSH_PERMISSION_UI_V1', action: String(action || 'STATUS').toUpperCase() }}, NOVA_PWA_PUSH_PERMISSION_ORIGIN_);\n    }} catch (error) {{\n      console.warn('[NOVA Push Permission] bridge', error);\n      applyNovaPushPermissionState_({{ permission: 'unknown' }});\n    }}\n  }}\n\n  if (!window.__NOVA_PUSH_PERMISSION_SETTINGS_V1__) {{\n    window.__NOVA_PUSH_PERMISSION_SETTINGS_V1__ = true;\n    window.addEventListener('message', event => {{\n      if (event.origin !== NOVA_PWA_PUSH_PERMISSION_ORIGIN_) return;\n      const detail = event.data || {{}};\n      if (detail.type !== 'NOVA_PUSH_PERMISSION_STATE_V1') return;\n      applyNovaPushPermissionState_(detail);\n    }});\n  }}\n\n""" + helper_anchor
    client = replace_once(client, helper_anchor, helpers, 'push permission settings helpers', 212)

    intro_old = "        <div><h2>개인 알림 설정</h2><p>이 설정은 사번 기준으로 저장됩니다. 효과음과 음량은 NOVA가 실행 중일 때의 자체 알림음에 적용되며, 앱을 닫은 상태의 Web Push 소리는 휴대폰·PC 운영체제의 알림 설정을 따릅니다.</p></div>\n        <div class=\"notification-pref-row\"><span>알림음</span>"
    intro_new = "        <div><h2>개인 알림 설정</h2><p>이 설정은 사번 기준으로 저장됩니다. 효과음과 음량은 NOVA가 실행 중일 때의 자체 알림음에 적용되며, 앱을 닫은 상태의 Web Push 소리는 휴대폰·PC 운영체제의 알림 설정을 따릅니다.</p></div>\n        <div class=\"notification-push-card\"><div><strong>백그라운드 Push 알림</strong><small id=\"novaPushPermissionStatus\">기기 알림 상태를 확인하고 있습니다.</small></div><button id=\"novaPushPermissionButton\" type=\"button\">Push 알림 켜기</button></div>\n        <div class=\"notification-pref-row\"><span>알림음</span>"
    client = replace_once(client, intro_old, intro_new, 'notification settings push card', 213)

    listener_old = "    volume?.addEventListener('input', () => { if (output) output.textContent = `${Number(volume.value || 0)}%`; });\n    $('novaPrefPreview')?.addEventListener('click', async () => {"
    listener_new = "    volume?.addEventListener('input', () => { if (output) output.textContent = `${Number(volume.value || 0)}%`; });\n    $('novaPushPermissionButton')?.addEventListener('click', () => requestNovaPushPermissionUi_('SHOW'));\n    window.setTimeout(() => requestNovaPushPermissionUi_('STATUS'), 0);\n    $('novaPrefPreview')?.addEventListener('click', async () => {"
    client = replace_once(client, listener_old, listener_new, 'push permission settings listener', 214)
    client_path.write_text(client, encoding='utf-8')


pwa_path = Path('pwa/v2/index.html')
pwa = pwa_path.read_text(encoding='utf-8')
if MARKER not in pwa:
    pwa = replace_once(
        pwa,
        "let bridge=null,registration=null,syncBusy=false,gateTimer=null;",
        "let bridge=null,registration=null,syncBusy=false,gateTimer=null,gateClosedSession=false; // NOVA_PUSH_PERMISSION_SETTINGS_V1",
        'PWA permission state',
        215,
    )
    pwa = replace_once(
        pwa,
        "  if(!bridge&&!force)return;\n  if(!force&&promptSnoozed())return;",
        "  if(!bridge&&!force)return;\n  if(!force&&gateClosedSession)return;\n  if(!force&&promptSnoozed()&&Notification.permission!=='default')return;",
        'PWA permission gate visibility',
        216,
    )
    pwa = replace_once(
        pwa,
        "function hideGate(snooze=false){clearTimeout(gateTimer);GATE.classList.remove('show');if(snooze)localStorage.setItem(PROMPT_KEY,String(Date.now()))}",
        "function hideGate(snooze=false){clearTimeout(gateTimer);GATE.classList.remove('show');if(snooze){gateClosedSession=true;localStorage.setItem(PROMPT_KEY,String(Date.now()))}}",
        'PWA permission gate dismiss',
        217,
    )

    upsert_anchor = "async function upsertSubscription(sub){\n"
    report_helper = """async function reportPushPermissionState(){
  let permission='unsupported',subscribed=false;
  try{
    if('Notification' in window) permission=String(Notification.permission||'default');
    const reg=registration||(('serviceWorker' in navigator)?await registerSW():null);
    if(reg?.pushManager) subscribed=Boolean(await reg.pushManager.getSubscription());
    if(isiOS()&&!standalone()&&permission!=='granted') permission='standalone-required';
  }catch(e){console.warn('[NOVA PWA] permission state',e)}
  try{FRAME.contentWindow?.postMessage({type:'NOVA_PUSH_PERMISSION_STATE_V1',permission,subscribed,standalone:standalone()},'*')}catch(_){ }
}

""" + upsert_anchor
    pwa = replace_once(pwa, upsert_anchor, report_helper, 'PWA permission reporting helper', 218)

    pwa = replace_once(
        pwa,
        "    if(Notification.permission==='denied'){hideGate(false);return}",
        "    if(Notification.permission==='denied'){hideGate(false);await reportPushPermissionState();return}",
        'PWA denied state report',
        219,
    )
    pwa = replace_once(
        pwa,
        "    if(sub){await upsertSubscription(sub);localStorage.removeItem(PROMPT_KEY);hideGate(false);return}\n    if(Notification.permission==='default')showGate();",
        "    if(sub){await upsertSubscription(sub);localStorage.removeItem(PROMPT_KEY);hideGate(false);await reportPushPermissionState();return}\n    if(Notification.permission==='default')showGate('NOVA 앱 알림을 켜면 앱을 닫아도 업무 알림을 받을 수 있습니다.',{sticky:true});\n    await reportPushPermissionState();",
        'PWA existing subscription state report',
        220,
    )
    pwa = replace_once(
        pwa,
        "    if(permission!=='granted'){hideGate(true);return}",
        "    if(permission!=='granted'){hideGate(true);await reportPushPermissionState();return}",
        'PWA request result report',
        221,
    )
    pwa = replace_once(
        pwa,
        "    await upsertSubscription(sub);localStorage.removeItem(PROMPT_KEY);hideGate(false);",
        "    await upsertSubscription(sub);localStorage.removeItem(PROMPT_KEY);gateClosedSession=false;hideGate(false);await reportPushPermissionState();",
        'PWA successful permission report',
        222,
    )

    old_message = """window.addEventListener('message',e=>{
  const d=e.data||{};
  if(d.type!=='NOVA_PUSH_BRIDGE_V2'||!d.token||!d.employeeNo)return;
  const supabaseUrl=String(d.supabaseUrl||'').replace(/\\/+$/,'');
  const employeeNo=String(d.employeeNo||'').trim(),c=claims(d.token);
  if(supabaseUrl!==SUPABASE||String(c?.employee_no||'').trim()!==employeeNo)return;
  bridge={supabaseUrl:SUPABASE,publishableKey:String(d.publishableKey||PUB),token:String(d.token),employeeNo};
  badge(Number(d.unread||0));void syncExisting();
});
"""
    new_message = """window.addEventListener('message',e=>{
  const d=e.data||{};
  if(e.source===FRAME.contentWindow&&d.type==='NOVA_PUSH_PERMISSION_UI_V1'){
    const action=String(d.action||'STATUS').toUpperCase();
    if(action==='SHOW'){
      gateClosedSession=false;
      localStorage.removeItem(PROMPT_KEY);
      if(!('Notification' in window))void reportPushPermissionState();
      else if(Notification.permission==='granted')void syncExisting().finally(reportPushPermissionState);
      else showGate(Notification.permission==='denied'?'브라우저에서 NOVA 알림이 차단되어 있습니다. 사이트 알림 권한을 허용해 주세요.':'아래 버튼을 눌러 NOVA Push 알림 권한을 허용해 주세요.',{force:true,sticky:true});
    }
    void reportPushPermissionState();
    return;
  }
  if(d.type!=='NOVA_PUSH_BRIDGE_V2'||!d.token||!d.employeeNo)return;
  const supabaseUrl=String(d.supabaseUrl||'').replace(/\\/+$/,'');
  const employeeNo=String(d.employeeNo||'').trim(),c=claims(d.token);
  if(supabaseUrl!==SUPABASE||String(c?.employee_no||'').trim()!==employeeNo)return;
  bridge={supabaseUrl:SUPABASE,publishableKey:String(d.publishableKey||PUB),token:String(d.token),employeeNo};
  badge(Number(d.unread||0));void syncExisting();void reportPushPermissionState();
});
"""
    pwa = replace_once(pwa, old_message, new_message, 'PWA permission UI bridge', 223)
    pwa_path.write_text(pwa, encoding='utf-8')


# Browser syntax and marker validation.
client = client_path.read_text(encoding='utf-8')
pwa = pwa_path.read_text(encoding='utf-8')
for text, needle, label in [
    (client, MARKER, 'Client permission marker'),
    (client, 'novaPushPermissionButton', 'Client push permission button'),
    (client, "type: 'NOVA_PUSH_PERMISSION_UI_V1'", 'Client permission bridge'),
    (pwa, MARKER, 'PWA permission marker'),
    (pwa, "d.type==='NOVA_PUSH_PERMISSION_UI_V1'", 'PWA permission bridge handler'),
    (pwa, 'reportPushPermissionState', 'PWA permission state reporter'),
]:
    if needle not in text:
        fail(f'missing {label}: {needle}', 224)

for source in ['Client.html', 'pwa/v2/index.html']:
    text = Path(source).read_text(encoding='utf-8')
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
    if not scripts:
        fail(f'no script block in {source}', 225)
    # Apps Script template tags in Index-like files are absent here; both sources are plain JS inside script blocks.
    joined = '\n'.join(scripts)
    if '<?' in joined:
        joined = re.sub(r'<\?[\s\S]*?\?>', 'null', joined)
    result = subprocess.run(['node', '--check', '-'], input=joined, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        fail(f'{source} syntax: {(result.stderr or result.stdout).strip()}', 226)

print('Applied NOVA Push permission settings V1 patch.')
