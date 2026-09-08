-- NOVA_HOUSEMAN_NOTIFICATION_EARLY_EXIT_V1
-- Preserve HOUSEMAN assignment notification semantics while avoiding notification
-- eligibility work for status-only updates where assigned_employee_no is unchanged.

create or replace function nova_private.nova_houseman_notification_trigger()
returns trigger
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_changed boolean := false;
  v_emp text := btrim(coalesce(new.assigned_employee_no, ''));
  v_priority text := case when coalesce(new.important, false) then 'HIGH' else 'NORMAL' end;
begin
  if tg_op = 'INSERT' then
    v_changed := v_emp <> '';
  else
    v_changed := v_emp <> '' and new.assigned_employee_no is distinct from old.assigned_employee_no;
  end if;

  -- HOUSEMAN_NOTIFICATION_EARLY_EXIT_V1
  if not v_changed then return new; end if;

  if not nova_private.nova_notification_business_date_active(new.business_date) then return new; end if;
  if upper(coalesce(new.status_code, '')) not in ('SAVING','REGISTERED','ASSIGNED','ACCEPTED','PROCESSING') then return new; end if;

  perform nova_private.nova_notification_emit(
    v_emp,
    'HOUSEMAN_ASSIGN',
    case when coalesce(new.important, false) then '중요 하우스맨 오더' else '새 하우스맨 오더' end,
    concat_ws(' · ', nullif(new.room_no, '') || '호', nullif(new.item_summary, '')),
    new.site,
    new.room_no,
    'HOUSEMAN_ORDER',
    new.order_id,
    v_priority,
    jsonb_build_object('route','houseman','site',new.site,'roomNo',new.room_no,'orderId',new.order_id),
    'HOUSEMAN_ASSIGN|' || new.order_id || '|' || v_emp || '|' || coalesce(new.version, 0)::text
  );
  return new;
end;
$function$;
