-- MONTHLY_HISTORY_DB_FIRST_V1
-- Returns only business-date/site slices explicitly marked native_complete.
-- Existing Sheet history remains the fallback for all other slices.

create or replace function public.nova_monthly_history_v1(
  p_start_date text,
  p_end_date text,
  p_site text default ''
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
  v_start date;
  v_end date;
  v_site text := trim(coalesce(p_site,''));
  v_native_keys jsonb := '[]'::jsonb;
  v_items jsonb := '[]'::jsonb;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='월별조회 권한이 없습니다.';
  end if;
  begin v_start := trim(p_start_date)::date; exception when others then raise exception '시작일자를 확인해 주세요.'; end;
  begin v_end := trim(p_end_date)::date; exception when others then raise exception '종료일자를 확인해 주세요.'; end;
  if v_end < v_start then raise exception '조회 종료일자는 시작일자보다 빠를 수 없습니다.'; end if;
  if v_end - v_start > 62 then raise exception 'DB 월별조회 범위는 최대 63일입니다.'; end if;
  if v_site<>'' and not (
    (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
    or v_site=coalesce(v_user.default_site,'')
    or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))
  ) then raise exception using errcode='42501', message='사업장 권한이 없습니다.'; end if;

  select coalesce(jsonb_agg(jsonb_build_object(
    'businessDate', s.business_date::text,
    'site', s.site,
    'version', s.version,
    'completedAt', case when s.completed_at is null then '' else to_char(s.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') end
  ) order by s.business_date,s.site),'[]'::jsonb)
  into v_native_keys
  from public.nova_reporting_state s
  where s.native_complete=true
    and s.business_date between v_start and v_end
    and (v_site='' or s.site=v_site)
    and (
      (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
      or s.site=coalesce(v_user.default_site,'')
      or s.site=any(coalesce(v_user.allowed_sites,array[]::text[]))
    );

  with native_scope as (
    select s.business_date,s.site
    from public.nova_reporting_state s
    where s.native_complete=true
      and s.business_date between v_start and v_end
      and (v_site='' or s.site=v_site)
      and (
        (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
        or s.site=coalesce(v_user.default_site,'')
        or s.site=any(coalesce(v_user.allowed_sites,array[]::text[]))
      )
  ), rows as (
    select e.event_time as sort_at,
      jsonb_build_object(
        '기록ID',coalesce(nullif(e.request_id,''),e.id::text),
        '기록구분',case when e.action like 'QM_%' then 'QM' when e.action='CHANGE_ROOM_STATUS' then 'ROOM_STATUS_CHANGE' else 'CLEANING' end,
        '업무일자',e.business_date::text,'사업장',e.site,'객실번호',e.room_no,
        '대상사번',case when e.action like 'CLEANING_%' then coalesce(nullif(e.detail->>'primaryEmployeeNo',''),e.employee_no) else e.employee_no end,
        '처리상태',case e.action when 'CLEANING_START' then 'ROOMMAID_START' when 'CLEANING_COMPLETE' then 'ROOMMAID_COMPLETE' else e.action end,
        '세부내용JSON',(coalesce(e.detail,'{}'::jsonb)||jsonb_build_object('requestId',e.request_id))::text,
        '등록사번',e.employee_no,
        '등록일시',to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '수정일시',to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '처리시작일시',case when e.action in ('CLEANING_START','QM_START') then to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') else '' end,
        '완료일시',case when e.action in ('CLEANING_COMPLETE','QM_COMPLETE') then to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') else '' end,
        '변경버전',e.room_version,'삭제여부','N'
      ) as row_data
    from public.nova_room_events e
    join native_scope n on n.business_date=e.business_date and n.site=e.site
    where e.action like 'CLEANING_%' or e.action like 'QM_%' or e.action='CHANGE_ROOM_STATUS'

    union all

    select q.completed_at,
      jsonb_build_object(
        '기록ID',q.inspection_id,'기록구분','QM_CHECKLIST','업무일자',q.business_date::text,'사업장',q.site,'객실번호',q.room_no,
        '대상사번',q.qm_employee_no,'처리상태',q.result_status,
        '세부내용JSON',jsonb_build_object(
          'qmEmployeeNo',q.qm_employee_no,'roommaidEmployeeNo',q.roommaid_employee_no,
          'secondaryRoommaidEmployeeNo',q.secondary_roommaid_employee_no,'checklistRevision',q.checklist_revision,
          'answers',q.answers,'defects',q.defects,
          'startedAt',coalesce(to_char(q.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),
          'completedAt',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
          'durationMinutes',q.duration_minutes,'requestId',q.request_id
        )::text,
        '등록사번',q.qm_employee_no,'등록일시',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '수정일시',to_char(q.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '처리시작일시',coalesce(to_char(q.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),
        '완료일시',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '변경버전',q.source_version,'삭제여부','N'
      )
    from public.nova_qm_inspections q
    join native_scope n on n.business_date=q.business_date and n.site=q.site

    union all

    select h.updated_at,
      jsonb_build_object(
        '기록ID',h.order_id,'기록구분','HOUSEMAN_ORDER','업무일자',h.business_date::text,'사업장',h.site,'객실번호',h.room_no,
        '대상사번',h.assigned_employee_no,'처리상태',h.status_code,
        '세부내용JSON',jsonb_build_object(
          'items',h.items,'registeredBy',h.registered_by,'acceptedByEmployeeNo',h.accepted_by_employee_no,
          'assignmentMode',h.assignment_mode,'autoAssigned',h.auto_assigned,'assignedBuilding',h.assigned_building,'requester',h.requester
        )::text,
        '등록사번',h.registered_by,'등록일시',to_char(h.registered_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '수정일시',to_char(h.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        '파트',h.part,'품목',h.item_summary,'수량',h.quantity,'추가내용',h.note,'요청자',h.requester,
        '배정사번',h.assigned_employee_no,'처리자사번',h.processor_employee_no,
        '중요여부',case when h.important then 'Y' else 'N' end,
        '인수인계여부',case when h.handover then 'Y' else 'N' end,
        '접수일시',coalesce(to_char(h.accepted_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),
        '처리시작일시',coalesce(to_char(h.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),
        '완료일시',coalesce(to_char(h.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),
        '처리불가사유',h.unable_reason,'변경버전',h.version,'삭제여부','N'
      )
    from public.nova_houseman_orders h
    join native_scope n on n.business_date=h.business_date and n.site=h.site
  )
  select coalesce(jsonb_agg(row_data order by sort_at desc),'[]'::jsonb) into v_items from rows;

  return jsonb_build_object(
    'ok',true,'dbFirst',true,
    'startDate',v_start::text,'endDate',v_end::text,'site',v_site,
    'nativeKeys',v_native_keys,'items',v_items
  );
end;
$$;

revoke all on function public.nova_monthly_history_v1(text,text,text) from public;
revoke execute on function public.nova_monthly_history_v1(text,text,text) from anon;
grant execute on function public.nova_monthly_history_v1(text,text,text) to authenticated,service_role;
