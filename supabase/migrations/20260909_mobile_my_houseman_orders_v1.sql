-- MOBILE_MY_HOUSEMAN_ORDERS_V1
-- ROOMMAID/QM users can read only houseman orders they themselves registered.
-- Existing order creation/assignment/processing data and permissions are unchanged.

create index if not exists nova_houseman_orders_registered_by_date_site_idx
  on public.nova_houseman_orders (registered_by, business_date, site, registered_at desc);

create or replace function public.nova_mobile_my_houseman_orders_v1(
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
  v_orders jsonb := '[]'::jsonb;
begin
  if v_actor = '' then
    raise exception using errcode='42501', message='로그인이 필요합니다.';
  end if;

  select * into v_user
    from public.nova_users
   where employee_no = v_actor
     and enabled = true;

  if not found or upper(trim(coalesce(v_user.role,''))) not in ('ROOMMAID','QM') then
    raise exception using errcode='42501', message='내 요청 조회 권한이 없습니다.';
  end if;

  if p_business_date is null or v_site = '' then
    raise exception '업무일자와 사업장을 확인해 주세요.';
  end if;

  if cardinality(coalesce(v_user.allowed_sites, '{}'::text[])) > 0
     and not (v_site = any(v_user.allowed_sites)) then
    raise exception using errcode='42501', message='해당 사업장 조회 권한이 없습니다.';
  end if;

  if cardinality(coalesce(v_user.allowed_sites, '{}'::text[])) = 0
     and trim(coalesce(v_user.default_site,'')) <> ''
     and trim(coalesce(v_user.default_site,'')) <> v_site then
    raise exception using errcode='42501', message='해당 사업장 조회 권한이 없습니다.';
  end if;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'orderId', o.order_id,
        'businessDate', o.business_date::text,
        'site', o.site,
        'roomNo', o.room_no,
        'part', o.part,
        'itemSummary', o.item_summary,
        'quantity', o.quantity,
        'note', o.note,
        'requester', o.requester,
        'assignedEmployeeNo', coalesce(o.assigned_employee_no,''),
        'assignedName', coalesce(o.assigned_name,''),
        'processorEmployeeNo', coalesce(o.processor_employee_no,''),
        'processorName', coalesce(o.processor_name,''),
        'statusCode', o.status_code,
        'important', o.important,
        'registeredAt', o.registered_at,
        'acceptedAt', o.accepted_at,
        'startedAt', o.started_at,
        'completedAt', o.completed_at,
        'unableReason', o.unable_reason,
        'updatedAt', o.updated_at,
        'version', o.version
      ) order by o.registered_at desc
    ),
    '[]'::jsonb
  ) into v_orders
  from (
    select *
      from public.nova_houseman_orders
     where business_date = p_business_date
       and site = v_site
       and registered_by = v_actor
     order by registered_at desc
     limit 200
  ) o;

  return jsonb_build_object(
    'ok', true,
    'businessDate', p_business_date::text,
    'site', v_site,
    'orders', v_orders,
    'count', jsonb_array_length(v_orders)
  );
end;
$function$;

revoke all on function public.nova_mobile_my_houseman_orders_v1(date,text) from public;
revoke all on function public.nova_mobile_my_houseman_orders_v1(date,text) from anon;
grant execute on function public.nova_mobile_my_houseman_orders_v1(date,text) to authenticated;
