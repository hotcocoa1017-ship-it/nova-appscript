from pathlib import Path
import re
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
updated = text
changed = False

# 1) Realtime 설정 조회 성공과 Supabase 보조 연결 성공을 분리합니다.
stable_marker = 'API 설정과 보조 Realtime 연결을 분리해 고속 API 유지'
if stable_marker not in updated:
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

    next_text, count = pattern.subn(replacement, updated, count=1)
    if count != 1:
        print('ERROR: Could not locate exactly one initNovaRealtime_ block.', file=sys.stderr)
        sys.exit(2)
    updated = next_text
    changed = True
    print('Applied stable Realtime init hotfix to Client.html.')
else:
    print('Realtime init hotfix already applied.')

# 2) 객실조치 상태(BROKEN/ROOM_CHECK/완료)는 공용 DB version과 분리합니다.
# 이벤트 미러/5분 정방향 동기화가 DB version을 재정렬해도 객실조치 완료가
# 가짜 VERSION_CONFLICT로 거절되지 않아야 합니다. 실제 충돌 판정은
# 기존 expectedState.operationalStatus 및 서버의 상태검증을 그대로 사용합니다.
old_expected_version = "expectedVersion: action === 'CLEAR_ASSIGNMENT' ? 0 : Number(room.version || 0),"
new_expected_version = "expectedVersion: ['CLEAR_ASSIGNMENT', 'UPDATE_ROOM_OPERATION_STATUS'].includes(action) ? 0 : Number(room.version || 0),"

if new_expected_version in updated:
    print('Operational-status version-domain hotfix already applied.')
elif old_expected_version in updated:
    updated = updated.replace(old_expected_version, new_expected_version, 1)
    changed = True
    print('Applied operational-status version-domain hotfix to Client.html.')
else:
    print('ERROR: Could not locate operational-status expectedVersion line.', file=sys.stderr)
    sys.exit(3)

if changed:
    path.write_text(updated, encoding='utf-8')
    print('Client.html hotfixes written.')
else:
    print('Client.html already up to date.')
