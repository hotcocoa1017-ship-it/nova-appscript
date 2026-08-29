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
# 이벤트 미러/정방향 동기화가 DB version을 재정렬해도 객실조치 완료가
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

# 3) 객실조치 '완료'(operationalStatus='')에서 Cloud Run 5xx/네트워크 오류가 나면
# 오류 알림으로 끝내지 않고 상태기반 Apps Script 안전경로로 즉시 확정합니다.
# 고장/객실확인 등록 및 다른 Realtime 액션은 기존 DB 우선 경로를 그대로 유지합니다.
completion_failover_marker = '객실조치 완료 Realtime 실패 · 안전경로로 자동 전환'
if completion_failover_marker not in updated:
    old_catch = """    } catch (error) {\n      const code = String(error?.code || '').trim().toUpperCase();\n\n      // 권한/상태 오류는 DB 보정으로 해결되지 않으므로 느린 Sheets JIT 동기화를 실행하지 않습니다.\n"""
    new_catch = """    } catch (error) {\n      const code = String(error?.code || '').trim().toUpperCase();\n      const errorStatus = Number(error?.status || 0);\n      const operationalStatusCompletion = mappedAction === 'UPDATE_ROOM_OPERATION_STATUS'\n        && !String(safe.operationalStatus || '').trim();\n\n      // 객실조치 완료 Realtime 실패 · 안전경로로 자동 전환\n      // 완료는 빈 상태값('')을 보내므로 Cloud Run 런타임이 5xx/네트워크 오류를 반환해도\n      // 실제 직전 객실조치 상태만 비교하는 Apps Script 안전경로로 확정하고,\n      // 성공 후 해당 1객실만 DB에 즉시 재동기화합니다. 4xx 권한/상태 오류는 우회하지 않습니다.\n      if (operationalStatusCompletion && (errorStatus === 0 || errorStatus >= 500)) {\n        console.warn('[NOVA Realtime] 객실조치 완료 API 실패 · 안전경로로 전환합니다.', error);\n        const fallbackPayload = Object.assign({}, legacySafe, {\n          action: 'UPDATE_ROOM_OPERATION_STATUS',\n          operationalStatus: '',\n          expectedVersion: 0,\n          expectedOperationalStatus: String(safe?.expectedState?.operationalStatus || '')\n        });\n        delete fallbackPayload.sheetExpectedVersion;\n        const fallbackResult = await callServer('updateRoomOperationalStatusSafe', state.token, fallbackPayload);\n        if (!fallbackResult?.ok) throw new Error(fallbackResult?.message || '객실조치 완료를 저장하지 못했습니다.');\n        void callServer('syncNovaRealtimeRoomForAction', state.token, {\n          businessDate: safe.businessDate,\n          site: safe.site,\n          roomNo: safe.roomNo,\n          action: 'UPDATE_ROOM_OPERATION_STATUS'\n        }).catch(syncError => {\n          console.warn('[NOVA Realtime] 객실조치 완료 후 DB 단건 재동기화는 정기 동기화로 넘깁니다.', syncError);\n        });\n        return Object.assign({}, fallbackResult, { realtimeFallback: true, realtimeFallbackReason: 'OPERATION_STATUS_COMPLETE_5XX' });\n      }\n\n      // 권한/상태 오류는 DB 보정으로 해결되지 않으므로 느린 Sheets JIT 동기화를 실행하지 않습니다.\n"""
    if old_catch not in updated:
        print('ERROR: Could not locate Realtime action catch block for completion failover.', file=sys.stderr)
        sys.exit(4)
    updated = updated.replace(old_catch, new_catch, 1)
    changed = True
    print('Applied operational-status completion failover to Client.html.')
else:
    print('Operational-status completion failover already applied.')

# 4) 완료 처리의 Cloud Run 오류는 재시도 3회로 지연시키지 않습니다.
# 다른 API는 기존 retry 정책을 유지합니다.
no_retry_marker = "options.noRetry !== true"
if no_retry_marker not in updated:
    old_retryable = "const retryable = response.status === 429 || response.status >= 500;"
    new_retryable = "const retryable = (response.status === 429 || response.status >= 500) && options.noRetry !== true;"
    if old_retryable not in updated:
        print('ERROR: Could not locate Realtime retry policy.', file=sys.stderr)
        sys.exit(5)
    updated = updated.replace(old_retryable, new_retryable, 1)
    changed = True
    print('Applied optional no-retry support to Realtime fetch.')
