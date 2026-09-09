-- ROOM_LAST_QM_CARD_V1
-- Preserve existing room/QM data. Add only a persistent last-valid-QM summary and two read-only card fields.

create schema if not exists nova_private;

create table if not exists nova_private.room_last_qm_state_v1 (
  site text not null,
  room_no text not null,
  last_qm_business_date date,
  last_qm_employee_no text,
  valid boolean not null default false,
  invalidated_business_date date,
  invalidated_reason text,
  updated_at timestamptz not null default now(),
  primary key (site, room_no)
);

alter table public.nova_rooms_current
  add column if not exists last_qm_business_date date;

alter table public.nova_rooms_current
  add column if not exists last_qm_employee_no text;

create or replace function nova_private.apply_room_last_qm_state_v1(
  p_site text,
  p_room_no text,
  p_action text,
  p_after_status text,
  p_business_date date,
  p_employee_no text
)
returns void
language plpgsql
security definer
set search_path = nova_private, public, pg_catalog
as $$
declare
  v_site text := trim(coalesce(p_site,''));
  v_room_no text := trim(coalesce(p_room_no,''));
  v_action text := upper(trim(coalesce(p_action,'')));
  v_after_status text := upper(trim(coalesce(p_after_status,'')));
  v_invalid boolean := false;
  v_reason text := '';
begin
  if v_site = '' or v_room_no = '' or p_business_date is null then
    return;
  end if;

  if v_action = 'QM_COMPLETE' then
    insert into nova_private.room_last_qm_state_v1(
      site, room_no, last_qm_business_date, last_qm_employee_no,
      valid, invalidated_business_date, invalidated_reason, updated_at
    ) values (
      v_site, v_room_no, p_business_date, nullif(trim(coalesce(p_employee_no,'')),''),
      true, null, null, now()
    )
    on conflict (site, room_no) do update set
      last_qm_business_date = excluded.last_qm_business_date,
      last_qm_employee_no = excluded.last_qm_employee_no,
      valid = true,
      invalidated_business_date = null,
      invalidated_reason = null,
      updated_at = now();

    update public.nova_rooms_current
       set last_qm_business_date = p_business_date,
           last_qm_employee_no = nullif(trim(coalesce(p_employee_no,'')),'')
     where business_date = p_business_date
       and site = v_site
       and room_no = v_room_no;
    return;
  end if;

  if v_action = 'CLEANING_COMPLETE' then
    v_invalid := true;
    v_reason := 'CLEANING_COMPLETE';
  elsif v_action = 'CHANGE_ROOM_STATUS'
        and (v_after_status = 'DUE_OUT' or v_after_status like 'CHECKED_OUT%') then
    v_invalid := true;
    v_reason := v_after_status;
  end if;

  if not v_invalid then
    return;
  end if;

  update nova_private.room_last_qm_state_v1
     set valid = false,
         invalidated_business_date = p_business_date,
         invalidated_reason = v_reason,
         updated_at = now()
   where site = v_site
     and room_no = v_room_no
     and valid = true;

  update public.nova_rooms_current
     set last_qm_business_date = null,
         last_qm_employee_no = null
   where business_date = p_business_date
     and site = v_site
     and room_no = v_room_no;
end;
$$;

revoke all on function nova_private.apply_room_last_qm_state_v1(text,text,text,text,date,text) from public;

create or replace function nova_private.room_last_qm_event_trigger_v1()
returns trigger
language plpgsql
security definer
set search_path = nova_private, public, pg_catalog
as $$
begin
  perform nova_private.apply_room_last_qm_state_v1(
    new.site,
    new.room_no,
    new.action,
    new.after_status,
    new.business_date,
    new.employee_no
  );
  return new;
end;
$$;

revoke all on function nova_private.room_last_qm_event_trigger_v1() from public;

drop trigger if exists trg_nova_room_last_qm_state_v1 on public.nova_room_events;
create trigger trg_nova_room_last_qm_state_v1
after insert on public.nova_room_events
for each row
when (new.action in ('QM_COMPLETE','CLEANING_COMPLETE','CHANGE_ROOM_STATUS'))
execute function nova_private.room_last_qm_event_trigger_v1();

create or replace function nova_private.room_last_qm_carry_to_current_v1()
returns trigger
language plpgsql
security definer
set search_path = nova_private, public, pg_catalog
as $$
declare
  v_date date;
  v_employee_no text;
begin
  select s.last_qm_business_date, s.last_qm_employee_no
    into v_date, v_employee_no
    from nova_private.room_last_qm_state_v1 s
   where s.site = new.site
     and s.room_no = new.room_no
     and s.valid = true
     and s.last_qm_business_date <= new.business_date;

  if found then
    new.last_qm_business_date := v_date;
    new.last_qm_employee_no := v_employee_no;
  else
    new.last_qm_business_date := null;
    new.last_qm_employee_no := null;
  end if;
  return new;
end;
$$;

revoke all on function nova_private.room_last_qm_carry_to_current_v1() from public;

