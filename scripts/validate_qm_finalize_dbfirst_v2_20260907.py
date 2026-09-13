from pathlib import Path
import re
import subprocess
import tempfile

SQL = Path('supabase/migrations/20260907_qm_inspection_finalize_db_first_v2.sql').read_text(encoding='utf-8')
CLIENT = Path('Client.html').read_text(encoding='utf-8')


def require(text: str, needle: str, label: str):
    if needle not in text:
        raise SystemExit(f'ERROR: missing {label}: {needle}')


def forbid(text: str, needle: str, label: str):
    if needle in text:
        raise SystemExit(f'ERROR: forbidden {label}: {needle}')


def require_order(text: str, first: str, second: str, label: str):
    a = text.find(first)
    b = text.find(second)
    if a < 0 or b < 0 or a >= b:
        raise SystemExit(f'ERROR: invalid order for {label}')


def require_regex(text: str, pattern: str, label: str):
    if not re.search(pattern, text, flags=re.S):
        raise SystemExit(f'ERROR: missing {label}: {pattern}')


# SQL: one atomic DB transaction owns room terminal state + inspection + draft + event.
require(SQL, 'NOVA_QM_INSPECTION_FINALIZE_DB_FIRST_V2', 'SQL marker')
require(SQL, 'create or replace function public.nova_qm_inspection_finalize_v2(', 'V2 RPC')
require(SQL, 'security definer', 'security definer')
require(SQL, "set search_path = ''", 'empty search path')
require(SQL, "upper(coalesce(v_user.role,''))<>'QM'", 'QM role guard')
require(SQL, 'public.nova_is_active_qm_for_site(v_actor,v_site)', 'site authorization')
require(SQL, "'QM_INSPECTION_FINALIZE_V2'", 'request dedup action')
require(SQL, 'pg_advisory_xact_lock', 'transaction advisory lock')
require_regex(SQL, r'from public\.nova_rooms_current r.*?for update;', 'room row lock')
require(SQL, "if v_before_status<>'QM_CHECKING'", 'QM_CHECKING terminal precondition')
require(SQL, 'v_room.version<>v_expected_version', 'exact room version check')
require(SQL, 'insert into public.nova_qm_inspections(', 'inspection DB write')
require(SQL, 'update public.nova_qm_drafts', 'draft completion write')
require_regex(SQL, r"update public\.nova_rooms_current\s+set cleaning_status='QM_COMPLETED'.*?version=version\+1", 'atomic room terminal update')
require(SQL, "'QM_COMPLETE',v_before_status,'QM_COMPLETED'", 'Realtime room event')
require(SQL, "'source','QM_INSPECTION_FINALIZE_DB_FIRST_V2'", 'event source marker')
require(SQL, "'finalizeRpcVersion','V2'", 'response V2 marker')
require(SQL, "'preassigned',coalesce(v_room.preassigned,false)", 'preassigned preservation')
require(SQL, "'vip',coalesce(v_room.vip,false)", 'VIP preservation')
require(SQL, "'importantRoom',coalesce(v_room.important_room,false)", 'important-room preservation')
require(SQL, 'revoke all on function public.nova_qm_inspection_finalize_v2(jsonb,text) from public;', 'PUBLIC revoke')
require(SQL, 'revoke all on function public.nova_qm_inspection_finalize_v2(jsonb,text) from anon;', 'anon revoke')
require(SQL, 'grant execute on function public.nova_qm_inspection_finalize_v2(jsonb,text) to authenticated;', 'authenticated grant')
require(SQL, 'grant execute on function public.nova_qm_inspection_finalize_v2(jsonb,text) to service_role;', 'service role grant')
forbid(SQL, 'nova_qm_inspection_finalize_v1(', 'V1 delegation')

