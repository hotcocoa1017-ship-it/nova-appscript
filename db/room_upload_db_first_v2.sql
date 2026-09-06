-- ROOM_UPLOAD_DB_FIRST_V2
-- Uses the Apps Script/global data version chosen after reconciling the latest DB room version.

create or replace function public.nova_room_upload_apply_v2(
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
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_current_version bigint := 0;
  v_next_version bigint := coalesce(p_version,0);
  v_count integer := 0;
  v_room jsonb;
  v_room_no text;
  v_reset boolean := upper(trim(coalesce(p_upload->>'applyMode',''))) = 'RESET_REPLACE';
  v_response jsonb;
  v_existing record;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='객실 업로드 권한이 없습니다.';
  end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
          or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501', message='사업장 권한이 없습니다.';
  end if;
  if jsonb_typeof(coalesce(p_rooms,'[]'::jsonb))<>'array' or jsonb_array_length(coalesce(p_rooms,'[]'::jsonb))=0 then
    raise exception '업로드 객실정보가 없습니다.';
  end if;
  if jsonb_array_length(p_rooms)>5000 then raise exception '업로드 객실 수가 허용범위를 초과했습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'ROOM_UPLOAD_APPLY_V2',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing
    from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'ROOM_UPLOAD_APPLY_V2' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then
      return v_existing.response_json || jsonb_build_object('idempotent',true);
    end if;
    raise exception '동일 요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_ROOM_UPLOAD|'||v_date::text||'|'||v_site,0));
  select coalesce(max(version),0) into v_current_version
  from public.nova_rooms_current where business_date=v_date and site=v_site;

  if p_expected_version is not null and p_expected_version>=0 and v_current_version<>p_expected_version then
    raise exception '객실정보가 다른 사용자에 의해 먼저 변경되었습니다. 다시 불러온 뒤 업로드해 주세요.';
  end if;
  if v_next_version <= v_current_version then
    raise exception '업로드 변경버전이 최신 DB 버전보다 앞서지 않습니다. 다시 불러온 뒤 업로드해 주세요.';
  end if;

  for v_room in select value from jsonb_array_elements(p_rooms)
  loop
    v_room_no:=trim(coalesce(v_room->>'roomNo',''));
    if v_room_no='' then raise exception '객실번호가 없는 업로드 행이 있습니다.'; end if;

    insert into public.nova_rooms_current(
      business_date,site,room_no,building,room_status,cleaning_status,cleaning_type,assignment_type,
      roommaid_employee_no,secondary_roommaid_employee_no,qm_employee_no,operational_status,version,
      cleaning_started_at,cleaning_completed_at,updated_by,updated_at
    ) values(
      v_date,v_site,v_room_no,trim(coalesce(v_room->>'building','')),
      upper(trim(coalesce(v_room->>'roomStatus',''))),
      upper(trim(coalesce(v_room->>'cleaningStatus','WAITING'))),
      upper(trim(coalesce(v_room->>'cleaningType','NORMAL'))),
      upper(trim(coalesce(v_room->>'assignmentType','SOLO'))),
      trim(coalesce(v_room->>'roommaidEmployeeNo','')),
      trim(coalesce(v_room->>'secondaryRoommaidEmployeeNo','')),
      trim(coalesce(v_room->>'qmEmployeeNo','')),
      trim(coalesce(v_room->>'operationalStatus','')),
      v_next_version,
      case when v_reset then null else (select cleaning_started_at from public.nova_rooms_current x where x.business_date=v_date and x.site=v_site and x.room_no=v_room_no) end,
      case when v_reset then null else (select cleaning_completed_at from public.nova_rooms_current x where x.business_date=v_date and x.site=v_site and x.room_no=v_room_no) end,
      v_actor,now()
    )
    on conflict(business_date,site,room_no) do update set
      building=excluded.building,
      room_status=excluded.room_status,
      cleaning_status=excluded.cleaning_status,
      cleaning_type=excluded.cleaning_type,
      assignment_type=excluded.assignment_type,
      roommaid_employee_no=excluded.roommaid_employee_no,
      secondary_roommaid_employee_no=excluded.secondary_roommaid_employee_no,
      qm_employee_no=excluded.qm_employee_no,
      operational_status=excluded.operational_status,
      version=excluded.version,
      cleaning_started_at=case when v_reset then null else public.nova_rooms_current.cleaning_started_at end,
      cleaning_completed_at=case when v_reset then null else public.nova_rooms_current.cleaning_completed_at end,
      updated_by=excluded.updated_by,
      updated_at=now();
    v_count:=v_count+1;
  end loop;

  delete from public.nova_rooms_current r
  where r.business_date=v_date and r.site=v_site
    and not exists (
      select 1 from jsonb_array_elements(p_rooms) j
      where trim(coalesce(j->>'roomNo',''))=r.room_no
    );

  update public.nova_room_upload_snapshots
  set is_active=false
  where business_date=v_date and site=v_site and is_active;

  insert into public.nova_room_upload_snapshots(
    business_date,site,upload_version,file_name,extension,apply_mode,counts,rooms_by_status,
    total_rooms,roommaid_assignment,registered_by,registered_at,is_active
  ) values(
    v_date,v_site,v_next_version,
    trim(coalesce(p_upload->>'fileName','')),
    trim(coalesce(p_upload->>'extension','')),
    upper(trim(coalesce(p_upload->>'applyMode',''))),
    coalesce(p_upload->'counts','{}'::jsonb),
    coalesce(p_upload->'roomsByStatus','{}'::jsonb),
    v_count,
    coalesce(p_upload->'roommaidAssignment','{}'::jsonb),
    v_actor,now(),true
  );

  insert into public.nova_reporting_state(
    business_date,site,native_complete,completed_by,completed_at,reason,version,updated_at
  ) values(
    v_date,v_site,false,'',null,'ROOM_UPLOAD_DB_FIRST_PENDING_FULL_REPORT',v_next_version,now()
  )
  on conflict(business_date,site) do update set
    native_complete=false,
    completed_by='',
    completed_at=null,
    reason='ROOM_UPLOAD_DB_FIRST_PENDING_FULL_REPORT',
    version=greatest(public.nova_reporting_state.version+1,excluded.version),
    updated_at=now();

  v_response:=jsonb_build_object(
    'ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,
    'totalRooms',v_count,'previousVersion',v_current_version,'version',v_next_version,
    'requestId',v_request_id,'idempotent',false
  );
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

revoke all on function public.nova_room_upload_apply_v2(text,text,jsonb,jsonb,bigint,bigint,text) from public;
revoke execute on function public.nova_room_upload_apply_v2(text,text,jsonb,jsonb,bigint,bigint,text) from anon;
grant execute on function public.nova_room_upload_apply_v2(text,text,jsonb,jsonb,bigint,bigint,text) to authenticated,service_role;
