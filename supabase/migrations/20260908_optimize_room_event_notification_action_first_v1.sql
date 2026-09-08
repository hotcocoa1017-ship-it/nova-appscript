-- NOVA_ROOM_EVENT_NOTIFICATION_ACTION_FIRST_V1
-- Most room events do not emit notifications. Reject non-notification actions before
-- evaluating the business-date window; notification semantics remain unchanged.

create or replace function nova_private.nova_room_event_notification_trigger()
returns trigger
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_room public.nova_rooms_current%rowtype;
  v_emp text;
  v_key text := coalesce(new.event_id::text, new.id::text);
begin
  -- ROOM_EVENT_NOTIFICATION_ACTION_FIRST_V1
  if upper(coalesce(new.action, '')) not in ('QM_REWORK','CLEANING_COMPLETE') then return new; end if;
  if not nova_private.nova_notification_business_date_active(new.business_date) then return new; end if;

  select * into v_room
  from public.nova_rooms_current r
  where r.business_date = new.business_date
    and r.site = new.site
    and r.room_no = new.room_no
  limit 1;

  if not found then return new; end if;

  if upper(new.action) = 'QM_REWORK' then
    v_emp := btrim(coalesce(v_room.roommaid_employee_no, ''));
    if v_emp <> '' then
      perform nova_private.nova_notification_emit(
        v_emp,'QM_REWORK','QM 재정비 요청',new.room_no || '호 · 재정비가 요청되었습니다.',
        new.site,new.room_no,'ROOM_EVENT',v_key,'HIGH',
        jsonb_build_object('route','cleaning','site',new.site,'roomNo',new.room_no,'eventId',v_key),
        'QM_REWORK|' || v_key || '|' || v_emp
      );
    end if;
    v_emp := btrim(coalesce(v_room.secondary_roommaid_employee_no, ''));
    if v_emp <> '' and v_emp is distinct from btrim(coalesce(v_room.roommaid_employee_no, '')) then
      perform nova_private.nova_notification_emit(
        v_emp,'QM_REWORK','QM 재정비 요청',new.room_no || '호 · 재정비가 요청되었습니다.',
        new.site,new.room_no,'ROOM_EVENT',v_key,'HIGH',
        jsonb_build_object('route','cleaning','site',new.site,'roomNo',new.room_no,'eventId',v_key),
        'QM_REWORK|' || v_key || '|' || v_emp
      );
    end if;
  elsif upper(new.action) = 'CLEANING_COMPLETE' then
    v_emp := btrim(coalesce(v_room.qm_employee_no, ''));
    if v_emp <> '' then
      perform nova_private.nova_notification_emit(
        v_emp,'CLEANING_COMPLETE','청소 완료 · QM 점검 가능',new.room_no || '호 청소가 완료되었습니다.',
        new.site,new.room_no,'ROOM_EVENT',v_key,'NORMAL',
        jsonb_build_object('route','qm','site',new.site,'roomNo',new.room_no,'eventId',v_key),
        'CLEANING_COMPLETE|' || v_key || '|' || v_emp
      );
    end if;
  end if;

  return new;
end;
$function$;
