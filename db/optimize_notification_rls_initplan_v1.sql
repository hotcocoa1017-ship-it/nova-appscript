-- NOVA notification center V1 RLS performance optimization.
-- Applied after nova_notification_center_v1.
-- auth.jwt() is evaluated once through an InitPlan instead of per row.

drop policy if exists "nova notifications read own" on public.nova_notifications;
create policy "nova notifications read own"
on public.nova_notifications
for select
to authenticated
using (
  recipient_employee_no = coalesce(((select auth.jwt()) ->> 'employee_no'), '')
);

drop policy if exists "nova notifications mark own read" on public.nova_notifications;
create policy "nova notifications mark own read"
on public.nova_notifications
for update
to authenticated
using (
  recipient_employee_no = coalesce(((select auth.jwt()) ->> 'employee_no'), '')
)
with check (
  recipient_employee_no = coalesce(((select auth.jwt()) ->> 'employee_no'), '')
);

drop policy if exists "nova notification realtime receive" on realtime.messages;
create policy "nova notification realtime receive"
on realtime.messages
for select
to authenticated
using (
  extension = 'broadcast'
  and realtime.topic() = (
    'nova:user:' || coalesce(((select auth.jwt()) ->> 'employee_no'), '') || ':notifications'
  )
);