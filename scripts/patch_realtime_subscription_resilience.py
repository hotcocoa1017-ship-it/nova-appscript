from pathlib import Path
import subprocess
import sys

for step_script, label in [
    ('scripts/patch_archive_prune_admin_ui.py', 'Archive prune admin UI'),
    ('scripts/patch_archive_prune_realtime_refresh.py', 'Archive prune realtime refresh'),
    ('scripts/patch_pwa_web_push_v2.py', 'NOVA PWA Web Push V2 bridge'),
    ('scripts/patch_pwa_bridge_login_resilience.py', 'NOVA PWA login bridge resilience'),
    ('scripts/patch_notification_preferences_archive_settings_v2.py', 'NOVA personal notification settings + Archive settings'),
    ('scripts/patch_notification_preview_audio_unlock_v1.py', 'NOVA notification preview audio unlock V1'),
    ('scripts/patch_notification_preview_client_fallback_v2.py', 'NOVA notification preview client fallback V2'),
    ('scripts/patch_push_permission_settings_v1.py', 'NOVA Push permission settings V1'),
    ('scripts/patch_personal_settings_role_access_v3.py', 'NOVA personal settings role access V3'),
    ('scripts/validate_notification_preferences_archive_settings_v2.py', 'NOVA notification preferences + Archive settings validation'),
    ('scripts/validate_notification_center_v1.py', 'NOVA notification center V1 validation'),
]:
    step = subprocess.run([sys.executable, step_script], check=False)
    if step.returncode != 0:
        print(f'ERROR: {label} failed ({step.returncode})', file=sys.stderr)
        sys.exit(step.returncode)

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
marker = 'REALTIME_SUBSCRIPTION_RESILIENCE_V1'

if marker in text:
    print('Realtime subscription resilience patch already applied.')
    sys.exit(0)

old_auth = "    novaRealtime_.supabase.realtime.setAuth(auth.token);\n"
new_auth = "    await novaRealtime_.supabase.realtime.setAuth(auth.token); // REALTIME_SUBSCRIPTION_RESILIENCE_V1\n"
if text.count(old_auth) != 1:
    print(f'ERROR: initial realtime setAuth anchor count={text.count(old_auth)}', file=sys.stderr)
    sys.exit(90)
text = text.replace(old_auth, new_auth, 1)

old_refresh = "        novaRealtime_.supabase.realtime.setAuth(next.token);\n        await novaRealtimeEnsureSubscriptions_();\n"
new_refresh = "        await novaRealtime_.supabase.realtime.setAuth(next.token);\n        await novaRealtimeEnsureSubscriptions_();\n"
if text.count(old_refresh) != 1:
    print(f'ERROR: refresh realtime setAuth anchor count={text.count(old_refresh)}', file=sys.stderr)
    sys.exit(91)
text = text.replace(old_refresh, new_refresh, 1)

old_subscribe = """        .subscribe((status, error) => {
          if (error) console.error(`[NOVA Realtime] ${site} 구독 오류`, error);
          if (status === 'SUBSCRIBED') setSyncStatus(`Realtime 연결 · ${site}`);
        });
      novaRealtime_.channels.set(site, channel);
"""
new_subscribe = """        .subscribe((status, error) => {
          if (status === 'SUBSCRIBED') {
            setSyncStatus(`Realtime 연결 · ${site}`);
            return;
          }
          const failed = Boolean(error) || ['CHANNEL_ERROR', 'TIMED_OUT', 'CLOSED'].includes(String(status || '').toUpperCase());
          if (!failed) return;
          console.error(`[NOVA Realtime] ${site} 구독 실패 (${status || 'UNKNOWN'})`, error || '');
          if (novaRealtime_.channels.get(site) === channel) novaRealtime_.channels.delete(site);
          if (novaRealtime_.supabase) {
            void novaRealtime_.supabase.removeChannel(channel).catch(() => {});
          }
          window.setTimeout(() => {
            if (!state.token || document.hidden || !novaRealtimeIsEnabled_()) return;
            if (!novaRealtimeRelevantSites_().includes(site)) return;
            void novaRealtimeEnsureSubscriptions_().catch(retryError => {
              console.warn(`[NOVA Realtime] ${site} 구독 재시도 실패`, retryError);
            });
          }, 1200);
        });
      novaRealtime_.channels.set(site, channel);
"""
if text.count(old_subscribe) != 1:
    print(f'ERROR: realtime subscribe anchor count={text.count(old_subscribe)}', file=sys.stderr)
    sys.exit(92)
text = text.replace(old_subscribe, new_subscribe, 1)

path.write_text(text, encoding='utf-8')
print('Applied resilient private Realtime subscription patch.')