-- HOUSEMAN_SHIFT_SITE_LIST_PERF_V1
-- Replace the expensive distinct-site scan over nova_rooms_current with the DB-first site master.
-- Runtime behavior is preserved: authorized active sites are returned in site-name order,
-- and the currently selected authorized site is retained as a safe fallback if the master is stale.

do $migration$
declare
  v_def text;
  v_old text := $old$  select coalesce(jsonb_agg(s.site order by s.site),'[]'::jsonb) into v_sites from (select distinct site from public.nova_rooms_current where coalesce(site,'')<>'' and ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0) or site=coalesce(v_user.default_site,'') or site=any(coalesce(v_user.allowed_sites,array[]::text[])))) s;$old$;
  v_new text := $new$  -- HOUSEMAN_SHIFT_SITE_LIST_PERF_V1 · 사업장 마스터 2행 조회로 객실 전체 스캔 제거
  select coalesce(jsonb_agg(s.site order by s.site),'[]'::jsonb) into v_sites
  from (
    select c.code as site
    from public.nova_code_settings c
    where c.group_code='사업장' and c.enabled=true and c.confirmed=true
      and ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
        or c.code=coalesce(v_user.default_site,'') or c.code=any(coalesce(v_user.allowed_sites,array[]::text[])))
    union all
    select v_site
    where v_site<>'' and not exists (
      select 1 from public.nova_code_settings c
      where c.group_code='사업장' and c.enabled=true and c.confirmed=true and c.code=v_site
    )
  ) s;$new$;
begin
  select pg_get_functiondef(p.oid) into v_def
  from pg_proc p
  join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname='nova_houseman_shift_zone_get_v1' and p.prokind='f'
  limit 1;

  if v_def is null then
    raise exception 'nova_houseman_shift_zone_get_v1 not found';
  end if;
  if position('HOUSEMAN_SHIFT_SITE_LIST_PERF_V1' in v_def) > 0 then
    return;
  end if;
  if position(v_old in v_def) = 0 then
    raise exception 'Expected legacy site-list query was not found; refusing partial patch';
  end if;

  execute replace(v_def, v_old, v_new);
end;
$migration$;
