-- NOVA Core 3.0 Phase 1
-- Authoritative ROOMMAID current-room read RPC.
-- Returns only rows assigned to the authenticated roommaid.

create or replace function nova_private.roommaid_rooms_v1_internal(
  p_business_date date,
  p_site text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_employee_no text := trim(coalesce(v_claims->>'employee_no', ''));
  v_site text := trim(coalesce(p_site, ''));
  v_user public.nova_users%rowtype;
  v_rooms jsonb;
begin
  if v_employee_no = '' then
    raise exception using errcode = '42501', message = '로그인이 필요합니다.';
  end if;
  if p_business_date is null or v_site = '' then
    raise exception using errcode = '22023', message = '업무일자와 사업장을 확인하세요.';
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

  select coalesce(jsonb_agg(jsonb_build_object(
    'businessDate', r.business_date::text,
    'site', r.site,
    'roomNo', r.room_no,
    'building', coalesce(r.building,''),
    'roomStatus', r.room_status,
    'cleaningStatus', r.cleaning_status,
    'cleaningType', r.cleaning_type,
    'assignmentType', r.assignment_type,
    'roommaidEmployeeNo', coalesce(r.roommaid_employee_no,''),
    'secondaryRoommaidEmployeeNo', coalesce(r.secondary_roommaid_employee_no,''),
    'qmEmployeeNo', coalesce(r.qm_employee_no,''),
    'operationalStatus', coalesce(r.operational_status,''),
    'version', r.version,
    'cleaningStartedAt', r.cleaning_started_at,
    'cleaningCompletedAt', r.cleaning_completed_at,
    'updatedAt', r.updated_at
  ) order by r.room_no), '[]'::jsonb)
  into v_rooms
  from public.nova_rooms_current r
  where r.business_date = p_business_date
    and r.site = v_site
    and (
      trim(coalesce(r.roommaid_employee_no,'')) = v_employee_no
      or trim(coalesce(r.secondary_roommaid_employee_no,'')) = v_employee_no
    );

  return jsonb_build_object(
    'ok', true,
    'businessDate', p_business_date::text,
    'site', v_site,
    'employeeNo', v_employee_no,
    'rooms', v_rooms,
    'serverTime', now()
  );
end;
$function$;

revoke all on function nova_private.roommaid_rooms_v1_internal(date,text) from public, anon;
grant execute on function nova_private.roommaid_rooms_v1_internal(date,text) to authenticated, service_role;

create or replace function public.nova_roommaid_rooms_v1(
  p_business_date date,
  p_site text
)
returns jsonb
language sql
security invoker
set search_path = ''
as $function$
  select nova_private.roommaid_rooms_v1_internal(p_business_date, p_site);
$function$;

revoke all on function public.nova_roommaid_rooms_v1(date,text) from public, anon;
grant execute on function public.nova_roommaid_rooms_v1(date,text) to authenticated, service_role;
