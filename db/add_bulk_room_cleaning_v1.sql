-- NOVA DB-first bulk room cleaning primitive v1
-- Applied to Supabase nova-realtime on 2026-09-05.
-- Benchmark basis: 1,500 rooms, START + COMPLETE, Realtime broadcast enabled.
-- Production recommendation: 500 rooms/call x 3 parallel calls.
-- SECURITY: service_role only. Do not grant anon/authenticated.

create or replace function public.nova_bulk_room_cleaning_action_v1(
  p_items jsonb,
  p_action text,
  p_batch_request_id text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_action text := upper(trim(coalesce(p_action, '')));
  v_batch_id text := trim(coalesce(p_batch_request_id, ''));
  v_count integer;
  v_claimed_ids text[] := array[]::text[];
  v_failure_map jsonb := '{}'::jsonb;
  v_success_map jsonb := '{}'::jsonb;
  v_duplicate_map jsonb := '{}'::jsonb;
  v_response_map jsonb := '{}'::jsonb;
  v_results jsonb := '[]'::jsonb;
  v_updated integer := 0;
  v_failed integer := 0;
  v_duplicate integer := 0;
begin
  if v_action not in ('CLEANING_START', 'CLEANING_COMPLETE') then
    raise exception 'unsupported action: %', v_action;
  end if;
  if p_items is null or jsonb_typeof(p_items) <> 'array' then
    raise exception 'p_items must be a JSON array';
  end if;
  v_count := jsonb_array_length(p_items);
  if v_count < 1 or v_count > 500 then
    raise exception 'batch size must be between 1 and 500 (received %)', v_count;
  end if;

  -- Reject malformed batches before claiming IDs so input bugs never partially write live rooms.
  if exists (
    select 1
    from jsonb_array_elements(p_items) e(value)
    where trim(coalesce(value->>'requestId','')) = ''
       or trim(coalesce(value->>'employeeNo','')) = ''
       or trim(coalesce(value->>'site','')) = ''
       or trim(coalesce(value->>'roomNo','')) = ''
       or coalesce(value->>'businessDate','') !~ '^\d{4}-\d{2}-\d{2}$'
       or (trim(coalesce(value->>'expectedVersion','')) <> '' and coalesce(value->>'expectedVersion','') !~ '^\d+$')
  ) then
    raise exception 'bulk item validation failed';
  end if;
  if (
    select count(*) <> count(distinct trim(value->>'requestId'))
    from jsonb_array_elements(p_items) e(value)
  ) then
    raise exception 'requestId must be unique inside one bulk call';
  end if;

  -- Atomic request-id claims. Concurrent replay becomes a duplicate, not a second room write.
  with parsed as (
    select
      trim(value->>'requestId') as request_id,
      trim(value->>'employeeNo') as employee_no
    from jsonb_array_elements(p_items) e(value)
  ), claimed as (
    insert into public.nova_request_dedup(request_id, employee_no, action, response_json)
    select request_id, employee_no, v_action, null from parsed
    on conflict (request_id) do nothing
    returning request_id
  )
  select coalesce(array_agg(request_id), array[]::text[])
  into v_claimed_ids
  from claimed;

  -- Stable lock ordering prevents overlapping 500-room calls from taking row locks in reverse order.
  perform r.id
  from public.nova_rooms_current r
  join (
    select
      trim(value->>'requestId') as request_id,
      (value->>'businessDate')::date as business_date,
      trim(value->>'site') as site,
      trim(value->>'roomNo') as room_no
    from jsonb_array_elements(p_items) e(value)
  ) i on i.business_date = r.business_date and i.site = r.site and i.room_no = r.room_no
  where i.request_id = any(v_claimed_ids)
  order by r.business_date, r.site, r.room_no
  for update of r;

  -- Store deterministic state/version failures in dedup too, so retries cannot become accidental writes.
  with parsed as (
    select
      trim(value->>'requestId') as request_id,
      trim(value->>'employeeNo') as employee_no,
      upper(trim(coalesce(value->>'role','SYSTEM'))) as role_name,
      (value->>'businessDate')::date as business_date,
      trim(value->>'site') as site,
      trim(value->>'roomNo') as room_no,
      coalesce(nullif(trim(coalesce(value->>'expectedVersion','')), '')::bigint, 0) as expected_version
    from jsonb_array_elements(p_items) e(value)
  ), evaluated as (
    select i.*, r.id as room_id, r.room_status, r.cleaning_status, r.version,
      case
        when r.id is null then 'ROOM_NOT_FOUND'
        when i.expected_version > 0 and r.version <> i.expected_version then 'VERSION_CONFLICT'
        when v_action = 'CLEANING_START' and upper(coalesce(r.room_status,'')) = 'DUE_OUT' then 'DUE_OUT_BLOCKED'
        when v_action = 'CLEANING_START' and upper(coalesce(r.cleaning_status,'')) not in ('ASSIGNED','WAITING','REWORK') then 'INVALID_STATE'
        when v_action = 'CLEANING_COMPLETE' and upper(coalesce(r.cleaning_status,'')) <> 'CLEANING' then 'INVALID_STATE'
        else null
      end as error_code
    from parsed i
    left join public.nova_rooms_current r
      on r.business_date = i.business_date and r.site = i.site and r.room_no = i.room_no
    where i.request_id = any(v_claimed_ids)
  )
  select coalesce(jsonb_object_agg(request_id,
    jsonb_build_object(
      'ok', false,
      'code', error_code,
      'requestId', request_id,
      'businessDate', business_date,
      'site', site,
      'roomNo', room_no,
      'currentStatus', coalesce(cleaning_status,''),
      'roomStatus', coalesce(room_status,''),
      'expectedVersion', expected_version,
      'currentVersion', coalesce(version,0)
    )
  ), '{}'::jsonb)
  into v_failure_map
  from evaluated
  where error_code is not null;

  -- One set-based room UPDATE and one set-based event INSERT per <=500-room call.
  -- The existing nova_rooms_current trigger still broadcasts every changed room through Realtime.
  with parsed as (
    select
      trim(value->>'requestId') as request_id,
      trim(value->>'employeeNo') as employee_no,
      upper(trim(coalesce(value->>'role','SYSTEM'))) as role_name,
      (value->>'businessDate')::date as business_date,
      trim(value->>'site') as site,
      trim(value->>'roomNo') as room_no,
      coalesce(nullif(trim(coalesce(value->>'expectedVersion','')), '')::bigint, 0) as expected_version
    from jsonb_array_elements(p_items) e(value)
  ), eligible as (
    select i.*, r.id as room_id,
      upper(coalesce(r.cleaning_status,'')) as before_status,
      case
        when v_action = 'CLEANING_START' then 'CLEANING'
        when nullif(trim(coalesce(r.qm_employee_no,'')), '') is not null then 'QM_WAITING'
        else 'COMPLETED'
      end as after_status
    from parsed i
    join public.nova_rooms_current r
      on r.business_date = i.business_date and r.site = i.site and r.room_no = i.room_no
    where i.request_id = any(v_claimed_ids)
      and not (v_failure_map ? i.request_id)
  ), updated as (
    update public.nova_rooms_current r
    set cleaning_status = e.after_status,
        version = r.version + 1,
        cleaning_started_at = case when v_action = 'CLEANING_START' then now() else r.cleaning_started_at end,
        cleaning_completed_at = case when v_action = 'CLEANING_START' then null else now() end,
        updated_by = e.employee_no,
        updated_at = now()
    from eligible e
    where r.id = e.room_id
    returning
      e.request_id, e.employee_no, e.role_name, e.business_date, e.site, e.room_no,
      e.expected_version, e.before_status, e.after_status, r.version as new_version
  ), event_insert as (
    insert into public.nova_room_events(
      request_id, business_date, site, room_no, action,
      before_status, after_status, employee_no, room_version, detail, event_time
    )
    select
      u.request_id, u.business_date, u.site, u.room_no, v_action,
      u.before_status, u.after_status, u.employee_no, u.new_version,
      jsonb_build_object(
        'bulk', true,
        'batchRequestId', v_batch_id,
        'role', u.role_name,
        'expectedVersion', u.expected_version
      ),
      now()
    from updated u
    returning request_id
  )
  select coalesce(jsonb_object_agg(u.request_id,
    jsonb_build_object(
      'ok', true,
      'requestId', u.request_id,
      'businessDate', u.business_date,
      'site', u.site,
      'roomNo', u.room_no,
      'action', v_action,
      'beforeStatus', u.before_status,
      'afterStatus', u.after_status,
      'version', u.new_version
    )
  ), '{}'::jsonb)
  into v_success_map
  from updated u
  left join event_insert ei on ei.request_id = u.request_id;

  update public.nova_request_dedup d
  set response_json = v_failure_map -> d.request_id
  where d.request_id = any(v_claimed_ids) and v_failure_map ? d.request_id;

  update public.nova_request_dedup d
  set response_json = v_success_map -> d.request_id
  where d.request_id = any(v_claimed_ids) and v_success_map ? d.request_id;

  with parsed as (
    select trim(value->>'requestId') as request_id
    from jsonb_array_elements(p_items) e(value)
  )
  select coalesce(jsonb_object_agg(i.request_id,
    coalesce(d.response_json, jsonb_build_object('ok', true, 'requestId', i.request_id))
      || jsonb_build_object('duplicate', true)
  ), '{}'::jsonb)
  into v_duplicate_map
  from parsed i
  join public.nova_request_dedup d on d.request_id = i.request_id
  where not (i.request_id = any(v_claimed_ids));

  v_response_map := v_duplicate_map || v_failure_map || v_success_map;

  select coalesce(jsonb_agg(
    coalesce(v_response_map -> trim(value->>'requestId'),
      jsonb_build_object('ok', false, 'code', 'MISSING_RESULT', 'requestId', trim(value->>'requestId')))
    order by ord
  ), '[]'::jsonb)
  into v_results
  from jsonb_array_elements(p_items) with ordinality e(value, ord);

  select count(*) into v_updated from jsonb_each(v_success_map);
  select count(*) into v_failed from jsonb_each(v_failure_map);
  v_duplicate := v_count - coalesce(array_length(v_claimed_ids, 1), 0);

  return jsonb_build_object(
    'ok', true,
    'action', v_action,
    'batchRequestId', v_batch_id,
    'requested', v_count,
    'updated', v_updated,
    'failed', v_failed,
    'duplicates', v_duplicate,
    'results', v_results
  );
end;
$$;

revoke all on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) from public;
revoke all on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) from anon;
revoke all on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) from authenticated;
grant execute on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) to service_role;

comment on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) is
'NOVA DB-first set-based bulk cleaning primitive. Max 500 rooms/call; service_role only. Benchmark target is three parallel 500-room calls for 1,500-room bursts. Per-room request_id dedup, deterministic row locks, version/state checks, event log and Realtime trigger are preserved.';
