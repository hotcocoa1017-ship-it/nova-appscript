-- NOVA_ROOMMAID_CLOSE_CANCEL_DB_FIRST_V1
-- Preserve existing ROOMMAID close reset permission (ADMIN, ORDER) without broadening general daily-close cancel rights.

create or replace function public.nova_roommaid_close_cancel_v1(
  p_business_date text,
  p_site text,
  p_reason text,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no', ''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text := trim(coalesce(p_site, ''));
  v_request_id text := trim(coalesce(p_request_id, ''));
  v_existing record;
  v_cancelled_count integer := 0;
  v_response jsonb;
begin
  if v_actor = '' then
    raise exception using errcode = '42501', message = '로그인이 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_actor and enabled = true;

  if not found or upper(coalesce(v_user.role, '')) not in ('ADMIN', 'ORDER') then
    raise exception using errcode = '42501', message = '룸메이드 마감 초기화 권한이 없습니다.';
  end if;

  begin
    v_date := trim(p_business_date)::date;
  exception when others then
    raise exception '업무일자를 확인해 주세요.';
  end;

  if v_site = '' then
    raise exception '사업장을 선택하세요.';
  end if;

  if not (
    (coalesce(trim(v_user.default_site), '') = '' and cardinality(coalesce(v_user.allowed_sites, array[]::text[])) = 0)
    or v_site = coalesce(v_user.default_site, '')
    or v_site = any(coalesce(v_user.allowed_sites, array[]::text[]))
  ) then
    raise exception using errcode = '42501', message = '사업장 권한이 없습니다.';
  end if;

  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then
    raise exception '요청 ID 형식이 올바르지 않습니다.';
  end if;

  insert into public.nova_request_dedup(request_id, employee_no, action, response_json)
  values(v_request_id, v_actor, 'ROOMMAID_CLOSE_CANCEL_V1', null)
  on conflict(request_id) do nothing;

  if not found then
    select employee_no, action, response_json
      into v_existing
    from public.nova_request_dedup
    where request_id = v_request_id;

    if not found
      or v_existing.employee_no <> v_actor
      or v_existing.action <> 'ROOMMAID_CLOSE_CANCEL_V1' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;

    if v_existing.response_json is not null then
      return v_existing.response_json || jsonb_build_object('idempotent', true);
    end if;

    raise exception '동일 마감초기화 요청이 처리 중입니다.';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended('NOVA_DAILY_CLOSE|' || v_date::text || '|' || v_site, 0)
  );

  update public.nova_daily_close_snapshots
  set is_active = false,
      cancelled_by = v_actor,
      cancelled_at = now(),
      updated_at = now()
  where business_date = v_date
    and site = v_site
    and is_active;
  get diagnostics v_cancelled_count = row_count;

  if v_cancelled_count > 0 then
    insert into public.nova_reporting_state(
      business_date, site, native_complete, completed_by, completed_at, reason, version, updated_at
    ) values(
      v_date, v_site, false, '', null,
      'ROOMMAID_CLOSE_CANCELLED' || case when trim(coalesce(p_reason, '')) <> '' then ':' || left(trim(p_reason), 120) else '' end,
      1, now()
    )
    on conflict(business_date, site) do update
    set native_complete = false,
        completed_by = '',
        completed_at = null,
        reason = excluded.reason,
        version = public.nova_reporting_state.version + 1,
        updated_at = now();
  end if;

  v_response := jsonb_build_object(
    'ok', true,
    'dbFirst', true,
    'businessDate', v_date::text,
    'site', v_site,
    'cancelledCount', v_cancelled_count,
    'noDbSnapshot', v_cancelled_count = 0,
    'cancelledBy', v_actor,
    'requestId', v_request_id,
    'idempotent', false
  );

  update public.nova_request_dedup
  set response_json = v_response
  where request_id = v_request_id;

  return v_response;
end;
$function$;

revoke all on function public.nova_roommaid_close_cancel_v1(text,text,text,text) from public;
revoke all on function public.nova_roommaid_close_cancel_v1(text,text,text,text) from anon;
grant execute on function public.nova_roommaid_close_cancel_v1(text,text,text,text) to authenticated;
grant execute on function public.nova_roommaid_close_cancel_v1(text,text,text,text) to service_role;
