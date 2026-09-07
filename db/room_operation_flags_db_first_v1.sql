-- ROOM_OPERATION_FLAGS_DB_FIRST_V1
-- 선배정/VIP/중요객실을 nova_rooms_current의 정식 현재상태로 승격하고
-- 기존 객실업로드 v2를 감싸는 v3 RPC에서 플래그까지 같은 트랜잭션으로 확정합니다.

alter table public.nova_rooms_current
  add column if not exists preassigned boolean not null default false,
  add column if not exists vip boolean not null default false,
  add column if not exists important_room boolean not null default false;

create or replace function public.nova_room_operation_flags_update_v1(
  p_business_date text,
  p_site text,
  p_room_no text,
  p_preassigned boolean,
  p_vip boolean,
  p_important_room boolean,
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
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_room_no text := trim(coalesce(p_room_no,''));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_room public.nova_rooms_current%rowtype;
  v_previous_preassigned boolean := false;
  v_previous_vip boolean := false;
  v_previous_important_room boolean := false;
  v_response jsonb;
  v_existing record;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='객실 운영표시 변경 권한이 없습니다.';
  end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' or v_room_no='' then raise exception '객실 운영표시에 사업장과 객실번호가 필요합니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
          or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501', message='사업장 권한이 없습니다.';
  end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'ROOM_OPERATION_FLAGS_UPDATE_V1',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing
    from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'ROOM_OPERATION_FLAGS_UPDATE_V1' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then
      return v_existing.response_json || jsonb_build_object('idempotent',true);
    end if;
    raise exception '동일 객실 운영표시 요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_ROOM_FLAGS|'||v_date::text||'|'||v_site||'|'||v_room_no,0));
  select * into v_room
  from public.nova_rooms_current
  where business_date=v_date and site=v_site and room_no=v_room_no
  for update;
  if not found then raise exception 'DB 현재객실현황에서 해당 객실을 찾을 수 없습니다.'; end if;

  v_previous_preassigned := coalesce(v_room.preassigned,false);
  v_previous_vip := coalesce(v_room.vip,false);
  v_previous_important_room := coalesce(v_room.important_room,false);

  if v_previous_preassigned=coalesce(p_preassigned,false)
     and v_previous_vip=coalesce(p_vip,false)
     and v_previous_important_room=coalesce(p_important_room,false) then
    v_response := jsonb_build_object(
      'ok',true,'dbFirst',true,'action','UPDATE_OPERATION_FLAGS',
      'businessDate',v_date::text,'site',v_site,'roomNo',v_room_no,
      'preassigned',v_previous_preassigned,'vip',v_previous_vip,'importantRoom',v_previous_important_room,
      'version',v_room.version,'requestId',v_request_id,'idempotent',true,
      'room',jsonb_build_object(
        'businessDate',v_date::text,'site',v_site,'roomNo',v_room_no,
        'building',coalesce(v_room.building,''),'roomStatus',coalesce(v_room.room_status,''),
        'cleaningStatus',coalesce(v_room.cleaning_status,''),'cleaningType',coalesce(v_room.cleaning_type,''),
        'assignmentType',coalesce(v_room.assignment_type,''),'roommaidEmployeeNo',coalesce(v_room.roommaid_employee_no,''),
        'secondaryRoommaidEmployeeNo',coalesce(v_room.secondary_roommaid_employee_no,''),'qmEmployeeNo',coalesce(v_room.qm_employee_no,''),
        'operationalStatus',coalesce(v_room.operational_status,''),'preassigned',v_previous_preassigned,
        'vip',v_previous_vip,'importantRoom',v_previous_important_room,
        'updatedAt',to_char(v_room.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'version',v_room.version
      )
    );
    update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
    return v_response;
  end if;

  update public.nova_rooms_current
  set preassigned=coalesce(p_preassigned,false),
      vip=coalesce(p_vip,false),
      important_room=coalesce(p_important_room,false),
      version=version+1,
      updated_by=v_actor,
      updated_at=now()
  where id=v_room.id
  returning * into v_room;

  insert into public.nova_room_events(
    request_id,business_date,site,room_no,action,before_status,after_status,
    employee_no,room_version,detail,event_time
  ) values(
    v_request_id,v_date,v_site,v_room_no,'UPDATE_OPERATION_FLAGS',
    coalesce(v_room.room_status,''),coalesce(v_room.room_status,''),v_actor,v_room.version,
    jsonb_build_object(
      'role',upper(coalesce(v_user.role,'')),'source','NOVA_ROOM_OPERATION_FLAGS_DB_FIRST_V1',
      'previousPreassigned',v_previous_preassigned,'previousVip',v_previous_vip,'previousImportantRoom',v_previous_important_room,
      'preassigned',coalesce(v_room.preassigned,false),'vip',coalesce(v_room.vip,false),'importantRoom',coalesce(v_room.important_room,false),
      'roomStatus',coalesce(v_room.room_status,''),'cleaningStatus',coalesce(v_room.cleaning_status,''),
      'cleaningType',coalesce(v_room.cleaning_type,''),'assignmentType',coalesce(v_room.assignment_type,''),
      'primaryEmployeeNo',coalesce(v_room.roommaid_employee_no,''),'secondaryEmployeeNo',coalesce(v_room.secondary_roommaid_employee_no,''),
      'qmEmployeeNo',coalesce(v_room.qm_employee_no,''),'operationalStatus',coalesce(v_room.operational_status,'')
    ),now()
  );

  v_response := jsonb_build_object(
    'ok',true,'dbFirst',true,'action','UPDATE_OPERATION_FLAGS',
    'businessDate',v_date::text,'site',v_site,'roomNo',v_room_no,
    'preassigned',coalesce(v_room.preassigned,false),'vip',coalesce(v_room.vip,false),'importantRoom',coalesce(v_room.important_room,false),
    'version',v_room.version,'requestId',v_request_id,'idempotent',false,
    'room',jsonb_build_object(
      'businessDate',v_date::text,'site',v_site,'roomNo',v_room_no,
      'building',coalesce(v_room.building,''),'roomStatus',coalesce(v_room.room_status,''),
      'cleaningStatus',coalesce(v_room.cleaning_status,''),'cleaningType',coalesce(v_room.cleaning_type,''),
      'assignmentType',coalesce(v_room.assignment_type,''),'roommaidEmployeeNo',coalesce(v_room.roommaid_employee_no,''),
      'secondaryRoommaidEmployeeNo',coalesce(v_room.secondary_roommaid_employee_no,''),'qmEmployeeNo',coalesce(v_room.qm_employee_no,''),
      'operationalStatus',coalesce(v_room.operational_status,''),'preassigned',coalesce(v_room.preassigned,false),
      'vip',coalesce(v_room.vip,false),'importantRoom',coalesce(v_room.important_room,false),
      'updatedAt',to_char(v_room.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'version',v_room.version
    )
  );
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

create or replace function public.nova_room_upload_state_v2(
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
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_rooms jsonb := '[]'::jsonb;
  v_version bigint := 0;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='객실 업로드 조회 권한이 없습니다.';
  end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
          or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501', message='사업장 권한이 없습니다.';
  end if;

  select coalesce(max(r.version),0),
         coalesce(jsonb_agg(jsonb_build_object(
           '업무일자',r.business_date::text,'사업장',r.site,'객실번호',r.room_no,'동',r.building,
           '객실상태',r.room_status,'청소상태',r.cleaning_status,'정비유형',r.cleaning_type,'배정유형',r.assignment_type,
           '룸메이드사번',r.roommaid_employee_no,'보조룸메이드사번',r.secondary_roommaid_employee_no,'QM사번',r.qm_employee_no,
           '객실운영상태',r.operational_status,
           '선배정여부',case when coalesce(r.preassigned,false) then 'Y' else 'N' end,
           'VIP여부',case when coalesce(r.vip,false) then 'Y' else 'N' end,
           '중요객실여부',case when coalesce(r.important_room,false) then 'Y' else 'N' end,
           '마지막변경버전',r.version,'수정일시',to_char(r.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS')
         ) order by r.room_no),'[]'::jsonb)
  into v_version,v_rooms
  from public.nova_rooms_current r
  where r.business_date=v_date and r.site=v_site;

  return jsonb_build_object('ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,'version',v_version,'currentRows',v_rooms);
end;
$$;

create or replace function public.nova_room_upload_apply_v3(
  p_business_date text,
  p_site text,
  p_rooms jsonb,
  p_upload jsonb,
  p_expected_version bigint,
  p_version bigint,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_response jsonb;
  v_room jsonb;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_room_no text;
begin
  v_response := public.nova_room_upload_apply_v2(
    p_business_date,p_site,p_rooms,p_upload,p_expected_version,p_version,p_request_id
  );
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;

  for v_room in select value from jsonb_array_elements(coalesce(p_rooms,'[]'::jsonb))
  loop
    v_room_no := trim(coalesce(v_room->>'roomNo',''));
    if v_room_no<>'' then
      update public.nova_rooms_current
      set preassigned=coalesce((v_room->>'preassigned')::boolean,false),
          vip=coalesce((v_room->>'vip')::boolean,false),
          important_room=coalesce((v_room->>'importantRoom')::boolean,false)
      where business_date=v_date and site=v_site and room_no=v_room_no;
    end if;
  end loop;

  return v_response || jsonb_build_object('flagsDbFirst',true,'uploadRpcVersion','V3');
end;
$$;

revoke all on function public.nova_room_operation_flags_update_v1(text,text,text,boolean,boolean,boolean,text) from public;
revoke execute on function public.nova_room_operation_flags_update_v1(text,text,text,boolean,boolean,boolean,text) from anon;
grant execute on function public.nova_room_operation_flags_update_v1(text,text,text,boolean,boolean,boolean,text) to authenticated,service_role;

revoke all on function public.nova_room_upload_state_v2(text,text) from public;
revoke execute on function public.nova_room_upload_state_v2(text,text) from anon;
grant execute on function public.nova_room_upload_state_v2(text,text) to authenticated,service_role;

revoke all on function public.nova_room_upload_apply_v3(text,text,jsonb,jsonb,bigint,bigint,text) from public;
revoke execute on function public.nova_room_upload_apply_v3(text,text,jsonb,jsonb,bigint,bigint,text) from anon;
grant execute on function public.nova_room_upload_apply_v3(text,text,jsonb,jsonb,bigint,bigint,text) to authenticated,service_role;
