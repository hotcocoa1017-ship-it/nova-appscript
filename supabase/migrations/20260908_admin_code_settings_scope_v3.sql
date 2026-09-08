-- NOVA_ADMIN_CODE_SETTINGS_SCOPE_V3
-- 사업장/객실타입/직무는 현재 데이터에서 자동 시드되는 기존 동작을 보존하기 위해 아직 Sheet authority로 유지합니다.
update public.nova_code_settings_state
set baseline_count=48,reason='STABLE_ADMIN_GROUPS_VERIFIED_20260908',version=version+1,updated_at=now()
where scope='ADMIN';

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
  v_baseline_count integer := 48;
  v_row_count integer := 0;
  v_version bigint := 0;
begin
  if v_actor = '' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) <> 'ADMIN' then
    raise exception using errcode='42501',message='관리 코드 조회 권한이 없습니다.';
  end if;
  select coalesce(native_complete,false),coalesce(baseline_count,48)
    into v_state_complete,v_baseline_count from public.nova_code_settings_state where scope='ADMIN';
  select coalesce(jsonb_agg(jsonb_build_object(
      'group',group_code,'code',code,'label',label,'order',sort_order,
      'enabled',case when enabled then 'Y' else 'N' end,'note',note,
      'version',version,'updatedAt',updated_at
    ) order by group_code,sort_order,label,code),'[]'::jsonb),
    count(*)::integer,coalesce(bool_and(confirmed),false),coalesce(max(version),0)
  into v_items,v_row_count,v_all_rows_confirmed,v_version
  from public.nova_code_settings
  where group_code = any(array['동','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목']);
  return jsonb_build_object(
    'ok',true,'dbFirst',true,
    'confirmed',coalesce(v_state_complete,false) and v_row_count>=v_baseline_count and coalesce(v_all_rows_confirmed,false),
    'baselineCount',v_baseline_count,'rowCount',v_row_count,'version',v_version,'items',v_items
  );
end;
$$;

create or replace function public.nova_admin_code_settings_save_v1(
  p_group text,p_code text,p_label text,p_order integer,p_enabled text,p_note text,p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_group text:=trim(coalesce(p_group,'')); v_code text:=upper(trim(coalesce(p_code,'')));
  v_label text:=trim(coalesce(p_label,'')); v_note text:=trim(coalesce(p_note,''));
  v_order integer:=greatest(0,coalesce(p_order,9999));
  v_enabled boolean:=upper(trim(coalesce(p_enabled,'Y')) <> 'N';
  v_protected boolean:=false; v_existing boolean:=false;
  v_request_id text:=trim(coalesce(p_request_id,'')); v_dedup record; v_version bigint:=1; v_response jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,''))<>'ADMIN' then raise exception using errcode='42501',message='관리 코드 저장 권한이 없습니다.'; end if;
  if not (v_group=any(array['동','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목'])) then raise exception '아직 DB 관리대상이 아닌 코드그룹입니다.'; end if;
  if v_code='' or length(v_code)>60 or v_code !~ '^[0-9A-Z가-힣_-]+$' then raise exception '코드를 확인해 주세요.'; end if;
  if v_label='' then raise exception '표시명을 입력하세요.'; end if;
  if upper(trim(coalesce(p_enabled,'Y'))) not in ('Y','N') then raise exception '사용여부를 확인해 주세요.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  v_protected :=
    (v_group='권한' and v_code=any(array['ADMIN','ORDER','QM','HOUSEMAN','ROOMMAID','PUBLIC'])) or
    (v_group='객실상태' and v_code=any(array['VACANT_CLEAN','STOCK','STOCK_RC','STOCK_HU','STAY','DUE_OUT','CHECKED_OUT','CHECKED_OUT_RC','CHECKED_OUT_HU','RECHECKIN'])) or
    (v_group='청소상태' and v_code=any(array['NOT_REQUIRED','WAITING','ASSIGNED','CLEANING','COMPLETED','QM_WAITING','QM_CHECKING','QM_COMPLETED','REWORK'])) or
    (v_group='정비유형' and v_code=any(array['NORMAL','DS'])) or
    (v_group='룸메이드배정유형' and v_code=any(array['SOLO','PAIR','PAIR_TRAINING']));
  if v_protected then v_enabled:=true; end if;
  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'ADMIN_CODE_SAVE_V1',null) on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_dedup from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_dedup.employee_no<>v_actor or v_dedup.action<>'ADMIN_CODE_SAVE_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if;
    if v_dedup.response_json is not null then return v_dedup.response_json||jsonb_build_object('idempotent',true); end if;
    raise exception '동일 관리 코드 저장 요청이 처리 중입니다.';
  end if;
  select exists(select 1 from public.nova_code_settings where group_code=v_group and code=v_code) into v_existing;
  insert into public.nova_code_settings(group_code,code,label,sort_order,enabled,note,confirmed,updated_by,version,updated_at)
  values(v_group,v_code,v_label,v_order,v_enabled,v_note,true,v_actor,1,now())
  on conflict(group_code,code) do update set
    label=excluded.label,sort_order=excluded.sort_order,enabled=excluded.enabled,note=excluded.note,
    confirmed=true,updated_by=excluded.updated_by,version=public.nova_code_settings.version+1,updated_at=now()
  returning version into v_version;
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'group',v_group,'code',v_code,'label',v_label,'order',v_order,
    'enabled',case when v_enabled then 'Y' else 'N' end,'note',v_note,'created',not v_existing,'version',v_version,
    'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

