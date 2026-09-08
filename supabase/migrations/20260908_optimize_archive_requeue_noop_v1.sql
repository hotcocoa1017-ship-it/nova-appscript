-- NOVA_ARCHIVE_REQUEUE_NOOP_PERF_V1
-- Avoid firing the statement-level Archive Realtime/integrity trigger when no lease is expired.
-- The existing UPDATE and all side effects are preserved whenever an expired LEASED job exists.
create or replace function public.nova_archive_requeue_expired_leases()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_count integer := 0;
begin
  if not exists (
    select 1
    from public.nova_archive_jobs
    where status='LEASED'
      and lease_expires_at is not null
      and lease_expires_at < now()
  ) then
    return jsonb_build_object('ok',true,'requeuedOrFailed',0);
  end if;

  update public.nova_archive_jobs
  set status = case when attempts >= max_attempts then 'FAILED' else 'PENDING' end,
      lease_token = null,
      lease_expires_at = null,
      next_attempt_at = case when attempts >= max_attempts then next_attempt_at else now() + interval '1 minute' end,
      last_error = case when attempts >= max_attempts then coalesce(nullif(last_error,''),'archive lease expired') else 'archive lease expired; requeued' end,
      updated_at = now()
  where status='LEASED'
    and lease_expires_at is not null
    and lease_expires_at < now();
  get diagnostics v_count = row_count;
  return jsonb_build_object('ok',true,'requeuedOrFailed',v_count);
end;
$function$;
