-- NOVA_REPORT_CLOSE_DB_FIRST_V1
-- Reporting/close foundation. No production read path is switched by this migration alone.

create table if not exists public.nova_room_upload_snapshots (
  business_date date not null,
  site text not null,
  upload_version bigint not null,
  file_name text not null default '',
  extension text not null default '',
  apply_mode text not null default '',
  counts jsonb not null default '{}'::jsonb,
  rooms_by_status jsonb not null default '{}'::jsonb,
  total_rooms integer not null default 0 check (total_rooms >= 0),
  roommaid_assignment jsonb not null default '{}'::jsonb,
  registered_by text not null,
  registered_at timestamptz not null default now(),
  is_active boolean not null default true,
  primary key (business_date, site, upload_version)
);
create unique index if not exists nova_room_upload_snapshots_one_active_idx
  on public.nova_room_upload_snapshots (business_date, site) where is_active;

create table if not exists public.nova_qm_inspections (
  inspection_id text primary key,
  business_date date not null,
  site text not null,
  room_no text not null,
  qm_employee_no text not null,
  roommaid_employee_no text not null default '',
  secondary_roommaid_employee_no text not null default '',
  checklist_revision text not null default '',
  answers jsonb not null default '[]'::jsonb,
  defects jsonb not null default '[]'::jsonb,
  result_status text not null check (result_status in ('PASS','FAIL')),
  started_at timestamptz,
  completed_at timestamptz not null,
  duration_minutes numeric,
  request_id text not null unique,
  source_version bigint not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists nova_qm_inspections_period_idx
  on public.nova_qm_inspections (business_date, site, qm_employee_no);
create index if not exists nova_qm_inspections_roommaid_idx
  on public.nova_qm_inspections (business_date, site, roommaid_employee_no);

create table if not exists public.nova_departure_delays (
  business_date date not null,
  site text not null,
  room_no text not null,
  building text not null default '',
  day_type text not null default '',
  checkout_time text not null default '',
  alert_time text not null default '',
  recipient_count integer not null default 0,
  notified_at timestamptz not null default now(),
  registered_by text not null default 'SYSTEM',
  version bigint not null default 0,
  detail jsonb not null default '{}'::jsonb,
  primary key (business_date, site, room_no)
);

create table if not exists public.nova_daily_close_snapshots (
  business_date date not null,
  site text not null,
  snapshot jsonb not null,
  source_signature text not null default '',
  source_updated_at text not null default '',
  closed_by text not null,
  closed_by_name text not null default '',
  closed_at timestamptz not null,
  version bigint not null default 1 check (version > 0),
  request_id text not null unique,
  is_active boolean not null default true,
  cancelled_by text not null default '',
  cancelled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (business_date, site)
);
create index if not exists nova_daily_close_snapshots_month_idx
  on public.nova_daily_close_snapshots (business_date, site) where is_active;

create table if not exists public.nova_reporting_state (
  business_date date not null,
  site text not null,
  native_complete boolean not null default false,
  completed_by text not null default '',
  completed_at timestamptz,
  reason text not null default '',
  version bigint not null default 1 check (version > 0),
  updated_at timestamptz not null default now(),
  primary key (business_date, site)
);

alter table public.nova_room_upload_snapshots enable row level security;
alter table public.nova_qm_inspections enable row level security;
alter table public.nova_departure_delays enable row level security;
alter table public.nova_daily_close_snapshots enable row level security;
alter table public.nova_reporting_state enable row level security;

revoke all on table public.nova_room_upload_snapshots from anon, authenticated;
revoke all on table public.nova_qm_inspections from anon, authenticated;
revoke all on table public.nova_departure_delays from anon, authenticated;
revoke all on table public.nova_daily_close_snapshots from anon, authenticated;
revoke all on table public.nova_reporting_state from anon, authenticated;
grant select, insert, update, delete on table public.nova_room_upload_snapshots to service_role;
grant select, insert, update, delete on table public.nova_qm_inspections to service_role;
grant select, insert, update, delete on table public.nova_departure_delays to service_role;
grant select, insert, update, delete on table public.nova_daily_close_snapshots to service_role;
grant select, insert, update, delete on table public.nova_reporting_state to service_role;

-- Enrich future roommaid START/COMPLETE events at the DB boundary so reports never depend on Sheet assignment state.
create or replace function nova_private.enrich_room_event_detail_v1()
returns trigger
language plpgsql
security definer
set search_path = public, nova_private, pg_catalog
as $$
declare
  v_room public.nova_rooms_current%rowtype;
  v_cleaning_type text;
  v_credit numeric := 1;
begin
  if upper(coalesce(new.action,'')) not in ('CLEANING_START','CLEANING_COMPLETE') then return new; end if;
  select * into v_room
  from public.nova_rooms_current
  where business_date=new.business_date and site=new.site and room_no=new.room_no;
  if not found then return new; end if;
  v_cleaning_type := upper(coalesce(nullif(v_room.cleaning_type,''),'NORMAL'));
  v_credit := case v_cleaning_type
    when 'DS' then 0.5
    when '5S' then 1.5
    when 'EVALUATION' then 1.5
    when 'STAFF_DORM' then 1.5
    when 'DEEP_CLEANING' then 1.5
    else 1
  end;
  new.detail := coalesce(new.detail,'{}'::jsonb) || jsonb_build_object(
    'cleaningType', v_cleaning_type,
    'assignmentType', upper(coalesce(nullif(v_room.assignment_type,''),'SOLO')),
    'primaryEmployeeNo', coalesce(v_room.roommaid_employee_no,''),
    'secondaryEmployeeNo', coalesce(v_room.secondary_roommaid_employee_no,''),
    'qmEmployeeNo', coalesce(v_room.qm_employee_no,''),
    'creditUnit', v_credit,
    'reportEnriched', true
  );
  return new;
end;
$$;

drop trigger if exists trg_nova_room_events_report_enrich on public.nova_room_events;
create trigger trg_nova_room_events_report_enrich
before insert on public.nova_room_events
for each row execute function nova_private.enrich_room_event_detail_v1();

create or replace function public.nova_room_upload_apply_v1(
  p_business_date text,
  p_site text,
  p_rooms jsonb,
  p_upload jsonb,
  p_expected_version bigint,
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
  v_next_version bigint := 1;
  v_count integer := 0;
  v_room jsonb;
  v_room_no text;
  v_response jsonb;
  v_existing record;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then raise exception using errcode='42501',message='객실 업로드 권한이 없습니다.'; end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0) or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then raise exception using errcode='42501',message='사업장 권한이 없습니다.'; end if;
  if jsonb_typeof(coalesce(p_rooms,'[]'::jsonb))<>'array' or jsonb_array_length(coalesce(p_rooms,'[]'::jsonb))=0 then raise exception '업로드 객실정보가 없습니다.'; end if;
  if jsonb_array_length(p_rooms)>5000 then raise exception '업로드 객실 수가 허용범위를 초과했습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'ROOM_UPLOAD_APPLY_V1',null) on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'ROOM_UPLOAD_APPLY_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if;
    if v_existing.response_json is not null then return v_existing.response_json || jsonb_build_object('idempotent',true); end if;
    raise exception '동일 요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_ROOM_UPLOAD|'||v_date::text||'|'||v_site,0));
  select coalesce(max(version),0) into v_current_version from public.nova_rooms_current where business_date=v_date and site=v_site;
  if p_expected_version is not null and p_expected_version>=0 and v_current_version<>p_expected_version then
    raise exception '객실정보가 다른 사용자에 의해 먼저 변경되었습니다. 다시 불러온 뒤 업로드해 주세요.';
  end if;
  v_next_version:=v_current_version+1;

  delete from public.nova_rooms_current where business_date=v_date and site=v_site;
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
      upper(trim(coalesce(v_room->>'roomStatus',''))),upper(trim(coalesce(v_room->>'cleaningStatus','WAITING'))),
      upper(trim(coalesce(v_room->>'cleaningType','NORMAL'))),upper(trim(coalesce(v_room->>'assignmentType','SOLO'))),
      trim(coalesce(v_room->>'roommaidEmployeeNo','')),trim(coalesce(v_room->>'secondaryRoommaidEmployeeNo','')),
      trim(coalesce(v_room->>'qmEmployeeNo','')),trim(coalesce(v_room->>'operationalStatus','')),
      v_next_version,null,null,v_actor,now()
    );
    v_count:=v_count+1;
  end loop;

  update public.nova_room_upload_snapshots set is_active=false where business_date=v_date and site=v_site and is_active;
  insert into public.nova_room_upload_snapshots(
    business_date,site,upload_version,file_name,extension,apply_mode,counts,rooms_by_status,total_rooms,roommaid_assignment,registered_by,registered_at,is_active
  ) values(
    v_date,v_site,v_next_version,trim(coalesce(p_upload->>'fileName','')),trim(coalesce(p_upload->>'extension','')),
    upper(trim(coalesce(p_upload->>'applyMode',''))),coalesce(p_upload->'counts','{}'::jsonb),coalesce(p_upload->'roomsByStatus','{}'::jsonb),
    v_count,coalesce(p_upload->'roommaidAssignment','{}'::jsonb),v_actor,now(),true
  );

  insert into public.nova_reporting_state(business_date,site,native_complete,completed_by,completed_at,reason,version,updated_at)
  values(v_date,v_site,false,'',null,'ROOM_UPLOAD_DB_FIRST_PENDING_FULL_REPORT',v_next_version,now())
  on conflict(business_date,site) do update set native_complete=false,completed_by='',completed_at=null,reason='ROOM_UPLOAD_DB_FIRST_PENDING_FULL_REPORT',version=greatest(public.nova_reporting_state.version+1,excluded.version),updated_at=now();

  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,'totalRooms',v_count,'version',v_next_version,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

