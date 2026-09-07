-- NOVA_QM_INSPECTION_FINALIZE_DB_FIRST_V2
-- Staged only. Do not apply to production until the validate-only gate is green.
-- Atomically commits the QM terminal room state, inspection result, draft completion and room event.

create or replace function public.nova_qm_inspection_finalize_v2(
  p_payload jsonb,
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
  v_room public.nova_rooms_current%rowtype;
  v_draft public.nova_qm_drafts%rowtype;
  v_existing record;
  v_date date;
  v_site text := trim(coalesce(p_payload->>'site',''));
  v_room_no text := trim(coalesce(p_payload->>'roomNo',''));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_inspection_id text := trim(coalesce(p_payload->>'inspectionId',''));
  v_draft_id text := trim(coalesce(p_payload->>'draftId',''));
  v_result text := upper(trim(coalesce(p_payload->>'resultStatus','')));
  v_expected_version bigint := 0;
  v_started_at timestamptz;
  v_completed_at timestamptz := now();
  v_duration numeric;
  v_before_status text;
  v_response jsonb;
  v_item_fail_count integer := 0;
  v_custom_defect_count integer := 0;
begin
  if v_actor='' then
    raise exception using errcode='42501', message='로그인이 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,''))<>'QM' then
    raise exception using errcode='42501', message='QM 점검 저장 권한이 없습니다.';
  end if;

  if trim(coalesce(p_payload->>'businessDate','')) !~ '^\d{4}-\d{2}-\d{2}$' then
    raise exception '업무일자를 확인해 주세요.';
  end if;
  begin
    v_date:=trim(p_payload->>'businessDate')::date;
  exception when others then
    raise exception '업무일자를 확인해 주세요.';
  end;

  if v_site='' or v_room_no='' then
    raise exception 'QM 최종점검 식별정보가 없습니다.';
  end if;
  if v_result not in ('PASS','FAIL') then
    raise exception 'QM 점검결과를 확인해 주세요.';
  end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then
    raise exception '요청 ID 형식이 올바르지 않습니다.';
  end if;
  if not public.nova_is_active_qm_for_site(v_actor,v_site) then
    raise exception using errcode='42501', message='해당 사업장의 QM 권한이 없습니다.';
  end if;

  if jsonb_typeof(coalesce(p_payload->'answers','[]'::jsonb)) <> 'array'
     or jsonb_typeof(coalesce(p_payload->'defects','[]'::jsonb)) <> 'array' then
    raise exception 'QM 점검 상세자료 형식을 확인해 주세요.';
  end if;

  begin
    v_expected_version := greatest(0,coalesce(nullif(p_payload->>'expectedVersion','')::bigint,0));
  exception when others then
    raise exception 'QM 객실 버전을 확인해 주세요.';
  end;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'QM_INSPECTION_FINALIZE_V2',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json
      into v_existing
    from public.nova_request_dedup
    where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'QM_INSPECTION_FINALIZE_V2' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then
      return v_existing.response_json || jsonb_build_object('idempotent',true);
    end if;
    raise exception '동일 점검결과가 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_QM_FINAL|'||v_date::text||'|'||v_site||'|'||v_room_no,0));

  select * into v_room
  from public.nova_rooms_current r
  where r.business_date=v_date and r.site=v_site and r.room_no=v_room_no
  for update;
  if not found then
    raise exception 'DB 현재객실현황에서 해당 객실을 찾을 수 없습니다.';
  end if;
  if trim(coalesce(v_room.qm_employee_no,''))<>v_actor then
    raise exception using errcode='42501', message='본인에게 배정된 객실만 점검할 수 있습니다.';
  end if;
  v_before_status:=upper(trim(coalesce(v_room.cleaning_status,'')));
  if v_before_status<>'QM_CHECKING' then
    raise exception '점검중 상태의 객실에서만 체크리스트를 제출할 수 있습니다.';
  end if;
  if v_expected_version>0 and v_room.version<>v_expected_version then
    raise exception using errcode='40001', message='객실이 다른 사용자에 의해 먼저 변경되었습니다. 최신 화면을 불러온 뒤 다시 처리하세요.';
  end if;

  if v_draft_id<>'' then
    select * into v_draft
    from public.nova_qm_drafts d
    where d.draft_id=v_draft_id
      and d.business_date=v_date and d.site=v_site and d.room_no=v_room_no
      and d.qm_employee_no=v_actor
    for update;
  else
    select * into v_draft
    from public.nova_qm_drafts d
    where d.business_date=v_date and d.site=v_site and d.room_no=v_room_no
      and d.qm_employee_no=v_actor and d.status='IN_PROGRESS'
    order by d.saved_at desc,d.started_at desc
    limit 1
    for update;
  end if;

  if found then
    v_draft_id:=v_draft.draft_id;
    v_started_at:=v_draft.started_at;
  else
    begin
      v_started_at:=nullif(trim(coalesce(p_payload->>'startedAt','')),'')::timestamp at time zone 'Asia/Seoul';
    exception when others then
      v_started_at:=null;
    end;
  end if;
  if v_started_at is null then v_started_at:=v_completed_at; end if;
  v_duration:=round((extract(epoch from (v_completed_at-v_started_at))/60.0)::numeric,2);

  if v_inspection_id='' then
    v_inspection_id:=case when v_draft_id<>'' then v_draft_id else 'QMINS-'||replace(v_request_id,'-','') end;
  end if;

  if exists(select 1 from public.nova_qm_inspections i where i.inspection_id=v_inspection_id) then
    select request_id into v_existing
    from public.nova_qm_inspections i
    where i.inspection_id=v_inspection_id;
    if coalesce(v_existing.request_id,'')<>v_request_id then
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
      coalesce(v_room.roommaid_employee_no,''),coalesce(v_room.secondary_roommaid_employee_no,''),
      trim(coalesce(p_payload->>'checklistRevision','')),
      coalesce(p_payload->'answers','[]'::jsonb),coalesce(p_payload->'defects','[]'::jsonb),v_result,
      v_started_at,v_completed_at,v_duration,v_request_id,v_room.version,now(),now()
    );
  end if;

  update public.nova_qm_drafts
  set checklist_revision=trim(coalesce(p_payload->>'checklistRevision',checklist_revision)),
      answers=coalesce(p_payload->'answers',answers),
      defects=coalesce(p_payload->'defects',defects),
      status='COMPLETED',completed_at=v_completed_at,saved_at=now(),
      version=version+1,last_request_id=v_request_id
  where business_date=v_date and site=v_site and room_no=v_room_no
    and qm_employee_no=v_actor and status='IN_PROGRESS';

  update public.nova_rooms_current
  set cleaning_status='QM_COMPLETED',
      version=version+1,
      updated_by=v_actor,
      updated_at=now()
  where id=v_room.id
  returning * into v_room;

  select count(*)::integer into v_item_fail_count
  from jsonb_array_elements(coalesce(p_payload->'answers','[]'::jsonb)) a
  where upper(trim(coalesce(a->>'result','')))='FAIL';
  v_custom_defect_count:=jsonb_array_length(coalesce(p_payload->'defects','[]'::jsonb));

  insert into public.nova_room_events(
    request_id,business_date,site,room_no,action,before_status,after_status,
    employee_no,room_version,detail,event_time
  ) values(
    v_request_id,v_date,v_site,v_room_no,'QM_COMPLETE',v_before_status,'QM_COMPLETED',
    v_actor,v_room.version,
    jsonb_build_object(
      'role','QM','qmName',coalesce(v_user.name,''),'source','QM_INSPECTION_FINALIZE_DB_FIRST_V2',
      'qmEmployeeNo',v_actor,'cleaningStatus','QM_COMPLETED','qualityResult',v_result,
      'inspectionId',v_inspection_id,'draftId',v_draft_id,
      'checklistRevision',trim(coalesce(p_payload->>'checklistRevision','')),
      'failedCount',v_item_fail_count+v_custom_defect_count,
      'primaryEmployeeNo',coalesce(v_room.roommaid_employee_no,''),
      'secondaryEmployeeNo',coalesce(v_room.secondary_roommaid_employee_no,'')
    ),now()
  );

  v_response:=jsonb_build_object(
    'ok',true,'dbFirst',true,'finalizeRpcVersion','V2','inspectionId',v_inspection_id,'draftId',v_draft_id,
    'businessDate',v_date::text,'site',v_site,'roomNo',v_room_no,'resultStatus',v_result,
    'durationMinutes',v_duration,'requestId',v_request_id,'version',v_room.version,'idempotent',false,
    'room',jsonb_build_object(
      'businessDate',v_room.business_date::text,'site',v_room.site,'roomNo',v_room.room_no,
      'building',coalesce(v_room.building,''),'roomStatus',coalesce(v_room.room_status,''),
      'cleaningStatus',coalesce(v_room.cleaning_status,''),'cleaningType',coalesce(v_room.cleaning_type,'NORMAL'),
      'assignmentType',coalesce(v_room.assignment_type,'SOLO'),
      'roommaidEmployeeNo',coalesce(v_room.roommaid_employee_no,''),
      'secondaryRoommaidEmployeeNo',coalesce(v_room.secondary_roommaid_employee_no,''),
      'qmEmployeeNo',coalesce(v_room.qm_employee_no,''),'operationalStatus',coalesce(v_room.operational_status,''),
      'preassigned',coalesce(v_room.preassigned,false),'vip',coalesce(v_room.vip,false),'importantRoom',coalesce(v_room.important_room,false),
      'version',v_room.version,'updatedAt',v_room.updated_at
    )
  );
  update public.nova_request_dedup
  set response_json=v_response
  where request_id=v_request_id;
  return v_response;
end;
$function$;

revoke all on function public.nova_qm_inspection_finalize_v2(jsonb,text) from public;
revoke all on function public.nova_qm_inspection_finalize_v2(jsonb,text) from anon;
grant execute on function public.nova_qm_inspection_finalize_v2(jsonb,text) to authenticated;
grant execute on function public.nova_qm_inspection_finalize_v2(jsonb,text) to service_role;
