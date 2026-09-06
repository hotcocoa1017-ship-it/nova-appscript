-- DAILY_CLOSE_SAVE_DB_FIRST_V1
-- Manual ADMIN/ORDER close is committed to PostgreSQL before the legacy Sheet mirror.

create or replace function public.nova_daily_close_save_v2(
  p_business_date text,
  p_site text,
  p_snapshot jsonb,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  v_actor text:=trim(coalesce(v_claims->>'employee_no',''));
  v_user public.nova_users%rowtype;
  v_date date;
  v_site text:=trim(coalesce(p_site,''));
  v_request_id text:=trim(coalesce(p_request_id,''));
  v_closed_at timestamptz;
  v_version bigint:=1;
  v_response jsonb;
  v_existing record;
begin
  if v_actor='' then raise exception using errcode='42501',message='로그인이 필요합니다.'; end if;
  select * into v_user from public.nova_users where employee_no=v_actor and enabled=true;
  if not found or upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER') then
    raise exception using errcode='42501',message='마감 저장 권한이 없습니다.';
  end if;
  if trim(coalesce(p_business_date,'')) !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '업무일자를 확인해 주세요.'; end if;
  begin v_date:=trim(p_business_date)::date; exception when others then raise exception '업무일자를 확인해 주세요.'; end;
  if v_site='' then raise exception '사업장을 선택하세요.'; end if;
  if jsonb_typeof(coalesce(p_snapshot,'null'::jsonb))<>'object' then raise exception '마감정보를 확인해 주세요.'; end if;
  if coalesce((p_snapshot->>'totalRooms')::integer,0)<=0 then raise exception '마감할 객실자료가 없습니다.'; end if;
  if not ((coalesce(trim(v_user.default_site),'')='' and cardinality(coalesce(v_user.allowed_sites,array[]::text[]))=0)
          or v_site=coalesce(v_user.default_site,'') or v_site=any(coalesce(v_user.allowed_sites,array[]::text[]))) then
    raise exception using errcode='42501',message='사업장 권한이 없습니다.';
  end if;
  if v_request_id !~ '^[A-Za-z0-9._:-]{8,180}$' then raise exception '요청 ID 형식이 올바르지 않습니다.'; end if;
  begin
    v_closed_at:=nullif(trim(coalesce(p_snapshot->>'closedAt','')),'')::timestamp at time zone 'Asia/Seoul';
  exception when others then v_closed_at:=now(); end;
  if v_closed_at is null then v_closed_at:=now(); end if;

  insert into public.nova_request_dedup(request_id,employee_no,action,response_json)
  values(v_request_id,v_actor,'DAILY_CLOSE_SAVE_V2',null)
  on conflict(request_id) do nothing;
  if not found then
    select employee_no,action,response_json into v_existing
    from public.nova_request_dedup where request_id=v_request_id;
    if not found or v_existing.employee_no<>v_actor or v_existing.action<>'DAILY_CLOSE_SAVE_V2' then
      raise exception '이미 다른 요청에 사용된 요청 ID입니다.';
    end if;
    if v_existing.response_json is not null then
      return v_existing.response_json || jsonb_build_object('idempotent',true);
    end if;
    raise exception '동일 마감요청이 처리 중입니다. 잠시 후 다시 확인해 주세요.';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('NOVA_DAILY_CLOSE|'||v_date::text||'|'||v_site,0));
  select coalesce(version,0)+1 into v_version
  from public.nova_daily_close_snapshots
  where business_date=v_date and site=v_site;
  if v_version is null then v_version:=1; end if;

  insert into public.nova_daily_close_snapshots(
    business_date,site,snapshot,source_signature,source_updated_at,
    closed_by,closed_by_name,closed_at,version,request_id,is_active,
    cancelled_by,cancelled_at,created_at,updated_at
  ) values(
    v_date,v_site,p_snapshot,
    trim(coalesce(p_snapshot->>'sourceSignature','')),
    trim(coalesce(p_snapshot->>'sourceUpdatedAt','')),
    v_actor,coalesce(v_user.name,''),v_closed_at,v_version,v_request_id,true,
    '',null,now(),now()
  )
  on conflict(business_date,site) do update set
    snapshot=excluded.snapshot,
    source_signature=excluded.source_signature,
    source_updated_at=excluded.source_updated_at,
    closed_by=excluded.closed_by,
    closed_by_name=excluded.closed_by_name,
    closed_at=excluded.closed_at,
    version=public.nova_daily_close_snapshots.version+1,
    request_id=excluded.request_id,
    is_active=true,
    cancelled_by='',cancelled_at=null,updated_at=now()
  returning version into v_version;

  v_response:=jsonb_build_object(
    'ok',true,'dbFirst',true,'businessDate',v_date::text,'site',v_site,
    'version',v_version,'requestId',v_request_id,'idempotent',false,
    'closedAt',to_char(v_closed_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),
    'closedBy',v_actor,'closedByName',coalesce(v_user.name,'')
  );
  update public.nova_request_dedup set response_json=v_response where request_id=v_request_id;
  return v_response;
end;
$$;

revoke all on function public.nova_daily_close_save_v2(text,text,jsonb,text) from public;
revoke execute on function public.nova_daily_close_save_v2(text,text,jsonb,text) from anon;
grant execute on function public.nova_daily_close_save_v2(text,text,jsonb,text) to authenticated,service_role;