else:
    print('Realtime no-retry support already applied.')

completion_no_retry = "noRetry: mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' && !String(safe.operationalStatus || '').trim(),"
if completion_no_retry not in updated:
    old_send = """    const send = () => novaRealtimeFetch_(`/v1/rooms/${encodeURIComponent(String(safe.roomNo || ''))}/action`, {\n      method: 'POST',\n      headers: { 'X-Request-Id': safe.requestId },\n      body: JSON.stringify(safe)\n    });\n"""
    new_send = """    const send = () => novaRealtimeFetch_(`/v1/rooms/${encodeURIComponent(String(safe.roomNo || ''))}/action`, {\n      method: 'POST',\n      headers: { 'X-Request-Id': safe.requestId },\n      noRetry: mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' && !String(safe.operationalStatus || '').trim(),\n      body: JSON.stringify(safe)\n    });\n"""
    if old_send not in updated:
        print('ERROR: Could not locate Realtime room action sender.', file=sys.stderr)
        sys.exit(6)
    updated = updated.replace(old_send, new_send, 1)
    changed = True
    print('Disabled repeated 5xx retry for operational-status completion only.')
else:
    print('Operational-status completion no-retry already applied.')

# 5) 객실조치 완료는 현재 확인된 Cloud Run 5xx 경로를 기다리지 않고
# 상태기반 Apps Script 안전경로로 바로 확정합니다. DB 단건 동기화는 응답 후 비동기로 처리합니다.
# 고장/객실확인 등록은 기존 Realtime 고속경로를 그대로 사용합니다.
completion_direct_marker = '객실조치 완료는 Cloud Run 우회 · 안전경로 직접 저장'
if completion_direct_marker not in updated:
    old_direct_anchor = """    delete safe.sheetExpectedVersion;\n    safe.action = mappedAction;\n"""
    new_direct_anchor = """    const operationalStatusCompletionDirect = mappedAction === 'UPDATE_ROOM_OPERATION_STATUS'\n      && !String(safe.operationalStatus || '').trim();\n    if (operationalStatusCompletionDirect) {\n      // 객실조치 완료는 Cloud Run 우회 · 안전경로 직접 저장\n      // 화면은 이미 optimistic patch로 즉시 반영하고, 확정 저장만 안전경로 1회 호출합니다.\n      const directPayload = Object.assign({}, legacySafe, {\n        action: 'UPDATE_ROOM_OPERATION_STATUS',\n        operationalStatus: '',\n        expectedVersion: 0,\n        expectedOperationalStatus: String(safe?.expectedState?.operationalStatus || '')\n      });\n      delete directPayload.sheetExpectedVersion;\n      const directResult = await callServer('updateRoomOperationalStatusSafe', state.token, directPayload);\n      if (!directResult?.ok) throw new Error(directResult?.message || '객실조치 완료를 저장하지 못했습니다.');\n      void callServer('syncNovaRealtimeRoomForAction', state.token, {\n        businessDate: safe.businessDate,\n        site: safe.site,\n        roomNo: safe.roomNo,\n        action: 'UPDATE_ROOM_OPERATION_STATUS'\n      }).catch(syncError => {\n        console.warn('[NOVA Realtime] 객실조치 완료 후 DB 단건 재동기화는 정기 동기화로 넘깁니다.', syncError);\n      });\n      return Object.assign({}, directResult, { realtimeDirectSafePath: true });\n    }\n\n    delete safe.sheetExpectedVersion;\n    safe.action = mappedAction;\n"""
    if old_direct_anchor not in updated:
        print('ERROR: Could not locate Realtime room action direct-route anchor.', file=sys.stderr)
        sys.exit(7)
    updated = updated.replace(old_direct_anchor, new_direct_anchor, 1)
    changed = True
    print('Routed operational-status completion directly to safe path.')
else:
    print('Operational-status completion direct safe path already applied.')

if changed:
    path.write_text(updated, encoding='utf-8')
    print('Client.html hotfixes written.')
else:
    print('Client.html already up to date.')