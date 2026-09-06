-- ROOM_UPLOAD_RESET_DB_PARITY_V1
-- RESET_REPLACE clears room-maintenance/QM report sources while preserving Houseman orders, shifts and zones.

create or replace function nova_private.room_upload_reset_report_sources_v1()
returns trigger
language plpgsql
security definer
set search_path = public, nova_private, pg_catalog
as $$
begin
  if upper(coalesce(new.apply_mode,'')) <> 'RESET_REPLACE' then
    return new;
  end if;

  -- Same business meaning as resetRoomMaintenanceHistoryForUpload_: room-status/cleaning/QM/close are reset.
  -- Houseman orders live in nova_houseman_orders and are intentionally preserved.
  delete from public.nova_room_events
  where business_date=new.business_date and site=new.site;

  delete from public.nova_qm_drafts
  where business_date=new.business_date and site=new.site;

  delete from public.nova_qm_inspections
  where business_date=new.business_date and site=new.site;

  update public.nova_daily_close_snapshots
  set is_active=false,
      cancelled_by=new.registered_by,
      cancelled_at=now(),
      version=version+1,
      updated_at=now()
  where business_date=new.business_date and site=new.site and is_active;

  return new;
end;
$$;

drop trigger if exists trg_nova_room_upload_reset_report_sources on public.nova_room_upload_snapshots;
create trigger trg_nova_room_upload_reset_report_sources
after insert on public.nova_room_upload_snapshots
for each row execute function nova_private.room_upload_reset_report_sources_v1();
