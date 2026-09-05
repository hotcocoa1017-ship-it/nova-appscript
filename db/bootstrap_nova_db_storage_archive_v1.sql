-- NOVA DB + Storage archive foundation v1
-- Applied to Supabase project nova-realtime on 2026-09-05.
-- This migration is intentionally non-destructive: it creates the private archive bucket,
-- archive manifest metadata, and usage snapshots. It does not delete hot DB/Sheet data.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'nova-archive',
  'nova-archive',
  false,
  52428800,
  array['application/gzip','application/x-gzip','application/json','text/csv','application/octet-stream']::text[]
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create table if not exists public.nova_archive_manifests (
  id bigint generated always as identity primary key,
  source_name text not null,
  period_start date not null,
  period_end date not null,
  storage_bucket text not null default 'nova-archive',
  object_path text not null,
  archive_format text not null default 'jsonl.gz',
  schema_version integer not null default 1,
  row_count bigint not null default 0 check (row_count >= 0),
  checksum_sha256 text not null,
  compressed_bytes bigint check (compressed_bytes is null or compressed_bytes >= 0),
  uncompressed_bytes bigint check (uncompressed_bytes is null or uncompressed_bytes >= 0),
  status text not null default 'UPLOADED'
    check (status in ('UPLOADING','UPLOADED','VERIFIED','FAILED','HOT_DELETED','RESTORED')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  verified_at timestamptz,
  hot_deleted_at timestamptz,
  restored_at timestamptz,
  constraint nova_archive_period_valid check (period_end >= period_start),
  constraint nova_archive_object_unique unique (storage_bucket, object_path)
);

create index if not exists nova_archive_manifests_source_period_idx
  on public.nova_archive_manifests (source_name, period_start desc, period_end desc);
create index if not exists nova_archive_manifests_status_idx
  on public.nova_archive_manifests (status, created_at desc);

alter table public.nova_archive_manifests enable row level security;

comment on table public.nova_archive_manifests is
  'NOVA DB+Storage archive manifest. Storage object is authoritative only after checksum/row-count verification; hot data deletion is recorded separately.';

create table if not exists public.nova_usage_snapshots (
  id bigint generated always as identity primary key,
  snapshot_at timestamptz not null default now(),
  metric_name text not null,
  metric_value numeric not null,
  unit text not null,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists nova_usage_snapshots_metric_time_idx
  on public.nova_usage_snapshots (metric_name, snapshot_at desc);

alter table public.nova_usage_snapshots enable row level security;
