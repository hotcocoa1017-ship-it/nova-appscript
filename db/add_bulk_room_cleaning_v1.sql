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
  v_count integer := 0;
  v_updated integer := 0;
  v_failed integer := 0;
  v_duplicate integer := 0;
  v_results jsonb := '[]'::jsonb;
  v_item jsonb;
  v_request_id text;
  v_employee_no text;
  v_role text;
  v_business_date date;
  v_site text;
  v_room_no text;
  v_expected_version bigint;
  v_claimed text;
  v_previous jsonb;
  v_room public.nova_rooms_current%rowtype;
  v_after_status text;
  v_new_version bigint;
  v_response jsonb;
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

  for v_item in
    select value
    from jsonb_array_elements(p_items)
    order by coalesce(value->>'businessDate',''), coalesce(value->>'site',''), coalesce(value->>'roomNo',''), coalesce(value->>'requestId','')
  loop
    begin
      v_request_id := trim(coalesce(v_item->>'requestId', ''));
      v_employee_no := trim(coalesce(v_item->>'employeeNo', ''));
      v_role := upper(trim(coalesce(v_item->>'role', 'SYSTEM')));
      v_site := trim(coalesce(v_item->>'site', ''));
      v_room_no := trim(coalesce(v_item->>'roomNo', ''));
      v_business_date := nullif(trim(coalesce(v_item->>'businessDate', '')), '')::date;
      v_expected_version := coalesce(nullif(trim(coalesce(v_item->>'expectedVersion','')), '')::bigint, 0);

      if v_request_id = '' or v_employee_no = '' or v_business_date is null or v_site = '' or v_room_no = '' then
        v_response := jsonb_build_object(
          'ok', false, 'code', 'INVALID_REQUEST', 'requestId', v_request_id,
          'businessDate', v_business_date, 'site', v_site, 'roomNo', v_room_no
        );
        v_failed := v_failed + 1;
        v_results := v_results || jsonb_build_array(v_response);
        continue;
      end if;

      v_claimed := null;
      insert into public.nova_request_dedup(request_id, employee_no, action, response_json)
      values (v_request_id, v_employee_no, v_action, null)
      on conflict (request_id) do nothing
      returning request_id into v_claimed;

      if v_claimed is null then
        select response_json into v_previous
        from public.nova_request_dedup
        where request_id = v_request_id;
        v_response := coalesce(v_previous, jsonb_build_object('ok', true, 'requestId', v_request_id))
          || jsonb_build_object('duplicate', true);
        v_duplicate := v_duplicate + 1;
        v_results := v_results || jsonb_build_array(v_response);
        continue;
      end if;

      select * into v_room
      from public.nova_rooms_current
      where business_date = v_business_date and site = v_site and room_no = v_room_no
      for update;

      if not found then
        v_response := jsonb_build_object('ok', false, 'code', 'ROOM_NOT_FOUND', 'requestId', v_request_id,
          'businessDate', v_business_date, 'site', v_site, 'roomNo', v_room_no);
      elsif v_expected_version > 0 and v_room.version <> v_expected_version then
        v_response := jsonb_build_object('ok', false, 'code', 'VERSION_CONFLICT', 'requestId', v_request_id,
          'businessDate', v_business_date, 'site', v_site, 'roomNo', v_room_no,
          'expectedVersion', v_expected_version, 'currentVersion', v_room.version);
      elsif v_action = 'CLEANING_START' and upper(coalesce(v_room.room_status,'')) = 'DUE_OUT' then
        v_response := jsonb_build_object('ok', false, 'code', 'DUE_OUT_BLOCKED', 'requestId', v_request_id,
          'businessDate', v_business_date, 'site', v_site, 'roomNo', v_room_no,
          'currentStatus', v_room.cleaning_status, 'roomStatus', v_room.room_status, 'currentVersion', v_room.version);
      elsif v_action = 'CLEANING_START' and upper(coalesce(v_room.cleaning_status,'')) not in ('ASSIGNED','WAITING','REWORK') then
        v_response := jsonb_build_object('ok', false, 'code', 'INVALID_STATE', 'requestId', v_request_id,
          'businessDate', v_business_date, 'site', v_site, 'roomNo', v_room_no,
          'currentStatus', v_room.cleaning_status, 'currentVersion', v_room.version);
      elsif v_action = 'CLEANING_COMPLETE' and upper(coalesce(v_room.cleaning_status,'')) <> 'CLEANING' then
        v_response := jsonb_build_object('ok', false, 'code', 'INVALID_STATE', 'requestId', v_request_id,
          'businessDate', v_business_date, 'site', v_site, 'roomNo', v_room_no,
          'currentStatus', v_room.cleaning_status, 'currentVersion', v_room.version);
      else
        if v_action = 'CLEANING_START' then
          v_after_status := 'CLEANING';
          update public.nova_rooms_current
          set cleaning_status = v_after_status,
              version = version + 1,
              cleaning_started_at = now(),
              cleaning_completed_at = null,
              updated_by = v_employee_no,
              updated_at = now()
          where id = v_room.id
          returning version into v_new_version;
        else
          v_after_status := case
            when nullif(trim(coalesce(v_room.qm_employee_no,'')), '') is not null then 'QM_WAITING'
            else 'COMPLETED'
          end;
          update public.nova_rooms_current
          set cleaning_status = v_after_status,
              version = version + 1,
              cleaning_completed_at = now(),
              updated_by = v_employee_no,
              updated_at = now()
          where id = v_room.id
          returning version into v_new_version;
        end if;

        insert into public.nova_room_events(
          request_id, business_date, site, room_no, action,
          before_status, after_status, employee_no, room_version, detail, event_time
        ) values (
          v_request_id, v_business_date, v_site, v_room_no, v_action,
          upper(coalesce(v_room.cleaning_status,'')), v_after_status, v_employee_no, v_new_version,
          jsonb_build_object('bulk', true, 'batchRequestId', v_batch_id, 'role', v_role, 'expectedVersion', v_expected_version),
          now()
        );

        v_response := jsonb_build_object(
          'ok', true, 'requestId', v_request_id, 'businessDate', v_business_date,
          'site', v_site, 'roomNo', v_room_no, 'action', v_action,
          'beforeStatus', upper(coalesce(v_room.cleaning_status,'')),
          'afterStatus', v_after_status, 'version', v_new_version
        );
        v_updated := v_updated + 1;
      end if;

      if coalesce((v_response->>'ok')::boolean, false) = false then
        v_failed := v_failed + 1;
      end if;
      update public.nova_request_dedup set response_json = v_response where request_id = v_request_id;
      v_results := v_results || jsonb_build_array(v_response);
    exception when others then
      v_response := jsonb_build_object(
        'ok', false, 'code', 'ITEM_ERROR', 'requestId', coalesce(v_request_id,''),
        'site', coalesce(v_site,''), 'roomNo', coalesce(v_room_no,''), 'message', sqlerrm
      );
      v_failed := v_failed + 1;
      if coalesce(v_request_id,'') <> '' and coalesce(v_employee_no,'') <> '' then
        insert into public.nova_request_dedup(request_id, employee_no, action, response_json)
        values (v_request_id, v_employee_no, v_action, v_response)
        on conflict (request_id) do update set response_json = excluded.response_json;
      end if;
      v_results := v_results || jsonb_build_array(v_response);
    end;
  end loop;

  return jsonb_build_object(
    'ok', true, 'action', v_action, 'batchRequestId', v_batch_id,
    'requested', v_count, 'updated', v_updated, 'failed', v_failed,
    'duplicates', v_duplicate, 'results', v_results
  );
end;
$$;

revoke all on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) from public;
revoke all on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) from anon;
revoke all on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) from authenticated;
grant execute on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) to service_role;

comment on function public.nova_bulk_room_cleaning_action_v1(jsonb, text, text) is
'NOVA DB-first bulk cleaning primitive. Max 500 rooms/call; service_role only. Intended for 3 parallel calls for 1,500-room bursts. Per-room request_id dedup, row lock, version/state checks, event log and Realtime trigger are preserved.';
