create table if not exists public.nova_operation_settings (
  code text primary key,
  value text not null,
  confirmed boolean not null default false,
  updated_by text not null default '',
  version bigint not null default 1 check (version > 0),
  updated_at timestamptz not null default now()
);
alter table public.nova_operation_settings enable row level security;
revoke all on table public.nova_operation_settings from anon, authenticated;
grant select,insert,update,delete on table public.nova_operation_settings to service_role;

insert into public.nova_operation_settings(code,value,confirmed,updated_by,version)
values
 ('DS_WEIGHT','0.5',false,'SYSTEM',1),
 ('WEEKDAY_CHECKOUT','12:00',false,'SYSTEM',1),
 ('WEEKDAY_ALERT','13:00',false,'SYSTEM',1),
 ('WEEKEND_CHECKOUT','11:00',false,'SYSTEM',1),
 ('WEEKEND_ALERT','12:00',false,'SYSTEM',1),
 ('DEPARTURE_TRIGGER_MINUTES','5',false,'SYSTEM',1),
 ('AUTO_CLOSE_ENABLED','N',false,'SYSTEM',1),
 ('AUTO_CLOSE_TIME','23:50',false,'SYSTEM',1),
 ('AUTO_CLOSE_NOTIFY_FAILURE','Y',false,'SYSTEM',1)
on conflict(code) do nothing;

create or replace function public.nova_operation_settings_save_v1(p_values jsonb,p_request_id text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_request_id text:=trim(coalesce(p_request_id,''));
  v_required text[]:=array['DS_WEIGHT','WEEKDAY_CHECKOUT','WEEKDAY_ALERT','WEEKEND_CHECKOUT','WEEKEND_ALERT','DEPARTURE_TRIGGER_MINUTES','AUTO_CLOSE_ENABLED','AUTO_CLOSE_TIME','AUTO_CLOSE_NOTIFY_FAILURE'];
  v_code text; v_value text; v_response jsonb; v_existing record; v_version bigint:=1;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,''))<>'ADMIN' then raise exception using errcode='42501',message='운영설정 저장 권한이 없습니다.'; end if;
  if jsonb_typeof(coalesce(p_values,'null'::jsonb))<>'object' then raise exception '운영설정 값을 확인해 주세요.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  foreach v_code in array v_required loop
    if not (p_values ? v_code) then raise exception '필수 운영설정 % 값이 없습니다.',v_code; end if;
  end loop;
  if coalesce(p_values->>'DS_WEIGHT','') !~ '^[0-9]+([.][0-9]+)?$' or (p_values->>'DS_WEIGHT')::numeric<0 or (p_values->>'DS_WEIGHT')::numeric>2 then raise exception 'D/S 인정 정비수 값을 확인해 주세요.'; end if;
  foreach v_code in array array['WEEKDAY_CHECKOUT','WEEKDAY_ALERT','WEEKEND_CHECKOUT','WEEKEND_ALERT','AUTO_CLOSE_TIME'] loop
    v_value:=trim(coalesce(p_values->>v_code,''));
    if v_value !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' then raise exception '운영설정 % 시간 형식을 확인해 주세요.',v_code; end if;
  end loop;
  if coalesce(p_values->>'DEPARTURE_TRIGGER_MINUTES','') not in ('1','5','10','15','30') then raise exception '퇴실지연 점검주기 값을 확인해 주세요.'; end if;
  if upper(coalesce(p_values->>'AUTO_CLOSE_ENABLED','')) not in ('Y','N') or upper(coalesce(p_values->>'AUTO_CLOSE_NOTIFY_FAILURE','')) not in ('Y','N') then raise exception '자동마감 Y/N 설정을 확인해 주세요.'; end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'OPERATION_SETTINGS_SAVE_V1',null) on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'OPERATION_SETTINGS_SAVE_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if;
    if v_existing.response_json is not null then return v_existing.response_json||jsonb_build_object('idempotent',true); end if;
    raise exception '동일 운영설정 저장 요청이 처리 중입니다.';
  end if;
  foreach v_code in array v_required loop
    v_value:=trim(coalesce(p_values->>v_code,''));
    insert into public.nova_operation_settings(code,value,confirmed,updated_by,version,updated_at)
    values(v_code,v_value,true,v_actor,1,now())
    on conflict(code) do update set value=excluded.value,confirmed=true,updated_by=excluded.updated_by,version=public.nova_operation_settings.version+1,updated_at=now();
  end loop;
  select coalesce(max(version),1) into v_version from public.nova_operation_settings where code=any(v_required);
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'confirmed',true,'version',v_version,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end; $$;
revoke all on function public.nova_operation_settings_save_v1(jsonb,text) from public;
revoke execute on function public.nova_operation_settings_save_v1(jsonb,text) from anon;
grant execute on function public.nova_operation_settings_save_v1(jsonb,text) to authenticated,service_role;

