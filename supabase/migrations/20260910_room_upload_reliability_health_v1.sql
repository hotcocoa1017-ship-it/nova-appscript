-- ROOM_UPLOAD_RELIABILITY_HEALTH_V1
-- Read-only operational health summary for guarded V5 room uploads.
-- Legacy/pre-V5 snapshots are intentionally excluded so historical rows are not misclassified.

create or replace function public.nova_room_upload_health_v1(
  p_days integer default 30,
  p_site text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no', ''));
  v_user public.nova_users%rowtype;
  v_days integer := greatest(1, least(90, coalesce(p_days, 30)));
  v_site text := trim(coalesce(p_site, ''));
  v_total bigint := 0;
  v_completed bigint := 0;
  v_failed bigint := 0;
  v_stuck bigint := 0;
  v_pending bigint := 0;
  v_legacy_excluded bigint := 0;
  v_success_rate numeric;
  v_avg_sheet_seconds numeric;
  v_p95_sheet_seconds numeric;
  v_avg_realtime_seconds numeric;
  v_p95_realtime_seconds numeric;
  v_stuck_items jsonb := '[]'::jsonb;
begin
  if v_actor = '' then
    raise exception using errcode='42501', message='로그인이 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_actor and enabled = true;

  if not found or upper(coalesce(v_user.role, '')) not in ('ADMIN', 'ORDER') then
    raise exception using errcode='42501', message='객실 업로드 상태 조회 권한이 없습니다.';
  end if;

  if v_site <> '' and not (
    (coalesce(trim(v_user.default_site), '') = '' and cardinality(coalesce(v_user.allowed_sites, array[]::text[])) = 0)
    or v_site = coalesce(v_user.default_site, '')
    or v_site = any(coalesce(v_user.allowed_sites, array[]::text[]))
  ) then
    raise exception using errcode='42501', message='사업장 권한이 없습니다.';
  end if;

  with scoped as (
    select s.*,
      extract(epoch from (now() - coalesce(s.db_committed_at, s.registered_at))) / 60.0 as age_minutes,
      case
        when s.db_committed_at is not null
         and upper(coalesce(s.sheet_mirror_status, '')) = 'MIRRORED'
         and upper(coalesce(s.realtime_status, '')) = 'CONVERGED' then true
        else false
      end as completed,
      case
        when upper(coalesce(s.sheet_mirror_status, '')) = 'FAILED'
          or upper(coalesce(s.realtime_status, '')) = 'FAILED' then true
        else false
      end as explicit_failed
    from public.nova_room_upload_snapshots s
    where s.registered_at >= now() - make_interval(days => v_days)
      and s.guard_version = 'ROOM_UPLOAD_SITE_GUARD_V1'
      and trim(coalesce(s.request_id, '')) <> ''
      and (v_site = '' or s.site = v_site)
      and (
        (coalesce(trim(v_user.default_site), '') = '' and cardinality(coalesce(v_user.allowed_sites, array[]::text[])) = 0)
        or s.site = coalesce(v_user.default_site, '')
        or s.site = any(coalesce(v_user.allowed_sites, array[]::text[]))
      )
  ), stats as (
    select
      count(*)::bigint as total,
      count(*) filter (where completed)::bigint as completed_count,
      count(*) filter (where explicit_failed)::bigint as failed_count,
      count(*) filter (
        where db_committed_at is not null
          and not completed
          and (
            explicit_failed
            or now() - db_committed_at > interval '10 minutes'
          )
      )::bigint as stuck_count,
      count(*) filter (
        where db_committed_at is not null
          and not completed
          and not explicit_failed
          and now() - db_committed_at <= interval '10 minutes'
      )::bigint as pending_count,
      avg(extract(epoch from (sheet_mirrored_at - db_committed_at))) filter (
        where db_committed_at is not null and sheet_mirrored_at is not null
      ) as avg_sheet_seconds,
      percentile_cont(0.95) within group (order by extract(epoch from (sheet_mirrored_at - db_committed_at))) filter (
        where db_committed_at is not null and sheet_mirrored_at is not null
      ) as p95_sheet_seconds,
      avg(extract(epoch from (realtime_converged_at - db_committed_at))) filter (
        where db_committed_at is not null and realtime_converged_at is not null
      ) as avg_realtime_seconds,
      percentile_cont(0.95) within group (order by extract(epoch from (realtime_converged_at - db_committed_at))) filter (
        where db_committed_at is not null and realtime_converged_at is not null
      ) as p95_realtime_seconds
    from scoped
  )
  select total, completed_count, failed_count, stuck_count, pending_count,
         avg_sheet_seconds, p95_sheet_seconds, avg_realtime_seconds, p95_realtime_seconds
  into v_total, v_completed, v_failed, v_stuck, v_pending,
       v_avg_sheet_seconds, v_p95_sheet_seconds, v_avg_realtime_seconds, v_p95_realtime_seconds
  from stats;

  select count(*)::bigint
  into v_legacy_excluded
  from public.nova_room_upload_snapshots s
  where s.registered_at >= now() - make_interval(days => v_days)
    and (v_site = '' or s.site = v_site)
    and (
      (coalesce(trim(v_user.default_site), '') = '' and cardinality(coalesce(v_user.allowed_sites, array[]::text[])) = 0)
      or s.site = coalesce(v_user.default_site, '')
      or s.site = any(coalesce(v_user.allowed_sites, array[]::text[]))
    )
    and not (
      s.guard_version = 'ROOM_UPLOAD_SITE_GUARD_V1'
      and trim(coalesce(s.request_id, '')) <> ''
    );

  if v_total > 0 then
    v_success_rate := round((v_completed::numeric * 100.0) / v_total::numeric, 4);
  else
    v_success_rate := null;
  end if;

  with scoped as (
    select s.*,
      extract(epoch from (now() - coalesce(s.db_committed_at, s.registered_at))) / 60.0 as age_minutes
    from public.nova_room_upload_snapshots s
    where s.registered_at >= now() - make_interval(days => v_days)
      and s.guard_version = 'ROOM_UPLOAD_SITE_GUARD_V1'
      and trim(coalesce(s.request_id, '')) <> ''
      and s.db_committed_at is not null
      and (v_site = '' or s.site = v_site)
      and (
        (coalesce(trim(v_user.default_site), '') = '' and cardinality(coalesce(v_user.allowed_sites, array[]::text[])) = 0)
        or s.site = coalesce(v_user.default_site, '')
        or s.site = any(coalesce(v_user.allowed_sites, array[]::text[]))
      )
      and not (
        upper(coalesce(s.sheet_mirror_status, '')) = 'MIRRORED'
        and upper(coalesce(s.realtime_status, '')) = 'CONVERGED'
      )
      and (
        upper(coalesce(s.sheet_mirror_status, '')) = 'FAILED'
        or upper(coalesce(s.realtime_status, '')) = 'FAILED'
        or now() - s.db_committed_at > interval '10 minutes'
      )
    order by s.db_committed_at desc
    limit 10
  )
  select coalesce(jsonb_agg(jsonb_build_object(
    'businessDate', business_date::text,
    'site', site,
    'uploadVersion', upload_version,
    'ageMinutes', round(age_minutes::numeric, 1),
    'sheetStatus', coalesce(sheet_mirror_status, ''),
    'realtimeStatus', coalesce(realtime_status, ''),
    'lastError', left(coalesce(last_error, ''), 300)
  )), '[]'::jsonb)
  into v_stuck_items
  from scoped;

  return jsonb_build_object(
    'ok', true,
    'scopeDays', v_days,
    'site', v_site,
    'guardVersion', 'ROOM_UPLOAD_SITE_GUARD_V1',
    'graceMinutes', 10,
    'totalV5Uploads', coalesce(v_total, 0),
    'completedUploads', coalesce(v_completed, 0),
    'failedUploads', coalesce(v_failed, 0),
    'stuckUploads', coalesce(v_stuck, 0),
    'pendingWithinGrace', coalesce(v_pending, 0),
    'legacyExcludedUploads', coalesce(v_legacy_excluded, 0),
    'empiricalSuccessRatePercent', v_success_rate,
    'targetPercent', 99.9,
    'avgSheetMirrorSeconds', case when v_avg_sheet_seconds is null then null else round(v_avg_sheet_seconds::numeric, 3) end,
    'p95SheetMirrorSeconds', case when v_p95_sheet_seconds is null then null else round(v_p95_sheet_seconds::numeric, 3) end,
    'avgRealtimeConvergeSeconds', case when v_avg_realtime_seconds is null then null else round(v_avg_realtime_seconds::numeric, 3) end,
    'p95RealtimeConvergeSeconds', case when v_p95_realtime_seconds is null then null else round(v_p95_realtime_seconds::numeric, 3) end,
    'status', case
      when coalesce(v_total, 0) = 0 then 'NO_V5_SAMPLE'
      when coalesce(v_stuck, 0) > 0 or coalesce(v_failed, 0) > 0 then 'DEGRADED'
      when coalesce(v_pending, 0) > 0 then 'OBSERVING'
      when v_success_rate >= 99.9 then 'HEALTHY'
      else 'BELOW_TARGET'
    end,
    'stuckItems', v_stuck_items
  );
end;
$function$;

revoke all on function public.nova_room_upload_health_v1(integer, text) from public;
revoke all on function public.nova_room_upload_health_v1(integer, text) from anon;
grant execute on function public.nova_room_upload_health_v1(integer, text) to authenticated;
grant execute on function public.nova_room_upload_health_v1(integer, text) to service_role;
