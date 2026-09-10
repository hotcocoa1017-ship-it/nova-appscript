-- ROOM_UPLOAD_RELIABILITY_GUARD_V5
-- Fail-closed validation wrapper around the proven V4 atomic apply path.
-- This migration does not modify current room rows.

create schema if not exists nova_private;

create table if not exists nova_private.room_upload_site_guard_v1 (
  site text primary key,
  expected_room_count integer not null check (expected_room_count > 0 and expected_room_count <= 5000),
  guard_version text not null default 'ROOM_UPLOAD_SITE_GUARD_V1',
  note text not null default '',
  updated_at timestamptz not null default now()
);

insert into nova_private.room_upload_site_guard_v1(site, expected_room_count, note)
values
  ('쏘라노', 755, '설악 쏘라노 활성 객실 안전기준'),
  ('별관', 798, '설악 별관 활성 객실 안전기준')
on conflict (site) do update
set expected_room_count = excluded.expected_room_count,
    note = excluded.note,
    updated_at = now();

alter table public.nova_room_upload_snapshots
  add column if not exists request_id text not null default '',
  add column if not exists guard_version text not null default '',
  add column if not exists db_committed_at timestamptz,
  add column if not exists sheet_mirror_status text not null default '',
  add column if not exists sheet_mirrored_at timestamptz,
  add column if not exists realtime_status text not null default '',
  add column if not exists realtime_converged_at timestamptz,
  add column if not exists last_error text not null default '';

create unique index if not exists nova_room_upload_snapshots_request_id_uidx
  on public.nova_room_upload_snapshots(request_id)
  where request_id <> '';

