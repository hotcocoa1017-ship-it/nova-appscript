-- NOVA operation settings DB-first read RPC v1
-- Applied additively to Supabase project nova-realtime.

create or replace function public.nova_operation_settings_read_v1()
returns jsonb
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_actor text := trim(coalesce(v_claims->>'employee_no', ''));
  v_user public.nova_users%rowtype;
  v_required text[] := array['DS_WEIGHT','WEEKDAY_CHECKOUT','WEEKDAY_ALERT','WEEKEND_CHECKOUT','WEEKEND_ALERT','DEPARTURE_TRIGGER_MINUTES','AUTO_CLOSE_ENABLED','AUTO_CLOSE_TIME','AUTO_CLOSE_NOTIFY_FAILURE'];
  v_values jsonb := '{}'::jsonb;
  v_confirmed boolean := false;
  v_version bigint := 0;
begin
  if v_actor = '' then
    raise exception using errcode='42501', message='로그인이 필요합니다.';
  end if;

  select * into v_user
    from public.nova_users
   where employee_no = v_actor
     and enabled = true;
  if not found or upper(coalesce(v_user.role, '')) <> 'ADMIN' then
    raise exception using errcode='42501', message='운영설정 조회 권한이 없습니다.';
  end if;

  select coalesce(jsonb_object_agg(code, value), '{}'::jsonb),
         count(*) = cardinality(v_required) and bool_and(confirmed),
         coalesce(max(version), 0)
    into v_values, v_confirmed, v_version
    from public.nova_operation_settings
   where code = any(v_required);

  return jsonb_build_object(
    'ok', true,
    'dbFirst', true,
    'values', v_values,
    'confirmed', coalesce(v_confirmed, false),
    'version', v_version
  );
end;
$function$;

revoke all on function public.nova_operation_settings_read_v1() from public, anon;
grant execute on function public.nova_operation_settings_read_v1() to authenticated, service_role;
