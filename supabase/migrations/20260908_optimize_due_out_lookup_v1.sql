-- NOVA_DUE_OUT_LOOKUP_PERF_V1
-- Accelerate departure-delay capture/dashboard without changing their existing predicates.
create index if not exists idx_nova_rooms_current_due_out_lookup
on public.nova_rooms_current (business_date, site, room_no)
include (building, version, updated_at)
where upper(coalesce(room_status,'')) = 'DUE_OUT';
