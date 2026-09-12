from pathlib import Path
import re
import subprocess
import tempfile

SQL = Path('supabase/migrations/20260907_qm_inspection_finalize_db_first_v2.sql').read_text(encoding='utf-8')
AUTH_SQL = Path('supabase/migrations/20260913_qm_finalize_context_authority_v2.sql').read_text(encoding='utf-8')
RESUME_SQL = Path('supabase/migrations/20260913_qm_resume_context_db_authority_v1.sql').read_text(encoding='utf-8')
EDGE = Path('supabase/functions/nova-qm-db-resilient-v1/index.ts').read_text(encoding='utf-8')
HOTFIX = Path('QmFinalizePreflightFastHotfix.js').read_text(encoding='utf-8')
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

# Regression guard: DB draft context is authoritative before finalize validation.
require(AUTH_SQL, 'QM_FINALIZE_CONTEXT_AUTHORITY_V2', 'context authority migration marker')
require(AUTH_SQL, 'create or replace function public.nova_qm_finalize_resolve_context_v1(', 'authoritative context resolver')
require(AUTH_SQL, "d.draft_id = v_draft_id", 'draft-id recovery')
require(AUTH_SQL, "d.site = v_site", 'site+room recovery')
require(AUTH_SQL, "d.room_no = v_room_no", 'room recovery')
require(AUTH_SQL, 'if v_match_count = 1 then', 'unique room-only recovery')
require(AUTH_SQL, 'elsif v_match_count > 1 then', 'ambiguous room-only fail closed')
require(AUTH_SQL, "'{businessDate}'", 'authoritative businessDate overwrite')
require(AUTH_SQL, "'{site}'", 'authoritative site overwrite')
require(AUTH_SQL, "'{roomNo}'", 'authoritative room overwrite')
require(AUTH_SQL, "'{draftId}'", 'authoritative draft overwrite')
require(AUTH_SQL, "v_existing.response_json is not null", 'idempotent retry before context parsing')
require_order(AUTH_SQL, 'v_existing.response_json is not null', 'v_payload := public.nova_qm_finalize_resolve_context_v1(p_payload);', 'idempotency before context resolution')
require(AUTH_SQL, 'return public.nova_qm_inspection_finalize_v2_core_20260912(v_payload, p_request_id);', 'canonical atomic core delegation')

# A read-only resolver must cover Client sessions that enter the no-Realtime legacy branch.
require(RESUME_SQL, 'QM_RESUME_CONTEXT_DB_AUTHORITY_V1', 'resume-context DB marker')
require(RESUME_SQL, 'create or replace function public.nova_qm_resume_context_v1(', 'resume-context RPC')
require(RESUME_SQL, "d.status = 'IN_PROGRESS'", 'active draft scope')
require(RESUME_SQL, 'if v_count > 1 then', 'resume ambiguity fail closed')
require(RESUME_SQL, "'businessDate', v_draft.business_date::text", 'resume businessDate authority')
require(RESUME_SQL, "'draftId', v_draft.draft_id", 'resume draft authority')
require(RESUME_SQL, 'grant execute on function public.nova_qm_resume_context_v1(text,text) to authenticated;', 'resume authenticated grant')

# Edge remains transport-only and exposes the read-only resume resolver.
require(EDGE, 'QM_RESUME_CONTEXT_EDGE_V8', 'Edge V8 marker')
require(EDGE, 'X-NOVA-QM-Transport": "direct-db-edge-v8', 'Edge V8 transport marker')
require(EDGE, '"nova_qm_resume_context_v1"', 'Edge resume RPC allowlist')
require_regex(
    EDGE,
    r'if \(rpc === "nova_qm_resume_context_v1"\) \{\s*const rows = await tx`select public\.nova_qm_resume_context_v1',
    'Edge delegates resume context to DB'
)
require_regex(
    EDGE,
    r'if \(rpc === "nova_qm_inspection_finalize_v2"\) \{\s*const payload = jsonObject\(args\.p_payload, "QM finalize payload"\);\s*const rows = await tx`select public\.nova_qm_inspection_finalize_v2',
    'Edge delegates finalize context resolution to DB'
)
forbid(EDGE, 'payload.businessDate = draftBusinessDate', 'duplicate Edge finalize date authority')

# Apps Script must recover DB context before server preflight/legacy finalize and keep Sheet fallback only as compatibility.
require(HOTFIX, 'QM_RESUME_CONTEXT_DB_AUTHORITY_V1', 'Apps Script resume-context marker')
require(HOTFIX, "rpc: 'nova_qm_resume_context_v1'", 'Apps Script direct resume RPC')
require(HOTFIX, 'function novaFinalizeResumedQmDbFirst_', 'server legacy DB-finalize helper')
require(HOTFIX, "rpc: 'nova_qm_inspection_finalize_v2'", 'server legacy finalize RPC')
require(HOTFIX, 'QM_LEGACY_BRANCH_DB_FINALIZE_V1', 'legacy branch DB-finalize marker')
require(HOTFIX, 'const needsDbResumeContext = !String(safe.businessDate', 'legacy missing-context detector')
require(HOTFIX, 'dbResult = novaFinalizeResumedQmDbFirst_', 'legacy DB finalize invocation')
require(HOTFIX, 'safe.realtimeCommitted === true', 'post-DB Sheet mirror compatibility')
require(HOTFIX, 'novaResolveResumedQmBusinessDate_', 'Sheet compatibility fallback preserved')
require_order(HOTFIX, 'dbContext = novaResolveResumedQmDbContext_', 'dbResult = novaFinalizeResumedQmDbFirst_', 'DB context before legacy DB finalize')

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

# Existing Client no-Realtime branch stays intact; server now upgrades malformed resumed context to DB finalize.
require_regex(
    CLIENT,
    r"if \(!novaRealtimeIsEnabled_\(\)\) \{.*?ensureQmInspectionDraftReady_\(active\).*?callServer\('submitQmChecklistInspection'",
    'Realtime-disabled legacy Client branch preserved'
)

# Generated Client JS syntax must be valid before any deployment gate can open.
scripts = re.findall(r'<script[^>]*>(.*?)</script>', CLIENT, flags=re.S | re.I)
if not scripts:
    raise SystemExit('ERROR: Client.html has no script blocks')
with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8', delete=False) as handle:
    handle.write('\n'.join(scripts))
    temp_js = handle.name
subprocess.run(['node', '--check', temp_js], check=True)

print('PASS: QM finalize V2 preserves atomic semantics and covers resumed sessions on both Realtime and no-Realtime paths with DB-authoritative context + idempotent finalization.')
