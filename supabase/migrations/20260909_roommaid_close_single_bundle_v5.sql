-- ROOMMAID_CLOSE_SINGLE_BUNDLE_V5
-- Adds compact current-room rows to the existing roommaid close history RPC so Apps Script
-- can render a close journal with one DB-first round trip. Existing fields and auth behavior remain compatible.

create or replace function public.nova_roommaid_close_history_v1(p_business_date text, p_site text)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text:=trim(coalesce(p_site,''));
  v_native boolean:=false;
  v_state_version bigint:=0;
  v_active_uploads integer:=0;
  v_snapshot_rooms integer:=0;
  v_current_rooms integer:=0;
  v_live_native boolean:=false;
  v_cache_exists boolean:=false;
  v_cache_complete boolean:=false;
  v_cache_rows integer:=0;
  v_saved jsonb:=null;
  v_items jsonb:='[]'::jsonb;
  v_current_rows_payload jsonb:='[]'::jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501',message='룸메이드 마감 조회 권한이 없습니다.';
  end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;

  select s.native_complete,s.version
    into v_native,v_state_version
  from public.nova_reporting_state s
  where s.business_date=v_date and s.site=v_site;

  select true,cs.complete,cs.row_count
    into v_cache_exists,v_cache_complete,v_cache_rows
  from public.nova_roommaid_close_history_cache_state cs
  where cs.business_date=v_date and cs.site=v_site;
  v_cache_exists:=coalesce(v_cache_exists,false);
  v_cache_complete:=coalesce(v_cache_complete,false);
  v_cache_rows:=coalesce(v_cache_rows,0);

  if not coalesce(v_native,false) and v_date >= date '2026-09-08' then
    select count(*)::int,coalesce(max(u.total_rooms),0)::int
      into v_active_uploads,v_snapshot_rooms
    from public.nova_room_upload_snapshots u
    where u.business_date=v_date and u.site=v_site and u.is_active;

    select count(*)::int
      into v_current_rooms
    from public.nova_rooms_current r
    where r.business_date=v_date and r.site=v_site;

    v_live_native:=v_active_uploads=1
      and v_snapshot_rooms>0
      and v_current_rooms=v_snapshot_rooms;

    if v_cache_exists and not v_cache_complete then
      v_live_native:=false;
    end if;
    if v_live_native then v_native:=true; end if;
  end if;

  select jsonb_build_object(
      'businessDate',c.business_date::text,
      'site',c.site,
      'snapshot',c.snapshot - 'rooms',
      'sourceSignature',c.source_signature,
      'sourceUpdatedAt',c.source_updated_at,
      'closedBy',c.closed_by,
      'closedByName',c.closed_by_name,
      'closedAt',to_char(c.closed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
      'version',c.version,
      'requestId',c.request_id,
      'dbFirst',true
    )
    into v_saved
  from public.nova_daily_close_snapshots c
  where c.business_date=v_date and c.site=v_site and c.is_active=true
  order by c.version desc,c.closed_at desc
  limit 1;

  if not coalesce(v_native,false) then
    return jsonb_build_object(
      'ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,
      'nativeComplete',false,'stateVersion',coalesce(v_state_version,0),
      'liveNativeReady',false,'cacheComplete',v_cache_complete,'cacheRows',v_cache_rows,
      'saved',v_saved,'items','[]'::jsonb,
      'currentRowsCompact',true,
      'currentRowSchema',jsonb_build_array('roomNo','building','roomStatus','cleaningStatus','cleaningType','assignmentType','roommaidEmployeeNo','secondaryRoommaidEmployeeNo','qmEmployeeNo','operationalStatus','version','updatedAt'),
      'currentRows','[]'::jsonb
    );
  end if;

  v_items:=nova_private.roommaid_close_history_rows_v2(v_date,v_site);

  select coalesce(jsonb_agg(
    jsonb_build_array(
      r.room_no,
      coalesce(r.building,''),
      coalesce(r.room_status,''),
      coalesce(r.cleaning_status,''),
      coalesce(r.cleaning_type,''),
      coalesce(r.assignment_type,''),
      coalesce(r.roommaid_employee_no,''),
      coalesce(r.secondary_roommaid_employee_no,''),
      coalesce(r.qm_employee_no,''),
      coalesce(r.operational_status,''),
      coalesce(r.version,0),
      to_char(r.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS')
    ) order by r.room_no
  ),'[]'::jsonb)
    into v_current_rows_payload
  from public.nova_rooms_current r
  where r.business_date=v_date and r.site=v_site;

  if v_current_rooms=0 then
    v_current_rooms:=jsonb_array_length(v_current_rows_payload);
  end if;

  return jsonb_build_object(
    'ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,
    'nativeComplete',true,'stateVersion',coalesce(v_state_version,0),
    'liveNativeReady',v_live_native,
    'snapshotRooms',v_snapshot_rooms,'currentRooms',v_current_rooms,
    'cacheComplete',v_cache_complete,'cacheRows',v_cache_rows,
    'saved',v_saved,
    'items',v_items,
    'currentRowsCompact',true,
    'currentRowSchema',jsonb_build_array('roomNo','building','roomStatus','cleaningStatus','cleaningType','assignmentType','roommaidEmployeeNo','secondaryRoommaidEmployeeNo','qmEmployeeNo','operationalStatus','version','updatedAt'),
    'currentRows',v_current_rows_payload
  );
end;
$function$;

comment on function public.nova_roommaid_close_history_v1(text,text)
is 'ROOMMAID_CLOSE_SINGLE_BUNDLE_V5: history + saved close + compact current-room rows in one authorized DB-first RPC.';
