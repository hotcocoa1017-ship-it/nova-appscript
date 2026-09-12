-- SHIFT_MANAGEMENT_SITE_SCOPE_PARITY_V1
-- Restore legacy shift-management site behavior only inside houseman shift/zone RPCs.
-- ADMIN/ORDER may manage any active confirmed site from the site master; other module permissions are unchanged.

do $migration$
declare
  v_def text;
  v_new text;
begin
  select pg_get_functiondef('public.nova_houseman_shift_zone_get_v1(text,text)'::regprocedure) into v_def;
  v_new := replace(
    v_def,
    $old$  if not ((coalesce(trim(v_user.default_site),'') = '' and cardinality(coalesce(v_user.allowed_sites,array[]::text[])) = 0) or v_site = coalesce(v_user.default_site,'') or v_site = any(coalesce(v_user.allowed_sites,array[]::text[]))) then raise exception using errcode = '42501', message = '사업장 권한이 없습니다.'; end if;$old$,
    $new$  if not exists(select 1 from public.nova_code_settings c where c.group_code='사업장' and c.enabled=true and c.confirmed=true and c.code=v_site) then raise exception using errcode='42501',message='근무조 관리 대상 사업장이 아닙니다.'; end if;$new$
  );
  if v_new = v_def then raise exception 'shift get auth anchor not found'; end if;
  v_def := v_new;
  v_new := replace(
    v_def,
    $old$    where c.group_code='사업장' and c.enabled=true and c.confirmed=true
      and ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
        or c.code=coalesce(v_user.default_site,'') or c.code=any(coalesce(v_user.allowed_sites,array[]::text[])))$old$,
    $new$    where c.group_code='사업장' and c.enabled=true and c.confirmed=true$new$
  );
  if v_new = v_def then raise exception 'shift get site-list anchor not found'; end if;
  execute v_new;

  select pg_get_functiondef('public.nova_houseman_shift_save_v1(text,text,jsonb,text)'::regprocedure) into v_def;
  v_new := replace(
    v_def,
    $old$if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0) or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then raise exception using errcode='42501',message='사업장 권한이 없습니다.'; end if;$old$,
    $new$if not exists(select 1 from public.nova_code_settings c where c.group_code='사업장' and c.enabled=true and c.confirmed=true and c.code=v_site) then raise exception using errcode='42501',message='근무조 관리 대상 사업장이 아닙니다.'; end if;$new$
  );
  if v_new = v_def then raise exception 'shift save auth anchor not found'; end if;
  execute v_new;

  select pg_get_functiondef('public.nova_houseman_zone_save_v1(text,text,text,jsonb,text,text)'::regprocedure) into v_def;
  v_new := replace(
    v_def,
    $old$if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0) or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then raise exception using errcode='42501',message='사업장 권한이 없습니다.'; end if;$old$,
    $new$if not exists(select 1 from public.nova_code_settings c where c.group_code='사업장' and c.enabled=true and c.confirmed=true and c.code=v_site) then raise exception using errcode='42501',message='근무조 관리 대상 사업장이 아닙니다.'; end if;$new$
  );
  if v_new = v_def then raise exception 'zone save auth anchor not found'; end if;
  execute v_new;

  select pg_get_functiondef('public.nova_houseman_shift_zone_bootstrap_v3(text,text,jsonb,jsonb,text)'::regprocedure) into v_def;
  v_new := replace(
    v_def,
    $old$  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
      or v_site=coalesce(v_user.default_site,'')
      or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501',message='사업장 권한이 없습니다.';
  end if;$old$,
    $new$  if not exists(select 1 from public.nova_code_settings c where c.group_code='사업장' and c.enabled=true and c.confirmed=true and c.code=v_site) then
    raise exception using errcode='42501',message='근무조 관리 대상 사업장이 아닙니다.';
  end if;$new$
  );
  if v_new = v_def then raise exception 'shift bootstrap auth anchor not found'; end if;
  execute v_new;
end;
$migration$;
