-- NOVA QM Draft DB-first V1 rollback
-- Safe to run only if the new QM DB-first path is disabled.
-- Existing NOVA production tables are not touched by this rollback.

revoke all on function public.nova_save_qm_draft(text,date,text,text,text,jsonb,jsonb,bigint,text) from authenticated;
drop function if exists public.nova_save_qm_draft(text,date,text,text,text,jsonb,jsonb,bigint,text);

revoke all on function public.nova_is_active_qm_for_site(text,text) from authenticated;
drop function if exists public.nova_is_active_qm_for_site(text,text);

drop table if exists public.nova_qm_drafts;