create or replace function nova_private.capture_departure_delays_v1(p_now timestamptz default now())
returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_date date:=(p_now at time zone 'Asia/Seoul')::date;
  v_time time:=(p_now at time zone 'Asia/Seoul')::time;
  v_weekend boolean:=extract(isodow from v_date) in (6,7);
  v_checkout text; v_alert text; v_confirmed integer:=0; v_inserted integer:=0;
begin
  select count(*) into v_confirmed from public.nova_operation_settings where code in ('WEEKDAY_CHECKOUT','WEEKDAY_ALERT','WEEKEND_CHECKOUT','WEEKEND_ALERT') and confirmed;
  if v_confirmed<>4 then return jsonb_build_object('ok',true,'skipped',true,'reason','OPERATION_SETTINGS_UNCONFIRMED','inserted',0); end if;
  select value into v_checkout from public.nova_operation_settings where code=case when v_weekend then 'WEEKEND_CHECKOUT' else 'WEEKDAY_CHECKOUT' end;
  select value into v_alert from public.nova_operation_settings where code=case when v_weekend then 'WEEKEND_ALERT' else 'WEEKDAY_ALERT' end;
  if v_alert is null or v_alert !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' then return jsonb_build_object('ok',false,'skipped',true,'reason','INVALID_ALERT_TIME','inserted',0); end if;
  if v_time < v_alert::time then return jsonb_build_object('ok',true,'skipped',true,'reason','BEFORE_ALERT_TIME','businessDate',v_date::text,'alertTime',v_alert,'inserted',0); end if;
  insert into public.nova_departure_delays(business_date,site,room_no,building,day_type,checkout_time,alert_time,recipient_count,notified_at,registered_by,version,detail)
  select r.business_date,r.site,r.room_no,coalesce(r.building,''),case when v_weekend then '주말' else '주중' end,v_checkout,v_alert,0,p_now,'DB_CRON',r.version,
    jsonb_build_object('source','DB_CRON_NATIVE','roomStatus',r.room_status,'capturedAt',to_char(p_now at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'))
  from public.nova_rooms_current r
  where r.business_date=v_date and upper(coalesce(r.room_status,''))='DUE_OUT'
  on conflict(business_date,site,room_no) do nothing;
  get diagnostics v_inserted=row_count;
  return jsonb_build_object('ok',true,'skipped',false,'businessDate',v_date::text,'dayType',case when v_weekend then '주말' else '주중' end,'checkoutTime',v_checkout,'alertTime',v_alert,'inserted',v_inserted);
end; $$;
revoke all on function nova_private.capture_departure_delays_v1(timestamptz) from public,anon,authenticated;
grant execute on function nova_private.capture_departure_delays_v1(timestamptz) to service_role;

create or replace function nova_private.evaluate_reporting_native_complete_v1(p_business_date date,p_site text,p_snapshot jsonb,p_actor text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_room_count integer:=0; v_upload_count integer:=0; v_upload_total integer:=0; v_cleaning_complete integer:=0; v_unenriched_cleaning integer:=0;
  v_qm_complete integer:=0; v_qm_inspections integer:=0; v_houseman_completed integer:=0; v_houseman_unable integer:=0; v_departure_delay integer:=0;
  v_expected_rooms integer:=coalesce((p_snapshot->>'totalRooms')::integer,0); v_expected_cleaning integer:=coalesce((p_snapshot->>'cleaningCompleted')::integer,0);
  v_expected_qm integer:=coalesce((p_snapshot->>'qmCompleted')::integer,0); v_expected_houseman_completed integer:=coalesce((p_snapshot->>'housemanCompleted')::integer,0);
  v_expected_houseman_unable integer:=coalesce((p_snapshot->>'housemanUnable')::integer,0); v_expected_departure_delay integer:=coalesce((p_snapshot->>'departureDelayCount')::integer,0);
  v_settings_confirmed integer:=0; v_ok boolean:=true; v_reasons text[]:=array[]::text[]; v_reason text:=''; v_version bigint:=1;
begin
  select count(*) into v_settings_confirmed from public.nova_operation_settings where code in ('WEEKDAY_CHECKOUT','WEEKDAY_ALERT','WEEKEND_CHECKOUT','WEEKEND_ALERT') and confirmed;
  select count(*) into v_room_count from public.nova_rooms_current where business_date=p_business_date and site=p_site;
  select count(*),coalesce(max(total_rooms),0) into v_upload_count,v_upload_total from public.nova_room_upload_snapshots where business_date=p_business_date and site=p_site and is_active;
  select count(*) filter(where action='CLEANING_COMPLETE'),count(*) filter(where action in ('CLEANING_START','CLEANING_COMPLETE') and coalesce((detail->>'reportEnriched')::boolean,false)=false),count(*) filter(where action='QM_COMPLETE') into v_cleaning_complete,v_unenriched_cleaning,v_qm_complete from public.nova_room_events where business_date=p_business_date and site=p_site;
  select count(*) into v_qm_inspections from public.nova_qm_inspections where business_date=p_business_date and site=p_site;
  select count(*) filter(where status_code='COMPLETED'),count(*) filter(where status_code='UNABLE') into v_houseman_completed,v_houseman_unable from public.nova_houseman_orders where business_date=p_business_date and site=p_site;
  select count(*) into v_departure_delay from public.nova_departure_delays where business_date=p_business_date and site=p_site;
  if v_settings_confirmed<>4 then v_ok:=false; v_reasons:=array_append(v_reasons,'OPERATION_SETTINGS_UNCONFIRMED'); end if;
  if v_upload_count<>1 then v_ok:=false; v_reasons:=array_append(v_reasons,'ACTIVE_UPLOAD_SNAPSHOT_MISSING'); end if;
  if v_expected_rooms<=0 or v_room_count<>v_expected_rooms or v_upload_total<>v_expected_rooms then v_ok:=false; v_reasons:=array_append(v_reasons,'ROOM_COUNT_MISMATCH'); end if;
  if v_unenriched_cleaning>0 then v_ok:=false; v_reasons:=array_append(v_reasons,'CLEANING_EVENT_NOT_ENRICHED'); end if;
  if v_cleaning_complete<>v_expected_cleaning then v_ok:=false; v_reasons:=array_append(v_reasons,'CLEANING_COMPLETE_MISMATCH'); end if;
  if v_qm_complete<>v_expected_qm or v_qm_inspections<>v_expected_qm then v_ok:=false; v_reasons:=array_append(v_reasons,'QM_INSPECTION_MISMATCH'); end if;
  if v_houseman_completed<>v_expected_houseman_completed or v_houseman_unable<>v_expected_houseman_unable then v_ok:=false; v_reasons:=array_append(v_reasons,'HOUSEMAN_RESULT_MISMATCH'); end if;
  if v_departure_delay<>v_expected_departure_delay then v_ok:=false; v_reasons:=array_append(v_reasons,'DEPARTURE_DELAY_MISMATCH'); end if;
  v_reason:=case when v_ok then 'DB_NATIVE_REPORT_COMPLETE' else array_to_string(v_reasons,',') end;
  select coalesce(version,0)+1 into v_version from public.nova_reporting_state where business_date=p_business_date and site=p_site; if v_version is null then v_version:=1; end if;
  insert into public.nova_reporting_state(business_date,site,native_complete,completed_by,completed_at,reason,version,updated_at)
  values(p_business_date,p_site,v_ok,case when v_ok then p_actor else '' end,case when v_ok then now() else null end,v_reason,v_version,now())
  on conflict(business_date,site) do update set native_complete=excluded.native_complete,completed_by=excluded.completed_by,completed_at=excluded.completed_at,reason=excluded.reason,version=public.nova_reporting_state.version+1,updated_at=now() returning version into v_version;
  return jsonb_build_object('ok',true,'nativeComplete',v_ok,'reason',v_reason,'version',v_version,'actual',jsonb_build_object('rooms',v_room_count,'uploadTotalRooms',v_upload_total,'cleaningComplete',v_cleaning_complete,'unenrichedCleaning',v_unenriched_cleaning,'qmCompleteEvents',v_qm_complete,'qmInspections',v_qm_inspections,'housemanCompleted',v_houseman_completed,'housemanUnable',v_houseman_unable,'departureDelay',v_departure_delay),'expected',jsonb_build_object('rooms',v_expected_rooms,'cleaningComplete',v_expected_cleaning,'qmCompleted',v_expected_qm,'housemanCompleted',v_expected_houseman_completed,'housemanUnable',v_expected_houseman_unable,'departureDelay',v_expected_departure_delay));
end; $$;
revoke all on function nova_private.evaluate_reporting_native_complete_v1(date,text,jsonb,text) from public,anon,authenticated;
grant execute on function nova_private.evaluate_reporting_native_complete_v1(date,text,jsonb,text) to service_role;

create or replace function public.nova_daily_close_cancel_v1(p_business_date text,p_site text,p_reason text,p_request_id text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb); v_actor text:=trim(coalesce(v_claims->>'employee_no','')); v_user public.nova_users%rowtype;
  v_date date; v_site text:=trim(coalesce(p_site,'')); v_request_id text:=trim(coalesce(p_request_id,'')); v_response jsonb; v_existing record; v_found boolean:=false;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,''))<>'ADMIN' then raise exception using errcode='42501',message='마감 취소 권한이 없습니다.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0) or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then raise exception using errcode='42501',message='사업장 권한이 없습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  insert into public.nova_request_dedup(request_id,employee_no,action,response_json) values(v_request_id,v_actor,'DAILY_CLOSE_CANCEL_V1',null) on conflict(request_id) do nothing;
  if not found then select employee_no,action,response_json into v_existing from public.nova_request_dedup where request_id=v_request_id; if not found or v_existing.employee_no<>v_actor or v_existing.action<>'DAILY_CLOSE_CANCEL_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if; if v_existing.response_json is not null then return v_existing.response_json||jsonb_build_object('idempotent',true); end if; raise exception '동일 마감취소 요청이 처리 중입니다.'; end if;
  perform pg_advisory_xact_lock(hashtextextended('NOVA_DAILY_CLOSE|'||v_date::text||'|'||v_site,0));
  update public.nova_daily_close_snapshots set is_active=false,cancelled_by=v_actor,cancelled_at=now(),updated_at=now() where business_date=v_date and site=v_site and is_active returning true into v_found;
  if not coalesce(v_found,false) then raise exception '취소할 DB 마감자료가 없습니다.'; end if;
  insert into public.nova_reporting_state(business_date,site,native_complete,completed_by,completed_at,reason,version,updated_at) values(v_date,v_site,false,'',null,'DAILY_CLOSE_CANCELLED'||case when trim(coalesce(p_reason,''))<>'' then ':'||left(trim(p_reason),120) else '' end,1,now()) on conflict(business_date,site) do update set native_complete=false,completed_by='',completed_at=null,reason=excluded.reason,version=public.nova_reporting_state.version+1,updated_at=now();
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,'cancelledBy',v_actor,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end; $$;
revoke all on function public.nova_daily_close_cancel_v1(text,text,text,text) from public;
revoke execute on function public.nova_daily_close_cancel_v1(text,text,text,text) from anon;
grant execute on function public.nova_daily_close_cancel_v1(text,text,text,text) to authenticated,service_role;

create or replace function public.nova_daily_close_save_v2(p_business_date text,p_site text,p_snapshot jsonb,p_request_id text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb); v_actor text:=trim(coalesce(v_claims->>'employee_no','')); v_user public.nova_users%rowtype;
  v_date date; v_site text:=trim(coalesce(p_site,'')); v_request_id text:=trim(coalesce(p_request_id,'')); v_closed_at timestamptz; v_version bigint:=1; v_response jsonb; v_existing record; v_gate jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then raise exception using errcode='42501',message='마감 저장 권한이 없습니다.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if jsonb_typeof(coalesce(p_snapshot,'null'::jsonb))<>'object' then raise exception '마감정보를 확인해 주세요.'; end if;
  if coalesce((p_snapshot->>'totalRooms')::integer,0)<=0 then raise exception '마감할 객실자료가 없습니다.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0) or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then raise exception using errcode='42501',message='사업장 권한이 없습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  begin v_closed_at:=nullif(trim(coalesce(p_snapshot->>'closedAt','')),'')::timestamp at time zone 'Asia/Seoul'; exception when others then v_closed_at:=now(); end; if v_closed_at is null then v_closed_at:=now(); end if;
  insert into public.nova_request_dedup(request_id,employee_no,action,response_json) values(v_request_id,v_actor,'DAILY_CLOSE_SAVE_V2',null) on conflict(request_id) do nothing;
  if not found then select employee_no,action,response_json into v_existing from public.nova_request_dedup where request_id=v_request_id; if not found or v_existing.employee_no<>v_actor or v_existing.action<>'DAILY_CLOSE_SAVE_V2' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if; if v_existing.response_json is not null then return v_existing.response_json||jsonb_build_object('idempotent',true); end if; raise exception '동일 마감요청이 처리 중입니다.'; end if;
  perform pg_advisory_xact_lock(hashtextextended('NOVA_DAILY_CLOSE|'||v_date::text||'|'||v_site,0));
  select coalesce(version,0)+1 into v_version from public.nova_daily_close_snapshots where business_date=v_date and site=v_site; if v_version is null then v_version:=1; end if;
  insert into public.nova_daily_close_snapshots(business_date,site,snapshot,source_signature,source_updated_at,closed_by,closed_by_name,closed_at,version,request_id,is_active,cancelled_by,cancelled_at,created_at,updated_at)
  values(v_date,v_site,p_snapshot,trim(coalesce(p_snapshot->>'sourceSignature','')),trim(coalesce(p_snapshot->>'sourceUpdatedAt','')),v_actor,coalesce(v_user.name,''),v_closed_at,v_version,v_request_id,true,'',null,now(),now())
  on conflict(business_date,site) do update set snapshot=excluded.snapshot,source_signature=excluded.source_signature,source_updated_at=excluded.source_updated_at,closed_by=excluded.closed_by,closed_by_name=excluded.closed_by_name,closed_at=excluded.closed_at,version=public.nova_daily_close_snapshots.version+1,request_id=excluded.request_id,is_active=true,cancelled_by='',cancelled_at=null,updated_at=now() returning version into v_version;
  v_gate:=nova_private.evaluate_reporting_native_complete_v1(v_date,v_site,p_snapshot,v_actor);
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,'version',v_version,'requestId',v_request_id,'idempotent',false,'closedAt',to_char(v_closed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'closedBy',v_actor,'closedByName',coalesce(v_user.name,''),'reportingGate',v_gate);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end; $$;
revoke all on function public.nova_daily_close_save_v2(text,text,jsonb,text) from public;
revoke execute on function public.nova_daily_close_save_v2(text,text,jsonb,text) from anon;
grant execute on function public.nova_daily_close_save_v2(text,text,jsonb,text) to authenticated,service_role;

do $$ begin
  if exists(select 1 from cron.job where jobname='nova-departure-delay-native-v1') then perform cron.unschedule('nova-departure-delay-native-v1'); end if;
  perform cron.schedule('nova-departure-delay-native-v1','*/5 * * * *',$cmd$select nova_private.capture_departure_delays_v1(now());$cmd$);
end $$;