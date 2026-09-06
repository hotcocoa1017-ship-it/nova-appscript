-- NOVA Archive prune admin monitoring v1
-- Applied to Supabase nova-realtime on 2026-09-06.
-- Read-only aggregate for the ADMIN Archive screen.

create or replace function public.nova_archive_prune_status_service()
returns jsonb
language sql
stable
security invoker
set search_path to ''
as $function$
with stats as (
  select
    count(*) filter (where mode='COMMIT' and status='COMPLETED')::bigint as completed_batches,
    coalesce(sum(deleted_rows) filter (where mode='COMMIT' and status='COMPLETED'),0)::bigint as total_deleted_rows,
    count(*) filter (where status='FAILED')::bigint as failed_runs,
    max(completed_at) filter (where mode='COMMIT' and status='COMPLETED') as latest_completed_at
  from public.nova_archive_prune_runs
), recent as (
  select coalesce(jsonb_agg(to_jsonb(r) order by r.run_id desc),'[]'::jsonb) as recent_runs
  from (
    select run_id,mode,status,source_type,business_date,site,expected_rows,deleted_rows,remaining_rows,started_at,completed_at,message
    from public.nova_archive_prune_runs
    order by run_id desc
    limit 10
  ) r
), candidates as (
  select count(*)::bigint as remaining_candidates
  from public.nova_archive_retention_candidates_service(null,30,5000)
)
select jsonb_build_object(
  'retentionDays',30,
  'completedBatches',s.completed_batches,
  'totalDeletedRows',s.total_deleted_rows,
  'failedRuns',s.failed_runs,
  'latestCompletedAt',s.latest_completed_at,
  'remainingCandidates',c.remaining_candidates,
  'recentRuns',r.recent_runs
)
from stats s cross join recent r cross join candidates c;
$function$;

revoke all on function public.nova_archive_prune_status_service() from public;
revoke all on function public.nova_archive_prune_status_service() from anon;
revoke all on function public.nova_archive_prune_status_service() from authenticated;
grant execute on function public.nova_archive_prune_status_service() to service_role;
