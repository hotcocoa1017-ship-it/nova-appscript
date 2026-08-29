from pathlib import Path
import re
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

stable_marker = 'API 설정과 보조 Realtime 연결을 분리해 고속 API 유지'
if stable_marker in text:
    print('Realtime init hotfix already applied.')
    sys.exit(0)

pattern = re.compile(
    r"  async function initNovaRealtime_\(\) \{.*?\n  \}\n\n  function novaRealtimeMapRow_",
    re.S,
)

replacement = r'''  async function initNovaRealtime_() { // (API 설정과 보조 Realtime 연결을 분리해 고속 API 유지)
    if (!state.token) return false;
    if (!novaRealtime_.configLoaded) {
      try {
        const config = await callServer('getNovaRealtimeClientConfig', state.token);
        novaRealtime_.configLoaded = true;
        novaRealtime_.enabled = Boolean(config?.ok && config?.enabled && config?.apiBase);
        novaRealtime_.apiBase = String(config?.apiBase || '').replace(/\/+$/, '');
      } catch (error) {
        novaRealtime_.configLoaded = false;
        novaRealtime_.enabled = false;
        novaRealtime_.apiBase = '';
        console.error('[NOVA Realtime] 설정조회 실패:', error);
        setSyncStatus(`Realtime 연결 재시도 · ${error?.message || '설정 조회 오류'}`);
        return false;
      }
    }
    if (!novaRealtimeIsEnabled_()) return false;

    try {
      await novaRealtimeHydrateCurrentView_();
      const role = String(state.bootstrap?.user?.role || '').toUpperCase();
      if (['ADMIN', 'ORDER'].includes(role) && state.activeMenu === 'indicator') {
        try {
          await novaRealtimeEnsureSubscriptions_();
        } catch (subscriptionError) {
          console.warn('[NOVA Realtime] 구독 연결 실패 · DB 변경조회로 보조합니다.', subscriptionError);
        }
        novaRealtimeStartIndicatorDbFallback_();
        setSyncStatus('Realtime 관리자 연결 준비 완료');
      } else {
        setSyncStatus('고속 API 연결 준비 완료');
      }
    } catch (error) {
      // 화면 수화/구독 오류가 있어도 Cloud Run 고속 API 자체는 비활성화하지 않습니다.
      console.warn('[NOVA Realtime] 보조 연결 초기화 오류 · 고속 API는 유지합니다.', error);
      const role = String(state.bootstrap?.user?.role || '').toUpperCase();
      if (['ADMIN', 'ORDER'].includes(role) && state.activeMenu === 'indicator') novaRealtimeStartIndicatorDbFallback_();
      setSyncStatus('고속 API 연결 준비 완료 · Realtime 보조 연결 재시도');
    }
    return true;
  }

  function novaRealtimeMapRow_'''

updated, count = pattern.subn(replacement, text, count=1)
if count != 1:
    print('ERROR: Could not locate exactly one initNovaRealtime_ block.', file=sys.stderr)
    sys.exit(2)

path.write_text(updated, encoding='utf-8')
print('Applied stable Realtime init hotfix to Client.html.')
