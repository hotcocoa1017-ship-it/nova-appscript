-- NOVA Core 3.0 standalone authentication foundation.
-- Additive only. Existing Apps Script @271 auth is untouched.

create schema if not exists nova_private;
revoke all on schema nova_private from public;

create or replace function nova_private.core_login_identity_v1_internal(
  p_name text,
  p_employee_no text,
  p_site text default ''
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_name text := trim(coalesce(p_name, ''));
  v_employee_no text := trim(coalesce(p_employee_no, ''));
  v_site text := trim(coalesce(p_site, ''));
  v_user public.nova_users%rowtype;
  v_role text;
  v_session_site text := '';
begin
  if v_name = '' or v_employee_no = '' then
    raise exception using errcode = '22023', message = '이름과 사번을 입력하세요.';
  end if;
  if length(v_name) > 80 or length(v_employee_no) > 40 or length(v_site) > 40 then
    raise exception using errcode = '22023', message = '로그인 입력값을 확인하세요.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_employee_no
    and name = v_name
    and enabled = true;

  if not found then
    raise exception using errcode = '42501', message = '이름 또는 사번이 일치하지 않습니다.';
  end if;

  v_role := upper(trim(coalesce(v_user.role, '')));
  if v_role = '' then
    raise exception using errcode = '42501', message = '사용자 권한을 확인할 수 없습니다.';
  end if;

  if v_role not in ('ADMIN', 'ORDER') then
    if v_site = '' then
      raise exception using errcode = '22023', message = '사업장을 선택하세요.';
    end if;
    if v_site not in ('쏘라노', '별관') then
      raise exception using errcode = '42501', message = '사용할 수 없는 사업장입니다.';
    end if;
    if nullif(trim(coalesce(v_user.default_site, '')), '') is not null
       and trim(v_user.default_site) <> v_site then
      raise exception using errcode = '42501', message = '계정 기본사업장과 선택한 사업장이 다릅니다.';
    end if;
    if cardinality(coalesce(v_user.allowed_sites, array[]::text[])) > 0
       and not (v_site = any(v_user.allowed_sites)) then
      raise exception using errcode = '42501', message = '허용되지 않은 사업장입니다.';
    end if;
    v_session_site := v_site;
  end if;

  return jsonb_build_object(
    'ok', true,
    'employeeNo', v_user.employee_no,
    'name', v_user.name,
    'role', v_role,
    'sessionSite', v_session_site,
    'defaultSite', coalesce(v_user.default_site, ''),
    'allowedSites', coalesce(to_jsonb(v_user.allowed_sites), '[]'::jsonb)
  );
end;
$$;

revoke all on function nova_private.core_login_identity_v1_internal(text,text,text) from public, anon, authenticated;

create or replace function public.nova_core_login_identity_v1(
  p_name text,
  p_employee_no text,
  p_site text default ''
) returns jsonb
language sql
security invoker
set search_path = ''
as $$
  select nova_private.core_login_identity_v1_internal(p_name, p_employee_no, p_site);
$$;

revoke all on function public.nova_core_login_identity_v1(text,text,text) from public;
grant execute on function public.nova_core_login_identity_v1(text,text,text) to anon, authenticated;

create or replace function nova_private.core_me_v1_internal()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_employee_no text := trim(coalesce(v_claims->>'employee_no', ''));
  v_claim_site text := trim(coalesce(v_claims->>'site', ''));
  v_user public.nova_users%rowtype;
  v_role text;
begin
  if v_employee_no = '' then
    raise exception using errcode = '42501', message = '로그인이 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_employee_no
    and enabled = true;
  if not found then
    raise exception using errcode = '42501', message = '사용할 수 없는 계정입니다.';
  end if;

  v_role := upper(trim(coalesce(v_user.role, '')));
  if v_role not in ('ADMIN', 'ORDER') then
    if v_claim_site = '' or v_claim_site not in ('쏘라노', '별관') then
      raise exception using errcode = '42501', message = '로그인 사업장을 확인할 수 없습니다.';
    end if;
    if nullif(trim(coalesce(v_user.default_site, '')), '') is not null
       and trim(v_user.default_site) <> v_claim_site then
      raise exception using errcode = '42501', message = '계정 사업장이 변경되었습니다. 다시 로그인하세요.';
    end if;
    if cardinality(coalesce(v_user.allowed_sites, array[]::text[])) > 0
       and not (v_claim_site = any(v_user.allowed_sites)) then
      raise exception using errcode = '42501', message = '현재 사업장 권한이 없습니다.';
    end if;
  else
    v_claim_site := '';
  end if;

  return jsonb_build_object(
    'ok', true,
    'employeeNo', v_user.employee_no,
    'name', v_user.name,
    'role', v_role,
    'sessionSite', v_claim_site,
    'defaultSite', coalesce(v_user.default_site, ''),
    'allowedSites', coalesce(to_jsonb(v_user.allowed_sites), '[]'::jsonb),
    'serverTime', now()
  );
end;
$$;

revoke all on function nova_private.core_me_v1_internal() from public, anon, authenticated;

create or replace function public.nova_core_me_v1()
returns jsonb
language sql
security invoker
set search_path = ''
as $$
  select nova_private.core_me_v1_internal();
$$;

revoke all on function public.nova_core_me_v1() from public, anon;
grant execute on function public.nova_core_me_v1() to authenticated;
