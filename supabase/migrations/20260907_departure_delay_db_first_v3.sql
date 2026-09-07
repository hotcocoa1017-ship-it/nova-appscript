-- NOVA_DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4
-- Existing 5-minute PostgreSQL cron owns delay detection and NOVA notification creation.
-- App badge/sound/Web Push is the only alert channel; no Telegram/Archive credential is reused.

alter table public.nova_departure_delays
  alter column notified_at drop not null,
  alter column notified_at drop default;

create or replace function nova_private.capture_departure_delays_v1(
  p_now timestamptz default now()
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_date date := public.nova_business_date_v1(p_now);
  v_time time := (p_now at time zone 'Asia/Seoul')::time;
  v_weekend boolean := extract(isodow from v_date) in (6,7);
  v_checkout text;
  v_alert text;
  v_confirmed integer := 0;
  v_inserted integer := 0;
  v_notifications integer := 0;
begin
  select count(*) into v_confirmed
  from public.nova_operation_settings
  where code in ('WEEKDAY_CHECKOUT','WEEKDAY_ALERT','WEEKEND_CHECKOUT','WEEKEND_ALERT')
    and confirmed;

  if v_confirmed <> 4 then
    return jsonb_build_object('ok',true,'skipped',true,'reason','OPERATION_SETTINGS_UNCONFIRMED','inserted',0,'notifications',0);
  end if;

  select value into v_checkout
  from public.nova_operation_settings
  where code = case when v_weekend then 'WEEKEND_CHECKOUT' else 'WEEKDAY_CHECKOUT' end
    and confirmed;

  select value into v_alert
  from public.nova_operation_settings
  where code = case when v_weekend then 'WEEKEND_ALERT' else 'WEEKDAY_ALERT' end
    and confirmed;

  if coalesce(v_checkout,'') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
     or coalesce(v_alert,'') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' then
    return jsonb_build_object('ok',false,'skipped',true,'reason','INVALID_OPERATION_TIME','inserted',0,'notifications',0);
  end if;

  if v_time < v_alert::time then
    return jsonb_build_object('ok',true,'skipped',true,'reason','BEFORE_ALERT_TIME','businessDate',v_date::text,'alertTime',v_alert,'inserted',0,'notifications',0);
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_DEPARTURE_DELAY|' || v_date::text, 0));

  with inserted as materialized (
    insert into public.nova_departure_delays(
      business_date,site,room_no,building,day_type,checkout_time,alert_time,
      recipient_count,notified_at,registered_by,version,detail
    )
    select
      r.business_date,r.site,r.room_no,coalesce(r.building,''),
      case when v_weekend then '주말' else '주중' end,
      v_checkout,v_alert,0,null,'DB_CRON',greatest(coalesce(r.version,0),1),
      jsonb_build_object(
        'source','DB_CRON_NOTIFICATION_NATIVE_V4',
        'roomStatus',r.room_status,
        'capturedAt',to_char(p_now at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        'businessDateRule','09:00_CUTOFF'
      )
    from public.nova_rooms_current r
    where r.business_date = v_date
      and upper(coalesce(r.room_status,'')) = 'DUE_OUT'
    on conflict(business_date,site,room_no) do nothing
    returning site,room_no,building
  ),
  grouped as materialized (
    select site,array_agg(room_no order by room_no) as room_nos,count(*)::integer as room_count
    from inserted
    group by site
  ),
  recipients as materialized (
    select g.site,g.room_nos,g.room_count,u.employee_no
    from grouped g
    join public.nova_users u
      on u.enabled = true
     and upper(coalesce(u.role,'')) in ('ADMIN','ORDER','PUBLIC')
     and (
       upper(coalesce(u.role,'')) in ('ADMIN','ORDER')
       or coalesce(trim(u.default_site),'') = ''
       or trim(u.default_site) = g.site
     )
  ),
  emitted as materialized (
    select
      r.site,
      r.employee_no,
      nova_private.nova_notification_emit(
        r.employee_no,
        'DEPARTURE_DELAY',
        '퇴실지연 ' || r.room_count::text || '실',
        r.site || ' · ' || array_to_string(r.room_nos[1:20], ', ')
          || case when r.room_count > 20 then ' 외 ' || (r.room_count - 20)::text || '실' else '' end,
        r.site,
        coalesce(r.room_nos[1],''),
        'DEPARTURE_DELAY',
        v_date::text || '|' || r.site,
        'HIGH',
        jsonb_build_object(
          'route','indicator',
          'businessDate',v_date::text,
          'site',r.site,
          'roomNo',coalesce(r.room_nos[1],''),
          'roomNos',to_jsonb(r.room_nos),
          'roomCount',r.room_count,
          'checkoutTime',v_checkout,
          'alertTime',v_alert,
          'dayType',case when v_weekend then '주말' else '주중' end
        ),
        'DEPARTURE_DELAY|' || v_date::text || '|' || r.site || '|' || r.employee_no || '|' || md5(array_to_string(r.room_nos, ','))
      ) as notification_id
    from recipients r
  ),
  site_counts as materialized (
    select site,count(notification_id)::integer as recipient_count
    from emitted
    group by site
  ),
  updated as (
    update public.nova_departure_delays d
    set
      recipient_count = coalesce(sc.recipient_count,0),
      notified_at = case when coalesce(sc.recipient_count,0) > 0 then p_now else null end,
      detail = coalesce(d.detail,'{}'::jsonb) || jsonb_build_object(
        'notificationChannel','NOVA_NOTIFICATION_CENTER',
        'recipientCount',coalesce(sc.recipient_count,0),
        'notifiedAt',case when coalesce(sc.recipient_count,0) > 0 then to_char(p_now at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') else '' end
      )
    from inserted i
    left join site_counts sc on sc.site = i.site
    where d.business_date = v_date and d.site = i.site and d.room_no = i.room_no
    returning d.site,d.room_no
  )
  select
    (select count(*)::integer from inserted),
    (select count(notification_id)::integer from emitted)
  into v_inserted,v_notifications;

  return jsonb_build_object(
    'ok',true,'skipped',false,'dbFirst',true,'notificationNative',true,
    'businessDate',v_date::text,
    'dayType',case when v_weekend then '주말' else '주중' end,
    'checkoutTime',v_checkout,'alertTime',v_alert,
    'inserted',coalesce(v_inserted,0),'notifications',coalesce(v_notifications,0)
  );
end;
$function$;

revoke all on function nova_private.capture_departure_delays_v1(timestamptz)
  from public,anon,authenticated;

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
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_weekend boolean;
  v_checkout text := '';
  v_alert text := '';
  v_today date := (now() at time zone 'Asia/Seoul')::date;
  v_now_time text := to_char(now() at time zone 'Asia/Seoul','HH24:MI');
  v_reached boolean := false;
  v_items jsonb := '[]'::jsonb;
  v_due integer := 0;
  v_notified integer := 0;
  v_sites jsonb := '[]'::jsonb;
begin
  if v_actor = '' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;

  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501',message='퇴실지연 조회 권한이 없습니다.';
  end if;

  begin v_date := trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;

  if v_site <> '' and not (
    (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
    or v_site=coalesce(v_user.default_site,'')
    or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))
  ) then
    raise exception using errcode='42501',message='사업장 권한이 없습니다.';
  end if;

  v_weekend := extract(isodow from v_date) in (6,7);
  select coalesce(value,'') into v_checkout from public.nova_operation_settings
  where code=case when v_weekend then 'WEEKEND_CHECKOUT' else 'WEEKDAY_CHECKOUT' end and confirmed=true;
  select coalesce(value,'') into v_alert from public.nova_operation_settings
  where code=case when v_weekend then 'WEEKEND_ALERT' else 'WEEKDAY_ALERT' end and confirmed=true;

  v_reached := v_date < v_today or (
    v_date = v_today
    and v_alert ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
    and v_now_time >= v_alert
  );

  with scope as (
    select r.site,r.room_no,r.building,r.updated_at,d.notified_at,d.recipient_count
    from public.nova_rooms_current r
    left join public.nova_departure_delays d
      on d.business_date=r.business_date and d.site=r.site and d.room_no=r.room_no
    where r.business_date=v_date
      and upper(coalesce(r.room_status,''))='DUE_OUT'
      and (v_site='' or r.site=v_site)
      and (
        (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
        or r.site=coalesce(v_user.default_site,'')
        or r.site=any(coalesce(v_user.allowed_sites,array[]::text[]))
      )
  )
  select
    count(*)::integer,
    count(*) filter(where notified_at is not null)::integer,
    coalesce(jsonb_agg(jsonb_build_object(
      'roomNo',room_no,'site',site,'building',coalesce(building,''),'roomStatus','DUE_OUT',
      'delayed',v_reached,'notified',notified_at is not null,
      'notifiedAt',case when notified_at is null then '' else to_char(notified_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') end,
      'recipientCount',coalesce(recipient_count,0),
      'updatedAt',to_char(updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS')
    ) order by site,room_no),'[]'::jsonb)
  into v_due,v_notified,v_items
  from scope;

  select coalesce(jsonb_agg(site order by site),'[]'::jsonb) into v_sites
  from (
    select distinct site from public.nova_rooms_current
    where business_date=v_date and coalesce(site,'')<>''
      and (
        (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
        or site=coalesce(v_user.default_site,'')
        or site=any(coalesce(v_user.allowed_sites,array[]::text[]))
      )
  ) s;

  return jsonb_build_object(
    'ok',true,'dbFirst',true,'notificationNative',true,
    'businessDate',v_date::text,'site',v_site,'sites',v_sites,
    'rule',jsonb_build_object(
      'businessDate',v_date::text,'weekend',v_weekend,
      'dayType',case when v_weekend then '주말' else '주중' end,
      'checkoutTime',v_checkout,'alertTime',v_alert,'reached',v_reached
    ),
    'user',jsonb_build_object('employeeNo',v_actor,'role',v_user.role),
    'summary',jsonb_build_object(
      'dueOut',v_due,
      'delayed',case when v_reached then v_due else 0 end,
      'notified',case when v_reached then v_notified else 0 end,
      'waitingNotification',case when v_reached then greatest(0,v_due-v_notified) else 0 end
    ),
    'items',v_items
  );
end;
$function$;

revoke all on function public.nova_departure_delay_dashboard_v1(text,text) from public,anon;
grant execute on function public.nova_departure_delay_dashboard_v1(text,text) to authenticated,service_role;
