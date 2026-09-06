-- ROOM_UPLOAD_STATE_RPC_V1
-- Lightweight authorized DB snapshot used only to reconcile upload input before DB commit.

create or replace function public.nova_room_upload_state_v1(
  p_business_date text,
  p_site text
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
  v_date date;
  v_site text := trim(coalesce(p_site,''));
  v_rooms jsonb := '[]'::jsonb;
  v_version bigint := 0;
begin
  if v_actor='' then raise exception using errcode='42501', message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501', message='객실 업로드 조회 권한이 없습니다.';
  end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
          or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501', message='사업장 권한이 없습니다.';
  end if;

  select coalesce(max(r.version),0),
         coalesce(jsonb_agg(
           jsonb_build_object(
             '업무일자',r.business_date::text,
             '사업장',r.site,
             '객실번호',r.room_no,
             '동',r.building,
             '객실상태',r.room_status,
             '청소상태',r.cleaning_status,
             '정비유형',r.cleaning_type,
             '배정유형',r.assignment_type,
             '룸메이드사번',r.roommaid_employee_no,
             '보조룸메이드사번',r.secondary_roommaid_employee_no,
             'QM사번',r.qm_employee_no,
             '객실운영상태',r.operational_status,
             '마지막변경버전',r.version,
             '수정일시',to_char(r.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS')
           ) order by r.room_no
         ),'[]'::jsonb)
  into v_version,v_rooms
  from public.nova_rooms_current r
  where r.business_date=v_date and r.site=v_site;

  return jsonb_build_object(
    'ok',true,
    'dbFirst',true,
    'businessDate',v_date::text,
    'site',v_site,
    'version',v_version,
    'currentRows',v_rooms
  );
end;
$$;

revoke all on function public.nova_room_upload_state_v1(text,text) from public;
revoke execute on function public.nova_room_upload_state_v1(text,text) from anon;
grant execute on function public.nova_room_upload_state_v1(text,text) to authenticated,service_role;
