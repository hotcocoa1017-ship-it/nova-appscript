from pathlib import Path
import sys

CLIENT_PATH = Path('Client.html')
SYNC_PATH = Path('RealtimeDailySync.js')
client = CLIENT_PATH.read_text(encoding='utf-8')
sync = SYNC_PATH.read_text(encoding='utf-8')
MARKER = 'ROOM_UPLOAD_REALTIME_CONVERGENCE_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected=1')
    return text.replace(old, new, 1)


if MARKER in client and MARKER in sync:
    print(f'{MARKER} already applied.')
    sys.exit(0)

if MARKER not in sync:
    anchor = """function syncNovaRealtimeRoomForAction(token, payload) { // (룸메이드 작업 직전 누락객실 JIT 동기화)\n"""
    wrapper = """function syncRoomStatusUploadRealtimeNow(token, businessDate, site) { // ROOM_UPLOAD_REALTIME_CONVERGENCE_V1 · 업로드 직후 잠금 밖 DB 수렴\n  const user = requireRole_(token, ['ADMIN', 'ORDER']);\n  const dateText = novaRealtimeFinalBusinessDate_(businessDate);\n  const siteText = String(site || '').trim();\n  if (!siteText) throw new Error('객실현황 DB 즉시동기화에 사업장이 필요합니다.');\n  if (!novaRealtimeFinalEnabled_()) {\n    return { ok: true, skipped: true, reason: 'REALTIME_DISABLED', businessDate: dateText, site: siteText };\n  }\n\n  // 업로드 직후 stale Sheet가 최신 DB 액션을 덮지 않도록 반드시 DB→Sheet 이벤트를 먼저 비웁니다.\n  // backlog가 남으면 즉시 정방향 동기화를 포기하고 기존 1분 통합트리거에 맡깁니다.\n  const mirror = mirrorNovaRealtimeEventsDrain_({ maxBatches: 2, timeBudgetMs: 45000 });\n  if (mirror && mirror.hasMore) {\n    return {\n      ok: true,\n      deferred: true,\n      reason: 'REALTIME_EVENT_BACKLOG',\n      businessDate: dateText,\n      site: siteText,\n      mirror\n    };\n  }\n\n  const current = syncNovaRealtimeCurrentBusinessDate(dateText, siteText, {});\n  PropertiesService.getScriptProperties().setProperty(\n    NOVA_REALTIME_FINAL.LAST_FORWARD_SYNC_MS,\n    String(Date.now())\n  );\n  return {\n    ok: true,\n    immediate: true,\n    businessDate: dateText,\n    site: siteText,\n    mirror,\n    current,\n    requestedBy: String(user.employeeNo || '')\n  };\n}\n\n\n""" + anchor
    sync = replace_once(sync, anchor, wrapper, 'Realtime upload convergence wrapper')

if MARKER not in client:
    old = """      if (!result?.ok) throw new Error(result?.message || '객실현황 반영에 실패했습니다.');\n      closeModal();\n"""
    new = """      if (!result?.ok) throw new Error(result?.message || '객실현황 반영에 실패했습니다.');\n      // ROOM_UPLOAD_REALTIME_CONVERGENCE_V1 · Sheet 잠금이 해제된 뒤 별도 요청으로 DB를 즉시 수렴시킵니다.\n      // 서버가 먼저 pending DB 이벤트를 미러하므로 라이브 배정/QM 상태를 stale 업로드값으로 덮지 않습니다.\n      if (novaRealtimeIsEnabled_()) {\n        void callServer('syncRoomStatusUploadRealtimeNow', state.token, result.businessDate, result.site)\n          .then(syncResult => {\n            if (syncResult?.deferred) {\n              console.warn('[NOVA Realtime] 객실현황 즉시 DB 동기화 보류 · 이벤트 backlog', syncResult);\n              setSyncStatus('객실현황 DB 동기화 대기 · 예약동기화로 계속 반영');\n              return;\n            }\n            if (syncResult?.ok) {\n              console.log('[NOVA Realtime] 객실현황 즉시 DB 동기화 완료', syncResult);\n              setSyncStatus('객실현황 DB 동기화 완료');\n            }\n          })\n          .catch(error => {\n            console.warn('[NOVA Realtime] 객실현황 즉시 DB 동기화 실패 · 예약동기화 유지', error);\n            setSyncStatus('객실현황 DB 동기화 지연 · 예약동기화로 재반영');\n          });\n      }\n      closeModal();\n"""
    client = replace_once(client, old, new, 'Client upload post-apply convergence')

CLIENT_PATH.write_text(client, encoding='utf-8')
SYNC_PATH.write_text(sync, encoding='utf-8')
print(f'Applied {MARKER}: upload success now triggers mirror-first immediate DB convergence outside the Sheet write lock.')
