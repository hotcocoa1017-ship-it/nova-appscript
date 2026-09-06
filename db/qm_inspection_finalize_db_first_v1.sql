-- QM_INSPECTION_FINALIZE_DB_FIRST_V1
-- Final quality result is committed to PostgreSQL before Sheet history is mirrored.

create or replace function public.nova_qm_inspection_finalize_v1(
  p_payload jsonb,
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
  v_site text := trim(coalesce(p_payload->>'site',''));
  v_room_no text := trim(coalesce(p_payload->>'roomNo',''));
  v_inspection_id text := trim(coalesce(p_payload->>'inspectionId',''));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_result text := upper(trim(coalesce(p_payload->>'resultStatus','')));
  v_room public.nova_rooms_current%rowtype;
  v_started_at timestamptz;
  v_completed_at timestamptz;
  v_duration numeric;
  v_source_version bigint := greatest(0,coalesce(nullif(p_payload->>'sourceVersion','')::bigint,0));
  v_response jsonb;
  v_existing record;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,''))<>'QM' then
    raise exception using errcode='42501', message='QM 점검 저장 권한이 없습니다.';
  end if;
  if trim(coalesce(p_payload->>'businessDate','')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_date:=trim(p_payload->>'businessDate')::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' or v_room_no='' or v_inspection_id='' then raise exception 'QM 최종점검 식별정보가 없습니다.'; end if;
  if v_result not in ('PASS','FAIL') then raise exception 'QM 점검결과를 확인해 주세요.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;

  select * into v_room
  from public.nova_rooms_current
  where business_date=v_date and site=v_site and room_no=v_room_no;
  if not found then raise exception 'DB 현재객실현황에서 해당 객실을 찾을 수 없습니다.'; end if;
  if trim(coalesce(v_room.qm_employee_no,''))<>v_actor then
    raise exception using errcode='42501', message='본인에게 배정된 객실만 점검할 수 있습니다.';
  end if;
  if upper(coalesce(v_room.cleaning_status,'')) not in ('QM_WAITING','COMPLETED','QM_CHECKING','QM_COMPLETED','REWORK') then
    raise exception '현재 DB 객실상태에서는 QM 점검을 완료할 수 없습니다.';
  end if;

  begin
    v_started_at := nullif(trim(coalesce(p_payload->>'startedAt','')),'')::timestamp at time zone 'Asia/Seoul';
  exception when others then v_started_at:=null; end;
  begin
    v_completed_at := nullif(trim(coalesce(p_payload->>'completedAt','')),'')::timestamp at time zone 'Asia/Seoul';
  exception when others then v_completed_at:=now(); end;
  if v_completed_at is null then v_completed_at:=now(); end if;
  begin v_duration:=nullif(p_payload->>'durationMinutes','')::numeric; exception when others then v_duration:=null; end;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'QM_INSPECTION_FINALIZE_V1',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing
    from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'QM_INSPECTION_FINALIZE_V1' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then
      return v_existing.response_json || jsonb_build_object('idempotent',true);
    end if;
    raise exception '동일 점검결과가 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_QM_INSPECTION|'||v_inspection_id,0));

  if exists(select 1 from public.nova_qm_inspections where inspection_id=v_inspection_id) then
    select request_id into v_request_id from public.nova_qm_inspections where inspection_id=v_inspection_id;
    if v_request_id<>trim(coalesce(p_request_id,'')) then
      raise exception '이미 확정된 QM 점검기록입니다.';
    end if;
  else
    insert into public.nova_qm_inspections(
      inspection_id,business_date,site,room_no,qm_employee_no,
      roommaid_employee_no,secondary_roommaid_employee_no,
      checklist_revision,answers,defects,result_status,
      started_at,completed_at,duration_minutes,request_id,source_version,created_at,updated_at
    ) values(
      v_inspection_id,v_date,v_site,v_room_no,v_actor,
      trim(coalesce(p_payload->>'roommaidEmployeeNo','')),
      trim(coalesce(p_payload->>'secondaryRoommaidEmployeeNo','')),
      trim(coalesce(p_payload->>'checklistRevision','')),
      coalesce(p_payload->'answers','[]'::jsonb),
      coalesce(p_payload->'defects','[]'::jsonb),
      v_result,v_started_at,v_completed_at,v_duration,
      trim(coalesce(p_request_id,'')),v_source_version,now(),now()
    );
  end if;

  update public.nova_qm_drafts
  set status='COMPLETED', completed_at=v_completed_at, saved_at=now(), last_request_id=trim(coalesce(p_request_id,''))
  where business_date=v_date and site=v_site and room_no=v_room_no and qm_employee_no=v_actor;

  v_response:=jsonb_build_object(
    'ok',true,'dbFirst',true,'inspectionId',v_inspection_id,
    'businessDate',v_date::text,'site',v_site,'roomNo',v_room_no,
    'resultStatus',v_result,'sourceVersion',v_source_version,
    'requestId',trim(coalesce(p_request_id,'')),'idempotent',false
  );
  update public.nova_request_dedup set response_json=v_response
  where request_id=trim(coalesce(p_request_id,''));
  return v_response;
end;
$$;

revoke all on function public.nova_qm_inspection_finalize_v1(jsonb,text) from public;
revoke execute on function public.nova_qm_inspection_finalize_v1(jsonb,text) from anon;
grant execute on function public.nova_qm_inspection_finalize_v1(jsonb,text) to authenticated,service_role;
