-- NOVA_QM_BEGIN_SITE_AUTH_PERF_V1
-- Preserve nova_qm_begin_inspection_v1 behavior while eliminating the duplicate nova_users lookup
-- performed by nova_is_active_qm_for_site(). The already-loaded QM row is the authority for the
-- exact same default_site / allowed_sites rule. Row locking, state guards, events and draft semantics
-- are unchanged.

CREATE OR REPLACE FUNCTION public.nova_qm_begin_inspection_v1(p_business_date date, p_site text, p_room_no text, p_view text DEFAULT 'TARGETS'::text, p_request_id text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_catalog'
AS $function$
declare
  v_claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  v_employee_no text := trim(coalesce(v_claims->>'employee_no', ''));
  v_user public.nova_users%rowtype;
  v_room public.nova_rooms_current%rowtype;
  v_draft public.nova_qm_drafts%rowtype;
  v_view text := upper(trim(coalesce(p_view, 'TARGETS')));
  v_request_id text := nullif(trim(coalesce(p_request_id, '')), '');
  v_before text;
  v_has_roommaid boolean;
  v_already boolean := false;
  v_draft_id text;
begin
  if v_employee_no = '' then
    raise exception using errcode='42501', message='로그인이 필요합니다.';
  end if;

  select * into v_user
  from public.nova_users
  where employee_no = v_employee_no and enabled = true and upper(coalesce(role, '')) = 'QM';
  if not found then
    raise exception using errcode='42501', message='QM 사용자 정보를 확인할 수 없습니다.';
  end if;

  if trim(coalesce(p_site, '')) = '' or trim(coalesce(p_room_no, '')) = '' then
    raise exception using errcode='22023', message='점검할 사업장과 객실번호가 필요합니다.';
  end if;
  if v_view not in ('TARGETS', 'CLEANED', 'VACANT') then
    raise exception using errcode='22023', message='지원하지 않는 QM 점검경로입니다.';
  end if;

  -- NOVA 권한의 단일 기준: 활성 QM 계정 + nova_users 사업장 설정.
  -- 로그인 세션의 사업장 고정은 Apps Script/토큰 계층에서 별도로 검증한다.
  -- QM_BEGIN_SITE_AUTH_PERF_V1 · 이미 조회한 v_user로 동일 사업장 권한을 검증해 중복 함수/사용자 조회 제거
  if not (
    (nullif(trim(coalesce(v_user.default_site, '')), '') is null
      and cardinality(coalesce(v_user.allowed_sites, array[]::text[])) = 0)
    or nullif(trim(coalesce(v_user.default_site, '')), '') = trim(p_site)
    or trim(p_site) = any(coalesce(v_user.allowed_sites, array[]::text[]))
  ) then
    raise exception using errcode='42501', message='해당 사업장의 QM 권한이 없습니다.';
  end if;

  select * into v_room
  from public.nova_rooms_current r
  where r.business_date = p_business_date and r.site = trim(p_site) and r.room_no = trim(p_room_no)
  for update;
  if not found then
    raise exception using errcode='P0002', message='현재객실현황에서 해당 객실을 찾을 수 없습니다.';
  end if;

  v_before := upper(trim(coalesce(v_room.cleaning_status, '')));
  v_has_roommaid := nullif(trim(coalesce(v_room.roommaid_employee_no, '')), '') is not null
                    or nullif(trim(coalesce(v_room.secondary_roommaid_employee_no, '')), '') is not null;

  if v_before not in ('COMPLETED', 'QM_WAITING', 'QM_CHECKING') then
    raise exception using errcode='40001', message='현재 QM 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.';
  end if;

  if v_view = 'TARGETS' then
    if trim(coalesce(v_room.qm_employee_no, '')) <> v_employee_no then
      raise exception using errcode='40001', message='본인에게 배정된 QM 점검대상이 아닙니다. 목록을 새로고침해 주세요.';
    end if;
    if upper(trim(coalesce(v_room.operational_status, ''))) = 'REWORK' then
      raise exception using errcode='40001', message='재정비 중인 객실은 재정비 완료 후 점검을 계속할 수 있습니다.';
    end if;
  elsif v_view = 'VACANT' then
    if upper(trim(coalesce(v_room.room_status, ''))) <> 'VACANT_CLEAN' then
      raise exception using errcode='40001', message='현재 공실 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.';
    end if;
  else
    if upper(trim(coalesce(v_room.room_status, ''))) = 'VACANT_CLEAN' or not v_has_roommaid then
      raise exception using errcode='40001', message='현재 당일 청소완료 점검을 시작할 수 있는 상태가 아닙니다. 목록을 새로고침해 주세요.';
    end if;
  end if;

  if v_view in ('CLEANED', 'VACANT')
     and nullif(trim(coalesce(v_room.qm_employee_no, '')), '') is not null
     and trim(v_room.qm_employee_no) <> v_employee_no then
    raise exception using errcode='40001', message='다른 QM에게 이미 배정되었거나 점검 중인 객실입니다.';
  end if;

  if trim(coalesce(v_room.qm_employee_no, '')) = v_employee_no and v_before = 'QM_CHECKING' then
    v_already := true;
  else
    update public.nova_rooms_current
       set qm_employee_no = v_employee_no,
           cleaning_status = 'QM_CHECKING',
           version = version + 1,
           updated_by = v_employee_no,
           updated_at = now()
     where id = v_room.id
     returning * into v_room;

    insert into public.nova_room_events (
      request_id, business_date, site, room_no, action,
      before_status, after_status, employee_no, room_version, detail, event_time
    ) values (
      coalesce(v_request_id, gen_random_uuid()::text),
      v_room.business_date, v_room.site, v_room.room_no, 'QM_START',
      v_before, 'QM_CHECKING', v_employee_no, v_room.version,
      jsonb_build_object(
        'role', 'QM', 'qmName', v_user.name, 'source', 'QM_BEGIN_DB_FIRST_V1',
        'browseView', v_view, 'vacantSpotCheck', (v_view = 'VACANT'),
        'primaryEmployeeNo', coalesce(v_room.roommaid_employee_no, ''),
        'secondaryEmployeeNo', coalesce(v_room.secondary_roommaid_employee_no, ''),
        'qmEmployeeNo', v_employee_no, 'cleaningStatus', 'QM_CHECKING'
      ), now()
    );
  end if;

  select * into v_draft
  from public.nova_qm_drafts d
  where d.business_date = p_business_date
    and d.site = trim(p_site)
    and d.room_no = trim(p_room_no)
    and d.qm_employee_no = v_employee_no
    and d.status = 'IN_PROGRESS'
  order by d.saved_at desc, d.started_at desc
  limit 1
  for update;

  -- 이미 QM_CHECKING이던 기존 세션인데 DB 초안이 없으면 새 초안을 만들지 않습니다.
  -- 이 경우 클라이언트가 기존 Apps Script 경로로 내려가 기존 Sheet 초안을 그대로 이어갑니다.
  if not found and not v_already then
    v_draft_id := 'QMDRAFT-' || to_char(p_business_date, 'YYYYMMDD') || '-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10));
    begin
      insert into public.nova_qm_drafts (
        draft_id, business_date, site, room_no, qm_employee_no,
        checklist_revision, answers, defects, status, version,
        started_at, saved_at, last_request_id
      ) values (
        v_draft_id, p_business_date, trim(p_site), trim(p_room_no), v_employee_no,
        '', '[]'::jsonb, '[]'::jsonb, 'IN_PROGRESS', 1,
        now(), now(), v_request_id
      ) returning * into v_draft;
    exception when unique_violation then
      select * into v_draft
      from public.nova_qm_drafts d
      where d.business_date = p_business_date
        and d.site = trim(p_site)
        and d.room_no = trim(p_room_no)
        and d.qm_employee_no = v_employee_no
        and d.status = 'IN_PROGRESS'
      order by d.saved_at desc, d.started_at desc
      limit 1;
    end;
  end if;

  return jsonb_build_object(
    'ok', true,
    'dbFirst', true,
    'alreadyChecking', v_already,
    'requestId', v_request_id,
    'version', v_room.version,
    'room', jsonb_build_object(
      'businessDate', v_room.business_date::text, 'site', v_room.site, 'roomNo', v_room.room_no,
      'building', coalesce(v_room.building, ''), 'roomStatus', coalesce(v_room.room_status, ''),
      'cleaningStatus', coalesce(v_room.cleaning_status, ''), 'cleaningType', coalesce(v_room.cleaning_type, 'NORMAL'),
      'assignmentType', coalesce(v_room.assignment_type, 'SOLO'),
      'roommaidEmployeeNo', coalesce(v_room.roommaid_employee_no, ''),
      'secondaryRoommaidEmployeeNo', coalesce(v_room.secondary_roommaid_employee_no, ''),
      'qmEmployeeNo', coalesce(v_room.qm_employee_no, ''),
      'operationalStatus', coalesce(v_room.operational_status, ''),
      'version', v_room.version, 'updatedAt', v_room.updated_at
    ),
    'draft', case when v_draft.draft_id is null then null else jsonb_build_object(
      'draftId', v_draft.draft_id, 'rowNumber', 0,
      'businessDate', v_draft.business_date::text, 'site', v_draft.site, 'roomNo', v_draft.room_no,
      'checklistRevision', coalesce(v_draft.checklist_revision, ''),
      'answers', coalesce(v_draft.answers, '[]'::jsonb), 'defects', coalesce(v_draft.defects, '[]'::jsonb),
      'startedAt', v_draft.started_at, 'savedAt', v_draft.saved_at, 'dbVersion', v_draft.version
    ) end
  );
end;
$function$;
