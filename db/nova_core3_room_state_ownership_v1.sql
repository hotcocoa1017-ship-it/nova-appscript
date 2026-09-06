-- NOVA Core 3.0 Phase 1
-- Live room-state ownership guard V1
--
-- This migration is intentionally additive and transitional.
-- It does not remove existing Sheet sync or DB -> Sheet mirror.
-- It prevents a stale Sheet forward sync from overwriting live operational
-- fields after a room has participated in a committed DB event.

alter table public.nova_rooms_current
  add column if not exists live_state_owned_at timestamptz;

comment on column public.nova_rooms_current.live_state_owned_at is
  'NOVA Core 3.0: first time this business-date/site/room entered DB-authoritative live operational state.';

-- Existing rooms that already have committed DB events are already live-state owned.
update public.nova_rooms_current r
   set live_state_owned_at = e.first_event_at
  from (
    select business_date, site, room_no, min(event_time) as first_event_at
      from public.nova_room_events
     group by business_date, site, room_no
  ) e
 where r.business_date = e.business_date
   and r.site = e.site
   and r.room_no = e.room_no
   and r.live_state_owned_at is null;

create or replace function public.nova_guard_live_room_state_ownership_v1()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  -- A committed operational API action carries updated_by. Once that happens,
  -- the room remains DB-authoritative for the rest of this row's lifetime even
  -- after the asynchronous Sheet mirror clears updated_by.
  if new.live_state_owned_at is null
     and coalesce(btrim(new.updated_by), '') <> '' then
    new.live_state_owned_at := now();
  end if;

  -- The legacy/scheduled Sheet -> DB synchronizer writes with empty updated_by.
  -- After DB ownership has been acquired, it may continue to refresh descriptive
  -- bootstrap fields, but it must never regress live operational state.
  if old.live_state_owned_at is not null
     and coalesce(btrim(new.updated_by), '') = '' then
    new.cleaning_status := old.cleaning_status;
    new.cleaning_type := old.cleaning_type;
    new.assignment_type := old.assignment_type;
    new.roommaid_employee_no := old.roommaid_employee_no;
    new.secondary_roommaid_employee_no := old.secondary_roommaid_employee_no;
    new.qm_employee_no := old.qm_employee_no;
    new.operational_status := old.operational_status;
    new.cleaning_started_at := old.cleaning_started_at;
    new.cleaning_completed_at := old.cleaning_completed_at;
    new.live_state_owned_at := old.live_state_owned_at;
  end if;

  return new;
end;
$function$;

revoke all on function public.nova_guard_live_room_state_ownership_v1() from public;
revoke all on function public.nova_guard_live_room_state_ownership_v1() from anon;
revoke all on function public.nova_guard_live_room_state_ownership_v1() from authenticated;

-- Trigger functions are invoked by PostgreSQL, not by clients.
drop trigger if exists trg_nova_guard_live_room_state_ownership_v1
  on public.nova_rooms_current;

create trigger trg_nova_guard_live_room_state_ownership_v1
before update on public.nova_rooms_current
for each row
execute function public.nova_guard_live_room_state_ownership_v1();

-- Notes:
-- 1. room_status is deliberately NOT protected in V1 because the current
--    room-status upload/import path still needs a separate cutover audit.
-- 2. version remains protected by the existing
--    trg_nova_preserve_positive_room_version_on_sync trigger.
-- 3. Existing operational-status resurrection protection remains in place;
--    this guard is stricter once live-state ownership is acquired.
-- 4. Explicit disaster recovery from Sheets must never bypass this trigger.
--    A future ADMIN-only recovery function will be designed separately with
--    its own audit event and confirmation contract.
