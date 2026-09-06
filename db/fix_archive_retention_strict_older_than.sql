-- NOVA Archive prune preflight fix
-- 2026-09-06
-- "older than N days" must exclude records whose age is exactly N days.
-- Non-destructive: this only changes the retention candidate preview service.

create or replace function public.nova_archive_retention_candidates_service(
  p_source_type text default null::text,
  p_older_than_days integer default 90,
  p_limit integer default 500
)
returns table(
  batch_id uuid,
  source_type text,
  period_start date,
  period_end date,
  site text,
  object_path text,
  row_count integer,
  compressed_bytes bigint,
  archived_at timestamptz,
  verified_at timestamptz,
  age_days integer
)
language sql
stable
security invoker
set search_path to ''
as $function$
  select
    b.batch_id,
    b.source_type,
    b.period_start,
    b.period_end,
    b.site,
    b.object_path,
    b.row_count,
    b.compressed_bytes,
    b.archived_at,
    b.verified_at,
    (current_date - b.period_end)::integer as age_days
  from public.nova_archive_batches b
  where b.status = 'VERIFIED'
    and b.retired_at is null
    and (p_source_type is null or b.source_type = p_source_type)
    and b.period_end < current_date - greatest(1, least(coalesce(p_older_than_days, 90), 3650))
  order by b.period_end asc, b.source_type asc, b.site asc
  limit greatest(1, least(coalesce(p_limit, 500), 5000));
$function$;
