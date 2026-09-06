-- NOVA daily close atomic multi-site cancel RPC v1
-- PostgreSQL is authoritative; Sheet soft-delete must run only after this transaction succeeds.

create or replace function public.nova_daily_close_cancel_many_v1(
  p_business_date text,
  p_sites jsonb,
  p_reason text,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no', ''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_sites text[];
  v_site text;
  v_request_id text := trim(coalesce(p_request_id, ''));
  v_response jsonb;
  v_existing record;
  v_dedup_inserted integer := 0;
  v_active_count integer := 0;
  v_cancelled_count integer := 0;
begin
  if v_actor = '' then
    raise exception using errcode = '42501', message = '로그인이 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_actor and enabled = true;

  if not found or upper(coalesce(v_user.role, '')) <> 'ADMIN' then
    raise exception using errcode = '42501', message = '마감 취소 권한이 없습니다.';
  end if;

  begin
    v_date := trim(p_business_date)::date;
  exception when others then
    raise exception '업무일자를 확인해 주세요.';
  end;

  if p_sites is null or jsonb_typeof(p_sites) <> 'array' then
    raise exception '취소할 사업장 목록이 올바르지 않습니다.';
  end if;

  select coalesce(array_agg(site order by site), array[]::text[])
    into v_sites
  from (
    select distinct trim(value) as site
    from jsonb_array_elements_text(p_sites)
    where trim(value) <> ''
  ) q;

  if cardinality(v_sites) = 0 then
    raise exception '취소할 사업장이 없습니다.';
  end if;
  if cardinality(v_sites) > 20 then
    raise exception '한 번에 취소할 수 있는 사업장이 너무 많습니다.';
  end if;

  if not (coalesce(trim(v_user.default_site), '') = '' and cardinality(coalesce(v_user.allowed_sites, array[]::text[])) = 0) then
    if exists (
      select 1
      from unnest(v_sites) s(site)
      where s.site <> coalesce(v_user.default_site, '')
        and not (s.site = any(coalesce(v_user.allowed_sites, array[]::text[])))
    ) then
      raise exception using errcode = '42501', message = '사업장 권한이 없습니다.';
    end if;
  end if;

  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then
    raise exception '요청 ID 형식이 올바르지 않습니다.';
  end if;

  insert into public.nova_request_dedup(request_id, employee_no, action, response_json)
  values(v_request_id, v_actor, 'DAILY_CLOSE_CANCEL_MANY_V1', null)
  on conflict(request_id) do nothing;
  get diagnostics v_dedup_inserted = row_count;

  if v_dedup_inserted = 0 then
    select employee_no, action, response_json
      into v_existing
    from public.nova_request_dedup
    where request_id = v_request_id;

    if not found
      or v_existing.employee_no <> v_actor
      or v_existing.action <> 'DAILY_CLOSE_CANCEL_MANY_V1' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;

    if v_existing.response_json is not null then
      return v_existing.response_json || jsonb_build_object('idempotent', true);
    end if;

    raise exception '동일 마감취소 요청이 처리 중입니다.';
  end if;

  -- Deterministic lock order prevents multi-site deadlocks.
  foreach v_site in array v_sites loop
    perform pg_advisory_xact_lock(
      hashtextextended('NOVA_DAILY_CLOSE|' || v_date::text || '|' || v_site, 0)
    );
  end loop;

  -- Validate every requested site before changing any row. One missing site aborts the whole transaction.
  select count(*)::integer
    into v_active_count
  from public.nova_daily_close_snapshots
  where business_date = v_date
    and site = any(v_sites)
    and is_active;

  if v_active_count <> cardinality(v_sites) then
    raise exception '취소할 DB 마감자료가 없는 사업장이 포함되어 있습니다.';
  end if;

  update public.nova_daily_close_snapshots
  set is_active = false,
      cancelled_by = v_actor,
      cancelled_at = now(),
      updated_at = now()
  where business_date = v_date
    and site = any(v_sites)
    and is_active;
  get diagnostics v_cancelled_count = row_count;

  insert into public.nova_reporting_state(
    business_date, site, native_complete, completed_by, completed_at, reason, version, updated_at
  )
  select
    v_date,
    s.site,
    false,
    '',
    null,
    'DAILY_CLOSE_CANCELLED' ||
      case when trim(coalesce(p_reason, '')) <> '' then ':' || left(trim(p_reason), 120) else '' end,
    1,
    now()
  from unnest(v_sites) s(site)
  on conflict(business_date, site) do update
  set native_complete = false,
      completed_by = '',
      completed_at = null,
      reason = excluded.reason,
      version = public.nova_reporting_state.version + 1,
      updated_at = now();

  v_response := jsonb_build_object(
    'ok', true,
    'dbFirst', true,
    'businessDate', v_date::text,
    'sites', to_jsonb(v_sites),
    'cancelledCount', v_cancelled_count,
    'cancelledBy', v_actor,
    'requestId', v_request_id,
    'idempotent', false
  );

  update public.nova_request_dedup
  set response_json = v_response
  where request_id = v_request_id;

  return v_response;
end;
$$;

revoke all on function public.nova_daily_close_cancel_many_v1(text, jsonb, text, text) from public;
revoke all on function public.nova_daily_close_cancel_many_v1(text, jsonb, text, text) from anon;
revoke all on function public.nova_daily_close_cancel_many_v1(text, jsonb, text, text) from authenticated;
grant execute on function public.nova_daily_close_cancel_many_v1(text, jsonb, text, text) to authenticated;
grant execute on function public.nova_daily_close_cancel_many_v1(text, jsonb, text, text) to service_role;
