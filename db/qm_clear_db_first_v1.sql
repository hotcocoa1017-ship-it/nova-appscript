-- QM_CLEAR_DB_FIRST_V1
-- 관리자/오더테이커의 QM 배정 초기화를 PostgreSQL 원본으로 확정합니다.
-- 룸메이드 배정/청소완료 실적과 기존 QM 체크리스트/점검이력은 보존합니다.

create or replace function public.nova_qm_clear_v1(
  p_business_date text,
  p_site text,
  p_room_no text,
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
  v_previous_qm text := '';
  v_before_status text := '';
  v_after_status text := '';
  v_response jsonb;
  v_existing record;
begin
  if v_actor='' then
    raise exception using errcode='42501', message='로그인이 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='QM 배정 초기화 권한이 없습니다.';
  end if;

  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then
    raise exception '업무일자를 확인해 주세요.';
  end if;
  begin
    v_date := trim(p_business_date)::date;
  exception when others then
    raise exception '업무일자를 확인해 주세요.';
  end;

  if v_site='' or v_room_no='' then
    raise exception 'QM 배정 초기화에 사업장과 객실번호가 필요합니다.';
  end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then
    raise exception '요청 ID 형식이 올바르지 않습니다.';
  end if;

  if not (
    (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
    or v_site=coalesce(v_user.default_site,'')
    or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))
  ) then
    raise exception using errcode='42501', message='사업장 권한이 없습니다.';
  end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'QM_CLEAR_V1',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing
    from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'QM_CLEAR_V1' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then
      return v_existing.response_json || jsonb_build_object('idempotent',true);
    end if;
    raise exception '동일 QM 배정 초기화 요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_QM_CLEAR|'||v_date::text||'|'||v_site||'|'||v_room_no,0));

  select * into v_room
  from public.nova_rooms_current
  where business_date=v_date and site=v_site and room_no=v_room_no
  for update;
  if not found then
    raise exception 'DB 현재객실현황에서 해당 객실을 찾을 수 없습니다.';
  end if;

  v_previous_qm := trim(coalesce(v_room.qm_employee_no,''));
  if v_previous_qm='' then
    raise exception '초기화할 QM 배정이 없습니다.';
  end if;

  v_before_status := upper(trim(coalesce(v_room.cleaning_status,'')));
  v_after_status := case
    when v_before_status in ('QM_WAITING','QM_CHECKING','QM_COMPLETED','REWORK') then 'COMPLETED'
    else v_before_status
  end;

  update public.nova_rooms_current
  set qm_employee_no=null,
      cleaning_status=v_after_status,
      version=version+1,
      updated_by=v_actor,
      updated_at=now()
  where id=v_room.id
  returning * into v_room;

  insert into public.nova_room_events(
    request_id,business_date,site,room_no,action,before_status,after_status,
    employee_no,room_version,detail,event_time
  ) values(
    v_request_id,v_date,v_site,v_room_no,'QM_CLEAR',v_before_status,v_after_status,
    v_actor,v_room.version,
    jsonb_build_object(
      'role',upper(coalesce(v_user.role,'')),
      'source','NOVA_QM_CLEAR_DB_FIRST_V1',
      'previousQmEmployeeNo',v_previous_qm,
      'qmEmployeeNo','',
      'previousCleaningStatus',v_before_status,
      'cleaningStatus',v_after_status,
      'primaryEmployeeNo',coalesce(v_room.roommaid_employee_no,''),
      'secondaryEmployeeNo',coalesce(v_room.secondary_roommaid_employee_no,''),
      'cleaningType',coalesce(v_room.cleaning_type,''),
      'assignmentType',coalesce(v_room.assignment_type,'')
    ),
    now()
  );

  v_response := jsonb_build_object(
    'ok',true,
    'dbFirst',true,
    'action','QM_CLEAR',
    'businessDate',v_date::text,
    'site',v_site,
    'roomNo',v_room_no,
    'previousQmEmployeeNo',v_previous_qm,
    'previousCleaningStatus',v_before_status,
    'cleaningStatus',v_after_status,
    'version',v_room.version,
    'requestId',v_request_id,
    'idempotent',false,
    'room',jsonb_build_object(
      'businessDate',v_date::text,
      'site',v_site,
      'roomNo',v_room_no,
      'building',coalesce(v_room.building,''),
      'roomStatus',coalesce(v_room.room_status,''),
      'cleaningStatus',coalesce(v_room.cleaning_status,''),
      'cleaningType',coalesce(v_room.cleaning_type,''),
      'assignmentType',coalesce(v_room.assignment_type,''),
      'roommaidEmployeeNo',coalesce(v_room.roommaid_employee_no,''),
      'secondaryRoommaidEmployeeNo',coalesce(v_room.secondary_roommaid_employee_no,''),
      'qmEmployeeNo','',
      'operationalStatus',coalesce(v_room.operational_status,''),
      'updatedAt',to_char(v_room.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
      'version',v_room.version
    )
  );

  update public.nova_request_dedup
  set response_json=v_response
  where request_id=v_request_id;

  return v_response;
end;
$$;

revoke all on function public.nova_qm_clear_v1(text,text,text,text) from public;
revoke execute on function public.nova_qm_clear_v1(text,text,text,text) from anon;
grant execute on function public.nova_qm_clear_v1(text,text,text,text) to authenticated,service_role;
