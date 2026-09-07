-- NOVA_DEPARTURE_DELAY_DB_FIRST_V3
-- PostgreSQL owns delay detection/dedup/claim state. Telegram remains an Apps Script side effect.

alter table public.nova_departure_delays
  add column if not exists delivery_status text not null default 'PENDING',
  add column if not exists claimed_at timestamptz,
  add column if not exists claim_token text not null default '',
  add column if not exists last_error text not null default '';

alter table public.nova_departure_delays alter column notified_at drop not null;
alter table public.nova_departure_delays alter column notified_at drop default;

create index if not exists nova_departure_delays_delivery_idx
  on public.nova_departure_delays (business_date,delivery_status,claimed_at,site,room_no);

create or replace function public.nova_departure_delay_claim_service_v1(
  p_business_date text,
  p_claim_token text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_date date;
  v_claim text:=trim(coalesce(p_claim_token,''));
  v_weekend boolean;
  v_checkout text;
  v_alert text;
  v_today date:=(now() at time zone 'Asia/Seoul')::date;
  v_now_time text:=to_char(now() at time zone 'Asia/Seoul','HH24:MI');
  v_reached boolean:=false;
  v_items jsonb:='[]'::jsonb;
  v_setting_count integer:=0;
begin
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_claim !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception 'claim token 형식이 올바르지 않습니다.'; end if;
  v_weekend:=extract(isodow from v_date) in (6,7);

  select count(*) into v_setting_count
  from public.nova_operation_settings
  where code in ('WEEKDAY_CHECKOUT','WEEKDAY_ALERT','WEEKEND_CHECKOUT','WEEKEND_ALERT') and confirmed=true;
  if v_setting_count<>4 then
    return jsonb_build_object('ok',true,'dbFirst',true,'ready',false,'reason','OPERATION_SETTINGS_UNCONFIRMED','businessDate',v_date::text,'claimToken',v_claim,'items','[]'::jsonb);
  end if;

  select value into v_checkout from public.nova_operation_settings
  where code=case when v_weekend then 'WEEKEND_CHECKOUT' else 'WEEKDAY_CHECKOUT' end and confirmed=true;
  select value into v_alert from public.nova_operation_settings
  where code=case when v_weekend then 'WEEKEND_ALERT' else 'WEEKDAY_ALERT' end and confirmed=true;
  if coalesce(v_checkout,'') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' or coalesce(v_alert,'') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' then
    return jsonb_build_object('ok',true,'dbFirst',true,'ready',false,'reason','OPERATION_SETTINGS_INVALID','businessDate',v_date::text,'claimToken',v_claim,'items','[]'::jsonb);
  end if;

  v_reached:=v_date<v_today or (v_date=v_today and v_now_time>=v_alert);
  if not v_reached then
    return jsonb_build_object(
      'ok',true,'dbFirst',true,'ready',true,'reached',false,'businessDate',v_date::text,'claimToken',v_claim,
      'rule',jsonb_build_object('businessDate',v_date::text,'weekend',v_weekend,'dayType',case when v_weekend then '주말' else '주중' end,'checkoutTime',v_checkout,'alertTime',v_alert,'reached',false),
      'items','[]'::jsonb
    );
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_DEPARTURE_DELAY|'||v_date::text,0));

  -- Rooms that are no longer DUE_OUT are resolved and never notified.
  update public.nova_departure_delays d
  set delivery_status='RESOLVED',claim_token='',claimed_at=null,last_error='',detail=coalesce(d.detail,'{}'::jsonb)||jsonb_build_object('resolvedAt',now())
  where d.business_date=v_date and d.delivery_status in ('PENDING','CLAIMED')
    and not exists(
      select 1 from public.nova_rooms_current r
      where r.business_date=d.business_date and r.site=d.site and r.room_no=d.room_no and r.room_status='DUE_OUT'
    );

  insert into public.nova_departure_delays(
    business_date,site,room_no,building,day_type,checkout_time,alert_time,recipient_count,
    notified_at,registered_by,version,detail,delivery_status,claimed_at,claim_token,last_error
  )
  select r.business_date,r.site,r.room_no,coalesce(r.building,''),case when v_weekend then '주말' else '주중' end,
    v_checkout,v_alert,0,null,'SYSTEM',greatest(coalesce(r.version,0),1),
    jsonb_build_object('source','NOVA_DEPARTURE_DELAY_DB_FIRST_V3'),'PENDING',null,'',''
  from public.nova_rooms_current r
  where r.business_date=v_date and r.room_status='DUE_OUT'
  on conflict(business_date,site,room_no) do nothing;

  -- A crashed worker releases its claim after ten minutes.
  update public.nova_departure_delays
  set delivery_status='PENDING',claim_token='',claimed_at=null,last_error=case when last_error='' then 'STALE_CLAIM_RELEASED' else last_error end
  where business_date=v_date and delivery_status='CLAIMED' and claimed_at < now()-interval '10 minutes';

  with candidates as (
    select business_date,site,room_no
    from public.nova_departure_delays
    where business_date=v_date and delivery_status='PENDING'
    order by site,room_no
    for update skip locked
  ), claimed as (
    update public.nova_departure_delays d
    set delivery_status='CLAIMED',claim_token=v_claim,claimed_at=now(),last_error=''
    from candidates c
    where d.business_date=c.business_date and d.site=c.site and d.room_no=c.room_no
    returning d.site,d.room_no,d.building,d.day_type,d.checkout_time,d.alert_time,d.version
  )
  select coalesce(jsonb_agg(jsonb_build_object(
      'site',site,'roomNo',room_no,'building',building,'dayType',day_type,'checkoutTime',checkout_time,'alertTime',alert_time,'version',version
    ) order by site,room_no),'[]'::jsonb)
  into v_items from claimed;

  return jsonb_build_object(
    'ok',true,'dbFirst',true,'ready',true,'reached',true,'businessDate',v_date::text,'claimToken',v_claim,
    'rule',jsonb_build_object('businessDate',v_date::text,'weekend',v_weekend,'dayType',case when v_weekend then '주말' else '주중' end,'checkoutTime',v_checkout,'alertTime',v_alert,'reached',true),
    'items',v_items
  );
end;
$function$;

create or replace function public.nova_departure_delay_finalize_service_v1(
  p_claim_token text,
  p_results jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_claim text:=trim(coalesce(p_claim_token,''));
  v_item jsonb;
  v_site text;
  v_room text;
  v_ok boolean;
  v_recipient_count integer;
  v_error text;
  v_updated integer:=0;
begin
  if v_claim !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception 'claim token 형식이 올바르지 않습니다.'; end if;
  if jsonb_typeof(coalesce(p_results,'[]'::jsonb))<>'array' then raise exception '알림 처리결과를 확인해 주세요.'; end if;
  for v_item in select value from jsonb_array_elements(coalesce(p_results,'[]'::jsonb)) loop
    v_site:=trim(coalesce(v_item->>'site',''));
    v_room:=trim(coalesce(v_item->>'roomNo',''));
    v_ok:=coalesce((v_item->>'ok')::boolean,false);
    begin v_recipient_count:=greatest(0,coalesce((v_item->>'recipientCount')::integer,0)); exception when others then v_recipient_count:=0; end;
    v_error:=left(trim(coalesce(v_item->>'error','')),500);
    if v_site='' or v_room='' then continue; end if;
    if v_ok then
      update public.nova_departure_delays
      set delivery_status='NOTIFIED',notified_at=now(),recipient_count=v_recipient_count,claim_token='',claimed_at=null,last_error='',
          detail=coalesce(detail,'{}'::jsonb)||jsonb_build_object('notifiedAt',now(),'recipientCount',v_recipient_count)
      where site=v_site and room_no=v_room and claim_token=v_claim and delivery_status='CLAIMED';
    else
      update public.nova_departure_delays
      set delivery_status='PENDING',claim_token='',claimed_at=null,last_error=coalesce(nullif(v_error,''),'DELIVERY_NOT_CONFIRMED')
      where site=v_site and room_no=v_room and claim_token=v_claim and delivery_status='CLAIMED';
    end if;
    get diagnostics v_recipient_count = row_count;
    v_updated:=v_updated+v_recipient_count;
  end loop;
  return jsonb_build_object('ok',true,'dbFirst',true,'claimToken',v_claim,'updated',v_updated);
end;
$function$;

create or replace function public.nova_departure_delay_dashboard_v1(
  p_business_date text,
  p_site text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text:=trim(coalesce(p_site,''));
  v_weekend boolean;
  v_checkout text;
  v_alert text;
  v_today date:=(now() at time zone 'Asia/Seoul')::date;
  v_now_time text:=to_char(now() at time zone 'Asia/Seoul','HH24:MI');
  v_reached boolean:=false;
  v_items jsonb:='[]'::jsonb;
  v_due integer:=0;
  v_notified integer:=0;
  v_sites jsonb:='[]'::jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then raise exception using errcode='42501',message='퇴실지연 조회 권한이 없습니다.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site<>'' and not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
      or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501',message='사업장 권한이 없습니다.';
  end if;
  v_weekend:=extract(isodow from v_date) in (6,7);
  select value into v_checkout from public.nova_operation_settings where code=case when v_weekend then 'WEEKEND_CHECKOUT' else 'WEEKDAY_CHECKOUT' end and confirmed=true;
  select value into v_alert from public.nova_operation_settings where code=case when v_weekend then 'WEEKEND_ALERT' else 'WEEKDAY_ALERT' end and confirmed=true;
  v_reached:=v_date<v_today or (v_date=v_today and v_now_time>=coalesce(v_alert,'99:99'));

  with scope as (
    select r.business_date,r.site,r.room_no,r.building,r.room_status,r.updated_at,d.delivery_status,d.notified_at,d.recipient_count,d.last_error
    from public.nova_rooms_current r
    left join public.nova_departure_delays d on d.business_date=r.business_date and d.site=r.site and d.room_no=r.room_no
    where r.business_date=v_date and r.room_status='DUE_OUT'
      and (v_site='' or r.site=v_site)
      and ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
        or r.site=coalesce(v_user.default_site,'') or r.site=any(coalesce(v_user.allowed_sites,array[]::text[])))
  )
  select count(*),count(*) filter(where delivery_status='NOTIFIED'),
    coalesce(jsonb_agg(jsonb_build_object(
      'roomNo',room_no,'site',site,'building',coalesce(building,''),'roomStatus','DUE_OUT','delayed',v_reached,
      'notified',delivery_status='NOTIFIED','deliveryStatus',coalesce(delivery_status,''),
      'notifiedAt',case when notified_at is null then '' else to_char(notified_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') end,
      'recipientCount',coalesce(recipient_count,0),'lastError',coalesce(last_error,''),
      'updatedAt',to_char(updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS')
    ) order by site,room_no),'[]'::jsonb)
  into v_due,v_notified,v_items from scope;

  select coalesce(jsonb_agg(site order by site),'[]'::jsonb) into v_sites
  from (select distinct site from public.nova_rooms_current where business_date=v_date and coalesce(site,'')<>''
    and ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
      or site=coalesce(v_user.default_site,'') or site=any(coalesce(v_user.allowed_sites,array[]::text[])))) s;

  return jsonb_build_object(
    'ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,'sites',v_sites,
    'rule',jsonb_build_object('businessDate',v_date::text,'weekend',v_weekend,'dayType',case when v_weekend then '주말' else '주중' end,'checkoutTime',coalesce(v_checkout,''),'alertTime',coalesce(v_alert,''),'reached',v_reached),
    'user',jsonb_build_object('employeeNo',v_actor,'role',v_user.role),
    'summary',jsonb_build_object('dueOut',v_due,'delayed',case when v_reached then v_due else 0 end,'notified',case when v_reached then v_notified else 0 end,'waitingNotification',case when v_reached then greatest(0,v_due-v_notified) else 0 end),
    'items',v_items
  );
end;
$function$;

revoke all on function public.nova_departure_delay_claim_service_v1(text,text) from public,anon,authenticated;
revoke all on function public.nova_departure_delay_finalize_service_v1(text,jsonb) from public,anon,authenticated;
grant execute on function public.nova_departure_delay_claim_service_v1(text,text) to service_role;
grant execute on function public.nova_departure_delay_finalize_service_v1(text,jsonb) to service_role;
revoke all on function public.nova_departure_delay_dashboard_v1(text,text) from public,anon;
grant execute on function public.nova_departure_delay_dashboard_v1(text,text) to authenticated;
grant execute on function public.nova_departure_delay_dashboard_v1(text,text) to service_role;