# Client: stable request id -> preflight-normalized direct V2 -> only explicit pre-mutation fallback -> post-commit Sheet detail mirror.
require(CLIENT, 'QM_FINALIZE_DB_FIRST_V2', 'client marker')
require(CLIENT, 'function novaQmFinalizeStableRequestId_(active)', 'stable request helper')
require(CLIENT, 'sessionStorage.getItem(key)', 'request-id retry persistence')
require(CLIENT, "novaRealtimeRequestId_('QM_FINALIZE_V2'", 'V2 request id')
require(CLIENT, 'async function novaQmFinalizeDbFirstV2_', 'direct finalize helper')
require(CLIENT, '/rest/v1/rpc/nova_qm_inspection_finalize_v2', 'direct V2 endpoint')
require(CLIENT, 'body: JSON.stringify(body)', 'same request body reuse')
require(CLIENT, "error.code = 'QM_FINALIZE_DB_RESULT_UNKNOWN'", 'ambiguous result fail closed')
require(CLIENT, "return { ok: false, legacyFallback: true, reason: 'RPC_MISSING' }", 'missing RPC fallback')
require(CLIENT, "return { ok: false, legacyFallback: true, reason: 'AUTH_PREP_FAILED' }", 'pre-mutation auth fallback')
require(CLIENT, 'const finalizeStable = novaQmFinalizeStableRequestId_(active);', 'final handler stable request')
require(CLIENT, 'let realtime = await novaQmFinalizeDbFirstV2_(active, finalizePreflight, requestId);', 'V2 primary final commit')
require(CLIENT, 'if (realtime?.legacyFallback === true) {', 'explicit legacy fallback guard')
require(CLIENT, "realtime = await saveRoomActionRealtimeOrLegacy_('updateMobileRoomOperation'", 'legacy QM_COMPLETE fallback preserved')
require(CLIENT, 'applyQmRealtimeRoomLocal_(active.roomNo, realtime.room);', 'local DB room application')
require(CLIENT, 'realtimeCommitted: true', 'Sheet detail knows DB committed')
require(CLIENT, 'realtimeRequestId: requestId', 'Sheet detail request linkage')
require(CLIENT, 'realtimeVersion: Number(realtime.version || 0)', 'Sheet detail DB room version')
require(CLIENT, 'submitQmInspectionDetailWithBusyRetry_', 'existing Sheet history retry preserved')
require(CLIENT, "callServer('submitQmChecklistInspection'", 'legacy Sheet detail writer preserved')
require(CLIENT, 'try { sessionStorage.removeItem(finalizeStable.key); } catch (ignore) {}', 'stable id cleanup after safe completion')

require_order(CLIENT, 'let realtime = await novaQmFinalizeDbFirstV2_', 'applyQmRealtimeRoomLocal_(active.roomNo, realtime.room);', 'DB finalize before local completion')
require_order(CLIENT, 'applyQmRealtimeRoomLocal_(active.roomNo, realtime.room);', 'const persistDetail = async () => {', 'DB/local completion before Sheet detail mirror')
require_regex(
    CLIENT,
    r"let realtime = await novaQmFinalizeDbFirstV2_\(active, finalizePreflight, requestId\);\s*if \(realtime\?\.legacyFallback === true\) \{\s*realtime = await saveRoomActionRealtimeOrLegacy_",
    'generic QM_COMPLETE is reachable only through explicit legacyFallback'
)

# Existing no-Realtime legacy submission is unchanged.
require_regex(
    CLIENT,
    r"if \(!novaRealtimeIsEnabled_\(\)\) \{.*?ensureQmInspectionDraftReady_\(active\).*?callServer\('submitQmChecklistInspection'",
    'Realtime-disabled legacy path preserved'
)

# Generated Client JS syntax must be valid before any deployment gate can open.
scripts = re.findall(r'<script[^>]*>(.*?)</script>', CLIENT, flags=re.S | re.I)
if not scripts:
    raise SystemExit('ERROR: Client.html has no script blocks')
with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8', delete=False) as handle:
    handle.write('\n'.join(scripts))
    temp_js = handle.name
subprocess.run(['node', '--check', temp_js], check=True)

print('PASS: QM final submission V2 is staged as atomic DB-first, exact-version/idempotent, fail-closed after mutation may begin, preflight-compatible, legacy-compatible, and JavaScript syntax-safe.')
