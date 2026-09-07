from pathlib import Path
import re
import subprocess
import sys

MARKER = 'NOVA_PWA_WEB_PUSH_V2'
PWA_ORIGIN = 'https://nova-pwa-hotcocoa1017-3826.vercel.app'


def fail(message, code=120):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(code)


def replace_once(text, old, new, label, code):
    count = text.count(old)
    if count != 1:
        fail(f'{label} anchor count={count}', code)
    return text.replace(old, new, 1)


# 1) Apps Script doGet: sanitize PWA deep-link parameters and expose them to Index template.
api_path = Path('04_Api.js')
api = api_path.read_text(encoding='utf-8')
if MARKER not in api:
    api = replace_once(
        api,
        "function doGet(e) { // (웹앱 진입)\n  const template = HtmlService.createTemplateFromFile('Index');\n  template.appName = NOVA.APP_NAME;\n  template.version = NOVA.VERSION;\n",
        "function doGet(e) { // (웹앱 진입)\n  const template = HtmlService.createTemplateFromFile('Index');\n  template.appName = NOVA.APP_NAME;\n  template.version = NOVA.VERSION;\n  template.pwaRouteJson = getNovaPwaRouteJson_(e); // NOVA_PWA_WEB_PUSH_V2\n",
        'doGet PWA route injection',
        121,
    )
    anchor = "function include_(filename) { // (HTML 부분파일 포함)\n"
    helper = """function getNovaPwaRouteJson_(e) { // (PWA Push 딥링크 파라미터를 안전한 JSON으로 제한)
  const p = e && e.parameter ? e.parameter : {};
  const allowedRoutes = ['cleaning', 'qm', 'houseman', 'archive', 'indicator'];
  const routeValue = String(p.route || '').trim().toLowerCase();
  const siteValue = String(p.site || '').trim();
  const roomValue = String(p.roomNo || '').trim().replace(/[^0-9A-Za-z가-힣_-]/g, '').slice(0, 24);
  const notificationId = String(p.notificationId || '').replace(/[^0-9]/g, '').slice(0, 24);
  const payload = {
    route: allowedRoutes.includes(routeValue) ? routeValue : '',
    site: NOVA_LOGIN_SITES_.includes(siteValue) ? siteValue : '',
    roomNo: roomValue,
    notificationId
  };
  return JSON.stringify(payload)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026');
}

""" + anchor
    api = replace_once(api, anchor, helper, 'PWA route helper', 122)
    api_path.write_text(api, encoding='utf-8')

# 2) Index: make sanitized server-side deep-link data available before client scripts start.
index_path = Path('Index.html')
index = index_path.read_text(encoding='utf-8')
if 'window.__NOVA_PWA_ROUTE_V2__' not in index:
    anchor = "  <!-- Realtime client library: secret key는 포함하지 않습니다. -->\n"
    insert = "  <script>window.__NOVA_PWA_ROUTE_V2__ = <?!= pwaRouteJson ?>;</script> <!-- NOVA_PWA_WEB_PUSH_V2 -->\n\n" + anchor
    index = replace_once(index, anchor, insert, 'Index PWA route bootstrap', 123)
    index_path.write_text(index, encoding='utf-8')

