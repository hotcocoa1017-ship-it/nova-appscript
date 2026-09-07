from pathlib import Path
import re
import sys

APPLY_SQL = Path('supabase/migrations/20260907_room_upload_db_first_v4.sql').read_text(encoding='utf-8')
STATE_SQL = Path('supabase/staged/room_upload_state_v3.sql').read_text(encoding='utf-8')


def require(text: str, needle: str, label: str):
    if needle not in text:
        print(f'ERROR: missing {label}: {needle}', file=sys.stderr)
        raise SystemExit(91)


def forbid(text: str, needle: str, label: str):
    if needle in text:
        print(f'ERROR: forbidden {label}: {needle}', file=sys.stderr)
        raise SystemExit(92)


# Read authority: exact DB snapshot used by the existing upload business rules.
require(STATE_SQL, 'ROOM_UPLOAD_STATE_DB_AUTHORITY_V3', 'state V3 marker')
require(STATE_SQL, 'create or replace function public.nova_room_upload_state_v3(', 'state V3 RPC')
require(STATE_SQL, "'stateRpcVersion', 'V3'", 'state V3 response marker')
require(STATE_SQL, "'expectedVersions', v_expected_versions", 'per-room version snapshot')
require(STATE_SQL, "jsonb_object_agg(r.room_no, r.version)", 'per-room version aggregation')
for field in [
    "'마지막객실상태', coalesce(r.last_room_status,'')",
    "'이전객실상태', coalesce(r.previous_room_status,'')",
    "'이전청소상태', coalesce(r.previous_cleaning_status,'')",
    "'이전룸메이드사번', coalesce(r.previous_roommaid_employee_no,'')",
    "'이전보조룸메이드사번', coalesce(r.previous_secondary_roommaid_employee_no,'')",
    "'선배정여부', case when coalesce(r.preassigned,false) then 'Y' else 'N' end",
    "'VIP여부', case when coalesce(r.vip,false) then 'Y' else 'N' end",
    "'중요객실여부', case when coalesce(r.important_room,false) then 'Y' else 'N' end",
    "'마지막변경버전', r.version",
]:
    require(STATE_SQL, field, f'state V3 field {field}')
require(STATE_SQL, "security definer\nset search_path = ''", 'state V3 pinned empty search_path')
require(STATE_SQL, 'revoke all on function public.nova_room_upload_state_v3(text,text) from public;', 'state V3 PUBLIC revoke')
require(STATE_SQL, 'revoke all on function public.nova_room_upload_state_v3(text,text) from anon;', 'state V3 anon revoke')
require(STATE_SQL, 'grant execute on function public.nova_room_upload_state_v3(text,text) to authenticated;', 'state V3 authenticated grant')
require(STATE_SQL, 'grant execute on function public.nova_room_upload_state_v3(text,text) to service_role;', 'state V3 service_role grant')

# Apply V4: atomic write using every room's preview-time version.
require(APPLY_SQL, 'NOVA_ROOM_UPLOAD_DB_FIRST_V4', 'V4 marker')
require(APPLY_SQL, 'create or replace function public.nova_room_upload_apply_v4(', 'V4 RPC')
require(APPLY_SQL, 'p_expected_versions jsonb', 'per-room expected-version map')
require(APPLY_SQL, "jsonb_typeof(coalesce(p_expected_versions,'{}'::jsonb)) <> 'object'", 'expected-version object validation')
require(APPLY_SQL, "not (p_expected_versions ? c.room_no)", 'new DB room / stale snapshot detection')
require(APPLY_SQL, "(p_expected_versions->>c.room_no)::bigint <> c.version", 'exact per-room version comparison')
require(APPLY_SQL, "e.value::bigint <> 0", 'new-room expectedVersion=0 guard')
require(APPLY_SQL, 'pg_advisory_xact_lock', 'site/day transaction serialization')
require(APPLY_SQL, 'for update;', 'row lock')
require(APPLY_SQL, "'ROOM_UPLOAD_APPLY_V4'", 'request dedup action')
require(APPLY_SQL, "'uploadRpcVersion','V4'", 'V4 response marker')

for field in [
    'room_status', 'last_room_status', 'previous_room_status', 'previous_cleaning_status',
    'cleaning_status', 'cleaning_type', 'assignment_type',
    'roommaid_employee_no', 'secondary_roommaid_employee_no',
    'previous_roommaid_employee_no', 'previous_secondary_roommaid_employee_no',
    'qm_employee_no', 'operational_status', 'preassigned', 'vip', 'important_room',
    'cleaning_started_at', 'cleaning_completed_at', 'version', 'updated_by', 'updated_at',
]:
    require(APPLY_SQL, field, f'room-state field {field}')

require(APPLY_SQL, 'delete from public.nova_rooms_current r', 'atomic delete of absent rooms')
require(APPLY_SQL, 'insert into public.nova_room_upload_snapshots(', 'DB upload snapshot')
require(APPLY_SQL, 'insert into public.nova_reporting_state(', 'reporting-state invalidation')
require(APPLY_SQL, 'revoke all on function public.nova_room_upload_apply_v4(text,text,jsonb,jsonb,jsonb,bigint,text) from public;', 'V4 PUBLIC revoke')
require(APPLY_SQL, 'revoke all on function public.nova_room_upload_apply_v4(text,text,jsonb,jsonb,jsonb,bigint,text) from anon;', 'V4 anon revoke')
require(APPLY_SQL, 'grant execute on function public.nova_room_upload_apply_v4(text,text,jsonb,jsonb,jsonb,bigint,text) to authenticated;', 'V4 authenticated grant')
require(APPLY_SQL, 'grant execute on function public.nova_room_upload_apply_v4(text,text,jsonb,jsonb,jsonb,bigint,text) to service_role;', 'V4 service_role grant')
require(APPLY_SQL, "upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER')", 'role guard')
require(APPLY_SQL, "message='사업장 권한이 없습니다.'", 'site guard')

forbid(APPLY_SQL, 'nova_room_upload_apply_v2(', 'V2 delegation')
forbid(APPLY_SQL, 'nova_room_upload_apply_v3(', 'V3 delegation')
forbid(APPLY_SQL, 'p_expected_version bigint', 'single max-version precondition')

if STATE_SQL.count('create or replace function public.nova_room_upload_state_v3(') != 1:
    raise SystemExit('ERROR: state V3 function definition must occur exactly once')
if APPLY_SQL.count('create or replace function public.nova_room_upload_apply_v4(') != 1:
    raise SystemExit('ERROR: V4 function definition must occur exactly once')
if STATE_SQL.count('$function$') != 2 or APPLY_SQL.count('$function$') != 2:
    raise SystemExit('ERROR: SQL function body delimiters are incomplete')
if not re.search(r'insert into public\.nova_rooms_current\([\s\S]*?on conflict\(business_date,site,room_no\) do update set', APPLY_SQL):
    raise SystemExit('ERROR: complete rooms_current UPSERT block not found')

print('PASS: room upload state V3 + DB-first V4 are separately staged with full metadata, per-room optimistic concurrency, atomic locking, dedup and least-privilege grants.')
