-- NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1
-- QM 체크리스트/점검장소 정의를 공통 nova_code_settings에 보존합니다.
-- 현재 Sheet 활성/비활성 상태를 그대로 초기값으로 사용합니다.

insert into public.nova_code_settings(group_code,code,label,sort_order,enabled,note,confirmed,updated_by,version,updated_at)
values
  ('QM체크리스트','QMCL-01','침구 정돈 및 오염 상태',10,false,'{"placeCode":"BED_LINEN","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-02','객실 바닥·먼지·머리카락 상태',20,false,'{"placeCode":"FLOOR","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-03','욕실 청결 및 배수 상태',30,false,'{"placeCode":"BATHROOM","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-04','거울·유리·가구 오염 상태',40,false,'{"placeCode":"FURNITURE","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-05','소모품·비품 세팅 상태',50,false,'{"placeCode":"AMENITY","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-06','냄새·환기 상태',60,false,'{"placeCode":"BEDROOM","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-07','시설 이상 및 하자 여부',70,false,'{"placeCode":"FACILITY","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-08','최종 객실 전체 확인',1,true,'{"placeCode":"OVERALL","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-09','주방 싱크대·식기·오염 상태',25,false,'{"placeCode":"KITCHEN","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM체크리스트','QMCL-10','현관문·신발장·입구 청결 상태',5,false,'{"placeCode":"ENTRANCE","required":true,"photoRequired":false}',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','ENTRANCE','현관',10,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','KITCHEN','주방',20,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','BATHROOM','욕실',30,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','BEDROOM','침실',40,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','BED_LINEN','침대·이불',50,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','FLOOR','바닥',60,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','FURNITURE','가구·유리',70,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','AMENITY','비품·소모품',80,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','FACILITY','시설·하자',90,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('QM점검장소','OVERALL','객실 전체',100,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now())
on conflict(group_code,code) do nothing;

insert into public.nova_code_settings_state(scope,native_complete,baseline_count,reason,version,updated_at)
values('QM_CHECKLIST',true,20,'SHEET_VERIFIED_20260908',1,now())
on conflict(scope) do update set
  native_complete=excluded.native_complete,
  baseline_count=excluded.baseline_count,
  reason=excluded.reason,
  version=public.nova_code_settings_state.version+1,
  updated_at=now();

create or replace function public.nova_qm_checklist_codes_read_v1()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_items jsonb:='[]'::jsonb;
  v_count integer:=0;
  v_confirmed boolean:=false;
  v_state boolean:=false;
  v_baseline integer:=20;
  v_version bigint:=0;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER','QM') then
    raise exception using errcode='42501',message='QM 체크리스트 조회 권한이 없습니다.';
  end if;

  select coalesce(native_complete,false),coalesce(baseline_count,20)
    into v_state,v_baseline from public.nova_code_settings_state where scope='QM_CHECKLIST';

  select coalesce(jsonb_agg(jsonb_build_object(
      'group',group_code,'code',code,'label',label,'order',sort_order,
      'enabled',case when enabled then 'Y' else 'N' end,'note',note,
      'version',version,'updatedAt',updated_at
    ) order by group_code,sort_order,label,code),'[]'::jsonb),
    count(*)::integer,coalesce(bool_and(confirmed),false),coalesce(max(version),0)
  into v_items,v_count,v_confirmed,v_version
  from public.nova_code_settings
  where group_code in ('QM체크리스트','QM점검장소');

  return jsonb_build_object(
    'ok',true,'dbFirst',true,
    'confirmed',coalesce(v_state,false) and v_count>=v_baseline and coalesce(v_confirmed,false),
    'baselineCount',v_baseline,'rowCount',v_count,'version',v_version,'items',v_items
  );
end;
$$;

create or replace function public.nova_qm_checklist_place_save_v1(
  p_code text,p_label text,p_order integer,p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_code text:=upper(trim(coalesce(p_code,'')));
  v_label text:=trim(coalesce(p_label,''));
  v_order integer:=greatest(0,least(9999,coalesce(p_order,9999)));
  v_request_id text:=trim(coalesce(p_request_id,''));
  v_dedup record; v_existing boolean:=false; v_version bigint:=1; v_response jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501',message='QM 점검장소 관리 권한이 없습니다.';
  end if;
  if v_code='' or length(v_code)>60 or v_code !~ '^[0-9A-Z가-힣_-]+$' then raise exception '점검 장소 코드를 확인해 주세요.'; end if;
  if v_label='' or length(v_label)>40 then raise exception '점검 장소명은 1~40자로 입력하세요.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;

  select exists(select 1 from public.nova_code_settings where group_code='QM점검장소' and code=v_code) into v_existing;
  if not v_existing and (select count(*) from public.nova_code_settings where group_code='QM점검장소' and enabled)>=30 then
    raise exception '점검 장소는 최대 30개까지 등록할 수 있습니다.';
  end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'QM_PLACE_SAVE_V1',null) on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_dedup from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_dedup.employee_no<>v_actor or v_dedup.action<>'QM_PLACE_SAVE_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if;
    if v_dedup.response_json is not null then return v_dedup.response_json||jsonb_build_object('idempotent',true); end if;
    raise exception '동일 점검장소 저장 요청이 처리 중입니다.';
  end if;

  insert into public.nova_code_settings(group_code,code,label,sort_order,enabled,note,confirmed,updated_by,version,updated_at)
  values('QM점검장소',v_code,v_label,v_order,true,'',true,v_actor,1,now())
  on conflict(group_code,code) do update set
    label=excluded.label,sort_order=excluded.sort_order,enabled=true,note='',confirmed=true,
    updated_by=excluded.updated_by,version=public.nova_code_settings.version+1,updated_at=now()
  returning version into v_version;

  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'code',v_code,'label',v_label,'order',v_order,
    'created',not v_existing,'version',v_version,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

create or replace function public.nova_qm_checklist_item_save_v1(
  p_code text,p_label text,p_place_code text,p_order integer,p_required boolean,p_photo_required boolean,p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_code text:=upper(trim(coalesce(p_code,'')));
  v_label text:=trim(coalesce(p_label,''));
  v_place text:=upper(trim(coalesce(p_place_code,'')));
  v_order integer:=greatest(0,least(9999,coalesce(p_order,9999)));
  v_note text:=jsonb_build_object('placeCode',v_place,'required',coalesce(p_required,true),'photoRequired',coalesce(p_photo_required,false))::text;
  v_request_id text:=trim(coalesce(p_request_id,''));
  v_dedup record; v_existing boolean:=false; v_version bigint:=1; v_response jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501',message='QM 체크리스트 관리 권한이 없습니다.';
  end if;
  if v_code='' or length(v_code)>60 or v_code !~ '^[0-9A-Z가-힣_-]+$' then raise exception '체크리스트 코드를 확인해 주세요.'; end if;
  if v_label='' or length(v_label)>120 then raise exception '점검 항목명은 1~120자로 입력하세요.'; end if;
  if not exists(select 1 from public.nova_code_settings where group_code='QM점검장소' and code=v_place and enabled=true and confirmed=true) then
    raise exception '점검 장소를 선택하세요.';
  end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;

  select exists(select 1 from public.nova_code_settings where group_code='QM체크리스트' and code=v_code) into v_existing;
  if not v_existing and (select count(*) from public.nova_code_settings where group_code='QM체크리스트' and enabled)>=100 then
    raise exception '체크리스트는 최대 100개까지 등록할 수 있습니다.';
  end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'QM_ITEM_SAVE_V1',null) on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_dedup from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_dedup.employee_no<>v_actor or v_dedup.action<>'QM_ITEM_SAVE_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if;
    if v_dedup.response_json is not null then return v_dedup.response_json||jsonb_build_object('idempotent',true); end if;
    raise exception '동일 체크리스트 저장 요청이 처리 중입니다.';
  end if;

  insert into public.nova_code_settings(group_code,code,label,sort_order,enabled,note,confirmed,updated_by,version,updated_at)
  values('QM체크리스트',v_code,v_label,v_order,true,v_note,true,v_actor,1,now())
  on conflict(group_code,code) do update set
    label=excluded.label,sort_order=excluded.sort_order,enabled=true,note=excluded.note,confirmed=true,
    updated_by=excluded.updated_by,version=public.nova_code_settings.version+1,updated_at=now()
  returning version into v_version;

  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'code',v_code,'label',v_label,'placeCode',v_place,'order',v_order,
    'required',coalesce(p_required,true),'photoRequired',coalesce(p_photo_required,false),'created',not v_existing,
    'version',v_version,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

create or replace function public.nova_qm_checklist_item_disable_v1(p_code text,p_request_id text)
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype; v_code text:=upper(trim(coalesce(p_code,'')));
  v_request_id text:=trim(coalesce(p_request_id,'')); v_dedup record; v_row public.nova_code_settings%rowtype;
  v_version bigint:=0; v_response jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then raise exception using errcode='42501',message='QM 체크리스트 관리 권한이 없습니다.'; end if;
  if v_code='' then raise exception '삭제할 체크리스트 항목이 없습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  select * into v_row from public.nova_code_settings where group_code='QM체크리스트' and code=v_code and enabled=true;
  if not found then raise exception '체크리스트 항목을 찾을 수 없습니다.'; end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'QM_ITEM_DISABLE_V1',null) on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_dedup from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_dedup.employee_no<>v_actor or v_dedup.action<>'QM_ITEM_DISABLE_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if;
    if v_dedup.response_json is not null then return v_dedup.response_json||jsonb_build_object('idempotent',true); end if;
    raise exception '동일 체크리스트 사용중지 요청이 처리 중입니다.';
  end if;

  update public.nova_code_settings set enabled=false,confirmed=true,updated_by=v_actor,version=version+1,updated_at=now()
  where group_code='QM체크리스트' and code=v_code returning version into v_version;
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'code',v_code,'label',v_row.label,'version',v_version,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