create or replace function public.nova_admin_code_settings_disable_v1(p_group text,p_code text,p_request_id text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no','')); v_user public.nova_users%rowtype;
  v_group text:=trim(coalesce(p_group,'')); v_code text:=upper(trim(coalesce(p_code,'')));
  v_request_id text:=trim(coalesce(p_request_id,'')); v_dedup record; v_row public.nova_code_settings%rowtype;
  v_version bigint:=0; v_response jsonb; v_protected boolean:=false;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,''))<>'ADMIN' then raise exception using errcode='42501',message='관리 코드 사용중지 권한이 없습니다.'; end if;
  if not (v_group=any(array['동','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목'])) then raise exception '아직 DB 관리대상이 아닌 코드그룹입니다.'; end if;
  if v_code='' then raise exception '코드정보가 올바르지 않습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  v_protected :=
    (v_group='권한' and v_code=any(array['ADMIN','ORDER','QM','HOUSEMAN','ROOMMAID','PUBLIC'])) or
    (v_group='객실상태' and v_code=any(array['VACANT_CLEAN','STOCK','STOCK_RC','STOCK_HU','STAY','DUE_OUT','CHECKED_OUT','CHECKED_OUT_RC','CHECKED_OUT_HU','RECHECKIN'])) or
    (v_group='청소상태' and v_code=any(array['NOT_REQUIRED','WAITING','ASSIGNED','CLEANING','COMPLETED','QM_WAITING','QM_CHECKING','QM_COMPLETED','REWORK'])) or
    (v_group='정비유형' and v_code=any(array['NORMAL','DS'])) or
    (v_group='룸메이드배정유형' and v_code=any(array['SOLO','PAIR','PAIR_TRAINING']));
  if v_protected then raise exception '시스템 필수코드는 사용중지할 수 없습니다. 표시명만 변경하세요.'; end if;
  select * into v_row from public.nova_code_settings where group_code=v_group and code=v_code and enabled=true;
  if not found then raise exception '코드 항목을 찾을 수 없습니다.'; end if;
  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'ADMIN_CODE_DISABLE_V1',null) on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_dedup from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_dedup.employee_no<>v_actor or v_dedup.action<>'ADMIN_CODE_DISABLE_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if;
    if v_dedup.response_json is not null then return v_dedup.response_json||jsonb_build_object('idempotent',true); end if;
    raise exception '동일 관리 코드 사용중지 요청이 처리 중입니다.';
  end if;
  update public.nova_code_settings set enabled=false,confirmed=true,updated_by=v_actor,version=version+1,updated_at=now()
  where group_code=v_group and code=v_code returning version into v_version;
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'group',v_group,'code',v_code,'label',v_row.label,'version',v_version,
    'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

revoke all on function public.nova_admin_code_settings_read_v1() from public, anon;
revoke all on function public.nova_admin_code_settings_save_v1(text,text,text,integer,text,text,text) from public, anon;
revoke all on function public.nova_admin_code_settings_disable_v1(text,text,text) from public, anon;
grant execute on function public.nova_admin_code_settings_read_v1() to authenticated, service_role;
grant execute on function public.nova_admin_code_settings_save_v1(text,text,text,integer,text,text,text) to authenticated, service_role;
grant execute on function public.nova_admin_code_settings_disable_v1(text,text,text) to authenticated, service_role;
