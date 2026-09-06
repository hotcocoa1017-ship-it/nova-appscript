-- Fix Core 3 auth wrapper boundary.
-- Keep nova_private functions inaccessible; only vetted public wrappers execute as owner.

create or replace function public.nova_core_login_identity_v1(
  p_name text,
  p_employee_no text,
  p_site text default ''
) returns jsonb
language sql
security definer
set search_path = ''
as $$
  select nova_private.core_login_identity_v1_internal(p_name, p_employee_no, p_site);
$$;

revoke all on function public.nova_core_login_identity_v1(text,text,text) from public;
grant execute on function public.nova_core_login_identity_v1(text,text,text) to anon, authenticated;

create or replace function public.nova_core_me_v1()
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select nova_private.core_me_v1_internal();
$$;

revoke all on function public.nova_core_me_v1() from public, anon;
grant execute on function public.nova_core_me_v1() to authenticated;
