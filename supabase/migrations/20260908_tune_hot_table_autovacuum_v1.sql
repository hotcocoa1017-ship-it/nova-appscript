-- NOVA_HOT_TABLE_AUTOVACUUM_PERF_V1
-- Keep high-churn operational tables from accumulating large dead-tuple ratios between default autovacuum runs.
alter table public.nova_rooms_current set (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 100
);

alter table public.nova_qm_drafts set (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 10
);

alter table public.nova_houseman_orders set (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 30
);

alter table public.nova_archive_batches set (
  autovacuum_vacuum_scale_factor = 0.10,
  autovacuum_vacuum_threshold = 10
);