create or replace function public.nova_daily_close_save_v1(
  p_business_date text,
  p_site text,
  p_snapshot jsonb,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text:=trim(coalesce(p_site,''));
  v_request_id text:=trim(coalesce(p_request_id,''));
  v_version bigint:=1;
  v_response jsonb;
  v_existing record;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then raise exception using errcode='42501',message='마감 저장 권한이 없습니다.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' or jsonb_typeof(coalesce(p_snapshot,'null'::jsonb))<>'object' then raise exception '마감정보를 확인해 주세요.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0) or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then raise exception using errcode='42501',message='사업장 권한이 없습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  insert into public.nova_request_dedup(request_id,employee_no,action,response_json) values(v_request_id,v_actor,'DAILY_CLOSE_SAVE_V1',null) on conflict(request_id) do nothing;
  if not found then select employee_no,action,response_json into v_existing from public.nova_request_dedup where request_id=v_request_id; if not found or v_existing.employee_no<>v_actor or v_existing.action<>'DAILY_CLOSE_SAVE_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if; if v_existing.response_json is not null then return v_existing.response_json||jsonb_build_object('idempotent',true); end if; raise exception '동일 요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.'; end if;
  perform pg_advisory_xact_lock(hashtextextended('NOVA_DAILY_CLOSE|'||v_date::text||'|'||v_site,0));
  select coalesce(version,0)+1 into v_version from public.nova_daily_close_snapshots where business_date=v_date and site=v_site;
  if v_version is null then v_version:=1; end if;
  insert into public.nova_daily_close_snapshots(business_date,site,snapshot,source_signature,source_updated_at,closed_by,closed_by_name,closed_at,version,request_id,is_active,cancelled_by,cancelled_at,created_at,updated_at)
  values(v_date,v_site,p_snapshot,trim(coalesce(p_snapshot->>'sourceSignature','')),trim(coalesce(p_snapshot->>'sourceUpdatedAt','')),v_actor,coalesce(v_user.name,''),now(),v_version,v_request_id,true,'',null,now(),now())
  on conflict(business_date,site) do update set snapshot=excluded.snapshot,source_signature=excluded.source_signature,source_updated_at=excluded.source_updated_at,closed_by=excluded.closed_by,closed_by_name=excluded.closed_by_name,closed_at=excluded.closed_at,version=public.nova_daily_close_snapshots.version+1,request_id=excluded.request_id,is_active=true,cancelled_by='',cancelled_at=null,updated_at=now();
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,'version',v_version,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

create or replace function public.nova_daily_close_cancel_v1(p_business_date text,p_site text,p_request_id text)
returns jsonb language plpgsql security definer set search_path=public,pg_catalog as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb); v_actor text:=trim(coalesce(v_claims->>'employee_no','')); v_user public.nova_users%rowtype; v_date date; v_site text:=trim(coalesce(p_site,'')); v_request_id text:=trim(coalesce(p_request_id,'')); v_response jsonb; v_existing record;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if; select * into v_user from public.nova_users where employee_no=v_actor and enabled=true; if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then raise exception using errcode='42501',message='마감 취소 권한이 없습니다.'; end if; begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end; if v_site='' then raise exception '사업장을 선택하세요.'; end if; if v_request_id !~ '^[A-Za-z0-9._:-]{8,160}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  insert into public.nova_request_dedup(request_id,employee_no,action,response_json) values(v_request_id,v_actor,'DAILY_CLOSE_CANCEL_V1',null) on conflict(request_id) do nothing;
  if not found then select employee_no,action,response_json into v_existing from public.nova_request_dedup where request_id=v_request_id; if not found or v_existing.employee_no<>v_actor or v_existing.action<>'DAILY_CLOSE_CANCEL_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if; if v_existing.response_json is not null then return v_existing.response_json||jsonb_build_object('idempotent',true); end if; raise exception '동일 요청이 처리 중입니다.'; end if;
  update public.nova_daily_close_snapshots set is_active=false,cancelled_by=v_actor,cancelled_at=now(),version=version+1,updated_at=now() where business_date=v_date and site=v_site and is_active;
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,'cancelled',found,'requestId',v_request_id,'idempotent',false); update public.nova_request_dedup set response_json=v_response where request_id=v_request_id; return v_response;
end; $$;

