-- QM_RESUME_CONTEXT_DB_AUTHORITY_V1
-- Read-only authoritative resolver for resumed QM sessions whose browser state lost
-- businessDate/site/draftId. The resolver never mutates operational data and fails closed
-- when more than one active draft could match the same employee/room.

create or replace function public.nova_qm_resume_context_v1(
  p_room_no text,
  p_site text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb;
  v_actor text := trim(coalesce(v_claims ->> 'employee_no', ''));
  v_room_no text := trim(coalesce(p_room_no, ''));
  v_site text := trim(coalesce(p_site, ''));
  v_count integer := 0;
  v_draft public.nova_qm_drafts%rowtype;
begin
  if v_actor = '' then
    raise exception 'QM 인증정보가 없습니다.' using errcode = '28000';
  end if;
  if v_room_no = '' then
    raise exception 'QM 재개 객실번호가 없습니다.' using errcode = '22023';
  end if;

  select count(*)
    into v_count
    from public.nova_qm_drafts d
   where d.qm_employee_no = v_actor
     and d.room_no = v_room_no
     and d.status = 'IN_PROGRESS'
     and (v_site = '' or d.site = v_site);

  if v_count = 0 then
    return jsonb_build_object(
      'ok', false,
      'found', false,
      'ambiguous', false,
      'code', 'QM_RESUME_CONTEXT_NOT_FOUND',
      'roomNo', v_room_no
    );
  end if;

  if v_count > 1 then
    return jsonb_build_object(
      'ok', false,
      'found', false,
      'ambiguous', true,
      'code', 'QM_RESUME_CONTEXT_AMBIGUOUS',
      'roomNo', v_room_no,
      'candidateCount', v_count
    );
  end if;

  select d.*
    into v_draft
    from public.nova_qm_drafts d
   where d.qm_employee_no = v_actor
     and d.room_no = v_room_no
     and d.status = 'IN_PROGRESS'
     and (v_site = '' or d.site = v_site)
   limit 1;

  if not public.nova_is_active_qm_for_site(v_actor, v_draft.site) then
    raise exception '해당 사업장의 QM 조회 권한이 없습니다.' using errcode = '42501';
  end if;

  return jsonb_build_object(
    'ok', true,
    'found', true,
    'ambiguous', false,
    'businessDate', v_draft.business_date::text,
    'site', v_draft.site,
    'roomNo', v_draft.room_no,
    'draftId', v_draft.draft_id,
    'draftVersion', v_draft.version,
    'startedAt', v_draft.started_at,
    'savedAt', v_draft.saved_at,
    'source', 'NOVA_QM_RESUME_CONTEXT_DB_AUTHORITY_V1'
  );
end;
$function$;

revoke all on function public.nova_qm_resume_context_v1(text,text) from public;
revoke all on function public.nova_qm_resume_context_v1(text,text) from anon;
grant execute on function public.nova_qm_resume_context_v1(text,text) to authenticated;
grant execute on function public.nova_qm_resume_context_v1(text,text) to service_role;

comment on function public.nova_qm_resume_context_v1(text,text)
  is 'QM_RESUME_CONTEXT_DB_AUTHORITY_V1: resolve one authoritative IN_PROGRESS draft context for resumed sessions; fail closed on ambiguity.';