create or replace function public.nova_qm_checklist_place_disable_v1(p_code text,p_request_id text)
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype; v_code text:=upper(trim(coalesce(p_code,'')));
  v_request_id text:=trim(coalesce(p_request_id,'')); v_dedup record; v_row public.nova_code_settings%rowtype;
  v_using integer:=0; v_version bigint:=0; v_response jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then raise exception using errcode='42501',message='QM 점검장소 관리 권한이 없습니다.'; end if;
  if v_code='' then raise exception '삭제할 점검 장소가 없습니다.'; end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  select * into v_row from public.nova_code_settings where group_code='QM점검장소' and code=v_code and enabled=true;
  if not found then raise exception '점검 장소를 찾을 수 없습니다.'; end if;

  select count(*)::integer into v_using
  from public.nova_code_settings
  where group_code='QM체크리스트' and enabled=true
    and case when left(ltrim(note),1)='{' then coalesce((note::jsonb)->>'placeCode','') else '' end=v_code;
  if v_using>0 then raise exception '해당 장소를 사용하는 체크리스트 %개가 있습니다. 항목의 장소를 먼저 변경하세요.',v_using; end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'QM_PLACE_DISABLE_V1',null) on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_dedup from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_dedup.employee_no<>v_actor or v_dedup.action<>'QM_PLACE_DISABLE_V1' then raise exception '이미 다른 요청에 사용된 요청 ID입니다.'; end if;
    if v_dedup.response_json is not null then return v_dedup.response_json||jsonb_build_object('idempotent',true); end if;
    raise exception '동일 점검장소 사용중지 요청이 처리 중입니다.';
  end if;

  update public.nova_code_settings set enabled=false,confirmed=true,updated_by=v_actor,version=version+1,updated_at=now()
  where group_code='QM점검장소' and code=v_code returning version into v_version;
  v_response:=jsonb_build_object('ok',true,'dbFirst',true,'code',v_code,'label',v_row.label,'version',v_version,'requestId',v_request_id,'idempotent',false);
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

revoke all on function public.nova_qm_checklist_codes_read_v1() from public,anon;
revoke all on function public.nova_qm_checklist_place_save_v1(text,text,integer,text) from public,anon;
revoke all on function public.nova_qm_checklist_item_save_v1(text,text,text,integer,boolean,boolean,text) from public,anon;
revoke all on function public.nova_qm_checklist_item_disable_v1(text,text) from public,anon;
revoke all on function public.nova_qm_checklist_place_disable_v1(text,text) from public,anon;
grant execute on function public.nova_qm_checklist_codes_read_v1() to authenticated,service_role;
grant execute on function public.nova_qm_checklist_place_save_v1(text,text,integer,text) to authenticated,service_role;
grant execute on function public.nova_qm_checklist_item_save_v1(text,text,text,integer,boolean,boolean,text) to authenticated,service_role;
grant execute on function public.nova_qm_checklist_item_disable_v1(text,text) to authenticated,service_role;
grant execute on function public.nova_qm_checklist_place_disable_v1(text,text) to authenticated,service_role;
