from pathlib import Path
import re
import sys

SQL = Path('supabase/migrations/20260907_room_upload_db_first_v4.sql').read_text(encoding='utf-8')


def require(needle: str, label: str):
    if needle not in SQL:
        print(f'ERROR: missing {label}: {needle}', file=sys.stderr)
        raise SystemExit(91)


def forbid(needle: str, label: str):
    if needle in SQL:
        print(f'ERROR: forbidden {label}: {needle}', file=sys.stderr)
        raise SystemExit(92)


require('NOVA_ROOM_UPLOAD_DB_FIRST_V4', 'V4 migration marker')

# State V3 is intentionally bundled with V4 so one migration establishes the exact read/write contract.
require('create or replace function public.nova_room_upload_state_v3(', 'state V3 RPC')
require("'stateRpcVersion','V3'", 'state V3 response marker')
require("'expectedVersions',v_versions", 'per-room version snapshot')
require('jsonb_object_agg(r.room_no, to_jsonb(r.version))', 'per-room version aggregation')
for field in [
    "'마지막객실상태',r.last_room_status",
    "'이전객실상태',r.previous_room_status",
    "'이전청소상태',r.previous_cleaning_status",
    "'이전룸메이드사번',coalesce(r.previous_roommaid_employee_no,'')",
    "'이전보조룸메이드사번',coalesce(r.previous_secondary_roommaid_employee_no,'')",
    "'선배정여부',case when coalesce(r.preassigned,false) then 'Y' else 'N' end",
    "'VIP여부',case when coalesce(r.vip,false) then 'Y' else 'N' end",
    "'중요객실여부',case when coalesce(r.important_room,false) then 'Y' else 'N' end",
    "'마지막변경버전',r.version",
]:
    require(field, f'state V3 field {field}')
require('revoke all on function public.nova_room_upload_state_v3(text,text) from public;', 'state V3 PUBLIC revoke')
require('revoke all on function public.nova_room_upload_state_v3(text,text) from anon;', 'state V3 anon revoke')
require('grant execute on function public.nova_room_upload_state_v3(text,text) to authenticated;', 'state V3 authenticated grant')
require('grant execute on function public.nova_room_upload_state_v3(text,text) to service_role;', 'state V3 service_role grant')

# Apply V4 performs the atomic write using every room's exact preview-time DB version.
require('create or replace function public.nova_room_upload_apply_v4(', 'V4 RPC')
require('p_expected_versions jsonb', 'per-room expected-version map')
require("jsonb_typeof(coalesce(p_expected_versions,'{}'::jsonb)) <> 'object'", 'expected-version object validation')
require("not (p_expected_versions ? c.room_no)", 'new DB room / stale snapshot detection')
require("(p_expected_versions->>c.room_no)::bigint <> c.version", 'exact per-room version comparison')
require("e.value::bigint <> 0", 'new-room expectedVersion=0 guard')
require('pg_advisory_xact_lock', 'site/day transaction serialization')
require('for update;', 'row lock')
require("'ROOM_UPLOAD_APPLY_V4'", 'request dedup action')
require("'uploadRpcVersion','V4'", 'V4 response marker')

for field in [
    'room_status', 'last_room_status', 'previous_room_status', 'previous_cleaning_status',
    'cleaning_status', 'cleaning_type', 'assignment_type',
    'roommaid_employee_no', 'secondary_roommaid_employee_no',
    'previous_roommaid_employee_no', 'previous_secondary_roommaid_employee_no',
    'qm_employee_no', 'operational_status', 'preassigned', 'vip', 'important_room',
    'cleaning_started_at', 'cleaning_completed_at', 'version', 'updated_by', 'updated_at',
]:
    require(field, f'room-state field {field}')

require('delete from public.nova_rooms_current r', 'atomic delete of absent rooms')
require('insert into public.nova_room_upload_snapshots(', 'DB upload snapshot')
require('insert into public.nova_reporting_state(', 'reporting-state invalidation')
require('revoke all on function public.nova_room_upload_apply_v4(text,text,jsonb,jsonb,jsonb,bigint,text) from public;', 'V4 PUBLIC revoke')
require('revoke all on function public.nova_room_upload_apply_v4(text,text,jsonb,jsonb,jsonb,bigint,text) from anon;', 'V4 anon revoke')
require('grant execute on function public.nova_room_upload_apply_v4(text,text,jsonb,jsonb,jsonb,bigint,text) to authenticated;', 'V4 authenticated grant')
require('grant execute on function public.nova_room_upload_apply_v4(text,text,jsonb,jsonb,jsonb,bigint,text) to service_role;', 'V4 service_role grant')
require("upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER')", 'role guard')
require("message='사업장 권한이 없습니다.'", 'site guard')

forbid('nova_room_upload_apply_v2(', 'V2 delegation')
forbid('nova_room_upload_apply_v3(', 'V3 delegation')
forbid('p_expected_version bigint', 'single max-version precondition')

if SQL.count('create or replace function public.nova_room_upload_state_v3(') != 1:
    raise SystemExit('ERROR: state V3 definition must occur exactly once')
if SQL.count('create or replace function public.nova_room_upload_apply_v4(') != 1:
    raise SystemExit('ERROR: apply V4 definition must occur exactly once')
if SQL.count('$function$') != 4:
    raise SystemExit(f'ERROR: expected 4 function delimiters for two functions, got {SQL.count("$function$")}')
if not re.search(r'insert into public\.nova_rooms_current\([\s\S]*?on conflict\(business_date,site,room_no\) do update set', SQL):
    raise SystemExit('ERROR: complete rooms_current UPSERT block not found')

print('PASS: canonical room upload state V3 + apply V4 migration has full metadata, exact per-room optimistic concurrency, atomic scope locking, dedup and least-privilege grants.')
