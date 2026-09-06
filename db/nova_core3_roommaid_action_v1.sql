-- NOVA Core 3.0 Phase 1
-- Authenticated ROOMMAID START/COMPLETE RPC V1
--
-- Additive migration. Existing production routes are unchanged until the client
-- explicitly adopts this RPC as a DB-authoritative fallback/primary route.

create or replace function public.nova_roommaid_action_v1(
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
  v_user public.nova_users%rowtype;
  v_room public.nova_rooms_current%rowtype;
  v_before text;
  v_after text;
  v_response jsonb;
  v_existing_employee text;
  v_existing_action text;
  v_existing_response jsonb;
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
  if v_request_id = '' then
    raise exception using errcode = '22023', message = 'requestId가 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_employee_no
    and enabled = true
    and upper(coalesce(role, '')) = 'ROOMMAID';
  if not found then
    raise exception using errcode = '42501', message = '룸메이드 사용자 정보를 확인할 수 없습니다.';
  end if;

  -- Existing request ids are immutable. A replay by the same actor/action returns
  -- the original response; reuse by another actor/action is rejected.
  select employee_no, action, response_json
    into v_existing_employee, v_existing_action, v_existing_response
  from public.nova_request_dedup
  where request_id = v_request_id;

  if found then
    if v_existing_employee <> v_employee_no or upper(coalesce(v_existing_action,'')) <> v_action then
      raise exception using errcode = '23505', message = '이미 다른 작업에 사용된 requestId입니다.';
    end if;
    return coalesce(v_existing_response, jsonb_build_object(
      'ok', true,
      'requestId', v_request_id,
      'action', v_action
    )) || jsonb_build_object('duplicate', true, 'idempotent', true);
  end if;

  -- Atomic claim. A concurrent replay that loses the race will be handled by
  -- unique_violation below and replay the committed result.
  insert into public.nova_request_dedup(request_id, employee_no, action, response_json)
  values (v_request_id, v_employee_no, v_action, null);

  select * into v_room
  from public.nova_rooms_current
  where business_date = p_business_date
    and site = v_site
    and room_no = v_room_no
  for update;
  if not found then
    raise exception using errcode = 'P0002', message = '객실을 찾을 수 없습니다.';
  end if;

  -- Assignment is the final room-level authorization boundary. Both members of
  -- a legitimate two-person assignment may operate the room.
  if v_employee_no <> trim(coalesce(v_room.roommaid_employee_no, ''))
     and v_employee_no <> trim(coalesce(v_room.secondary_roommaid_employee_no, '')) then
    raise exception using errcode = '42501', message = '본인에게 배정된 객실만 처리할 수 있습니다.';
  end if;

  if v_expected_version > 0 and v_room.version <> v_expected_version then
    raise exception using errcode = '40001', message = '객실이 다른 요청에 의해 먼저 변경되었습니다. 최신 상태를 다시 불러오세요.';
  end if;

  v_before := upper(coalesce(v_room.cleaning_status, ''));

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
      cleaning_started_at = case when v_action = 'CLEANING_START' then now() else cleaning_started_at end,
      cleaning_completed_at = case when v_action = 'CLEANING_COMPLETE' then now() else null end,
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
      'directRpc', true,
      'role', 'ROOMMAID',
      'expectedVersion', v_expected_version
    ),
    now()
  );

  v_response := jsonb_build_object(
    'ok', true,
    'requestId', v_request_id,
    'action', v_action,
    'idempotent', false,
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
      'updatedAt', v_room.updated_at
    )
  );

  update public.nova_request_dedup
  set response_json = v_response
  where request_id = v_request_id;

  return v_response;
exception
  when unique_violation then
    select employee_no, action, response_json
      into v_existing_employee, v_existing_action, v_existing_response
    from public.nova_request_dedup
    where request_id = v_request_id;
    if v_existing_employee = v_employee_no and upper(coalesce(v_existing_action,'')) = v_action then
      return coalesce(v_existing_response, jsonb_build_object(
        'ok', true,
        'requestId', v_request_id,
        'action', v_action
      )) || jsonb_build_object('duplicate', true, 'idempotent', true);
    end if;
    raise;
end;
$function$;

-- SECURITY DEFINER is required because the core tables intentionally have RLS
-- enabled without browser table policies. The function itself performs JWT,
-- user-role and room-assignment authorization before any write.
revoke all on function public.nova_roommaid_action_v1(date,text,text,text,bigint,text) from public;
revoke all on function public.nova_roommaid_action_v1(date,text,text,text,bigint,text) from anon;
grant execute on function public.nova_roommaid_action_v1(date,text,text,text,bigint,text) to authenticated, service_role;
