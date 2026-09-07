-- ROOMMAID_CLOSE_HISTORY_DB_FIRST_V1
-- DB-native date/site only. Historical/incomplete dates remain on Sheet fallback.

create or replace function public.nova_roommaid_close_history_v1(
  p_business_date text,
  p_site text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_native boolean := false;
  v_state_version bigint := 0;
  v_items jsonb := '[]'::jsonb;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='룸메이드 마감 조회 권한이 없습니다.';
  end if;
  begin v_date := trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not (
    (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
    or v_site=coalesce(v_user.default_site,'')
    or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))
  ) then raise exception using errcode='42501', message='사업장 권한이 없습니다.'; end if;

  select s.native_complete, s.version into v_native, v_state_version
  from public.nova_reporting_state s
  where s.business_date=v_date and s.site=v_site;

  if not coalesce(v_native,false) then
    return jsonb_build_object(
      'ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,
      'nativeComplete',false,'stateVersion',coalesce(v_state_version,0),'items','[]'::jsonb
    );
  end if;

  with rows as (
    select u.registered_at as sort_at,
      jsonb_build_object(
        '기록ID','DB-UPLOAD-'||replace(u.business_date::text,'-','')||'-'||u.site||'-'||u.upload_version::text,
        '기록구분','ROOM_STATUS_UPLOAD','업무일자',u.business_date::text,'사업장',u.site,'객실번호','','대상사번','','처리상태','APPLIED',
        '세부내용JSON',jsonb_build_object('fileName',u.file_name,'extension',u.extension,'counts',u.counts,'totalRooms',u.total_rooms,'roomStatusSchema',1,'applyMode',u.apply_mode,'roomsByStatus',u.rooms_by_status,'roommaidAssignment',u.roommaid_assignment,'dbFirst',true)::text,
        '등록사번',u.registered_by,'등록일시',to_char(u.registered_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(u.registered_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'변경버전',u.upload_version,'삭제여부','N') as row_data
    from public.nova_room_upload_snapshots u where u.business_date=v_date and u.site=v_site and u.is_active

    union all

    select e.event_time,
      jsonb_build_object(
        '기록ID',coalesce(nullif(e.request_id,''),e.id::text),'기록구분',case when e.action like 'QM_%' then 'QM' when e.action='CHANGE_ROOM_STATUS' then 'ROOM_STATUS_CHANGE' else 'CLEANING' end,
        '업무일자',e.business_date::text,'사업장',e.site,'객실번호',e.room_no,'대상사번',case when e.action like 'CLEANING_%' then coalesce(nullif(e.detail->>'primaryEmployeeNo',''),e.employee_no) else e.employee_no end,
        '처리상태',case e.action when 'CLEANING_START' then 'ROOMMAID_START' when 'CLEANING_COMPLETE' then 'ROOMMAID_COMPLETE' else e.action end,
        '세부내용JSON',(coalesce(e.detail,'{}'::jsonb)||jsonb_build_object('requestId',e.request_id,'dbFirst',true))::text,'등록사번',e.employee_no,
        '등록일시',to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '처리시작일시',case when e.action in ('CLEANING_START','QM_START') then to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') else '' end,
        '완료일시',case when e.action in ('CLEANING_COMPLETE','QM_COMPLETE') then to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') else '' end,
        '변경버전',e.room_version,'삭제여부','N')
    from public.nova_room_events e where e.business_date=v_date and e.site=v_site and (e.action like 'CLEANING_%' or e.action like 'QM_%' or e.action='CHANGE_ROOM_STATUS')

    union all

    select q.completed_at,
      jsonb_build_object(
        '기록ID',q.inspection_id,'기록구분','QM_CHECKLIST','업무일자',q.business_date::text,'사업장',q.site,'객실번호',q.room_no,'대상사번',q.qm_employee_no,'처리상태',q.result_status,
        '세부내용JSON',jsonb_build_object('qmEmployeeNo',q.qm_employee_no,'roommaidEmployeeNo',q.roommaid_employee_no,'secondaryRoommaidEmployeeNo',q.secondary_roommaid_employee_no,'checklistRevision',q.checklist_revision,'answers',q.answers,'defects',q.defects,'startedAt',coalesce(to_char(q.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),'completedAt',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'durationMinutes',q.duration_minutes,'requestId',q.request_id,'dbFirst',true)::text,
        '등록사번',q.qm_employee_no,'등록일시',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(q.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '처리시작일시',coalesce(to_char(q.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),'완료일시',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'변경버전',q.source_version,'삭제여부','N')
    from public.nova_qm_inspections q where q.business_date=v_date and q.site=v_site

    union all

    select h.updated_at,
      jsonb_build_object(
        '기록ID',h.order_id,'기록구분','HOUSEMAN_ORDER','업무일자',h.business_date::text,'사업장',h.site,'객실번호',h.room_no,'대상사번',h.assigned_employee_no,'처리상태',h.status_code,
        '세부내용JSON',jsonb_build_object('items',h.items,'registeredBy',h.registered_by,'acceptedByEmployeeNo',h.accepted_by_employee_no,'assignmentMode',h.assignment_mode,'autoAssigned',h.auto_assigned,'assignedBuilding',h.assigned_building,'requester',h.requester,'dbFirst',true)::text,
        '등록사번',h.registered_by,'등록일시',to_char(h.registered_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(h.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '파트',h.part,'품목',h.item_summary,'수량',h.quantity,'추가내용',h.note,'요청자',h.requester,'배정사번',h.assigned_employee_no,'처리자사번',h.processor_employee_no,
        '중요여부',case when h.important then 'Y' else 'N' end,'인수인계여부',case when h.handover then 'Y' else 'N' end,
        '접수일시',coalesce(to_char(h.accepted_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),'처리시작일시',coalesce(to_char(h.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),'완료일시',coalesce(to_char(h.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),
        '처리불가사유',h.unable_reason,'변경버전',h.version,'삭제여부','N')
    from public.nova_houseman_orders h where h.business_date=v_date and h.site=v_site

    union all

    select d.notified_at,
      jsonb_build_object(
        '기록ID','DB-DD-'||replace(d.business_date::text,'-','')||'-'||d.site||'-'||d.room_no,'기록구분','DEPARTURE_DELAY','업무일자',d.business_date::text,'사업장',d.site,'객실번호',d.room_no,'처리상태','NOTIFIED',
        '세부내용JSON',(coalesce(d.detail,'{}'::jsonb)||jsonb_build_object('notificationType','DEPARTURE_DELAY','alertTime',d.alert_time,'checkoutTime',d.checkout_time,'dayType',d.day_type,'building',d.building,'recipientCount',d.recipient_count,'dbFirst',true))::text,
        '등록사번',d.registered_by,'등록일시',to_char(d.notified_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(d.notified_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'변경버전',d.version,'삭제여부','N')
    from public.nova_departure_delays d where d.business_date=v_date and d.site=v_site
  )
  select coalesce(jsonb_agg(row_data order by sort_at asc),'[]'::jsonb) into v_items from rows;

  return jsonb_build_object(
    'ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,
    'nativeComplete',true,'stateVersion',coalesce(v_state_version,0),'items',v_items
  );
end;
$$;

revoke all on function public.nova_roommaid_close_history_v1(text,text) from public, anon;
grant execute on function public.nova_roommaid_close_history_v1(text,text) to authenticated, service_role;
