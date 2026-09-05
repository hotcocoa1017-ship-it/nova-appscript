from pathlib import Path
import sys

PATH = Path('RealtimeDailySync.js')
MARKER = 'REALTIME_EVENT_DRAIN_3000_V1'
text = PATH.read_text(encoding='utf-8')
changed = False

# 500-event DB -> Sheet mirror batches are preserved, but one scheduled invocation may
# drain up to 6 pages (= 3,000 events: 1,500 START + 1,500 COMPLETE).
old_const = "  EVENT_BATCH_LIMIT: 500,\n  HISTORY_DEDUP_SCAN: 6000,"
new_const = "  EVENT_BATCH_LIMIT: 500,\n  EVENT_DRAIN_MAX_BATCHES: 6, // REALTIME_EVENT_DRAIN_3000_V1\n  EVENT_DRAIN_TIME_BUDGET_MS: 180 * 1000,\n  HISTORY_DEDUP_SCAN: 6000,"
if old_const in text:
    text = text.replace(old_const, new_const, 1)
    changed = True
elif 'EVENT_DRAIN_MAX_BATCHES: 6' not in text:
    raise SystemExit('Realtime event drain constants anchor not found')

# Use the bounded drain in the integrated scheduler and the compatibility event scheduler.
old_final = "  const mirror = mirrorNovaRealtimeEventsToSheets_();"
new_final = "  const mirror = mirrorNovaRealtimeEventsDrain_(); // REALTIME_EVENT_DRAIN_3000_V1"
if old_final in text:
    text = text.replace(old_final, new_final, 1)
    changed = True
elif new_final not in text:
    raise SystemExit('Integrated mirror call anchor not found')

old_event = "  const result = mirrorNovaRealtimeEventsToSheets_();\n  console.log(JSON.stringify(result));\n  return result;\n}\n\nfunction testNovaRealtimeEventMirror()"
new_event = "  const result = mirrorNovaRealtimeEventsDrain_(); // REALTIME_EVENT_DRAIN_3000_V1\n  console.log(JSON.stringify(result));\n  return result;\n}\n\nfunction testNovaRealtimeEventMirror()"
if old_event in text:
    text = text.replace(old_event, new_event, 1)
    changed = True
elif "const result = mirrorNovaRealtimeEventsDrain_(); // REALTIME_EVENT_DRAIN_3000_V1" not in text:
    raise SystemExit('Standalone mirror scheduler anchor not found')

# Manual test should exercise the same production drain behavior.
old_test = "function testNovaRealtimeEventMirror() { // (수동 이벤트 미러 검증)\n  const result = mirrorNovaRealtimeEventsToSheets_();"
new_test = "function testNovaRealtimeEventMirror() { // (수동 이벤트 미러 검증)\n  const result = mirrorNovaRealtimeEventsDrain_(); // REALTIME_EVENT_DRAIN_3000_V1"
if old_test in text:
    text = text.replace(old_test, new_test, 1)
    changed = True
elif new_test not in text:
    raise SystemExit('Manual mirror test anchor not found')

# Add bounded multi-page drain wrapper immediately before the existing single-page worker.
if 'function mirrorNovaRealtimeEventsDrain_' not in text:
    anchor = "function mirrorNovaRealtimeEventsToSheets_() { // (DB 이벤트를 기존 NOVA 자료구조로 배치반영)"
    if anchor not in text:
        raise SystemExit('Single-page mirror worker anchor not found')
    block = r'''function mirrorNovaRealtimeEventsDrain_(options) { // (최대 3,000 이벤트를 한 예약실행에서 500건씩 안전 배치반영) // REALTIME_EVENT_DRAIN_3000_V1
  const safe = options || {};
  const configuredMax = Number(safe.maxBatches || NOVA_REALTIME_FINAL.EVENT_DRAIN_MAX_BATCHES || 1);
  const maxBatches = Math.max(1, Math.min(6, Math.floor(configuredMax)));
  const timeBudgetMs = Math.max(30000, Number(safe.timeBudgetMs || NOVA_REALTIME_FINAL.EVENT_DRAIN_TIME_BUDGET_MS || 180000));
  const startedAt = Date.now();
  let batches = 0;
  let mirrored = 0;
  let duplicates = 0;
  let pulled = 0;
  let hasMore = false;
  let cursorTime = '';
  let cursorRequestId = '';
  let stoppedByTimeBudget = false;

  while (batches < maxBatches) {
    const batch = mirrorNovaRealtimeEventsToSheets_();
    batches += 1;
    mirrored += Number(batch && batch.mirrored || 0);
    duplicates += Number(batch && batch.duplicates || 0);
    pulled += Number(batch && batch.pulled || 0);
    hasMore = Boolean(batch && batch.hasMore);
    cursorTime = String(batch && batch.cursorTime || cursorTime);
    cursorRequestId = String(batch && batch.cursorRequestId || cursorRequestId);

    if (!hasMore || Number(batch && batch.pulled || 0) <= 0) break;
    if (Date.now() - startedAt >= timeBudgetMs) {
      stoppedByTimeBudget = true;
      break;
    }
  }

  return {
    ok: true,
    drain: true,
    batches,
    maxBatches,
    mirrored,
    duplicates,
    pulled,
    hasMore,
    stoppedByTimeBudget,
    elapsedMs: Date.now() - startedAt,
    cursorTime,
    cursorRequestId
  };
}

'''
    text = text.replace(anchor, block + anchor, 1)
    changed = True

required = [
    'REALTIME_EVENT_DRAIN_3000_V1',
    'EVENT_DRAIN_MAX_BATCHES: 6',
    'EVENT_DRAIN_TIME_BUDGET_MS: 180 * 1000',
    'function mirrorNovaRealtimeEventsDrain_',
    'const mirror = mirrorNovaRealtimeEventsDrain_();',
]
for needle in required:
    if needle not in text:
        raise SystemExit(f'Missing required marker after patch: {needle}')

if changed:
    PATH.write_text(text, encoding='utf-8')
    print('Applied Realtime 3,000-event bounded drain acceleration patch.')
else:
    print('Realtime 3,000-event drain patch already applied.')