# 3) Unified notification center: bridge the authenticated Supabase JWT to the outer PWA and apply deep links.
center_path = Path('NotificationCenterV1.html')
center = center_path.read_text(encoding='utf-8')
if MARKER not in center:
    center = replace_once(
        center,
        "const U={auth:null,client:null,channel:null,employee:'',token:'',items:[],known:new Set(),unread:0,legacy:0,writing:false,badgeObs:null,badge:null,audio:null,audioReady:false,sound:localStorage.getItem('novaNotificationSound')!=='0',busy:false,authBusy:false,authTimer:null,pollTimer:null,toastTimer:null};",
        "const U={auth:null,client:null,channel:null,employee:'',token:'',items:[],known:new Set(),unread:0,legacy:0,writing:false,badgeObs:null,badge:null,audio:null,audioReady:false,sound:localStorage.getItem('novaNotificationSound')!=='0',busy:false,authBusy:false,authTimer:null,pollTimer:null,toastTimer:null,pwaRouteDone:false};\nconst PWA_ORIGIN='https://nova-pwa-hotcocoa1017-3826.vercel.app'; // NOVA_PWA_WEB_PUSH_V2",
        'notification state/PWA origin',
        124,
    )
    anchor = "async function authBundle(){"
    helpers = """function pushBridge(){
  if(!U.auth||!U.employee||window.top===window)return;
  try{
    window.top.postMessage({
      type:'NOVA_PUSH_BRIDGE_V2',
      supabaseUrl:String(U.auth.supabaseUrl||''),
      publishableKey:String(U.auth.publishableKey||''),
      token:String(U.auth.token||''),
      employeeNo:String(U.employee||''),
      unread:Number(U.unread||0)
    },PWA_ORIGIN);
  }catch(_){ }
}
function applyPwaRoute(){
  if(U.pwaRouteDone)return;
  const p=window.__NOVA_PWA_ROUTE_V2__;
  if(!p||!String(p.route||''))return;
  U.pwaRouteDone=true;
  route({payload:p,room_no:String(p.roomNo||'')});
}
""" + anchor
    center = replace_once(center, anchor, helpers, 'PWA bridge helpers', 125)
    center = replace_once(
        center,
        "setTimeout(()=>U.writing=false,0)}",
        "setTimeout(()=>U.writing=false,0);pushBridge()}",
        'badge bridge refresh',
        126,
    )
    center = replace_once(
        center,
        "await load(false);scheduleAuth();schedulePoll()",
        "await load(false);applyPwaRoute();scheduleAuth();schedulePoll()",
        'PWA route after authenticated load',
        127,
    )
    center = replace_once(
        center,
        "U.auth=a;if(U.client)await U.client.realtime.setAuth(a.token);scheduleAuth()",
        "U.auth=a;if(U.client)await U.client.realtime.setAuth(a.token);pushBridge();scheduleAuth()",
        'PWA bridge after token renewal',
        128,
    )
    center_path.write_text(center, encoding='utf-8')

# Validation: production code must contain all guards and no privileged key.
api = api_path.read_text(encoding='utf-8')
index = index_path.read_text(encoding='utf-8')
center = center_path.read_text(encoding='utf-8')
requirements = [
    (api, MARKER, 'API marker'),
    (api, "allowedRoutes = ['cleaning', 'qm', 'houseman', 'archive', 'indicator']", 'route allowlist'),
    (index, 'window.__NOVA_PWA_ROUTE_V2__', 'Index route bootstrap'),
    (center, "const PWA_ORIGIN='https://nova-pwa-hotcocoa1017-3826.vercel.app'", 'exact PWA origin'),
    (center, "type:'NOVA_PUSH_BRIDGE_V2'", 'push bridge message'),
    (center, "window.top.postMessage", 'top-level bridge for Apps Script sandbox'),
    (center, 'applyPwaRoute()', 'PWA deep-link apply'),
]
for text, needle, label in requirements:
    if needle not in text:
        fail(f'missing {label}: {needle}', 129)
for forbidden in ['SUPABASE_SERVICE_ROLE_KEY', 'service_role', 'nova_web_push_vapid_private_v2', 'nova_web_push_dispatch_token_v2']:
    if forbidden in center or forbidden in index:
        fail(f'privileged browser literal present: {forbidden}', 130)

scripts = re.findall(r'<script[^>]*>(.*?)</script>', center, flags=re.S | re.I)
if not scripts:
    fail('NotificationCenterV1 has no script block', 131)
result = subprocess.run(['node', '--check', '-'], input='\n'.join(scripts), text=True, capture_output=True, check=False)
if result.returncode != 0:
    fail('NotificationCenterV1 syntax: ' + (result.stderr or result.stdout or 'node --check failed').strip(), 132)
result = subprocess.run(['node', '--check', '04_Api.js'], text=True, capture_output=True, check=False)
if result.returncode != 0:
    fail('04_Api.js syntax: ' + (result.stderr or result.stdout or 'node --check failed').strip(), 133)

print('NOVA PWA Web Push V2 bridge patch validated.')