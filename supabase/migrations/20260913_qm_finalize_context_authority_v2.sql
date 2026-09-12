-- QM_FINALIZE_CONTEXT_AUTHORITY_V2
-- Root-cause guard for resumed QM sessions after direct-DB transport promotion.
-- The browser may lose businessDate/site/draftId while the modal still retains roomNo.
-- Finalize therefore resolves canonical context from the authoritative DB draft BEFORE
-- date/site validation. Client/session fields are advisory only.

create or replace function public.nova_qm_finalize_resolve_context_v1(p_payload jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_payload jsonb := coalesce(p_payload, '{}'::jsonb);
  v_draft_id text := trim(coalesce(v_payload->>'draftId',''));
  v_site text := trim(coalesce(v_payload->>'site',''));
  v_room_no text := trim(coalesce(v_payload->>'roomNo',''));
  v_match public.nova_qm_drafts%rowtype;
  v_match_count integer := 0;
begin
  -- Authentication/business permissions remain enforced by the canonical core finalizer.
  -- This helper only resolves authoritative draft context before date/site validation.
  if v_actor = '' then
    return v_payload;
  end if;

  -- 1) Exact draft id is strongest and also supports retries after the draft completed.
  if v_draft_id <> '' then
    select d.* into v_match
    from public.nova_qm_drafts d
    where d.draft_id = v_draft_id
      and d.qm_employee_no = v_actor
    limit 1;
  end if;

  -- 2) Standard resumed-session recovery: actor + site + room + IN_PROGRESS.
  if v_match.draft_id is null and v_site <> '' and v_room_no <> '' then
    select d.* into v_match
    from public.nova_qm_drafts d
    where d.qm_employee_no = v_actor
      and d.site = v_site
      and d.room_no = v_room_no
      and d.status = 'IN_PROGRESS'
    order by d.saved_at desc, d.started_at desc
    limit 1;
  end if;

  -- 3) If browser state lost both businessDate and site, roomNo still identifies the modal.
  -- Recover only when there is exactly one active draft; ambiguity fails closed.
  if v_match.draft_id is null and v_room_no <> '' then
    select count(*) into v_match_count
    from public.nova_qm_drafts d
    where d.qm_employee_no = v_actor
      and d.room_no = v_room_no
      and d.status = 'IN_PROGRESS';

    if v_match_count = 1 then
      select d.* into v_match
      from public.nova_qm_drafts d
      where d.qm_employee_no = v_actor
        and d.room_no = v_room_no
        and d.status = 'IN_PROGRESS'
      order by d.saved_at desc, d.started_at desc
      limit 1;
    elsif v_match_count > 1 then
      raise exception using errcode='22023', message='진행 중인 QM 초안이 여러 건입니다. 화면을 새로고침한 뒤 다시 시도하세요.';
    end if;
  end if;

  -- DB draft is authoritative. Overwrite stale/blank client context as one atomic bundle.
  if v_match.draft_id is not null then
    v_payload := jsonb_set(v_payload, '{draftId}', to_jsonb(v_match.draft_id), true);
    v_payload := jsonb_set(v_payload, '{businessDate}', to_jsonb(v_match.business_date::text), true);
    v_payload := jsonb_set(v_payload, '{site}', to_jsonb(v_match.site), true);
    v_payload := jsonb_set(v_payload, '{roomNo}', to_jsonb(v_match.room_no), true);
  end if;

  return v_payload;
end;
$$;

revoke all on function public.nova_qm_finalize_resolve_context_v1(jsonb) from public, anon, authenticated;

-- Preserve the canonical atomic V2 body under a stable core name. Production already has
-- this function from the incident migration; deployment must fail rather than silently
-- replace the atomic implementation if that core is missing.
do $$
begin
  if to_regprocedure('public.nova_qm_inspection_finalize_v2_core_20260912(jsonb,text)') is null then
    raise exception 'QM finalize canonical core is missing';
  end if;
end $$;

create or replace function public.nova_qm_inspection_finalize_v2(p_payload jsonb, p_request_id text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_existing record;
  v_payload jsonb;
begin
  -- Idempotent retries are checked before context parsing. This covers the case where the
  -- first commit succeeded but the browser lost context before receiving the response.
  if v_actor <> '' and v_request_id <> '' then
    select employee_no, action, response_json
      into v_existing
    from public.nova_request_dedup
    where request_id = v_request_id;

    if found then
      if v_existing.employee_no <> v_actor or v_existing.action <> 'QM_INSPECTION_FINALIZE_V2' then
        raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
      end if;
      if v_existing.response_json is not null then
        return v_existing.response_json || jsonb_build_object('idempotent', true);
      end if;
      raise exception '동일 점검결과가 처리 중입니다. 잠시 후 다시 확인해 주세요.';
    end if;
  end if;

  v_payload := public.nova_qm_finalize_resolve_context_v1(p_payload);
  return public.nova_qm_inspection_finalize_v2_core_20260912(v_payload, p_request_id);
end;
$$;

comment on function public.nova_qm_finalize_resolve_context_v1(jsonb)
  is 'QM_FINALIZE_CONTEXT_AUTHORITY_V1: authoritative draft context recovery before finalize validation';
comment on function public.nova_qm_inspection_finalize_v2(jsonb,text)
  is 'QM_FINALIZE_CONTEXT_AUTHORITY_V2: idempotent retry guard + authoritative draft context + canonical atomic core';

grant execute on function public.nova_qm_inspection_finalize_v2(jsonb,text) to authenticated, service_role;
