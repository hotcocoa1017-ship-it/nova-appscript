-- NOVA Realtime private broadcast receive fallback
-- Applied to production nova-realtime on 2026-09-05.
-- Keeps existing JWT sites authorization and adds a server-side nova_users fallback
-- for enabled operational users whose token/site array may be empty.

create or replace function public.nova_realtime_topic_allowed(p_topic text)
returns boolean
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  select exists (
    select 1
    from public.nova_users u
    where u.employee_no = coalesce(
      (current_setting('request.jwt.claims', true)::jsonb ->> 'employee_no'), ''
    )
      and u.enabled = true
      and split_part(p_topic, ':', 1) = 'nova'
      and split_part(p_topic, ':', 2) = 'site'
      and split_part(p_topic, ':', 4) = 'rooms'
      and split_part(p_topic, ':', 5) = ''
      and (
        coalesce(array_length(u.allowed_sites, 1), 0) = 0
        or split_part(p_topic, ':', 3) = any(u.allowed_sites)
      )
  );
$$;

revoke all on function public.nova_realtime_topic_allowed(text) from public;
grant execute on function public.nova_realtime_topic_allowed(text) to authenticated;

drop policy if exists "nova realtime receive by site" on realtime.messages;
create policy "nova realtime receive by site"
on realtime.messages
for select
to authenticated
using (
  extension = 'broadcast'
  and (
    exists (
      select 1
      from jsonb_array_elements_text(
        coalesce(
          (current_setting('request.jwt.claims', true)::jsonb -> 'sites'),
          '[]'::jsonb
        )
      ) s(site_name)
      where realtime.topic() = ('nova:site:' || s.site_name || ':rooms')
    )
    or public.nova_realtime_topic_allowed(realtime.topic())
  )
);