drop trigger if exists trg_nova_rooms_current_last_qm_carry_v1 on public.nova_rooms_current;
create trigger trg_nova_rooms_current_last_qm_carry_v1
before insert on public.nova_rooms_current
for each row
execute function nova_private.room_last_qm_carry_to_current_v1();

-- Existing Broadcast no-op guard must treat the two new read fields as real changes.
create or replace function public.nova_rooms_current_broadcast()
returns trigger
language plpgsql
security definer
set search_path to ''
as $$
begin
  if tg_op = 'DELETE'
     and old.business_date < (now() at time zone 'Asia/Seoul')::date then
    return null;
  end if;

  if tg_op = 'UPDATE'
     and new.id is not distinct from old.id
     and new.business_date is not distinct from old.business_date
     and new.site is not distinct from old.site
     and new.room_no is not distinct from old.room_no
     and new.building is not distinct from old.building
     and new.room_status is not distinct from old.room_status
     and new.cleaning_status is not distinct from old.cleaning_status
     and new.cleaning_type is not distinct from old.cleaning_type
     and new.assignment_type is not distinct from old.assignment_type
     and new.roommaid_employee_no is not distinct from old.roommaid_employee_no
     and new.secondary_roommaid_employee_no is not distinct from old.secondary_roommaid_employee_no
     and new.qm_employee_no is not distinct from old.qm_employee_no
     and new.operational_status is not distinct from old.operational_status
     and new.version is not distinct from old.version
     and new.cleaning_started_at is not distinct from old.cleaning_started_at
     and new.cleaning_completed_at is not distinct from old.cleaning_completed_at
     and new.updated_by is not distinct from old.updated_by
     and new.last_qm_business_date is not distinct from old.last_qm_business_date
     and new.last_qm_employee_no is not distinct from old.last_qm_employee_no then
    return null;
  end if;

  perform realtime.broadcast_changes(
    'nova:site:' || coalesce(new.site, old.site) || ':rooms',
    tg_op,
    tg_op,
    tg_table_name,
    tg_table_schema,
    new,
    old
  );
  return null;
end;
$$;

-- Initial reconstruction from preserved Archive WORK_HISTORY.
-- Only the latest relevant archived transition per room matters:
-- QM_COMPLETE = valid, later CLEANING_COMPLETE/DUE_OUT/CHECKED_OUT* = invalid.
with ranked as (
  select
    site,
    room_no,
    business_date,
    employee_no,
    record_type,
    status,
    row_number() over (
      partition by site, room_no
      order by business_date desc,
               coalesce(source_row_number,0) desc,
               archived_at desc
    ) as rn
  from public.nova_archive_index
  where source_type = 'WORK_HISTORY'
    and business_date < (now() at time zone 'Asia/Seoul')::date
    and room_no is not null
    and trim(room_no) <> ''
    and (
      record_type = 'QM_COMPLETE'
      or record_type = 'CLEANING_COMPLETE'
      or (record_type = 'CHANGE_ROOM_STATUS' and (status = 'DUE_OUT' or status like 'CHECKED_OUT%'))
    )
)
insert into nova_private.room_last_qm_state_v1(
  site, room_no, last_qm_business_date, last_qm_employee_no, valid, updated_at
)
select
  site,
  room_no,
  business_date,
  nullif(trim(coalesce(employee_no,'')),''),
  true,
  now()
from ranked
where rn = 1
  and record_type = 'QM_COMPLETE'
on conflict (site, room_no) do update set
  last_qm_business_date = excluded.last_qm_business_date,
  last_qm_employee_no = excluded.last_qm_employee_no,
  valid = true,
  invalidated_business_date = null,
  invalidated_reason = null,
  updated_at = now();

-- Replay today's hot events in event order so the current state wins over Archive reconstruction.
do $$
declare
  r record;
begin
  for r in
    select site, room_no, action, after_status, business_date, employee_no
      from public.nova_room_events
     where business_date >= (now() at time zone 'Asia/Seoul')::date
       and action in ('QM_COMPLETE','CLEANING_COMPLETE','CHANGE_ROOM_STATUS')
       and (
         action <> 'CHANGE_ROOM_STATUS'
         or after_status = 'DUE_OUT'
         or after_status like 'CHECKED_OUT%'
       )
     order by business_date, coalesce(event_time,created_at), id
  loop
    perform nova_private.apply_room_last_qm_state_v1(
      r.site, r.room_no, r.action, r.after_status, r.business_date, r.employee_no
    );
  end loop;
end;
$$;

-- Attach only the new auxiliary fields to today's already-existing room rows.
update public.nova_rooms_current r
   set last_qm_business_date = s.last_qm_business_date,
       last_qm_employee_no = s.last_qm_employee_no
  from nova_private.room_last_qm_state_v1 s
 where r.business_date = (now() at time zone 'Asia/Seoul')::date
   and r.site = s.site
   and r.room_no = s.room_no
   and s.valid = true
   and s.last_qm_business_date <= r.business_date;
