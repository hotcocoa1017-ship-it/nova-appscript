-- NOVA QM Draft DB-first V1
-- Additive only: existing NOVA production tables are not modified.

create table if not exists public.nova_qm_drafts (
  draft_id text primary key,
  business_date date not null,
  site text not null,
  room_no text not null,
  qm_employee_no text not null,
  checklist_revision text not null default '',
  answers jsonb not null default '[]'::jsonb,
  defects jsonb not null default '[]'::jsonb,
  status text not null default 'IN_PROGRESS',
  version bigint not null default 1 check (version > 0),
  started_at timestamptz not null default now(),
  saved_at timestamptz not null default now(),
  completed_at timestamptz,
  last_request_id text,
  constraint nova_qm_drafts_status_check check (status in ('IN_PROGRESS','COMPLETED','CANCELLED'))
);

create index if not exists nova_qm_drafts_employee_date_idx
  on public.nova_qm_drafts (qm_employee_no, business_date desc, site);
create index if not exists nova_qm_drafts_room_idx
  on public.nova_qm_drafts (business_date, site, room_no);

alter table public.nova_qm_drafts enable row level security;

create or replace function public.nova_is_active_qm_for_site(p_employee_no text, p_site text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.nova_users u
    where u.employee_no = p_employee_no
      and u.enabled = true
      and upper(coalesce(u.role, '')) = 'QM'
      and (
        coalesce(array_length(u.allowed_sites, 1), 0) = 0
        or p_site = any(u.allowed_sites)
        or nullif(trim(coalesce(u.default_site, '')), '') = p_site
      )
  );
$$;

revoke all on function public.nova_is_active_qm_for_site(text,text) from public;
grant execute on function public.nova_is_active_qm_for_site(text,text) to authenticated;

create or replace function public.nova_save_qm_draft(
  p_draft_id text,
  p_business_date date,
  p_site text,
  p_room_no text,
  p_checklist_revision text,
  p_answers jsonb,
  p_defects jsonb,
  p_expected_version bigint default 0,
  p_request_id text default null
)
returns public.nova_qm_drafts
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb;
  v_employee_no text := trim(coalesce(v_claims ->> 'employee_no', ''));
  v_site_allowed boolean := false;
  v_row public.nova_qm_drafts;
begin
  if v_employee_no = '' then
    raise exception 'QM 인증정보가 없습니다.' using errcode = '28000';
  end if;

  select exists (
    select 1 from jsonb_array_elements_text(coalesce(v_claims -> 'sites', '[]'::jsonb)) s(site_name)
    where s.site_name = p_site
  ) into v_site_allowed;

  if not v_site_allowed or not public.nova_is_active_qm_for_site(v_employee_no, p_site) then
    raise exception '해당 사업장의 QM 저장 권한이 없습니다.' using errcode = '42501';
  end if;

  if trim(coalesce(p_draft_id, '')) = '' or trim(coalesce(p_room_no, '')) = '' then
    raise exception 'QM 초안 식별정보가 없습니다.' using errcode = '22023';
  end if;

  select * into v_row
  from public.nova_qm_drafts
  where draft_id = p_draft_id
  for update;

  if found then
    if v_row.qm_employee_no <> v_employee_no
       or v_row.business_date <> p_business_date
       or v_row.site <> p_site
       or v_row.room_no <> p_room_no then
      raise exception '다른 QM 초안은 수정할 수 없습니다.' using errcode = '42501';
    end if;
    if v_row.status <> 'IN_PROGRESS' then
      raise exception '이미 완료된 QM 초안입니다.' using errcode = '55000';
    end if;
    if coalesce(p_expected_version, 0) > 0 and v_row.version <> p_expected_version then
      raise exception 'QM 초안이 다른 요청에 의해 먼저 변경되었습니다.' using errcode = '40001';
    end if;
    if nullif(trim(coalesce(p_request_id, '')), '') is not null
       and v_row.last_request_id = p_request_id then
      return v_row;
    end if;

    update public.nova_qm_drafts
       set checklist_revision = coalesce(p_checklist_revision, ''),
           answers = coalesce(p_answers, '[]'::jsonb),
           defects = coalesce(p_defects, '[]'::jsonb),
           version = version + 1,
           saved_at = now(),
           last_request_id = nullif(trim(coalesce(p_request_id, '')), '')
     where draft_id = p_draft_id
     returning * into v_row;
    return v_row;
  end if;

  insert into public.nova_qm_drafts (
    draft_id, business_date, site, room_no, qm_employee_no,
    checklist_revision, answers, defects, status, version, started_at, saved_at, last_request_id
  ) values (
    p_draft_id, p_business_date, p_site, p_room_no, v_employee_no,
    coalesce(p_checklist_revision, ''), coalesce(p_answers, '[]'::jsonb), coalesce(p_defects, '[]'::jsonb),
    'IN_PROGRESS', 1, now(), now(), nullif(trim(coalesce(p_request_id, '')), '')
  ) returning * into v_row;
  return v_row;
end;
$$;

revoke all on function public.nova_save_qm_draft(text,date,text,text,text,jsonb,jsonb,bigint,text) from public;
grant execute on function public.nova_save_qm_draft(text,date,text,text,text,jsonb,jsonb,bigint,text) to authenticated;

revoke all on table public.nova_qm_drafts from anon;
grant select on table public.nova_qm_drafts to authenticated;

drop policy if exists "nova qm drafts read own" on public.nova_qm_drafts;
create policy "nova qm drafts read own"
on public.nova_qm_drafts
for select
to authenticated
using (
  qm_employee_no = coalesce((current_setting('request.jwt.claims', true)::jsonb ->> 'employee_no'), '')
  and exists (
    select 1 from jsonb_array_elements_text(coalesce((current_setting('request.jwt.claims', true)::jsonb -> 'sites'), '[]'::jsonb)) s(site_name)
    where s.site_name = site
  )
  and public.nova_is_active_qm_for_site(qm_employee_no, site)
);
