-- NOVA_ARCHIVE_INTEGRITY_MATCH_PERF_V1
-- Preserve all integrity checks while materializing active verified WORK_HISTORY index rows before
-- matching them against the hot room-event source. This avoids thousands of repeated batch PK probes.
create or replace function public.nova_archive_integrity_service()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_cutoff date := (now() at time zone 'Asia/Seoul')::date;
  v_source_partitions bigint := 0;
  v_source_rows bigint := 0;
  v_verified_partitions bigint := 0;
  v_missing_partitions bigint := 0;
  v_batch_row_mismatches bigint := 0;
  v_wh_source bigint := 0;
  v_wh_index bigint := 0;
  v_wh_matched bigint := 0;
  v_storage_objects bigint := 0;
  v_verified_batches bigint := 0;
  v_retired_batches bigint := 0;
  v_active_batches bigint := 0;
  v_orphan_storage bigint := 0;
  v_missing_storage bigint := 0;
  v_orphan_index bigint := 0;
  v_failed_jobs bigint := 0;
  v_stale_jobs bigint := 0;
  v_deep_failed bigint := 0;
  v_deep_pending bigint := 0;
  v_stale_deep bigint := 0;
  v_jobs jsonb := '{}'::jsonb;
  v_ok boolean := false;
begin
  with src as (
    select 'CURRENT_ROOM_HISTORY'::text source_type,business_date,site,count(*)::bigint rows
    from public.nova_rooms_current
    where business_date < v_cutoff
    group by business_date,site
    union all
    select 'WORK_HISTORY'::text,business_date,site,count(*)::bigint
    from public.nova_room_events
    where business_date < v_cutoff
    group by business_date,site
  ), ver as (
    select source_type,period_start business_date,site,batch_id,row_count,object_path
    from public.nova_archive_batches
    where status='VERIFIED' and retired_at is null
  )
  select count(*),coalesce(sum(s.rows),0),
         count(*) filter(where v.batch_id is not null),
         count(*) filter(where v.batch_id is null),
         count(*) filter(where v.batch_id is not null and s.rows<>v.row_count)
  into v_source_partitions,v_source_rows,v_verified_partitions,v_missing_partitions,v_batch_row_mismatches
  from src s left join ver v using(source_type,business_date,site);

  select count(*) into v_wh_source
  from public.nova_room_events e where e.business_date < v_cutoff;

  select count(*) into v_wh_index
  from public.nova_archive_index i
  join public.nova_archive_batches b on b.batch_id=i.batch_id
  where i.source_type='WORK_HISTORY'
    and i.business_date < v_cutoff
    and b.status='VERIFIED'
    and b.retired_at is null;

  with active_index as materialized (
    select i.archive_key,i.business_date,i.site,i.source_record_id
    from public.nova_archive_index i
    join public.nova_archive_batches b on b.batch_id=i.batch_id
    where i.source_type='WORK_HISTORY'
      and i.business_date < v_cutoff
      and b.status='VERIFIED'
      and b.retired_at is null
  )
  select count(*) into v_wh_matched
  from public.nova_room_events e
  join active_index i
    on i.archive_key=('WH:'||e.request_id)
   and i.business_date=e.business_date
   and i.site=e.site
   and i.source_record_id=e.request_id
  where e.business_date < v_cutoff;

  select count(*) into v_storage_objects
  from storage.objects where bucket_id='nova-archive';

  select count(*) into v_verified_batches
  from public.nova_archive_batches where status='VERIFIED';

  select count(*) into v_retired_batches
  from public.nova_archive_batches where status='VERIFIED' and retired_at is not null;

  select count(*) into v_active_batches
  from public.nova_archive_batches where status='VERIFIED' and retired_at is null;

  select count(*) into v_orphan_storage
  from storage.objects o
  left join public.nova_archive_batches b on b.object_path=o.name
  where o.bucket_id='nova-archive' and b.batch_id is null;

  select count(*) into v_missing_storage
  from public.nova_archive_batches b
  left join storage.objects o on o.bucket_id='nova-archive' and o.name=b.object_path
  where b.status='VERIFIED' and o.id is null;

  select count(*) into v_orphan_index
  from public.nova_archive_index i
  left join public.nova_archive_batches b on b.batch_id=i.batch_id
  where b.batch_id is null;

  select coalesce(jsonb_object_agg(status,cnt),'{}'::jsonb),
         coalesce(sum(cnt) filter(where status='FAILED'),0),
         coalesce(sum(cnt) filter(where status in ('PENDING','LEASED') and stale),0)
  into v_jobs,v_failed_jobs,v_stale_jobs
  from (
    select status,count(*)::bigint cnt,
           bool_or(updated_at < now()-interval '30 minutes') stale
    from public.nova_archive_jobs
    group by status
  ) x;

  select count(*) filter(where deep_verify_status='FAILED'),
         count(*) filter(where deep_verify_status='PENDING'),
         count(*) filter(
           where status='VERIFIED'
             and verified_at < now()-interval '24 hours'
             and (last_deep_verified_at is null or last_deep_verified_at < now()-interval '7 days')
         )
  into v_deep_failed,v_deep_pending,v_stale_deep
  from public.nova_archive_batches
  where status='VERIFIED';

  v_ok := v_missing_partitions=0
      and v_batch_row_mismatches=0
      and v_wh_source=v_wh_index
      and v_wh_source=v_wh_matched
      and v_failed_jobs=0
      and v_stale_jobs=0
      and v_orphan_storage=0
      and v_missing_storage=0
      and v_orphan_index=0
      and v_deep_failed=0
      and v_stale_deep=0;

  return jsonb_build_object(
    'ok',v_ok,
    'checkedAt',now(),
    'cutoffExclusive',v_cutoff,
    'sourcePartitionsPast',v_source_partitions,
    'sourceRowsPast',v_source_rows,
    'verifiedPartitionsPast',v_verified_partitions,
    'missingPartitionsPast',v_missing_partitions,
    'batchRowMismatches',v_batch_row_mismatches,
    'workHistorySourceRowsPast',v_wh_source,
    'workHistoryIndexRowsPast',v_wh_index,
    'workHistoryMatchedRowsPast',v_wh_matched,
    'jobs',v_jobs,
    'failedJobs',v_failed_jobs,
    'staleJobs',v_stale_jobs,
    'storageObjects',v_storage_objects,
    'verifiedBatchesTotal',v_verified_batches,
    'activeVerifiedBatches',v_active_batches,
    'retiredVerifiedBatches',v_retired_batches,
    'orphanStorageObjects',v_orphan_storage,
    'verifiedBatchesMissingObject',v_missing_storage,
    'orphanIndexRows',v_orphan_index,
    'deepVerifyFailed',v_deep_failed,
    'deepVerifyPending',v_deep_pending,
    'staleDeepVerify',v_stale_deep
  );
end;
$function$;