-- Read bundle returns Sheet-shaped objects so existing close/monthly calculators can be reused without changing business rules.
create or replace function public.nova_report_bundle_v1(p_business_date text,p_site text,p_include_history boolean default true)
returns jsonb language plpgsql security definer set search_path=public,pg_catalog as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb); v_actor text:=trim(coalesce(v_claims->>'employee_no','')); v_user public.nova_users%rowtype; v_date date; v_site text:=trim(coalesce(p_site,'')); v_native boolean:=false; v_rooms jsonb:='[]'::jsonb; v_history jsonb:='[]'::jsonb; v_close jsonb:=null; v_upload jsonb:=null;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if; select * into v_user from public.nova_users where employee_no=v_actor and enabled=true; if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then raise exception using errcode='42501',message='보고자료 조회 권한이 없습니다.'; end if; begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site<>'' and not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0) or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then raise exception using errcode='42501',message='사업장 권한이 없습니다.'; end if;
  select coalesce(bool_and(native_complete),false) into v_native from public.nova_reporting_state where business_date=v_date and (v_site='' or site=v_site);
  select coalesce(jsonb_agg(jsonb_build_object('업무일자',r.business_date::text,'사업장',r.site,'객실번호',r.room_no,'동',r.building,'객실상태',r.room_status,'청소상태',r.cleaning_status,'정비유형',r.cleaning_type,'배정유형',r.assignment_type,'룸메이드사번',r.roommaid_employee_no,'보조룸메이드사번',r.secondary_roommaid_employee_no,'QM사번',r.qm_employee_no,'객실운영상태',r.operational_status,'마지막변경버전',r.version,'수정일시',to_char(r.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS')) order by r.site,r.room_no),'[]'::jsonb) into v_rooms from public.nova_rooms_current r where r.business_date=v_date and (v_site='' or r.site=v_site);
  select to_jsonb(x) into v_upload from (select business_date::text as "businessDate",site,upload_version as version,file_name as "fileName",extension,apply_mode as "applyMode",counts,rooms_by_status as "roomsByStatus",total_rooms as "totalRooms",roommaid_assignment as "roommaidAssignment",to_char(registered_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') as "uploadedAt" from public.nova_room_upload_snapshots where business_date=v_date and (v_site='' or site=v_site) and is_active order by upload_version desc limit 1) x;
  if p_include_history and v_native then
    select coalesce(jsonb_agg(row_data order by event_sort),'[]'::jsonb) into v_history from (
      select e.event_time as event_sort, jsonb_build_object('기록ID',e.event_id::text,'기록구분',case when e.action like 'QM_%' then 'QM' when e.action='CHANGE_ROOM_STATUS' then 'ROOM_STATUS_CHANGE' else 'CLEANING' end,'업무일자',e.business_date::text,'사업장',e.site,'객실번호',e.room_no,'대상사번',case when e.action like 'CLEANING_%' then coalesce(e.detail->>'primaryEmployeeNo',e.employee_no) else e.employee_no end,'처리상태',case e.action when 'CLEANING_START' then 'ROOMMAID_START' when 'CLEANING_COMPLETE' then 'ROOMMAID_COMPLETE' else e.action end,'세부내용JSON',(coalesce(e.detail,'{}'::jsonb)||jsonb_build_object('requestId',e.request_id))::text,'등록사번',e.employee_no,'등록일시',to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'처리시작일시',case when e.action in ('CLEANING_START','QM_START') then to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') else '' end,'완료일시',case when e.action in ('CLEANING_COMPLETE','QM_COMPLETE') then to_char(e.event_time at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') else '' end,'변경버전',e.room_version,'삭제여부','N') row_data from public.nova_room_events e where e.business_date=v_date and (v_site='' or e.site=v_site) and (e.action like 'CLEANING_%' or e.action like 'QM_%' or e.action='CHANGE_ROOM_STATUS')
      union all
      select q.completed_at, jsonb_build_object('기록ID',q.inspection_id,'기록구분','QM_CHECKLIST','업무일자',q.business_date::text,'사업장',q.site,'객실번호',q.room_no,'대상사번',q.qm_employee_no,'처리상태',q.result_status,'세부내용JSON',jsonb_build_object('qmEmployeeNo',q.qm_employee_no,'roommaidEmployeeNo',q.roommaid_employee_no,'secondaryRoommaidEmployeeNo',q.secondary_roommaid_employee_no,'checklistRevision',q.checklist_revision,'answers',q.answers,'defects',q.defects,'startedAt',case when q.started_at is null then '' else to_char(q.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') end,'completedAt',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'durationMinutes',q.duration_minutes,'requestId',q.request_id)::text,'등록사번',q.qm_employee_no,'등록일시',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(q.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'처리시작일시',coalesce(to_char(q.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),'완료일시',to_char(q.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'변경버전',q.source_version,'삭제여부','N') from public.nova_qm_inspections q where q.business_date=v_date and (v_site='' or q.site=v_site)
      union all
      select h.updated_at, jsonb_build_object('기록ID',h.order_id,'기록구분','HOUSEMAN_ORDER','업무일자',h.business_date::text,'사업장',h.site,'객실번호',h.room_no,'대상사번',h.assigned_employee_no,'처리상태',h.status_code,'세부내용JSON',jsonb_build_object('items',h.items,'registeredBy',h.registered_by,'acceptedByEmployeeNo',h.accepted_by_employee_no,'assignmentMode',h.assignment_mode,'autoAssigned',h.auto_assigned,'assignedBuilding',h.assigned_building,'requester',h.requester)::text,'등록사번',h.registered_by,'등록일시',to_char(h.registered_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(h.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'파트',h.part,'품목',h.item_summary,'수량',h.quantity,'추가내용',h.note,'요청자',h.requester,'배정사번',h.assigned_employee_no,'처리자사번',h.processor_employee_no,'중요여부',case when h.important then 'Y' else 'N' end,'인수인계여부',case when h.handover then 'Y' else 'N' end,'접수일시',coalesce(to_char(h.accepted_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),'처리시작일시',coalesce(to_char(h.started_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),'완료일시',coalesce(to_char(h.completed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),''),'처리불가사유',h.unable_reason,'변경버전',h.version,'삭제여부','N') from public.nova_houseman_orders h where h.business_date=v_date and (v_site='' or h.site=v_site)
      union all
      select d.notified_at, jsonb_build_object('기록ID','DD-'||d.business_date::text||'-'||d.site||'-'||d.room_no,'기록구분','DEPARTURE_DELAY','업무일자',d.business_date::text,'사업장',d.site,'객실번호',d.room_no,'처리상태','NOTIFIED','세부내용JSON',(d.detail||jsonb_build_object('alertTime',d.alert_time,'checkoutTime',d.checkout_time,'dayType',d.day_type,'building',d.building,'recipientCount',d.recipient_count))::text,'등록사번',d.registered_by,'등록일시',to_char(d.notified_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'수정일시',to_char(d.notified_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'변경버전',d.version,'삭제여부','N') from public.nova_departure_delays d where d.business_date=v_date and (v_site='' or d.site=v_site)
    ) rows;
  end if;
  select snapshot into v_close from public.nova_daily_close_snapshots where business_date=v_date and (v_site='' or site=v_site) and is_active order by closed_at desc limit 1;
  return jsonb_build_object('ok',true,'dbFirst',true,'nativeComplete',v_native,'businessDate',v_date::text,'site',v_site,'currentRows',v_rooms,'historyRows',v_history,'uploadSnapshot',v_upload,'dailyClose',v_close);
end; $$;

-- Explicitly lock RPCs to authenticated custom NOVA JWTs / service role.
do $$
declare f regprocedure;
begin
  foreach f in array array[
    'public.nova_room_upload_apply_v1(text,text,jsonb,jsonb,bigint,text)'::regprocedure,
    'public.nova_daily_close_save_v1(text,text,jsonb,text)'::regprocedure,
    'public.nova_daily_close_cancel_v1(text,text,text)'::regprocedure,
    'public.nova_report_bundle_v1(text,text,boolean)'::regprocedure
  ] loop
    execute format('revoke all on function %s from public',f);
    execute format('revoke execute on function %s from anon',f);
    execute format('grant execute on function %s to authenticated, service_role',f);
  end loop;
end $$;
