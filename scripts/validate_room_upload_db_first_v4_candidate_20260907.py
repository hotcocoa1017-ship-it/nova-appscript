from pathlib import Path
import re

sql = Path('db/room_upload_db_first_v4_candidate_20260907.sql').read_text(encoding='utf-8')


def require(needle: str, label: str):
    if needle not in sql:
        raise SystemExit(f'ERROR: missing {label}: {needle}')
    print(f'[OK] {label}')


def forbid(needle: str, label: str):
    if needle in sql:
        raise SystemExit(f'ERROR: forbidden {label}: {needle}')
    print(f'[OK] {label}')


def require_regex(pattern: str, label: str):
    if not re.search(pattern, sql, flags=re.S | re.I):
        raise SystemExit(f'ERROR: missing {label}: {pattern}')
    print(f'[OK] {label}')


require('ROOM_UPLOAD_DB_FIRST_V4', 'candidate marker')
require('create or replace function public.nova_room_upload_state_v3(', 'state v3 RPC')
require('create or replace function public.nova_room_upload_apply_v4(', 'apply v4 RPC')
require('security definer', 'SECURITY DEFINER')
require('set search_path = public, pg_catalog', 'fixed search_path')
require("upper(coalesce(v_user.role, '')) not in ('ADMIN', 'ORDER')", 'ADMIN/ORDER authorization')
require("or v_site = any(coalesce(v_user.allowed_sites, array[]::text[]))", 'site scope authorization')

# State v3 must expose the exact metadata needed to calculate the legacy upload result from DB state.
for needle, label in [
    ("'마지막객실상태', r.last_room_status", 'last room status'),
    ("'이전객실상태', r.previous_room_status", 'previous room status'),
    ("'이전청소상태', r.previous_cleaning_status", 'previous cleaning status'),
    ("'이전룸메이드사번', coalesce(r.previous_roommaid_employee_no, '')", 'previous primary roommaid'),
    ("'이전보조룸메이드사번', coalesce(r.previous_secondary_roommaid_employee_no, '')", 'previous secondary roommaid'),
    ("'선배정여부'", 'preassigned state'),
    ("'VIP여부'", 'VIP state'),
    ("'중요객실여부'", 'important-room state'),
    ("'마지막변경버전', r.version", 'per-room version state'),
]:
    require(needle, f'state v3 exposes {label}')

# Per-room optimistic concurrency is mandatory; site max(version) alone is not accepted.
require("v_room->>'expectedVersion'", 'per-room expectedVersion input')
require("count(distinct trim(coalesce(value->>'roomNo', '')))", 'duplicate room detection')
require("pg_advisory_xact_lock(hashtextextended('NOVA_ROOM_UPLOAD|'", 'site upload transaction lock')
require_regex(r"from\s+public\.nova_rooms_current\s+r\s+where\s+r\.business_date\s*=\s*v_date\s+and\s+r\.site\s*=\s*v_site\s+order by\s+r\.room_no\s+for update", 'full current room set row lock')
require('if v_current_count <> v_input_count then', 'exact room-set count validation')
require('where r.room_no is null', 'missing-room validation')
require('and r.version <> e.expected_version', 'every room version comparison')
require("errcode = '40001'", 'serialization-style conflict code')
require('greatest(coalesce(p_version, 0), v_current_version + 1)', 'monotonic committed version')

# The v4 write must carry every DB-owned room field used by current NOVA behavior.
for needle, label in [
    ('last_room_status = excluded.last_room_status', 'last room status write'),
    ('previous_room_status = excluded.previous_room_status', 'previous room status write'),
    ('previous_cleaning_status = excluded.previous_cleaning_status', 'previous cleaning status write'),
    ('previous_roommaid_employee_no = excluded.previous_roommaid_employee_no', 'previous primary roommaid write'),
    ('previous_secondary_roommaid_employee_no = excluded.previous_secondary_roommaid_employee_no', 'previous secondary roommaid write'),
    ('preassigned = excluded.preassigned', 'preassigned write'),
    ('vip = excluded.vip', 'VIP write'),
    ('important_room = excluded.important_room', 'important-room write'),
    ("cleaning_started_at = case when v_reset then null else public.nova_rooms_current.cleaning_started_at end", 'cleaning start preservation'),
    ("cleaning_completed_at = case when v_reset then null else public.nova_rooms_current.cleaning_completed_at end", 'cleaning completion preservation'),
]:
    require(needle, label)

require("values(v_request_id, v_actor, 'ROOM_UPLOAD_APPLY_V4', null)", 'request dedup namespace')
require("'uploadRpcVersion', 'V4'", 'V4 response marker')
require("'perRoomConcurrency', true", 'per-room concurrency response marker')
require('revoke all on function public.nova_room_upload_apply_v4', 'apply v4 revoke')
require('from public, anon;', 'PUBLIC/anon revoke')
require('grant execute on function public.nova_room_upload_apply_v4', 'apply v4 authenticated grant')
require('to authenticated, service_role;', 'authenticated/service role only grant')

# V4 must not delegate to the unsafe max-version-only legacy writers.
forbid('nova_room_upload_apply_v2(', 'no v2 delegation')
forbid('nova_room_upload_apply_v3(', 'no v3 delegation')
forbid('p_expected_version', 'no site-wide expected-version parameter')

print('ROOM_UPLOAD_DB_FIRST_V4 candidate static validation PASS')
