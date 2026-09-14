-- NOVA Core 3.0 live-state ownership validation
-- SELECT-only post-migration checks.

-- A) Every room with at least one DB event must be marked owned.
select r.business_date, r.site, r.room_no, r.live_state_owned_at
from public.nova_rooms_current r
where exists (
  select 1 from public.nova_room_events e
  where e.business_date = r.business_date
    and e.site = r.site
    and e.room_no = r.room_no
)
and r.live_state_owned_at is null;

-- B) No owned room may have an ownership timestamp later than its first event.
with first_event as (
  select business_date, site, room_no, min(event_time) as first_event_at
  from public.nova_room_events
  group by business_date, site, room_no
)
select r.business_date, r.site, r.room_no,
       r.live_state_owned_at, e.first_event_at
from public.nova_rooms_current r
join first_event e using (business_date, site, room_no)
where r.live_state_owned_at > e.first_event_at + interval '1 second';

-- C) Trigger must exist and be enabled.
select t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) as definition
from pg_trigger t
join pg_class c on c.oid = t.tgrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname = 'nova_rooms_current'
  and t.tgname = 'trg_nova_guard_live_room_state_ownership_v1'
  and not t.tgisinternal;

-- D) Trigger function must not be directly executable by browser roles.
select
  has_function_privilege('anon', 'public.nova_guard_live_room_state_ownership_v1()', 'EXECUTE') as anon_execute,
  has_function_privilege('authenticated', 'public.nova_guard_live_room_state_ownership_v1()', 'EXECUTE') as authenticated_execute;

-- E) DB/current-event consistency must still be clean.
with latest_event as (
  select business_date, site, room_no, max(room_version) as max_event_version
  from public.nova_room_events
  group by business_date, site, room_no
)
select r.business_date, r.site, r.room_no, r.version, e.max_event_version
from public.nova_rooms_current r
join latest_event e using (business_date, site, room_no)
where r.version < e.max_event_version;

-- F) Distribution for rollout observation.
select business_date, site,
       count(*) as total_rooms,
       count(*) filter (where live_state_owned_at is not null) as db_owned_rooms,
       count(*) filter (where live_state_owned_at is null) as bootstrap_rooms
from public.nova_rooms_current
group by business_date, site
order by business_date desc, site;
