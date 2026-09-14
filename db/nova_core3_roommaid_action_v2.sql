-- NOVA Core 3.0 Phase 1
-- Server-grade ROOMMAID action transaction V2
--
-- Goals:
--   * PostgreSQL is the authoritative commit point.
--   * Stable request IDs are immutable and exactly-once at business level.
--   * Same-intent retries converge to success even when the caller's version is stale.
--   * Only the target room row is locked; unrelated rooms are never serialized.
--   * Event + outbox + response are committed in the same transaction.
--   * Google Sheet / Telegram are not part of this transaction.

create schema if not exists nova_private;
revoke all on schema nova_private from public, anon;
grant usage on schema nova_private to authenticated, service_role;

create table if not exists nova_private.core_idempotency (
  request_id text primary key,
  employee_no text not null,
  operation text not null,
  request_fingerprint text not null,
  response_json jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

alter table nova_private.core_idempotency enable row level security;
revoke all on nova_private.core_idempotency from public, anon, authenticated;

create table if not exists nova_private.core_outbox (
  id bigint generated always as identity primary key,
  event_type text not null,
  aggregate_type text not null,
  aggregate_key text not null,
  payload jsonb not null default '{}'::jsonb,
  available_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  processed_at timestamptz,
  attempts integer not null default 0,
  last_error text
);

alter table nova_private.core_outbox enable row level security;
revoke all on nova_private.core_outbox from public, anon, authenticated;

create index if not exists core_outbox_pending_idx
  on nova_private.core_outbox (available_at, id)
  where processed_at is null;

create or replace function nova_private.roommaid_action_v2_internal(
  p_business_date date,
  p_site text,
  p_room_no text,
  p_action text,
  p_expected_version bigint,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_employee_no text := trim(coalesce(v_claims->>'employee_no', ''));
  v_action text := upper(trim(coalesce(p_action, '')));
  v_site text := trim(coalesce(p_site, ''));
  v_room_no text := trim(coalesce(p_room_no, ''));
  v_request_id text := trim(coalesce(p_request_id, ''));
  v_expected_version bigint := greatest(coalesce(p_expected_version, 0), 0);
  v_fingerprint text;
  v_user public.nova_users%rowtype;
  v_room public.nova_rooms_current%rowtype;
  v_before text;
  v_after text;
  v_response jsonb;
  v_existing nova_private.core_idempotency%rowtype;
  v_claimed integer := 0;
  v_event_id uuid;
begin
  if v_employee_no = '' then
    raise exception using errcode = '42501', message = '로그인이 필요합니다.';
  end if;
  if p_business_date is null or v_site = '' or v_room_no = '' then
    raise exception using errcode = '22023', message = '업무일자·사업장·객실번호를 확인하세요.';
  end if;
  if v_action not in ('CLEANING_START', 'CLEANING_COMPLETE') then
    raise exception using errcode = '22023', message = '지원하지 않는 룸메이드 상태변경입니다.';
  end if;
  if length(v_request_id) < 8 or length(v_request_id) > 160 then
    raise exception using errcode = '22023', message = '유효한 requestId가 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_employee_no
    and enabled = true
    and upper(coalesce(role, '')) = 'ROOMMAID';
  if not found then
    raise exception using errcode = '42501', message = '룸메이드 사용자 정보를 확인할 수 없습니다.';
  end if;

  if cardinality(coalesce(v_user.allowed_sites, array[]::text[])) > 0
     and not (v_site = any(v_user.allowed_sites)) then
    raise exception using errcode = '42501', message = '허용되지 않은 사업장입니다.';
  end if;

  v_fingerprint := concat_ws('|',
    p_business_date::text,
    v_site,
    v_room_no,
    v_action,
    v_expected_version::text
  );

  insert into nova_private.core_idempotency(
    request_id, employee_no, operation, request_fingerprint
  ) values (
    v_request_id, v_employee_no, 'ROOMMAID_ACTION_V2', v_fingerprint
  )
  on conflict (request_id) do nothing;
  get diagnostics v_claimed = row_count;

  if v_claimed = 0 then
    select * into v_existing
    from nova_private.core_idempotency
    where request_id = v_request_id;

    if not found
       or v_existing.employee_no <> v_employee_no
       or v_existing.operation <> 'ROOMMAID_ACTION_V2'
       or v_existing.request_fingerprint <> v_fingerprint then
      raise exception using errcode = '23505', message = '이미 다른 요청에 사용된 requestId입니다.';
    end if;

    if v_existing.response_json is null then
      raise exception using errcode = '40001', message = '동일 요청이 처리 중입니다. 같은 requestId로 다시 확인하세요.';
    end if;

    return v_existing.response_json || jsonb_build_object(
      'duplicate', true,
      'idempotent', true
    );
  end if;

  -- Lock exactly one authoritative room row. Different rooms remain fully concurrent.
  select * into v_room
  from public.nova_rooms_current
  where business_date = p_business_date
    and site = v_site
    and room_no = v_room_no
  for update;
  if not found then
    raise exception using errcode = 'P0002', message = '객실을 찾을 수 없습니다.';
  end if;

  if v_employee_no <> trim(coalesce(v_room.roommaid_employee_no, ''))
     and v_employee_no <> trim(coalesce(v_room.secondary_roommaid_employee_no, '')) then
    raise exception using errcode = '42501', message = '본인에게 배정된 객실만 처리할 수 있습니다.';
  end if;

  v_before := upper(coalesce(v_room.cleaning_status, ''));

  -- Semantic convergence is checked before version conflict. If another valid
  -- request already achieved the same intent, the user sees success rather than
  -- the legacy "다른 사용자에 의해 변경" failure.
  if v_action = 'CLEANING_START' and v_before = 'CLEANING' then
    v_response := jsonb_build_object(
      'ok', true,
      'requestId', v_request_id,
      'action', v_action,
      'idempotent', false,
      'duplicate', false,
      'alreadyApplied', true,
      'changed', false,
      'businessDate', v_room.business_date::text,
      'site', v_room.site,
      'roomNo', v_room.room_no,
      'beforeStatus', v_before,
      'afterStatus', v_before,
      'version', v_room.version,
      'room', jsonb_build_object(
        'businessDate', v_room.business_date::text,
        'site', v_room.site,
        'roomNo', v_room.room_no,
        'building', coalesce(v_room.building,''),
        'roomStatus', v_room.room_status,
        'cleaningStatus', v_room.cleaning_status,
        'cleaningType', v_room.cleaning_type,
        'assignmentType', v_room.assignment_type,
        'roommaidEmployeeNo', coalesce(v_room.roommaid_employee_no,''),
        'secondaryRoommaidEmployeeNo', coalesce(v_room.secondary_roommaid_employee_no,''),
        'qmEmployeeNo', coalesce(v_room.qm_employee_no,''),
        'operationalStatus', coalesce(v_room.operational_status,''),
        'version', v_room.version,
        'cleaningStartedAt', v_room.cleaning_started_at,
        'cleaningCompletedAt', v_room.cleaning_completed_at,
        'updatedAt', v_room.updated_at
      )
    );

    update nova_private.core_idempotency
    set response_json = v_response, completed_at = now()
    where request_id = v_request_id;
    return v_response;
  end if;

  if v_action = 'CLEANING_COMPLETE'
     and v_before in ('COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED') then
    v_response := jsonb_build_object(
      'ok', true,
      'requestId', v_request_id,
      'action', v_action,
      'idempotent', false,
      'duplicate', false,
      'alreadyApplied', true,
      'changed', false,
      'businessDate', v_room.business_date::text,
      'site', v_room.site,
      'roomNo', v_room.room_no,
      'beforeStatus', v_before,
      'afterStatus', v_before,
      'version', v_room.version,
      'room', jsonb_build_object(
        'businessDate', v_room.business_date::text,
        'site', v_room.site,
        'roomNo', v_room.room_no,
        'building', coalesce(v_room.building,''),
        'roomStatus', v_room.room_status,
        'cleaningStatus', v_room.cleaning_status,
        'cleaningType', v_room.cleaning_type,
        'assignmentType', v_room.assignment_type,
        'roommaidEmployeeNo', coalesce(v_room.roommaid_employee_no,''),
        'secondaryRoommaidEmployeeNo', coalesce(v_room.secondary_roommaid_employee_no,''),
        'qmEmployeeNo', coalesce(v_room.qm_employee_no,''),
        'operationalStatus', coalesce(v_room.operational_status,''),
        'version', v_room.version,
        'cleaningStartedAt', v_room.cleaning_started_at,
        'cleaningCompletedAt', v_room.cleaning_completed_at,
        'updatedAt', v_room.updated_at
      )
    );

    update nova_private.core_idempotency
    set response_json = v_response, completed_at = now()
    where request_id = v_request_id;
    return v_response;
  end if;

  if v_expected_version > 0 and v_room.version <> v_expected_version then
    raise exception using errcode = '40001', message = '객실 최신 상태가 요청과 다릅니다. 서버 상태로 다시 동기화하세요.';
  end if;

  if v_action = 'CLEANING_START' then
    if upper(coalesce(v_room.room_status, '')) = 'DUE_OUT' then
      raise exception using errcode = '55000', message = '퇴실 전 객실은 청소를 시작할 수 없습니다.';
    end if;
    if v_before not in ('ASSIGNED', 'WAITING', 'REWORK') then
      raise exception using errcode = '55000', message = '현재 상태에서는 청소를 시작할 수 없습니다.';
    end if;
    v_after := 'CLEANING';
  else
    if v_before <> 'CLEANING' then
      raise exception using errcode = '55000', message = '청소중인 객실만 청소완료할 수 있습니다.';
    end if;
    v_after := case
      when nullif(trim(coalesce(v_room.qm_employee_no, '')), '') is not null then 'QM_WAITING'
      else 'COMPLETED'
    end;
  end if;

  update public.nova_rooms_current
  set cleaning_status = v_after,
      version = version + 1,
      cleaning_started_at = case
        when v_action = 'CLEANING_START' then now()
        else cleaning_started_at
      end,
      cleaning_completed_at = case
        when v_action = 'CLEANING_COMPLETE' then now()
        else null
      end,
      updated_by = v_employee_no,
      updated_at = now()
  where id = v_room.id
  returning * into v_room;

  insert into public.nova_room_events(
    request_id, business_date, site, room_no, action,
    before_status, after_status, employee_no, room_version, detail, event_time
  ) values (
    v_request_id, p_business_date, v_site, v_room_no, v_action,
    v_before, v_after, v_employee_no, v_room.version,
    jsonb_build_object(
      'core3', true,
      'apiVersion', 2,
      'role', 'ROOMMAID',
      'expectedVersion', v_expected_version
    ),
    now()
  ) returning event_id into v_event_id;

  insert into nova_private.core_outbox(
    event_type, aggregate_type, aggregate_key, payload
  ) values (
    'ROOM_STATE_CHANGED',
    'ROOM',
    concat_ws('|', p_business_date::text, v_site, v_room_no),
    jsonb_build_object(
      'eventId', v_event_id,
      'requestId', v_request_id,
      'businessDate', p_business_date::text,
      'site', v_site,
      'roomNo', v_room_no,
      'action', v_action,
      'beforeStatus', v_before,
      'afterStatus', v_after,
      'version', v_room.version,
      'employeeNo', v_employee_no
    )
  );

  v_response := jsonb_build_object(
    'ok', true,
    'requestId', v_request_id,
    'action', v_action,
    'idempotent', false,
    'duplicate', false,
    'alreadyApplied', false,
    'changed', true,
    'businessDate', v_room.business_date::text,
    'site', v_room.site,
    'roomNo', v_room.room_no,
    'beforeStatus', v_before,
    'afterStatus', v_after,
    'version', v_room.version,
    'room', jsonb_build_object(
      'businessDate', v_room.business_date::text,
      'site', v_room.site,
      'roomNo', v_room.room_no,
      'building', coalesce(v_room.building,''),
      'roomStatus', v_room.room_status,
      'cleaningStatus', v_room.cleaning_status,
      'cleaningType', v_room.cleaning_type,
      'assignmentType', v_room.assignment_type,
      'roommaidEmployeeNo', coalesce(v_room.roommaid_employee_no,''),
      'secondaryRoommaidEmployeeNo', coalesce(v_room.secondary_roommaid_employee_no,''),
      'qmEmployeeNo', coalesce(v_room.qm_employee_no,''),
      'operationalStatus', coalesce(v_room.operational_status,''),
      'version', v_room.version,
      'cleaningStartedAt', v_room.cleaning_started_at,
      'cleaningCompletedAt', v_room.cleaning_completed_at,
      'updatedAt', v_room.updated_at
    )
  );

  update nova_private.core_idempotency
  set response_json = v_response, completed_at = now()
  where request_id = v_request_id;

  return v_response;
end;
$function$;

revoke all on function nova_private.roommaid_action_v2_internal(date,text,text,text,bigint,text) from public, anon;
grant execute on function nova_private.roommaid_action_v2_internal(date,text,text,text,bigint,text) to authenticated, service_role;

create or replace function public.nova_roommaid_action_v2(
  p_business_date date,
  p_site text,
  p_room_no text,
  p_action text,
  p_expected_version bigint,
  p_request_id text
)
returns jsonb
language sql
security invoker
set search_path = ''
as $function$
  select nova_private.roommaid_action_v2_internal(
    p_business_date,
    p_site,
    p_room_no,
    p_action,
    p_expected_version,
    p_request_id
  );
$function$;

revoke all on function public.nova_roommaid_action_v2(date,text,text,text,bigint,text) from public, anon;
grant execute on function public.nova_roommaid_action_v2(date,text,text,text,bigint,text) to authenticated, service_role;
