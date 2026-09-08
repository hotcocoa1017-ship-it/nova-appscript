-- NOVA_ADMIN_CODE_SETTINGS_STATE_V2
create table if not exists public.nova_code_settings_state (
  scope text primary key,
  native_complete boolean not null default false,
  baseline_count integer not null default 0,
  reason text not null default '',
  version bigint not null default 1,
  updated_at timestamptz not null default now()
);
alter table public.nova_code_settings_state enable row level security;
revoke all on table public.nova_code_settings_state from public, anon, authenticated;
grant all on table public.nova_code_settings_state to service_role;

insert into public.nova_code_settings_state(scope,native_complete,baseline_count,reason,version,updated_at)
values('ADMIN',true,60,'SHEET_BASELINE_VERIFIED_20260908',1,now())
on conflict(scope) do update set native_complete=true,baseline_count=60,reason='SHEET_BASELINE_VERIFIED_20260908',version=public.nova_code_settings_state.version+1,updated_at=now();

create or replace function public.nova_admin_code_settings_read_v1()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no', ''));
  v_user public.nova_users%rowtype;
  v_items jsonb := '[]'::jsonb;
  v_all_rows_confirmed boolean := false;
  v_state_complete boolean := false;
  v_baseline_count integer := 60;
  v_row_count integer := 0;
  v_version bigint := 0;
begin
  if v_actor = '' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) <> 'ADMIN' then
    raise exception using errcode='42501',message='관리 코드 조회 권한이 없습니다.';
  end if;

  select coalesce(native_complete,false),coalesce(baseline_count,60)
    into v_state_complete,v_baseline_count
  from public.nova_code_settings_state where scope='ADMIN';

  select coalesce(jsonb_agg(jsonb_build_object(
      'group',group_code,'code',code,'label',label,'order',sort_order,
      'enabled',case when enabled then 'Y' else 'N' end,'note',note,
      'version',version,'updatedAt',updated_at
    ) order by group_code,sort_order,label,code),'[]'::jsonb),
    count(*)::integer,
    coalesce(bool_and(confirmed),false),
    coalesce(max(version),0)
  into v_items,v_row_count,v_all_rows_confirmed,v_version
  from public.nova_code_settings
  where group_code = any(array['사업장','동','객실타입','직무','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목']);

  return jsonb_build_object(
    'ok',true,'dbFirst',true,
    'confirmed',coalesce(v_state_complete,false) and v_row_count>=v_baseline_count and coalesce(v_all_rows_confirmed,false),
    'baselineCount',v_baseline_count,'rowCount',v_row_count,'version',v_version,'items',v_items
  );
end;
$$;

revoke all on function public.nova_admin_code_settings_read_v1() from public, anon;
grant execute on function public.nova_admin_code_settings_read_v1() to authenticated, service_role;
