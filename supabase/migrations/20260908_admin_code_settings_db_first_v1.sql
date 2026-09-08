-- NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1
-- 관리자 코드/명칭 11개 그룹만 PostgreSQL 권위로 전환합니다.
-- 운영설정은 nova_operation_settings가 별도 권위이며, 텔레그램/QM 정의는 이번 범위에서 제외합니다.

create table if not exists public.nova_code_settings (
  group_code text not null,
  code text not null,
  label text not null,
  sort_order integer not null default 9999,
  enabled boolean not null default true,
  note text not null default '',
  confirmed boolean not null default false,
  updated_by text not null default '',
  version bigint not null default 1,
  updated_at timestamptz not null default now(),
  primary key (group_code, code)
);

alter table public.nova_code_settings enable row level security;
revoke all on table public.nova_code_settings from public, anon, authenticated;
grant all on table public.nova_code_settings to service_role;

-- 2026-09-08 운영 코드설정 Sheet에서 직접 확인한 관리자 편집 대상 60행.
insert into public.nova_code_settings(group_code,code,label,sort_order,enabled,note,confirmed,updated_by,version,updated_at)
values
  ('권한','ADMIN','관리자',10,true,'전체 기능',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('권한','ORDER','오더테이커',20,true,'데스크톱 통합 운영',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('권한','QM','퀄리티매니저',30,true,'QM 점검',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('권한','HOUSEMAN','하우스맨',40,true,'하우스맨 오더',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('권한','ROOMMAID','룸메이드',50,true,'객실 정비',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('권한','PUBLIC','객실퍼블릭',60,true,'퇴실 여부 조회',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('객실상태','VACANT_CLEAN','공실',10,true,'미등록 또는 정비완료 객실',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','STOCK','재고',20,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','STOCK_RC','재고 R/C',30,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','STOCK_HU','재고 H/U',40,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','STAY','투숙',50,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','DUE_OUT','퇴실예정',60,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','CHECKED_OUT','퇴실',70,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','CHECKED_OUT_RC','퇴실R/C',71,true,'R/C 퇴실 정비대상',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','CHECKED_OUT_HU','퇴실H/U',72,true,'H/U 퇴실 정비대상',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실상태','RECHECKIN','재입실',80,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('청소상태','NOT_REQUIRED','정비대상 아님',5,true,'투숙·퇴실예정 기본상태',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('청소상태','WAITING','대기',10,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('청소상태','ASSIGNED','배정',20,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('청소상태','CLEANING','청소중',30,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('청소상태','COMPLETED','청소완료',40,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('청소상태','QM_WAITING','QM대기',50,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('청소상태','QM_CHECKING','QM점검중',55,true,'QM 모바일 점검 시작',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('청소상태','REWORK','재정비',60,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('청소상태','QM_COMPLETED','QM완료',70,true,'QM 최종 점검 완료',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('하우스맨파트','AMENITY','비품',10,true,'직원배정 가능',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('하우스맨파트','LINEN','린넨',20,true,'직원배정 가능',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('하우스맨파트','FACILITY','시설',30,true,'타 파트 처리 가능',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('하우스맨파트','INQUIRY','문의',40,true,'타 파트 처리 가능',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('하우스맨파트','OTHER','기타',50,true,'',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('정비유형','NORMAL','일반정비',10,true,'인정 정비수 1.0',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('정비유형','DS','D/S',20,true,'데일리서비스 · 인정 정비수 0.5',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('정비유형','5S','5S',30,true,'기본 인정정비수 × 1.5 · 마감 재고 차감',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('정비유형','EVALUATION','평가원',40,true,'기본 인정정비수 × 1.5 · 마감 재고 차감',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('정비유형','STAFF_DORM','직원숙소',50,true,'기본 인정정비수 × 1.5 · 마감 재고 차감',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('정비유형','DEEP_CLEANING','딥크리닝',60,true,'기본 인정정비수 × 1.5 · 마감 재고 차감',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('룸메이드배정유형','SOLO','1인 배정',10,true,'룸메이드 1명이 여러 객실을 담당',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('룸메이드배정유형','PAIR','2인1조',20,true,'두 명이 공동 정비',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('룸메이드배정유형','PAIR_TRAINING','2인1조(교육)',30,true,'교육 목적 공동 정비',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('동','1','1동',10,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('동','2','2동',20,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('동','3','3동',30,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('동','4','4동',40,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('동','5','5동',50,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('동','6','6동',60,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('동','7','7동',70,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('동','8','8동',80,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('동','9','9동',90,true,'객실번호 첫 자리 기준',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('사업장','쏘라노','쏘라노',10,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('사업장','별관','별관',10,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('객실타입','F','F',10,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실타입','G','G',20,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실타입','R','R',30,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('객실타입','T','T',40,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),

  ('직무','객실퍼블릭','객실퍼블릭',10,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('직무','룸메이드','룸메이드',20,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('직무','오더테이커','오더테이커',30,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('직무','운영','운영',40,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('직무','퀄리티매니저','퀄리티매니저',50,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now()),
  ('직무','하우스맨','하우스맨',60,true,'기존 데이터에서 자동등록',true,'MIGRATION_SHEET_VERIFIED',1,now())
on conflict(group_code,code) do update
set label=excluded.label,
    sort_order=excluded.sort_order,
    enabled=excluded.enabled,
    note=excluded.note,
    confirmed=true,
    updated_by='MIGRATION_SHEET_VERIFIED',
    updated_at=now();

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
  v_confirmed boolean := false;
  v_version bigint := 0;
begin
  if v_actor = '' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) <> 'ADMIN' then
    raise exception using errcode='42501',message='관리 코드 조회 권한이 없습니다.';
  end if;

  select coalesce(jsonb_agg(jsonb_build_object(
      'group',group_code,'code',code,'label',label,'order',sort_order,
      'enabled',case when enabled then 'Y' else 'N' end,'note',note,
      'version',version,'updatedAt',updated_at
    ) order by group_code,sort_order,label,code),'[]'::jsonb),
    count(*) = 60 and bool_and(confirmed),
    coalesce(max(version),0)
  into v_items,v_confirmed,v_version
  from public.nova_code_settings
  where group_code = any(array['사업장','동','객실타입','직무','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목']);

  return jsonb_build_object('ok',true,'dbFirst',true,'confirmed',coalesce(v_confirmed,false),'version',v_version,'items',v_items);
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
  v_group text:=trim(coalesce(p_group,''));
  v_code text:=upper(trim(coalesce(p_code,'')));
  v_label text:=trim(coalesce(p_label,''));
  v_note text:=trim(coalesce(p_note,''));
  v_order integer:=greatest(0,coalesce(p_order,9999));
  v_enabled boolean:=upper(trim(coalesce(p_enabled,'Y'))) <> 'N';
  v_protected boolean:=false;
  v_existing boolean:=false;
  v_request_id text:=trim(coalesce(p_request_id,''));
  v_dedup record;
  v_version bigint:=1;
  v_response jsonb;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,''))<>'ADMIN' then raise exception using errcode='42501',message='관리 코드 저장 권한이 없습니다.'; end if;
  if not (v_group=any(array['사업장','동','객실타입','직무','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목'])) then raise exception '관리할 수 없는 코드그룹입니다.'; end if;
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
  on conflict(group_code,code) do update
  set label=excluded.label,sort_order=excluded.sort_order,enabled=excluded.enabled,note=excluded.note,
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
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_group text:=trim(coalesce(p_group,''));
  v_code text:=upper(trim(coalesce(p_code,'')));
  v_request_id text:=trim(coalesce(p_request_id,''));
  v_dedup record;
  v_row public.nova_code_settings%rowtype;
  v_version bigint:=0;
  v_response jsonb;
  v_protected boolean:=false;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,''))<>'ADMIN' then raise exception using errcode='42501',message='관리 코드 사용중지 권한이 없습니다.'; end if;
  if not (v_group=any(array['사업장','동','객실타입','직무','권한','객실상태','청소상태','정비유형','룸메이드배정유형','하우스맨파트','하우스맨품목'])) then raise exception '관리할 수 없는 코드그룹입니다.'; end if;
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

  update public.nova_code_settings
  set enabled=false,confirmed=true,updated_by=v_actor,version=version+1,updated_at=now()
  where group_code=v_group and code=v_code
  returning version into v_version;

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
