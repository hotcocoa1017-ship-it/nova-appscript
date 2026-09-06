from pathlib import Path
import sys

CLIENT = Path('Client.html')
text = CLIENT.read_text(encoding='utf-8')

start_marker = '  function startMobileSync() {'
end_marker = '  function scheduleMobileSync_() {'
start = text.find(start_marker)
end = text.find(end_marker, start + 1) if start >= 0 else -1
mobile_start_block = text[start:end] if start >= 0 and end > start else ''

checks = [
    ('marker', text.count('ROOM_STATE_SYNC_HARDENING_V1') >= 8),
    ('indicator full reconcile state', 'indicatorFullReconcileAt: 0' in text),
    ('bounded fetch helper', 'function novaRealtimeBoundedFetch_' in text),
    ('primary Realtime fetch bounded', 'novaRealtimeBoundedFetch_(`${novaRealtime_.apiBase}${path}`' in text),
    ('room changes bounded', 'novaRealtimeBoundedFetch_(`${novaRealtime_.apiBase}/v1/room-changes`' in text),
    ('cleaning action 5s per-attempt timeout', "['CLEANING_START', 'CLEANING_COMPLETE'].includes(mappedAction) ? 5000 : 7000" in text),
    ('indicator full current-state helper', 'async function novaRealtimeReconcileIndicatorRooms_' in text),
    ('indicator full reconcile every 15s', '>= 15000' in text),
    ('indicator first reconcile starts quickly', 'window.setTimeout(run, 80)' in text),
    ('event cursor fallback preserved', 'novaRealtimeHydrateIndicatorFallback_()' in text),
    ('ROOMMAID push subscription', "role === 'ROOMMAID' && state.activeMenu === 'cleaning'" in mobile_start_block and 'void novaRealtimeEnsureSubscriptions_()' in mobile_start_block),
    ('QM push subscription', "role === 'QM' && state.activeMenu === 'qm'" in mobile_start_block and 'void novaRealtimeEnsureSubscriptions_()' in mobile_start_block),
    ('HOUSEMAN push subscription preserved', "role === 'HOUSEMAN' && state.activeMenu === 'houseman'" in mobile_start_block),
    ('mobile polling fallback preserved', 'delay = 3000 + Math.round(Math.random() * 700)' in text),
    ('mobile immediate DB reconcile on start', 'window.setTimeout(() => { void syncMobileDelta(); }, 0)' in mobile_start_block),
    ('roommaid optimistic pending action', "__pendingAction: action === 'START' ? 'CLEANING_START'" in text),
    ('stale DB does not revert pending start', "merged.cleaningStatus = String(legacyRoom.cleaningStatus" in text),
    ('DB confirmation clears pending action', 'delete merged.__pendingAction' in text),
    ('server confirmation clears roommaid pending action', 'delete confirmed.__pendingAction' in text),
    ('post-action DB reconcile', 'if (roommaidFastPath && !document.hidden)' in text and 'window.setTimeout(() => { void syncMobileDelta(); }, 80)' in text),
    ('roommaid role normalized', "const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase(); // ROOM_STATE_SYNC_HARDENING_V1" in text),
    ('due-out start guard preserved', 'ROOMMAID_DUE_OUT_START_GUARD_V2' in text),
    ('roommaid optimistic rollback preserved', 'restoreOptimisticRoommaidRoom_(roommaidRollback)' in text),
    ('indicator optimistic update preserved', "const fastAction = Boolean(optimisticPatch) && action !== 'QM_ASSIGN'" in text),
    ('indicator broadcast handler preserved', 'function novaRealtimeHandleBroadcast_' in text),
    ('QM acceleration preserved', 'QM_END_TO_END_ACCEL_V1' in text),
    ('QM houseman DB-first preserved', 'QM_HOUSEMAN_DBFIRST_V1' in text),
]

failed = []
for label, ok in checks:
    print(('PASS' if ok else 'FAIL') + ': ' + label)
    if not ok:
        failed.append(label)

# Negative checks are scoped to the function they are intended to protect.
negative = [
    ('startMobileSync is no longer HOUSEMAN-only', "if (novaRealtimeIsEnabled_() && role === 'HOUSEMAN' && state.activeMenu === 'houseman')" not in mobile_start_block),
    ('indicator no longer depends only on recent cursor', 'novaRealtime_.indicatorFullReconcileAt = 0' in text),
]
for label, ok in negative:
    print(('PASS' if ok else 'FAIL') + ': ' + label)
    if not ok:
        failed.append(label)

if failed:
    print('ROOM_STATE_SYNC_HARDENING_V1 validation FAILED: ' + ', '.join(failed), file=sys.stderr)
    raise SystemExit(98)

print(f'ROOM_STATE_SYNC_HARDENING_V1 validation PASS: {len(checks) + len(negative)}/{len(checks) + len(negative)}')
