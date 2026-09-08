-- NOVA_ARCHIVE_BATCH_METADATA_BROADCAST_PERF_V1
-- Skip the expensive archive integrity/realtime statement trigger when an UPDATE only
-- records deep-verify attempt metadata. All user-visible/archive-integrity state columns
-- continue to trigger the existing broadcast function unchanged.

drop trigger if exists nova_archive_batches_realtime_status on public.nova_archive_batches;

create trigger nova_archive_batches_realtime_status
after insert or delete or update of
  batch_id,
  source_type,
  period_start,
  period_end,
  site,
  object_path,
  row_count,
  uncompressed_bytes,
  compressed_bytes,
  checksum_sha256,
  schema_version,
  status,
  archived_at,
  verified_at,
  retired_at,
  created_by,
  note,
  last_deep_verified_at,
  deep_verify_status,
  deep_verify_error
on public.nova_archive_batches
for each statement
execute function public.nova_archive_broadcast_status_change();
