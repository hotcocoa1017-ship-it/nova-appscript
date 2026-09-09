-- QM_LAST_QM_MOBILE_CARD_V1
-- Read-only helper for QM mobile browse cards. Existing room/QM data is not modified.

create or replace function public.nova_qm_last_qm_cards_v1(
  p_business_date date,
  p_site text
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
  v_site text := trim(coalesce(p_site,''));
  v_rooms jsonb := '[]'::jsonb;
begin
  if v_actor = '' then
    raise exception using errcode='42501', message='로그인이 필요합니다.';
  end if;

  select * into v_user
    from public.nova_users
   where employee_no = v_actor
     and enabled = true;

  if not found or upper(trim(coalesce(v_user.role,''))) <> 'QM' then
    raise exception using errcode='42501', message='QM 객실 조회 권한이 없습니다.';
  end if;

  if p_business_date is null or v_site = '' then
    raise exception '업무일자와 사업장을 확인해 주세요.';
  end if;

  if not public.nova_is_active_qm_for_site(v_actor, v_site) then
    raise exception using errcode='42501', message='해당 사업장의 QM 권한이 없습니다.';
  end if;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'roomNo', r.room_no,
        'lastQmBusinessDate', r.last_qm_business_date::text,
        'lastQmEmployeeNo', coalesce(r.last_qm_employee_no,'')
      ) order by r.room_no
    ),
    '[]'::jsonb
  )
  into v_rooms
  from public.nova_rooms_current r
  where r.business_date = p_business_date
    and r.site = v_site
    and r.last_qm_business_date is not null;

  return jsonb_build_object(
    'ok', true,
    'businessDate', p_business_date::text,
    'site', v_site,
    'rooms', v_rooms
  );
end;
$function$;

revoke all on function public.nova_qm_last_qm_cards_v1(date,text) from public;
revoke all on function public.nova_qm_last_qm_cards_v1(date,text) from anon;
grant execute on function public.nova_qm_last_qm_cards_v1(date,text) to authenticated;
