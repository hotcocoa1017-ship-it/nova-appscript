-- NOVA_SHIFT_ZONE_DB_FIRST_V2
-- Explicitly remove anon EXECUTE grants and add a one-time roster initialization marker.

create table if not exists public.nova_houseman_roster_state (
  business_date date not null,
  site text not null,
  initialized_by text not null,
  initialized_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  version bigint not null default 1 check (version > 0),
  primary key (business_date, site)
);

alter table public.nova_houseman_roster_state enable row level security;
revoke all on table public.nova_houseman_roster_state from anon, authenticated;
grant select, insert, update, delete on table public.nova_houseman_roster_state to service_role;

-- Supabase projects can carry explicit default grants to anon; revoke them explicitly.
revoke execute on function public.nova_houseman_shift_zone_get_v1(text,text) from anon;
revoke execute on function public.nova_houseman_shift_save_v1(text,text,jsonb,text) from anon;
revoke execute on function public.nova_houseman_zone_save_v1(text,text,text,jsonb,text,text) from anon;
revoke execute on function public.nova_business_date_v1(timestamptz) from anon;

create or replace function public.nova_houseman_shift_zone_get_v2(
  p_business_date text,
  p_site text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_result jsonb;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_initialized boolean := false;
begin
  -- V1 performs the full JWT/user/site authorization before any state is returned.
  v_result := public.nova_houseman_shift_zone_get_v1(p_business_date, p_site);
  v_date := (v_result->>'businessDate')::date;
  select exists(
    select 1 from public.nova_houseman_roster_state
    where business_date=v_date and site=v_site
  ) into v_initialized;
  return v_result || jsonb_build_object('initialized',v_initialized,'dbFirstVersion',2);
end;
$$;

revoke all on function public.nova_houseman_shift_zone_get_v2(text,text) from public;
revoke execute on function public.nova_houseman_shift_zone_get_v2(text,text) from anon;
grant execute on function public.nova_houseman_shift_zone_get_v2(text,text) to authenticated, service_role;

create or replace function public.nova_houseman_shift_save_v2(
  p_business_date text,
  p_site text,
  p_assignments jsonb,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_result jsonb;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_version bigint := 1;
begin
  -- V1 performs authorization, validation, locking and idempotent roster replacement.
  v_result := public.nova_houseman_shift_save_v1(p_business_date,p_site,p_assignments,p_request_id);
  v_date := (v_result->>'businessDate')::date;
  v_version := greatest(1,coalesce((v_result->>'version')::bigint,1));

  insert into public.nova_houseman_roster_state(
    business_date,site,initialized_by,initialized_at,updated_at,version
  ) values(
    v_date,v_site,v_actor,now(),now(),v_version
  )
  on conflict(business_date,site) do update set
    initialized_by=excluded.initialized_by,
    updated_at=now(),
    version=greatest(public.nova_houseman_roster_state.version+1,excluded.version);

  return v_result || jsonb_build_object('initialized',true,'dbFirstVersion',2);
end;
$$;

revoke all on function public.nova_houseman_shift_save_v2(text,text,jsonb,text) from public;
revoke execute on function public.nova_houseman_shift_save_v2(text,text,jsonb,text) from anon;
grant execute on function public.nova_houseman_shift_save_v2(text,text,jsonb,text) to authenticated, service_role;
