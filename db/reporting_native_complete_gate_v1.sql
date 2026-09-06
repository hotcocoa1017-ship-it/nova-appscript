-- REPORTING_NATIVE_COMPLETE_GATE_V1
-- A date/site may switch monthly reporting from Sheet to DB only after the close snapshot
-- matches DB-native room/upload/cleaning/QM/Houseman/departure-delay data.

create or replace function nova_private.evaluate_reporting_native_complete_v1(
  p_business_date date,
  p_site text,
  p_snapshot jsonb,
  p_actor text
)
returns jsonb
language plpgsql
security definer
set search_path=public,nova_private,pg_catalog
as $$
declare
  v_room_count integer:=0;
  v_upload_count integer:=0;
  v_upload_total integer:=0;
  v_cleaning_complete integer:=0;
  v_unenriched_cleaning integer:=0;
  v_qm_complete integer:=0;
  v_qm_inspections integer:=0;
  v_houseman_completed integer:=0;
  v_houseman_unable integer:=0;
  v_departure_delay integer:=0;
  v_expected_rooms integer:=coalesce((p_snapshot->>'totalRooms')::integer,0);
  v_expected_cleaning integer:=coalesce((p_snapshot->>'cleaningCompleted')::integer,0);
  v_expected_qm integer:=coalesce((p_snapshot->>'qmCompleted')::integer,0);
  v_expected_houseman_completed integer:=coalesce((p_snapshot->>'housemanCompleted')::integer,0);
  v_expected_houseman_unable integer:=coalesce((p_snapshot->>'housemanUnable')::integer,0);
  v_expected_departure_delay integer:=coalesce((p_snapshot->>'departureDelayCount')::integer,0);
  v_ok boolean:=true;
  v_reasons text[]:=array[]::text[];
  v_reason text:='';
  v_version bigint:=1;
begin
  select count(*) into v_room_count from public.nova_rooms_current where business_date=p_business_date and site=p_site;
  select count(*),coalesce(max(total_rooms),0) into v_upload_count,v_upload_total from public.nova_room_upload_snapshots where business_date=p_business_date and site=p_site and is_active;
  select count(*) filter(where action='CLEANING_COMPLETE'),
         count(*) filter(where action in ('CLEANING_START','CLEANING_COMPLETE') and coalesce((detail->>'reportEnriched')::boolean,false)=false),
         count(*) filter(where action='QM_COMPLETE')
  into v_cleaning_complete,v_unenriched_cleaning,v_qm_complete
  from public.nova_room_events where business_date=p_business_date and site=p_site;
  select count(*) into v_qm_inspections from public.nova_qm_inspections where business_date=p_business_date and site=p_site;
  select count(*) filter(where status_code='COMPLETED'),count(*) filter(where status_code='UNABLE')
  into v_houseman_completed,v_houseman_unable from public.nova_houseman_orders where business_date=p_business_date and site=p_site;
  select count(*) into v_departure_delay from public.nova_departure_delays where business_date=p_business_date and site=p_site;

  if v_upload_count<>1 then v_ok:=false; v_reasons:=array_append(v_reasons,'ACTIVE_UPLOAD_SNAPSHOT_MISSING'); end if;
  if v_expected_rooms<=0 or v_room_count<>v_expected_rooms or v_upload_total<>v_expected_rooms then v_ok:=false; v_reasons:=array_append(v_reasons,'ROOM_COUNT_MISMATCH'); end if;
  if v_unenriched_cleaning>0 then v_ok:=false; v_reasons:=array_append(v_reasons,'CLEANING_EVENT_NOT_ENRICHED'); end if;
  if v_cleaning_complete<>v_expected_cleaning then v_ok:=false; v_reasons:=array_append(v_reasons,'CLEANING_COMPLETE_MISMATCH'); end if;
  if v_qm_complete<>v_expected_qm or v_qm_inspections<>v_expected_qm then v_ok:=false; v_reasons:=array_append(v_reasons,'QM_INSPECTION_MISMATCH'); end if;
  if v_houseman_completed<>v_expected_houseman_completed or v_houseman_unable<>v_expected_houseman_unable then v_ok:=false; v_reasons:=array_append(v_reasons,'HOUSEMAN_RESULT_MISMATCH'); end if;
  if v_departure_delay<>v_expected_departure_delay then v_ok:=false; v_reasons:=array_append(v_reasons,'DEPARTURE_DELAY_MISMATCH'); end if;

  v_reason:=case when v_ok then 'DB_NATIVE_REPORT_COMPLETE' else array_to_string(v_reasons,',') end;
  select coalesce(version,0)+1 into v_version from public.nova_reporting_state where business_date=p_business_date and site=p_site;
  if v_version is null then v_version:=1; end if;
  insert into public.nova_reporting_state(business_date,site,native_complete,completed_by,completed_at,reason,version,updated_at)
  values(p_business_date,p_site,v_ok,case when v_ok then p_actor else '' end,case when v_ok then now() else null end,v_reason,v_version,now())
  on conflict(business_date,site) do update set native_complete=excluded.native_complete,completed_by=excluded.completed_by,
    completed_at=excluded.completed_at,reason=excluded.reason,version=public.nova_reporting_state.version+1,updated_at=now()
  returning version into v_version;
  return jsonb_build_object('ok',true,'nativeComplete',v_ok,'reason',v_reason,'version',v_version,
    'actual',jsonb_build_object('rooms',v_room_count,'uploadTotalRooms',v_upload_total,'cleaningComplete',v_cleaning_complete,'unenrichedCleaning',v_unenriched_cleaning,'qmCompleteEvents',v_qm_complete,'qmInspections',v_qm_inspections,'housemanCompleted',v_houseman_completed,'housemanUnable',v_houseman_unable,'departureDelay',v_departure_delay),
    'expected',jsonb_build_object('rooms',v_expected_rooms,'cleaningComplete',v_expected_cleaning,'qmCompleted',v_expected_qm,'housemanCompleted',v_expected_houseman_completed,'housemanUnable',v_expected_houseman_unable,'departureDelay',v_expected_departure_delay));
end;
$$;

-- nova_daily_close_save_v2 calls this evaluator after DB close upsert and returns
-- reportingNativeComplete/reportingReason. The deployed migration contains the complete
-- function body; keep db/daily_close_save_db_first_v1.sql as the base implementation reference.
