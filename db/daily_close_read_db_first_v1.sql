-- DAILY_CLOSE_READ_DB_FIRST_V1
-- Reads only explicitly committed active close snapshots. Historical Sheet-only closes remain fallback data.

create or replace function public.nova_daily_close_read_v1(
  p_start_date text,
  p_end_date text,
  p_site text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_start date;
  v_end date;
  v_site text := trim(coalesce(p_site,''));
  v_items jsonb := '[]'::jsonb;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='마감자료 조회 권한이 없습니다.';
  end if;
  begin v_start:=trim(p_start_date)::date; exception when others then raise exception '조회 시작일을 확인해 주세요.'; end;
  begin v_end:=trim(p_end_date)::date; exception when others then raise exception '조회 종료일을 확인해 주세요.'; end;
  if v_end<v_start then raise exception '조회 종료일이 시작일보다 빠릅니다.'; end if;
  if v_end-v_start>370 then raise exception '마감자료 조회범위는 최대 371일입니다.'; end if;
  if v_site<>'' and not (
    (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
    or v_site=coalesce(v_user.default_site,'')
    or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))
  ) then
    raise exception using errcode='42501', message='사업장 권한이 없습니다.';
  end if;

  select coalesce(jsonb_agg(
    jsonb_build_object(
      'businessDate',c.business_date::text,
      'site',c.site,
      'snapshot',c.snapshot,
      'sourceSignature',c.source_signature,
      'sourceUpdatedAt',c.source_updated_at,
      'closedBy',c.closed_by,
      'closedByName',c.closed_by_name,
      'closedAt',to_char(c.closed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
      'version',c.version,
      'requestId',c.request_id,
      'dbFirst',true
    ) order by c.business_date,c.site
  ),'[]'::jsonb)
  into v_items
  from public.nova_daily_close_snapshots c
  where c.is_active=true
    and c.business_date between v_start and v_end
    and (v_site='' or c.site=v_site)
    and (
      (coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
      or c.site=coalesce(v_user.default_site,'')
      or c.site=any(coalesce(v_user.allowed_sites,array[]::text[]))
    );

  return jsonb_build_object(
    'ok',true,
    'dbFirst',true,
    'startDate',v_start::text,
    'endDate',v_end::text,
    'site',v_site,
    'items',v_items
  );
end;
$$;

revoke all on function public.nova_daily_close_read_v1(text,text,text) from public;
revoke execute on function public.nova_daily_close_read_v1(text,text,text) from anon;
grant execute on function public.nova_daily_close_read_v1(text,text,text) to authenticated,service_role;
