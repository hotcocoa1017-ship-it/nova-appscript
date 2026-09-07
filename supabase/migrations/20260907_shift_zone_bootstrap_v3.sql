-- NOVA_SHIFT_ZONE_DB_FIRST_V3
-- One-time Sheet -> PostgreSQL bootstrap for a business-date/site that has never been initialized.
-- Existing DB rows are never overwritten when roster_state is absent; partial state is rejected.

create or replace function public.nova_houseman_shift_zone_bootstrap_v3(
  p_business_date text,
  p_site text,
  p_assignments jsonb,
  p_zones jsonb,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_shift text;
  v_employee text;
  v_position integer;
  v_seen text[];
  v_zone jsonb;
  v_buildings text[];
  v_building text;
  v_shift_codes text[];
  v_existing record;
  v_response jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501',message='근무조 초기화 권한이 없습니다.';
  end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
      or v_site=coalesce(v_user.default_site,'')
      or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501',message='사업장 권한이 없습니다.';
  end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  if jsonb_typeof(coalesce(p_assignments,'{}'::jsonb))<>'object' then raise exception '근무조 정보를 확인해 주세요.'; end if;
  if jsonb_typeof(coalesce(p_zones,'{}'::jsonb))<>'object' then raise exception '담당동 정보를 확인해 주세요.'; end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'HOUSEMAN_SHIFT_ZONE_BOOTSTRAP_V3',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing
    from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'HOUSEMAN_SHIFT_ZONE_BOOTSTRAP_V3' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then return v_existing.response_json || jsonb_build_object('idempotent',true); end if;
    raise exception '동일 초기화 요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_SHIFT_ZONE_BOOTSTRAP|'||v_date::text||'|'||v_site,0));

  if exists(select 1 from public.nova_houseman_roster_state where business_date=v_date and site=v_site) then
    v_response:=public.nova_houseman_shift_zone_get_v2(v_date::text,v_site)
      || jsonb_build_object('bootstrapped',false,'initialized',true,'requestId',v_request_id,'idempotent',false);
    update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
    return v_response;
  end if;

  -- Never wipe unexplained partial DB data. This makes bootstrap fail closed.
  if exists(select 1 from public.nova_houseman_shift_assignments where business_date=v_date and site=v_site)
     or exists(select 1 from public.nova_houseman_zone_assignments where business_date=v_date and site=v_site) then
    raise exception '근무조 DB에 초기화표시 없는 기존 데이터가 있습니다. 자동 덮어쓰기를 중단했습니다.';
  end if;

  foreach v_shift in array array['A','B','C']::text[] loop
    if jsonb_typeof(coalesce(p_assignments->v_shift,'[]'::jsonb))<>'array' then raise exception '%조 근무조 정보를 확인해 주세요.',v_shift; end if;
    if jsonb_array_length(coalesce(p_assignments->v_shift,'[]'::jsonb))>10 then raise exception '%조는 최대 10명까지 배정할 수 있습니다.',v_shift; end if;
    v_position:=0;
    v_seen:=array[]::text[];
    for v_employee in select trim(value) from jsonb_array_elements_text(coalesce(p_assignments->v_shift,'[]'::jsonb)) loop
      if v_employee='' or v_employee=any(v_seen) then continue; end if;
      if not exists(select 1 from public.nova_users where employee_no=v_employee and enabled=true and upper(coalesce(role,''))='HOUSEMAN') then
        raise exception '% 사번은 사용 가능한 하우스맨 계정이 아닙니다.',v_employee;
      end if;
      v_seen:=array_append(v_seen,v_employee);
      v_position:=v_position+1;
      insert into public.nova_houseman_shift_assignments(
        business_date,site,shift_code,employee_no,position,registered_by,registered_at,updated_at,version
      ) values(v_date,v_site,v_shift,v_employee,v_position,v_actor,now(),now(),1);
    end loop;
  end loop;

  for v_employee,v_zone in select key,value from jsonb_each(coalesce(p_zones,'{}'::jsonb)) loop
    v_employee:=trim(coalesce(v_employee,''));
    if v_employee='' then continue; end if;
    if not exists(select 1 from public.nova_houseman_shift_assignments where business_date=v_date and site=v_site and employee_no=v_employee) then
      raise exception '% 사번은 해당 업무일자의 근무조에 등록되어 있지 않습니다.',v_employee;
    end if;
    v_buildings:=array[]::text[];
    if jsonb_typeof(v_zone)='array' then
      for v_building in select distinct trim(value) from jsonb_array_elements_text(v_zone) loop
        if v_building !~ '^[1-9]동$' then raise exception '담당동은 1동부터 9동까지만 선택할 수 있습니다.'; end if;
        v_buildings:=array_append(v_buildings,v_building);
      end loop;
    elsif jsonb_typeof(v_zone)='object' then
      if jsonb_typeof(coalesce(v_zone->'buildings','[]'::jsonb))<>'array' then raise exception '담당동 정보를 확인해 주세요.'; end if;
      for v_building in select distinct trim(value) from jsonb_array_elements_text(coalesce(v_zone->'buildings','[]'::jsonb)) loop
        if v_building !~ '^[1-9]동$' then raise exception '담당동은 1동부터 9동까지만 선택할 수 있습니다.'; end if;
        v_buildings:=array_append(v_buildings,v_building);
      end loop;
    else
      raise exception '담당동 정보를 확인해 주세요.';
    end if;
    if cardinality(v_buildings)=0 then continue; end if;
    select coalesce(array_agg(shift_code order by case shift_code when 'A' then 1 when 'B' then 2 else 3 end),array[]::text[])
      into v_shift_codes
    from public.nova_houseman_shift_assignments
    where business_date=v_date and site=v_site and employee_no=v_employee;
    insert into public.nova_houseman_zone_assignments(
      business_date,site,employee_no,buildings,shift_codes,registered_by,registered_at,updated_at,version
    ) values(v_date,v_site,v_employee,v_buildings,v_shift_codes,v_actor,now(),now(),1);
  end loop;

  insert into public.nova_houseman_roster_state(business_date,site,initialized_by,initialized_at,updated_at,version)
  values(v_date,v_site,v_actor,now(),now(),1);

  v_response:=public.nova_houseman_shift_zone_get_v2(v_date::text,v_site)
    || jsonb_build_object('bootstrapped',true,'initialized',true,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$function$;

revoke all on function public.nova_houseman_shift_zone_bootstrap_v3(text,text,jsonb,jsonb,text) from public;
revoke all on function public.nova_houseman_shift_zone_bootstrap_v3(text,text,jsonb,jsonb,text) from anon;
grant execute on function public.nova_houseman_shift_zone_bootstrap_v3(text,text,jsonb,jsonb,text) to authenticated;
grant execute on function public.nova_houseman_shift_zone_bootstrap_v3(text,text,jsonb,jsonb,text) to service_role;
