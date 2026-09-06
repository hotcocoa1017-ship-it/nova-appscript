-- NOVA_SHIFT_ZONE_DB_FIRST_V1
-- PostgreSQL becomes source-of-truth for the shared business date, Houseman shifts and zone assignments.
-- Existing Apps Script history writes remain asynchronous mirrors during the transition.

create table if not exists public.nova_houseman_shift_assignments (
  business_date date not null,
  site text not null,
  shift_code text not null check (shift_code in ('A','B','C')),
  employee_no text not null,
  position smallint not null check (position between 1 and 10),
  registered_by text not null,
  registered_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  version bigint not null default 1 check (version > 0),
  primary key (business_date, site, shift_code, employee_no),
  unique (business_date, site, shift_code, position)
);

create index if not exists nova_houseman_shift_assignments_employee_idx
  on public.nova_houseman_shift_assignments (business_date, site, employee_no);

create table if not exists public.nova_houseman_zone_assignments (
  business_date date not null,
  site text not null,
  employee_no text not null,
  buildings text[] not null default array[]::text[],
  shift_codes text[] not null default array[]::text[],
  registered_by text not null,
  registered_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  version bigint not null default 1 check (version > 0),
  primary key (business_date, site, employee_no)
);

create index if not exists nova_houseman_zone_assignments_buildings_idx
  on public.nova_houseman_zone_assignments using gin (buildings);

alter table public.nova_houseman_shift_assignments enable row level security;
alter table public.nova_houseman_zone_assignments enable row level security;

-- Tables are internal implementation details. Browser clients use the guarded RPCs below.
revoke all on table public.nova_houseman_shift_assignments from anon, authenticated;
revoke all on table public.nova_houseman_zone_assignments from anon, authenticated;
grant select, insert, update, delete on table public.nova_houseman_shift_assignments to service_role;
grant select, insert, update, delete on table public.nova_houseman_zone_assignments to service_role;

create or replace function public.nova_business_date_v1(p_at timestamptz default now())
returns date
language sql
stable
set search_path = public, pg_catalog
as $$
  select (((p_at at time zone 'Asia/Seoul') - interval '9 hours')::date);
$$;

revoke all on function public.nova_business_date_v1(timestamptz) from public;
grant execute on function public.nova_business_date_v1(timestamptz) to authenticated, service_role;

