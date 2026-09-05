from pathlib import Path
import sys

MARKER = 'LIVE_OPERATION_RETRY_RESILIENCE_V1'
path = Path('Client.html')
text = path.read_text(encoding='utf-8')
changed = False

# 1) Apps Script는 measureResponse_에서 BUSY_RETRY 예외를 {ok:false, code:'BUSY_RETRY'}로
#    정상 응답 형태로 반환합니다. 퇴실 고속경로의 기존 재시도 루프가 fulfilled 응답도
#    transient로 판단하도록 보완합니다.
old_retry = '''      for (let index = 0; index < delays.length; index += 1) {
        if (delays[index]) await wait_(delays[index] + Math.round(Math.random() * 250));
        try {
          return await callServer(legacyMethod, state.token, legacySafe);
        } catch (error) {
          lastError = error;
          if (!isTransientServerError_(error) || index === delays.length - 1) throw error;
        }
      }
      throw lastError || new Error('객실 작업 저장 오류');'''
new_retry = '''      for (let index = 0; index < delays.length; index += 1) {
        if (delays[index]) await wait_(delays[index] + Math.round(Math.random() * 250));
        try {
          const legacyResult = await callServer(legacyMethod, state.token, legacySafe); // LIVE_OPERATION_RETRY_RESILIENCE_V1
          if (legacyResult?.ok !== false) return legacyResult;
          if (!isTransientServerError_(legacyResult) || index === delays.length - 1) return legacyResult;
          lastError = legacyResult;
        } catch (error) {
          lastError = error;
          if (!isTransientServerError_(error) || index === delays.length - 1) throw error;
        }
      }
      if (lastError && typeof lastError === 'object' && Object.prototype.hasOwnProperty.call(lastError, 'ok')) return lastError;
      throw lastError || new Error('객실 작업 저장 오류');'''
if MARKER not in text:
    if old_retry not in text:
        print('ERROR: legacy retry loop anchor not found.', file=sys.stderr)
        raise SystemExit(101)
    text = text.replace(old_retry, new_retry, 1)
    changed = True

# 2) QM 최종 상태는 DB에서 먼저 확정되고 상세 체크리스트/업무이력은 Apps Script에 후행 저장됩니다.
#    이 후행 저장은 BUSY_RETRY(쓰기 전 잠금 실패) 응답에 한해서만 재시도합니다.
#    네트워크 오류/불명확한 실패는 재시도하지 않아 중복 이력 위험을 만들지 않습니다.
helper = '''
  async function submitQmInspectionDetailWithBusyRetry_(payload) { // LIVE_OPERATION_RETRY_RESILIENCE_V1 · QM 상세이력 BUSY_RETRY 전용 재시도
    const delays = [0, 500, 1300, 2600];
    let lastResult = null;
    for (let index = 0; index < delays.length; index += 1) {
      if (delays[index]) await wait_(delays[index] + Math.round(Math.random() * 180));
      const result = await callServer('submitQmChecklistInspection', state.token, payload);
      if (result?.ok !== false) return result;
      const code = String(result?.code || '').trim().toUpperCase();
      if (code !== 'BUSY_RETRY' || index === delays.length - 1) return result;
      lastResult = result;
    }
    return lastResult || { ok: false, code: 'BUSY_RETRY', message: 'QM 상세이력 저장이 지연되고 있습니다.' };
  }

'''
submit_anchor = '''  async function submitQmInspectionFinal_(event) { // (QM Realtime 최종상태 즉시반영·상세이력 background 저장)'''
if 'async function submitQmInspectionDetailWithBusyRetry_' not in text:
    if submit_anchor not in text:
        print('ERROR: QM submit anchor not found.', file=sys.stderr)
        raise SystemExit(102)
    text = text.replace(submit_anchor, helper + submit_anchor, 1)
    changed = True

old_persist = '''        return callServer('submitQmChecklistInspection', state.token, {
          businessDate: state.mobile.businessDate,
          site: state.mobile.site,
          roomNo: active.roomNo,
          draftId: active.draft.draftId,
          draftRowNumber: Number(active.draft.rowNumber || 0),
          revision: active.checklist.revision,
          answers: draft.answers,
          defects: draft.defects,
          expectedVersion: Number(active.sheetExpectedVersion || 0),
          realtimeCommitted: true,
          realtimeTargetStatus: targetStatus,
          realtimeRequestId: requestId,
          realtimeVersion: Number(realtime.version || 0)
        });'''
new_persist = '''        return submitQmInspectionDetailWithBusyRetry_({ // LIVE_OPERATION_RETRY_RESILIENCE_V1
          businessDate: state.mobile.businessDate,
          site: state.mobile.site,
          roomNo: active.roomNo,
          draftId: active.draft.draftId,
          draftRowNumber: Number(active.draft.rowNumber || 0),
          revision: active.checklist.revision,
          answers: draft.answers,
          defects: draft.defects,
          expectedVersion: Number(active.sheetExpectedVersion || 0),
          realtimeCommitted: true,
          realtimeTargetStatus: targetStatus,
          realtimeRequestId: requestId,
          realtimeVersion: Number(realtime.version || 0)
        });'''
if new_persist not in text:
    if old_persist not in text:
        print('ERROR: QM detail persist anchor not found.', file=sys.stderr)
        raise SystemExit(103)
    text = text.replace(old_persist, new_persist, 1)
    changed = True

# Safety checks
required = [
    "const legacyResult = await callServer(legacyMethod, state.token, legacySafe); // LIVE_OPERATION_RETRY_RESILIENCE_V1",
    'async function submitQmInspectionDetailWithBusyRetry_',
    "code !== 'BUSY_RETRY'",
    'return submitQmInspectionDetailWithBusyRetry_({ // LIVE_OPERATION_RETRY_RESILIENCE_V1',
]
for needle in required:
    if needle not in text:
        print(f'ERROR: required marker missing: {needle}', file=sys.stderr)
        raise SystemExit(104)

if changed:
    path.write_text(text, encoding='utf-8')
    print('Applied live operation retry resilience V1.')
else:
    print('Live operation retry resilience V1 already applied.')
