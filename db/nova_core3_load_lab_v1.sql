-- NOVA Core 3.0 Room State isolated load laboratory V1
--
-- IMPORTANT:
--   This migration is for a fresh Supabase DEVELOPMENT BRANCH only.
--   It deliberately refuses to run when NOVA operational users or rooms exist,
--   so applying it to the live production database fails before any load data is written.
--
-- Synthetic business date: 2099-01-01
-- Synthetic site:          쏘라노
-- Synthetic identities:    LOAD*
-- Synthetic rooms:         S*/C*/DUP*/CONT*/FAIL*/TIME*/MISS*

begin;

do $guard$
begin
  if exists (select 1 from public.nova_users limit 1)
     or exists (select 1 from public.nova_rooms_current limit 1) then
    raise exception using
      errcode = '55000',
      message = 'NOVA Core3 load lab seed refused: target database is not an empty isolated branch.';
  end if;
end;
$guard$;

create schema if not exists nova_private;

create table if not exists nova_private.core_load_lab_state (
  singleton boolean primary key default true check (singleton),
  marker text not null,
  seeded_at timestamptz not null default now()
);

revoke all on nova_private.core_load_lab_state from public, anon, authenticated;
grant select on nova_private.core_load_lab_state to service_role;

insert into nova_private.core_load_lab_state(singleton, marker)
values (true, 'ISOLATED_BRANCH_ONLY')
on conflict (singleton) do update
set marker = excluded.marker,
    seeded_at = now();

insert into public.nova_users(
  employee_no, name, role, enabled, default_site, allowed_sites, updated_at
)
values
  ('LOAD200',  'NOVA LOAD', 'ROOMMAID', true, '쏘라노', array['쏘라노']::text[], now()),
  ('LOAD500',  'NOVA LOAD', 'ROOMMAID', true, '쏘라노', array['쏘라노']::text[], now()),
  ('LOAD1000', 'NOVA LOAD', 'ROOMMAID', true, '쏘라노', array['쏘라노']::text[], now()),
  ('LOADDUP',  'NOVA LOAD', 'ROOMMAID', true, '쏘라노', array['쏘라노']::text[], now()),
  ('LOADCONT', 'NOVA LOAD', 'ROOMMAID', true, '쏘라노', array['쏘라노']::text[], now()),
  ('LOADFAIL', 'NOVA LOAD', 'ROOMMAID', true, '쏘라노', array['쏘라노']::text[], now()),
  ('LOADTIME', 'NOVA LOAD', 'ROOMMAID', true, '쏘라노', array['쏘라노']::text[], now()),
  ('LOADMISS', 'NOVA LOAD', 'ROOMMAID', true, '쏘라노', array['쏘라노']::text[], now());

with stages(employee_no, room_prefix, room_count, initial_status) as (
  values
    ('LOAD200'::text,  'S200'::text,  200,  'WAITING'::text),
    ('LOAD200'::text,  'C200'::text,  200,  'CLEANING'::text),
    ('LOAD500'::text,  'S500'::text,  500,  'WAITING'::text),
    ('LOAD500'::text,  'C500'::text,  500,  'CLEANING'::text),
    ('LOAD1000'::text, 'S1000'::text, 1000, 'WAITING'::text),
    ('LOAD1000'::text, 'C1000'::text, 1000, 'CLEANING'::text)
)
insert into public.nova_rooms_current(
  business_date,
  site,
  room_no,
  building,
  room_status,
  cleaning_status,
  cleaning_type,
  assignment_type,
  roommaid_employee_no,
  secondary_roommaid_employee_no,
  qm_employee_no,
  operational_status,
  version,
  cleaning_started_at,
  cleaning_completed_at,
  updated_by,
  updated_at
)
select
  date '2099-01-01',
  '쏘라노',
  s.room_prefix || lpad(g.n::text, 4, '0'),
  'LOAD',
  'STAY',
  s.initial_status,
  'NORMAL',
  'SOLO',
  s.employee_no,
  null,
  null,
  '',
  1,
  case when s.initial_status = 'CLEANING' then now() - interval '1 minute' else null end,
  null,
  'CORE3_LOAD_SEED',
  now()
from stages s
cross join lateral generate_series(1, s.room_count) as g(n);

insert into public.nova_rooms_current(
  business_date, site, room_no, building, room_status, cleaning_status,
  cleaning_type, assignment_type, roommaid_employee_no,
  secondary_roommaid_employee_no, qm_employee_no, operational_status,
  version, cleaning_started_at, cleaning_completed_at, updated_by, updated_at
)
values
  (date '2099-01-01','쏘라노','DUP2000001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADDUP',null,null,'',1,null,null,'CORE3_LOAD_SEED',now()),
  (date '2099-01-01','쏘라노','DUP5000001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADDUP',null,null,'',1,null,null,'CORE3_LOAD_SEED',now()),
  (date '2099-01-01','쏘라노','DUP10000001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADDUP',null,null,'',1,null,null,'CORE3_LOAD_SEED',now()),
  (date '2099-01-01','쏘라노','CONT2000001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADCONT',null,null,'',1,null,null,'CORE3_LOAD_SEED',now()),
  (date '2099-01-01','쏘라노','CONT5000001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADCONT',null,null,'',1,null,null,'CORE3_LOAD_SEED',now()),
  (date '2099-01-01','쏘라노','CONT10000001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADCONT',null,null,'',1,null,null,'CORE3_LOAD_SEED',now()),
  (date '2099-01-01','쏘라노','FAIL0001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADFAIL',null,null,'',1,null,null,'CORE3_LOAD_SEED',now()),
  (date '2099-01-01','쏘라노','TIME0001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADTIME',null,null,'',1,null,null,'CORE3_LOAD_SEED',now()),
  (date '2099-01-01','쏘라노','MISS0001','LOAD','STAY','WAITING','NORMAL','SOLO','LOADMISS',null,null,'',1,null,null,'CORE3_LOAD_SEED',now());

-- The branch must contain only the expected synthetic scope after seeding.
do $verify$
declare
  v_users integer;
  v_rooms integer;
begin
  select count(*) into v_users from public.nova_users;
  select count(*) into v_rooms from public.nova_rooms_current;

  if v_users <> 8 then
    raise exception 'Core3 load lab user count mismatch: %', v_users;
  end if;
  if v_rooms <> 3409 then
    raise exception 'Core3 load lab room count mismatch: %', v_rooms;
  end if;
  if exists (
    select 1 from public.nova_users where employee_no !~ '^LOAD'
  ) or exists (
    select 1 from public.nova_rooms_current
    where business_date <> date '2099-01-01'
       or site <> '쏘라노'
       or updated_by <> 'CORE3_LOAD_SEED'
  ) then
    raise exception 'Core3 load lab contains non-synthetic operational data.';
  end if;
end;
$verify$;

commit;