create or replace function public.nova_room_upload_apply_v5(
  p_business_date text,
  p_site text,
  p_rooms jsonb,
  p_upload jsonb,
  p_expected_versions jsonb,
  p_version bigint,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_date date;
  v_site text := trim(coalesce(p_site, ''));
  v_expected_count integer;
  v_guard_version text;
  v_room_count integer;
  v_expected_version_count integer;
  v_count_sum bigint;
  v_explicit_count bigint;
  v_vacant_count bigint;
  v_baseline_date date;
  v_baseline_count integer;
  v_result jsonb;
  v_version bigint;
begin
  if trim(coalesce(p_business_date, '')) !~ '^\d{4}-\d{2}-\d{2}$' then
    raise exception '업무일자를 확인해 주세요.';
  end if;
  begin
    v_date := trim(p_business_date)::date;
  exception when others then
    raise exception '업무일자를 확인해 주세요.';
  end;

  if v_site = '' then
    raise exception '사업장을 선택하세요.';
  end if;

  select g.expected_room_count, g.guard_version
    into v_expected_count, v_guard_version
  from nova_private.room_upload_site_guard_v1 g
  where g.site = v_site;

  if not found then
    raise exception '객실업로드 안전기준이 등록되지 않은 사업장입니다. 관리자에게 확인해 주세요. (%).', v_site;
  end if;

  if jsonb_typeof(coalesce(p_rooms, '[]'::jsonb)) <> 'array' then
    raise exception '업로드 객실정보 형식이 올바르지 않습니다.';
  end if;
  v_room_count := jsonb_array_length(p_rooms);
  if v_room_count <> v_expected_count then
    raise exception '객실업로드 안전검증 실패: % 객실은 정확히 %실이어야 하나 %실이 전달되었습니다.', v_site, v_expected_count, v_room_count;
  end if;

  if exists (
    select 1
    from jsonb_array_elements(p_rooms) r
    where trim(coalesce(r->>'roomNo', '')) !~ '^\d{4}$'
  ) then
    raise exception '객실업로드 안전검증 실패: 4자리 객실번호가 아닌 행이 있습니다.';
  end if;

  if exists (
    select 1
    from (
      select trim(r->>'roomNo') room_no, count(*) cnt
      from jsonb_array_elements(p_rooms) r
      group by trim(r->>'roomNo')
    ) d
    where d.cnt <> 1
  ) then
    raise exception '객실업로드 안전검증 실패: 중복 객실번호가 있습니다.';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(p_rooms) r
    where upper(trim(coalesce(r->>'roomStatus', ''))) not in (
      'VACANT_CLEAN','STOCK','STOCK_RC','STOCK_HU','STAY','DUE_OUT',
      'CHECKED_OUT','CHECKED_OUT_RC','CHECKED_OUT_HU','RECHECKIN'
    )
  ) then
    raise exception '객실업로드 안전검증 실패: 허용되지 않은 객실상태가 있습니다.';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(p_rooms) r
    where upper(trim(coalesce(r->>'cleaningStatus', ''))) not in (
      'WAITING','NOT_REQUIRED','ASSIGNED','CLEANING','COMPLETED',
      'QM_WAITING','QM_CHECKING','QM_COMPLETED','REWORK'
    )
  ) then
    raise exception '객실업로드 안전검증 실패: 허용되지 않은 청소상태가 있습니다.';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(p_rooms) r
    where upper(trim(coalesce(r->>'cleaningType', ''))) not in ('','NORMAL','DS')
  ) then
    raise exception '객실업로드 안전검증 실패: 허용되지 않은 정비유형이 있습니다.';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(p_rooms) r
    where upper(trim(coalesce(r->>'assignmentType', ''))) not in ('','SOLO','PAIR','PAIR_TRAINING')
  ) then
    raise exception '객실업로드 안전검증 실패: 허용되지 않은 배정유형이 있습니다.';
  end if;

  if jsonb_typeof(coalesce(p_expected_versions, '{}'::jsonb)) <> 'object' then
    raise exception '객실별 예상 버전 정보가 올바르지 않습니다.';
  end if;
  select count(*) into v_expected_version_count from jsonb_object_keys(p_expected_versions);
  if v_expected_version_count <> v_expected_count then
    raise exception '객실업로드 안전검증 실패: 객실별 예상 버전 수가 객실 수와 일치하지 않습니다.';
  end if;
  if exists (
    select 1 from jsonb_each_text(p_expected_versions) e
    where e.key !~ '^\d{4}$' or e.value !~ '^\d+$'
  ) then
    raise exception '객실업로드 안전검증 실패: 객실별 예상 버전 형식이 올바르지 않습니다.';
  end if;
  if exists (
    select 1 from jsonb_array_elements(p_rooms) r
    where not (p_expected_versions ? trim(r->>'roomNo'))
  ) then
    raise exception '객실업로드 안전검증 실패: 객실별 예상 버전이 누락되었습니다.';
  end if;
  if exists (
    select 1 from jsonb_object_keys(p_expected_versions) e(room_no)
    where not exists (
      select 1 from jsonb_array_elements(p_rooms) r
      where trim(r->>'roomNo') = e.room_no
    )
  ) then
    raise exception '객실업로드 안전검증 실패: 업로드 객실에 없는 예상 버전 키가 있습니다.';
  end if;

  if jsonb_typeof(coalesce(p_upload, '{}'::jsonb)) <> 'object' then
    raise exception '업로드 메타정보 형식이 올바르지 않습니다.';
  end if;
  if upper(trim(coalesce(p_upload->>'applyMode', ''))) not in ('RESET_REPLACE','MERGE_REPLACE') then
    raise exception '객실업로드 안전검증 실패: 적용모드가 올바르지 않습니다.';
  end if;
  if jsonb_typeof(coalesce(p_upload->'counts', '{}'::jsonb)) <> 'object' then
    raise exception '객실업로드 안전검증 실패: 상태별 객실 수 형식이 올바르지 않습니다.';
  end if;
  if exists (
    select 1 from jsonb_object_keys(p_upload->'counts') k
    where k not in ('VACANT_CLEAN','STOCK','STOCK_RC','STOCK_HU','STAY','DUE_OUT','CHECKED_OUT','RECHECKIN')
  ) then
    raise exception '객실업로드 안전검증 실패: 알 수 없는 상태 집계가 있습니다.';
  end if;
  if exists (
    select 1 from jsonb_each(p_upload->'counts') e
    where jsonb_typeof(e.value) <> 'number' or e.value::text !~ '^\d+$'
  ) then
    raise exception '객실업로드 안전검증 실패: 상태별 객실 수가 0 이상의 정수가 아닙니다.';
  end if;
  select coalesce(sum((e.value::text)::bigint), 0)
    into v_count_sum
  from jsonb_each(p_upload->'counts') e;
  if v_count_sum <> v_expected_count then
    raise exception '객실업로드 안전검증 실패: 상태별 합계 %실이 안전기준 %실과 일치하지 않습니다.', v_count_sum, v_expected_count;
  end if;
  v_vacant_count := coalesce(nullif(p_upload->'counts'->>'VACANT_CLEAN','')::bigint, 0);

  if jsonb_typeof(coalesce(p_upload->'roomsByStatus', '{}'::jsonb)) <> 'object' then
    raise exception '객실업로드 안전검증 실패: 상태별 객실목록 형식이 올바르지 않습니다.';
  end if;
  if exists (
    select 1 from jsonb_each(p_upload->'roomsByStatus') e
    where e.key not in ('STOCK','STOCK_RC','STOCK_HU','STAY','DUE_OUT','CHECKED_OUT','RECHECKIN')
       or jsonb_typeof(e.value) <> 'array'
  ) then
    raise exception '객실업로드 안전검증 실패: 상태별 객실목록에 허용되지 않은 항목이 있습니다.';
  end if;
  if exists (
    select 1
    from jsonb_each(p_upload->'roomsByStatus') e
    cross join lateral jsonb_array_elements_text(e.value) x(room_no)
    where trim(x.room_no) !~ '^\d{4}$'
       or not exists (
         select 1 from jsonb_array_elements(p_rooms) r
         where trim(r->>'roomNo') = trim(x.room_no)
       )
  ) then
    raise exception '객실업로드 안전검증 실패: 상태별 객실목록에 유효하지 않은 객실번호가 있습니다.';
  end if;
  if exists (
    select 1
    from (
      select trim(x.room_no) room_no, count(*) cnt
      from jsonb_each(p_upload->'roomsByStatus') e
      cross join lateral jsonb_array_elements_text(e.value) x(room_no)
      group by trim(x.room_no)
    ) d
    where d.cnt > 1
  ) then
    raise exception '객실업로드 안전검증 실패: 한 객실이 여러 원본 상태에 중복 포함되어 있습니다.';
  end if;
  if exists (
    select 1
    from jsonb_each(p_upload->'roomsByStatus') e
    where jsonb_array_length(e.value) <> coalesce(nullif(p_upload->'counts'->>e.key,'')::integer, 0)
  ) then
    raise exception '객실업로드 안전검증 실패: 상태별 객실목록과 집계 수가 일치하지 않습니다.';
  end if;
  select coalesce(sum(jsonb_array_length(e.value)), 0)
    into v_explicit_count
  from jsonb_each(p_upload->'roomsByStatus') e;
  if v_explicit_count + v_vacant_count <> v_expected_count then
    raise exception '객실업로드 안전검증 실패: 판독 객실과 공실 보정 합계가 안전기준과 일치하지 않습니다.';
  end if;

  -- A bogus 4-digit room could otherwise replace a missing real room while keeping the total count.
  -- Compare the incoming room set with the latest prior full operational room set for this site.
  select max(c.business_date) into v_baseline_date
  from public.nova_rooms_current c
  where c.site = v_site and c.business_date < v_date;

  if v_baseline_date is not null then
    select count(*) into v_baseline_count
    from public.nova_rooms_current c
    where c.site = v_site and c.business_date = v_baseline_date;

    if v_baseline_count = v_expected_count then
      if exists (
        select 1
        from public.nova_rooms_current c
        where c.site = v_site and c.business_date = v_baseline_date
          and not exists (
            select 1 from jsonb_array_elements(p_rooms) r
            where trim(r->>'roomNo') = c.room_no
          )
      ) or exists (
        select 1
        from jsonb_array_elements(p_rooms) r
        where not exists (
          select 1 from public.nova_rooms_current c
          where c.site = v_site and c.business_date = v_baseline_date
            and c.room_no = trim(r->>'roomNo')
        )
      ) then
        raise exception '객실업로드 안전검증 실패: 객실번호 구성이 최근 정상 객실목록(%)과 다릅니다. 객실마스터 변경 여부를 먼저 확인해 주세요.', v_baseline_date;
      end if;
    end if;
  end if;

  v_result := public.nova_room_upload_apply_v4(
    p_business_date,
    p_site,
    p_rooms,
    p_upload,
    p_expected_versions,
    p_version,
    p_request_id
  );

  v_version := coalesce(nullif(v_result->>'version','')::bigint, 0);
  if v_version > 0 then
    update public.nova_room_upload_snapshots s
    set request_id = trim(coalesce(p_request_id,'')),
        guard_version = v_guard_version,
        db_committed_at = coalesce(s.db_committed_at, now()),
        sheet_mirror_status = case when s.sheet_mirror_status = '' then 'PENDING' else s.sheet_mirror_status end,
        realtime_status = case when s.realtime_status = '' then 'DB_AUTHORITY' else s.realtime_status end,
        last_error = ''
    where s.business_date = v_date
      and s.site = v_site
      and s.upload_version = v_version
      and s.is_active = true;
  end if;

  return v_result || jsonb_build_object(
    'uploadRpcVersion', 'V5',
    'guardVersion', v_guard_version,
    'expectedRoomCount', v_expected_count,
    'baselineBusinessDate', coalesce(v_baseline_date::text, '')
  );
