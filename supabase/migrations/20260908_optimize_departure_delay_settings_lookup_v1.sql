-- NOVA_DEPARTURE_DELAY_SETTINGS_PERF_V1
-- Consolidate the four operation-setting checks into one read. Notification, locking and capture semantics are unchanged.
create or replace function nova_private.capture_departure_delays_v1(p_now timestamptz default now())
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
  select count(*) filter(where confirmed)::integer,
         max(value) filter(where code = case when v_weekend then 'WEEKEND_CHECKOUT' else 'WEEKDAY_CHECKOUT' end and confirmed),
         max(value) filter(where code = case when v_weekend then 'WEEKEND_ALERT' else 'WEEKDAY_ALERT' end and confirmed)
    into v_confirmed, v_checkout, v_alert
  from public.nova_operation_settings
  where code in ('WEEKDAY_CHECKOUT','WEEKDAY_ALERT','WEEKEND_CHECKOUT','WEEKEND_ALERT');

  if v_confirmed <> 4 then
    return jsonb_build_object('ok',true,'skipped',true,'reason','OPERATION_SETTINGS_UNCONFIRMED','inserted',0,'notifications',0);
  end if;

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
    select r.business_date,r.site,r.room_no,coalesce(r.building,''),
      case when v_weekend then '주말' else '주중' end,
      v_checkout,v_alert,0,null,'DB_CRON',greatest(coalesce(r.version,0),1),
      jsonb_build_object(
        'source','DB_CRON_NOTIFICATION_NATIVE_V4','roomStatus',r.room_status,
        'capturedAt',to_char(p_now at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
        'businessDateRule','09:00_CUTOFF'
      )
    from public.nova_rooms_current r
    where r.business_date = v_date and upper(coalesce(r.room_status,'')) = 'DUE_OUT'
    on conflict(business_date,site,room_no) do nothing
    returning site,room_no,building
  ), grouped as materialized (
    select site,array_agg(room_no order by room_no) as room_nos,count(*)::integer as room_count
    from inserted group by site
  ), recipients as materialized (
    select g.site,g.room_nos,g.room_count,u.employee_no
    from grouped g
    join public.nova_users u
      on u.enabled = true
     and upper(coalesce(u.role,'')) in ('ADMIN','ORDER','PUBLIC')
     and (upper(coalesce(u.role,'')) in ('ADMIN','ORDER') or coalesce(trim(u.default_site),'') = '' or trim(u.default_site) = g.site)
  ), emitted as materialized (
    select r.site,r.employee_no,
      nova_private.nova_notification_emit(
        r.employee_no,'DEPARTURE_DELAY','퇴실지연 ' || r.room_count::text || '실',
        r.site || ' · ' || array_to_string(r.room_nos[1:20], ', ') || case when r.room_count > 20 then ' 외 ' || (r.room_count - 20)::text || '실' else '' end,
        r.site,coalesce(r.room_nos[1],''),'DEPARTURE_DELAY',v_date::text || '|' || r.site,'HIGH',
        jsonb_build_object(
          'route','indicator','businessDate',v_date::text,'site',r.site,'roomNo',coalesce(r.room_nos[1],''),
          'roomNos',to_jsonb(r.room_nos),'roomCount',r.room_count,'checkoutTime',v_checkout,'alertTime',v_alert,
          'dayType',case when v_weekend then '주말' else '주중' end
        ),
        'DEPARTURE_DELAY|' || v_date::text || '|' || r.site || '|' || r.employee_no || '|' || md5(array_to_string(r.room_nos, ','))
      ) as notification_id
    from recipients r
  ), site_counts as materialized (
    select site,count(notification_id)::integer as recipient_count from emitted group by site
  ), updated as (
    update public.nova_departure_delays d
    set recipient_count = coalesce(sc.recipient_count,0),
        notified_at = case when coalesce(sc.recipient_count,0) > 0 then p_now else null end,
        detail = coalesce(d.detail,'{}'::jsonb) || jsonb_build_object(
          'notificationChannel','NOVA_NOTIFICATION_CENTER','recipientCount',coalesce(sc.recipient_count,0),
          'notifiedAt',case when coalesce(sc.recipient_count,0) > 0 then to_char(p_now at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') else '' end
        )
    from inserted i left join site_counts sc on sc.site = i.site
    where d.business_date = v_date and d.site = i.site and d.room_no = i.room_no
    returning d.site,d.room_no
  )
  select (select count(*)::integer from inserted),(select count(notification_id)::integer from emitted)
  into v_inserted,v_notifications;

  return jsonb_build_object('ok',true,'skipped',false,'dbFirst',true,'notificationNative',true,
    'businessDate',v_date::text,'dayType',case when v_weekend then '주말' else '주중' end,
    'checkoutTime',v_checkout,'alertTime',v_alert,'inserted',coalesce(v_inserted,0),'notifications',coalesce(v_notifications,0));
end;
$function$;
