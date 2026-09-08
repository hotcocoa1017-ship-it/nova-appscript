-- NOVA_ROOM_ASSIGNMENT_NOTIFICATION_EARLY_EXIT_V1
-- Preserve ROOMMAID/QM assignment notification semantics while avoiding business-date
-- eligibility work when UPDATE OF lists assignment columns but none actually changed.

create or replace function nova_private.nova_room_assignment_notification_trigger()
returns trigger
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_primary text := btrim(coalesce(new.roommaid_employee_no, ''));
  v_secondary text := btrim(coalesce(new.secondary_roommaid_employee_no, ''));
  v_qm text := btrim(coalesce(new.qm_employee_no, ''));
  v_old_primary text := btrim(coalesce(old.roommaid_employee_no, ''));
  v_old_secondary text := btrim(coalesce(old.secondary_roommaid_employee_no, ''));
  v_primary_changed boolean := false;
  v_secondary_changed boolean := false;
  v_qm_changed boolean := false;
begin
  v_primary_changed := v_primary <> ''
    and v_primary is distinct from v_old_primary
    and v_primary is distinct from v_old_secondary;

  v_secondary_changed := v_secondary <> ''
    and v_secondary is distinct from v_primary
    and v_secondary is distinct from v_old_primary
    and v_secondary is distinct from v_old_secondary;

  v_qm_changed := v_qm <> ''
    and new.qm_employee_no is distinct from old.qm_employee_no;

  -- ROOM_ASSIGNMENT_NOTIFICATION_EARLY_EXIT_V1
  if not (v_primary_changed or v_secondary_changed or v_qm_changed) then return new; end if;

  if not nova_private.nova_notification_business_date_active(new.business_date) then return new; end if;

  if v_primary_changed then
    perform nova_private.nova_notification_emit(
      v_primary,
      'ROOMMAID_ASSIGN',
      '새 정비객실 배정',
      concat_ws(' · ', nullif(new.room_no, '') || '호', nullif(new.cleaning_type, '')),
      new.site,
      new.room_no,
      'ROOM',
      new.id::text,
      'NORMAL',
      jsonb_build_object('route','cleaning','site',new.site,'roomNo',new.room_no),
      'ROOMMAID_ASSIGN|' || new.id::text || '|' || v_primary || '|' || coalesce(new.version, 0)::text
    );
  end if;

  if v_secondary_changed then
    perform nova_private.nova_notification_emit(
      v_secondary,
      'ROOMMAID_ASSIGN',
      '새 정비객실 배정',
      concat_ws(' · ', nullif(new.room_no, '') || '호', nullif(new.cleaning_type, '')),
      new.site,
      new.room_no,
      'ROOM',
      new.id::text,
      'NORMAL',
      jsonb_build_object('route','cleaning','site',new.site,'roomNo',new.room_no),
      'ROOMMAID_ASSIGN|' || new.id::text || '|' || v_secondary || '|' || coalesce(new.version, 0)::text
    );
  end if;

  if v_qm_changed then
    perform nova_private.nova_notification_emit(
      v_qm,
      'QM_ASSIGN',
      'QM 점검객실 배정',
      concat_ws(' · ', nullif(new.room_no, '') || '호', '점검대상'),
      new.site,
      new.room_no,
      'ROOM',
      new.id::text,
      'NORMAL',
      jsonb_build_object('route','qm','site',new.site,'roomNo',new.room_no),
      'QM_ASSIGN|' || new.id::text || '|' || v_qm || '|' || coalesce(new.version, 0)::text
    );
  end if;

  return new;
end;
$function$;
