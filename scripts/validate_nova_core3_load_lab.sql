-- Read-only validation for NOVA Core 3 isolated load branch.
-- Never mutates data.

select
  (select count(*) from public.nova_users) as user_count,
  (select count(*) from public.nova_users where employee_no ~ '^LOAD') as synthetic_user_count,
  (select count(*) from public.nova_rooms_current) as room_count,
  (select count(*) from public.nova_rooms_current where business_date = date '2099-01-01' and site = '쏘라노') as synthetic_room_count,
  (select count(*) from public.nova_rooms_current where updated_by = 'CORE3_LOAD_SEED') as seeded_room_count,
  (select count(*) from public.nova_room_events) as event_count,
  (select count(*) from nova_private.core_idempotency) as idempotency_count,
  (select count(*) from nova_private.core_outbox) as outbox_count,
  (select marker from nova_private.core_load_lab_state where singleton = true) as load_marker;

select
  count(*) filter (where cleaning_status = 'WAITING') as waiting,
  count(*) filter (where cleaning_status = 'CLEANING') as cleaning,
  count(*) filter (where cleaning_status = 'COMPLETED') as completed,
  min(version) as min_version,
  max(version) as max_version
from public.nova_rooms_current
where business_date = date '2099-01-01'
  and site = '쏘라노';

select employee_no, count(*) as assigned_rooms
from public.nova_rooms_current
where business_date = date '2099-01-01'
  and site = '쏘라노'
group by employee_no
order by employee_no;