create or replace function public.nova_houseman_shift_zone_get_v1(
  p_business_date text,
  p_site text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_employee_no text := trim(coalesce(v_claims->>'employee_no', ''));
  v_user public.nova_users%rowtype;
  v_business_date date;
  v_site text := trim(coalesce(p_site, ''));
  v_assignments jsonb := jsonb_build_object('A','[]'::jsonb,'B','[]'::jsonb,'C','[]'::jsonb);
  v_zone_assignments jsonb := '{}'::jsonb;
  v_zone_by_building jsonb := jsonb_build_object(
    '1동','[]'::jsonb,'2동','[]'::jsonb,'3동','[]'::jsonb,
    '4동','[]'::jsonb,'5동','[]'::jsonb,'6동','[]'::jsonb,
    '7동','[]'::jsonb,'8동','[]'::jsonb,'9동','[]'::jsonb
  );
  v_staff jsonb := '[]'::jsonb;
  v_attendance_staff jsonb := '[]'::jsonb;
  v_sites jsonb := '[]'::jsonb;
  v_building text;
  v_current_shift text;
  v_local_time time := (now() at time zone 'Asia/Seoul')::time;
  r record;
begin
  if v_employee_no = '' then
    raise exception using errcode = '42501', message = '로그인이 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_employee_no and enabled = true;

  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode = '42501', message = '근무조 관리 권한이 없습니다.';
  end if;

  if coalesce(trim(p_business_date),'') = '' then
    v_business_date := public.nova_business_date_v1(now());
  elsif trim(p_business_date) ~ '^\d{4}-\d{2}-\d{2}$' then
    begin
      v_business_date := trim(p_business_date)::date;
    exception when others then
      raise exception '업무일자를 확인해 주세요.';
    end;
  else
    raise exception '업무일자를 확인해 주세요.';
  end if;

  if v_site = '' then
    raise exception '사업장을 선택하세요.';
  end if;

  if not (
    (coalesce(trim(v_user.default_site),'') = '' and cardinality(coalesce(v_user.allowed_sites,array[]::text[])) = 0)
    or v_site = coalesce(v_user.default_site,'')
    or v_site = any(coalesce(v_user.allowed_sites,array[]::text[]))
  ) then
    raise exception using errcode = '42501', message = '사업장 권한이 없습니다.';
  end if;

  for r in
    select shift_code, employee_no
    from public.nova_houseman_shift_assignments
    where business_date = v_business_date and site = v_site
    order by case shift_code when 'A' then 1 when 'B' then 2 else 3 end, position, employee_no
  loop
    v_assignments := jsonb_set(
      v_assignments,
      array[r.shift_code],
      coalesce(v_assignments->r.shift_code,'[]'::jsonb) || to_jsonb(r.employee_no),
      true
    );
  end loop;

  for r in
    select employee_no, buildings, shift_codes, registered_at, updated_at
    from public.nova_houseman_zone_assignments
    where business_date = v_business_date and site = v_site
    order by employee_no
  loop
    v_zone_assignments := v_zone_assignments || jsonb_build_object(
      r.employee_no,
      jsonb_build_object(
        'employeeNo', r.employee_no,
        'buildings', to_jsonb(coalesce(r.buildings,array[]::text[])),
        'shiftCodes', to_jsonb(coalesce(r.shift_codes,array[]::text[])),
        'registeredAt', to_char(r.registered_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        'updatedAt', to_char(r.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS')
      )
    );
    foreach v_building in array coalesce(r.buildings,array[]::text[])
    loop
      if v_zone_by_building ? v_building then
        v_zone_by_building := jsonb_set(
          v_zone_by_building,
          array[v_building],
          coalesce(v_zone_by_building->v_building,'[]'::jsonb) || to_jsonb(r.employee_no),
          true
        );
      end if;
    end loop;
  end loop;

  select coalesce(jsonb_agg(
    jsonb_build_object(
      'employeeNo', u.employee_no,
      'name', u.name,
      'role', u.role,
      'defaultSite', coalesce(u.default_site,'')
    ) order by u.name, u.employee_no
  ), '[]'::jsonb)
  into v_staff
  from public.nova_users u
  where u.enabled = true and upper(coalesce(u.role,'')) = 'HOUSEMAN';

  select coalesce(jsonb_agg(
    jsonb_build_object(
      'employeeNo', x.employee_no,
      'name', x.name,
      'shiftCodes', to_jsonb(x.shift_codes),
      'shiftLabels', to_jsonb(array(
        select case s when 'A' then 'A조' when 'B' then 'B조' else 'C조' end
        from unnest(x.shift_codes) s
      ))
    ) order by x.name, x.employee_no
  ), '[]'::jsonb)
  into v_attendance_staff
  from (
    select u.employee_no, u.name,
           array_agg(a.shift_code order by case a.shift_code when 'A' then 1 when 'B' then 2 else 3 end) as shift_codes
    from public.nova_houseman_shift_assignments a
    join public.nova_users u on u.employee_no = a.employee_no
    where a.business_date = v_business_date and a.site = v_site
    group by u.employee_no, u.name
  ) x;

  select coalesce(jsonb_agg(s.site order by s.site), '[]'::jsonb)
  into v_sites
  from (
    select distinct site
    from public.nova_rooms_current
    where coalesce(site,'') <> ''
      and (
        (coalesce(trim(v_user.default_site),'') = '' and cardinality(coalesce(v_user.allowed_sites,array[]::text[])) = 0)
        or site = coalesce(v_user.default_site,'')
        or site = any(coalesce(v_user.allowed_sites,array[]::text[]))
      )
  ) s;

  if jsonb_array_length(v_sites) = 0 then
    v_sites := jsonb_build_array(v_site);
  end if;

  v_current_shift := case
    when v_local_time >= time '14:30' and v_local_time < time '23:30' then 'B'
    when v_local_time >= time '08:30' and v_local_time < time '14:30' then 'A'
    else 'C'
  end;

  return jsonb_build_object(
    'ok', true,
    'dbFirst', true,
    'businessDate', v_business_date::text,
    'site', v_site,
    'sites', v_sites,
    'shifts', jsonb_build_array(
      jsonb_build_object('code','A','label','A조','start','08:30','end','17:30','order',1),
      jsonb_build_object('code','B','label','B조','start','14:30','end','23:30','order',2),
      jsonb_build_object('code','C','label','C조','start','23:30','end','08:30','order',3)
    ),
    'assignments', v_assignments,
    'zoneAssignments', v_zone_assignments,
    'zoneAssignmentsByBuilding', v_zone_by_building,
    'buildings', jsonb_build_array('1동','2동','3동','4동','5동','6동','7동','8동','9동'),
    'attendanceStaff', v_attendance_staff,
    'staff', v_staff,
    'maxStaff', 10,
    'currentShift', v_current_shift,
    'serverTime', to_char(now() at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS')
  );
end;
$$;

revoke all on function public.nova_houseman_shift_zone_get_v1(text,text) from public;
grant execute on function public.nova_houseman_shift_zone_get_v1(text,text) to authenticated, service_role;

create or replace function public.nova_houseman_shift_save_v1(
  p_business_date text,
  p_site text,
  p_assignments jsonb,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_employee_no text := trim(coalesce(v_claims->>'employee_no', ''));
  v_user public.nova_users%rowtype;
  v_business_date date;
  v_site text := trim(coalesce(p_site,''));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_shift text;
  v_employee text;
  v_position integer;
  v_seen text[];
  v_version bigint;
  v_normalized jsonb := jsonb_build_object('A','[]'::jsonb,'B','[]'::jsonb,'C','[]'::jsonb);
  v_response jsonb;
  v_existing record;
begin
  if v_employee_no = '' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_employee_no and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='근무조 저장 권한이 없습니다.';
  end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_business_date := trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not (
    (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
    or v_site=coalesce(v_user.default_site,'')
    or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))
  ) then raise exception using errcode='42501', message='사업장 권한이 없습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  if jsonb_typeof(coalesce(p_assignments,'{}'::jsonb)) <> 'object' then raise exception '근무조 정보를 확인해 주세요.'; end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_employee_no,'HOUSEMAN_SHIFT_SAVE_V1',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_employee_no or v_existing.action<>'HOUSEMAN_SHIFT_SAVE_V1' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then return v_existing.response_json || jsonb_build_object('idempotent',true); end if;
    raise exception '동일 요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_SHIFT|'||v_business_date::text||'|'||v_site,0));
  select coalesce(max(version),0)+1 into v_version
  from public.nova_houseman_shift_assignments
  where business_date=v_business_date and site=v_site;

  delete from public.nova_houseman_shift_assignments where business_date=v_business_date and site=v_site;

  foreach v_shift in array array['A','B','C']::text[]
  loop
    if jsonb_typeof(coalesce(p_assignments->v_shift,'[]'::jsonb)) <> 'array' then
      raise exception '%조 근무조 정보를 확인해 주세요.', v_shift;
    end if;
    if jsonb_array_length(coalesce(p_assignments->v_shift,'[]'::jsonb)) > 10 then
      raise exception '%조는 최대 10명까지 배정할 수 있습니다.', v_shift;
    end if;
    v_position := 0;
    v_seen := array[]::text[];
    for v_employee in select trim(value) from jsonb_array_elements_text(coalesce(p_assignments->v_shift,'[]'::jsonb))
    loop
      if v_employee='' then continue; end if;
      if v_employee=any(v_seen) then continue; end if;
      if not exists(select 1 from public.nova_users where employee_no=v_employee and enabled=true and upper(coalesce(role,''))='HOUSEMAN') then
        raise exception '% 사번은 사용 가능한 하우스맨 계정이 아닙니다.', v_employee;
      end if;
      v_seen := array_append(v_seen,v_employee);
      v_position := v_position + 1;
      insert into public.nova_houseman_shift_assignments(
        business_date,site,shift_code,employee_no,position,registered_by,registered_at,updated_at,version
      ) values(
        v_business_date,v_site,v_shift,v_employee,v_position,v_employee_no,now(),now(),v_version
      );
      v_normalized := jsonb_set(v_normalized,array[v_shift],coalesce(v_normalized->v_shift,'[]'::jsonb)||to_jsonb(v_employee),true);
    end loop;
  end loop;

  -- Keep zone shift-code metadata consistent when the shift roster changes.
  update public.nova_houseman_zone_assignments z
  set shift_codes = coalesce((
        select array_agg(a.shift_code order by case a.shift_code when 'A' then 1 when 'B' then 2 else 3 end)
        from public.nova_houseman_shift_assignments a
        where a.business_date=z.business_date and a.site=z.site and a.employee_no=z.employee_no
      ),array[]::text[]),
      updated_at=now(),
      version=greatest(z.version+1,v_version)
  where z.business_date=v_business_date and z.site=v_site;

  v_response := jsonb_build_object(
    'ok',true,'dbFirst',true,'businessDate',v_business_date::text,'site',v_site,
    'assignments',v_normalized,'version',v_version,'requestId',v_request_id,
    'idempotent',false,'message',v_business_date::text||' '||v_site||' 근무조를 저장했습니다.'
  );
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

revoke all on function public.nova_houseman_shift_save_v1(text,text,jsonb,text) from public;
grant execute on function public.nova_houseman_shift_save_v1(text,text,jsonb,text) to authenticated, service_role;

create or replace function public.nova_houseman_zone_save_v1(
  p_business_date text,
  p_site text,
  p_employee_no text,
  p_buildings jsonb,
  p_action text,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_business_date date;
  v_site text := trim(coalesce(p_site,''));
  v_employee text := trim(coalesce(p_employee_no,''));
  v_action text := upper(trim(coalesce(p_action,'SAVE')));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_buildings text[] := array[]::text[];
  v_shift_codes text[] := array[]::text[];
  v_building text;
  v_exists boolean;
  v_version bigint;
  v_response jsonb;
  v_existing record;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='담당동 저장 권한이 없습니다.';
  end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_business_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not (
    (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
    or v_site=coalesce(v_user.default_site,'')
    or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))
  ) then raise exception using errcode='42501', message='사업장 권한이 없습니다.'; end if;
  if v_employee='' then raise exception '출근 직원을 선택하세요.'; end if;
  if v_action not in ('SAVE','UPDATE','CANCEL') then raise exception '지원하지 않는 담당동 작업입니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  if not exists(select 1 from public.nova_users where employee_no=v_employee and enabled=true and upper(coalesce(role,''))='HOUSEMAN') then
    raise exception '사용 가능한 하우스맨 계정이 아닙니다.';
  end if;
  if not exists(select 1 from public.nova_houseman_shift_assignments where business_date=v_business_date and site=v_site and employee_no=v_employee) then
    raise exception '선택한 직원은 해당 업무일자의 A·B·C 근무조에 등록되어 있지 않습니다.';
  end if;

  if v_action<>'CANCEL' then
    if jsonb_typeof(coalesce(p_buildings,'[]'::jsonb))<>'array' then raise exception '담당동 정보를 확인해 주세요.'; end if;
    for v_building in select distinct trim(value) from jsonb_array_elements_text(coalesce(p_buildings,'[]'::jsonb))
    loop
      if v_building !~ '^[1-9]동$' then raise exception '담당동은 1동부터 9동까지만 선택할 수 있습니다.'; end if;
      v_buildings:=array_append(v_buildings,v_building);
    end loop;
    if cardinality(v_buildings)=0 then raise exception '담당동을 한 개 이상 선택하세요.'; end if;
  end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'HOUSEMAN_ZONE_'||v_action||'_V1',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'HOUSEMAN_ZONE_'||v_action||'_V1' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then return v_existing.response_json || jsonb_build_object('idempotent',true); end if;
    raise exception '동일 요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_ZONE|'||v_business_date::text||'|'||v_site||'|'||v_employee,0));
  select exists(select 1 from public.nova_houseman_zone_assignments where business_date=v_business_date and site=v_site and employee_no=v_employee) into v_exists;
  if v_action='SAVE' and v_exists then raise exception '이미 담당동이 등록되어 있습니다. 변경 버튼을 사용하세요.'; end if;
  if v_action='UPDATE' and not v_exists then raise exception '기존 담당동 배정이 없습니다. 저장 버튼을 사용하세요.'; end if;
  if v_action='CANCEL' and not v_exists then raise exception '취소할 담당동 배정이 없습니다.'; end if;

  select coalesce(array_agg(shift_code order by case shift_code when 'A' then 1 when 'B' then 2 else 3 end),array[]::text[])
  into v_shift_codes
  from public.nova_houseman_shift_assignments
  where business_date=v_business_date and site=v_site and employee_no=v_employee;

  select coalesce(max(version),0)+1 into v_version
  from public.nova_houseman_zone_assignments
  where business_date=v_business_date and site=v_site and employee_no=v_employee;

  if v_action='CANCEL' then
    delete from public.nova_houseman_zone_assignments where business_date=v_business_date and site=v_site and employee_no=v_employee;
  else
    insert into public.nova_houseman_zone_assignments(
      business_date,site,employee_no,buildings,shift_codes,registered_by,registered_at,updated_at,version
    ) values(
      v_business_date,v_site,v_employee,v_buildings,v_shift_codes,v_actor,now(),now(),v_version
    )
    on conflict(business_date,site,employee_no) do update set
      buildings=excluded.buildings,
      shift_codes=excluded.shift_codes,
      updated_at=now(),
      version=public.nova_houseman_zone_assignments.version+1;
  end if;

  v_response:=jsonb_build_object(
    'ok',true,'dbFirst',true,'businessDate',v_business_date::text,'site',v_site,
    'employeeNo',v_employee,'action',v_action,
    'buildings',case when v_action='CANCEL' then '[]'::jsonb else to_jsonb(v_buildings) end,
    'version',v_version,'requestId',v_request_id,'idempotent',false,
    'message',case when v_action='CANCEL' then '담당동 배정을 취소했습니다.' when v_action='UPDATE' then '담당동을 변경했습니다.' else '담당동을 저장했습니다.' end
  );
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

revoke all on function public.nova_houseman_zone_save_v1(text,text,text,jsonb,text,text) from public;
grant execute on function public.nova_houseman_zone_save_v1(text,text,text,jsonb,text,text) to authenticated, service_role;
