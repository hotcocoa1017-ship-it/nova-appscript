from pathlib import Path
import sys

MARKER = 'NOVA_PWA_BRIDGE_LOGIN_RESILIENCE_V1'
path = Path('NotificationCenterV1.html')
text = path.read_text(encoding='utf-8')

if MARKER in text:
    print('NOVA PWA login bridge resilience already applied.')
    sys.exit(0)

# This patch runs after patch_pwa_web_push_v2.py, so pushBridge() must already exist.
if "function pushBridge(){" not in text or "type:'NOVA_PUSH_BRIDGE_V2'" not in text:
    print('ERROR: NOVA PWA Web Push V2 bridge must be applied first.', file=sys.stderr)
    sys.exit(140)

old = "U.token=nt;U.auth=a;U.employee=a.employee;U.client=window.supabase?.createClient?.(a.supabaseUrl,a.publishableKey,{auth:{persistSession:false,autoRefreshToken:false}})||null;"
new = "U.token=nt;U.auth=a;U.employee=a.employee;pushBridge();setTimeout(pushBridge,700);setTimeout(pushBridge,2200);U.client=window.supabase?.createClient?.(a.supabaseUrl,a.publishableKey,{auth:{persistSession:false,autoRefreshToken:false}})||null;/* NOVA_PWA_BRIDGE_LOGIN_RESILIENCE_V1 */"
count = text.count(old)
if count != 1:
    print(f'ERROR: initial authenticated bridge anchor count={count}', file=sys.stderr)
    sys.exit(141)
text = text.replace(old, new, 1)

# If the notification channel is already connected, a later life-cycle pass should still
# refresh the bridge. This covers restored tabs / PWA shell reload timing without
# changing the existing Realtime channel or notification behavior.
old_fast = "if(U.token===nt&&U.auth&&U.channel){shell();return}"
new_fast = "if(U.token===nt&&U.auth&&U.channel){shell();pushBridge();return}"
count_fast = text.count(old_fast)
if count_fast != 1:
    print(f'ERROR: connected bridge refresh anchor count={count_fast}', file=sys.stderr)
    sys.exit(142)
text = text.replace(old_fast, new_fast, 1)

path.write_text(text, encoding='utf-8')
print('Applied NOVA PWA login bridge resilience patch.')