end;
$function$;

create or replace function public.nova_room_upload_mark_stage_v1(
  p_business_date text,
  p_site text,
  p_upload_version bigint,
  p_request_id text,
  p_stage text,
  p_error text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_request_id text := trim(coalesce(p_request_id,''));
  v_stage text := upper(trim(coalesce(p_stage,'')));
begin
  if v_actor = '' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='객실 업로드 권한이 없습니다.';
  end if;
  begin v_date := trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
    or v_site=coalesce(v_user.default_site,'')
    or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501', message='사업장 권한이 없습니다.';
  end if;
  if v_stage not in ('SHEET_MIRRORED','SHEET_FAILED','REALTIME_CONVERGED','REALTIME_DEFERRED','REALTIME_FAILED') then
    raise exception '객실업로드 단계 값이 올바르지 않습니다.';
  end if;

  update public.nova_room_upload_snapshots s
  set sheet_mirror_status = case
        when v_stage='SHEET_MIRRORED' then 'MIRRORED'
        when v_stage='SHEET_FAILED' then 'FAILED'
        else s.sheet_mirror_status end,
      sheet_mirrored_at = case when v_stage='SHEET_MIRRORED' then coalesce(s.sheet_mirrored_at, now()) else s.sheet_mirrored_at end,
      realtime_status = case
        when v_stage='REALTIME_CONVERGED' then 'CONVERGED'
        when v_stage='REALTIME_DEFERRED' then 'DEFERRED'
        when v_stage='REALTIME_FAILED' then 'FAILED'
        else s.realtime_status end,
      realtime_converged_at = case when v_stage='REALTIME_CONVERGED' then coalesce(s.realtime_converged_at, now()) else s.realtime_converged_at end,
      last_error = left(coalesce(p_error,''), 1000)
  where s.business_date=v_date
    and s.site=v_site
    and s.upload_version=p_upload_version
    and s.request_id=v_request_id
    and s.is_active=true;

  if not found then
    raise exception '객실업로드 단계 갱신 대상을 찾지 못했습니다.';
  end if;

  return jsonb_build_object('ok',true,'stage',v_stage,'businessDate',v_date::text,'site',v_site,'version',p_upload_version);
end;
$function$;

revoke all on table nova_private.room_upload_site_guard_v1 from public, anon, authenticated;
revoke execute on function public.nova_room_upload_apply_v5(text,text,jsonb,jsonb,jsonb,bigint,text) from public, anon;
grant execute on function public.nova_room_upload_apply_v5(text,text,jsonb,jsonb,jsonb,bigint,text) to authenticated;
revoke execute on function public.nova_room_upload_mark_stage_v1(text,text,bigint,text,text,text) from public, anon;
grant execute on function public.nova_room_upload_mark_stage_v1(text,text,bigint,text,text,text) to authenticated;

-- Legacy apply versions are no longer called by the canonical client. Keep V4 temporarily
-- executable for already-open tabs during the rollout, but close older mutation surfaces now.
do $block$
begin
  if to_regprocedure('public.nova_room_upload_apply_v1(text,text,jsonb,jsonb,bigint,text)') is not null then
    execute 'revoke execute on function public.nova_room_upload_apply_v1(text,text,jsonb,jsonb,bigint,text) from authenticated';
  end if;
exception when undefined_function then null;
end
$block$;

do $block$
begin
  if to_regprocedure('public.nova_room_upload_apply_v2(text,text,jsonb,jsonb,bigint,text)') is not null then
    execute 'revoke execute on function public.nova_room_upload_apply_v2(text,text,jsonb,jsonb,bigint,text) from authenticated';
  end if;
exception when undefined_function then null;
end
$block$;

do $block$
begin
  if to_regprocedure('public.nova_room_upload_apply_v3(text,text,jsonb,jsonb,jsonb,bigint,text)') is not null then
    execute 'revoke execute on function public.nova_room_upload_apply_v3(text,text,jsonb,jsonb,jsonb,bigint,text) from authenticated';
  end if;
exception when undefined_function then null;
end
$block$;
