-- NOVA Core 3.0 Phase 1 read-only audit
-- Safety rule: this file contains SELECT statements only.
-- Run against production only as a read-only verification step.

-- 1) Duplicate current-room keys must be zero.
select business_date, site, room_no, count(*) as cnt
from public.nova_rooms_current
group by business_date, site, room_no
having count(*) > 1;

-- 2) Duplicate event request ids must be zero.
select request_id, count(*) as cnt
from public.nova_room_events
group by request_id
having count(*) > 1;

-- 3) Room current version must not lag the latest event version.
with latest_event as (
  select business_date, site, room_no, max(room_version) as max_event_version
  from public.nova_room_events
  group by business_date, site, room_no
)
select r.business_date, r.site, r.room_no, r.version, e.max_event_version
from public.nova_rooms_current r
join latest_event e using (business_date, site, room_no)
where r.version < e.max_event_version;

-- 4) Latest START/COMPLETE event must agree with current cleaning state.
with ranked as (
  select e.*,
         row_number() over (
           partition by business_date, site, room_no
           order by event_time desc, id desc
         ) as rn
  from public.nova_room_events e
  where action in ('CLEANING_START','CLEANING_COMPLETE')
)
select e.business_date, e.site, e.room_no,
       e.action, e.after_status as event_after_status,
       r.cleaning_status as current_cleaning_status,
       e.room_version, r.version
from ranked e
join public.nova_rooms_current r using (business_date, site, room_no)
where e.rn = 1
  and upper(coalesce(e.after_status,'')) <> upper(coalesce(r.cleaning_status,''));

-- 5) Cleaning START/COMPLETE transition graph must contain only allowed transitions.
select action, before_status, after_status, count(*) as cnt
from public.nova_room_events
where action in ('CLEANING_START','CLEANING_COMPLETE')
group by action, before_status, after_status
having not (
  (action = 'CLEANING_START'
   and upper(coalesce(before_status,'')) in ('WAITING','ASSIGNED')
   and upper(coalesce(after_status,'')) = 'CLEANING')
  or
  (action = 'CLEANING_COMPLETE'
   and upper(coalesce(before_status,'')) = 'CLEANING'
   and upper(coalesce(after_status,'')) in ('COMPLETED','QM_WAITING'))
);

-- 6) Assigned ROOMMAID users must exist, be enabled and have ROOMMAID role.
select r.business_date, r.site, r.room_no,
       r.roommaid_employee_no, u.role, u.enabled
from public.nova_rooms_current r
left join public.nova_users u
  on u.employee_no = r.roommaid_employee_no
where nullif(trim(coalesce(r.roommaid_employee_no,'')), '') is not null
  and (
    u.employee_no is null
    or u.enabled is distinct from true
    or upper(coalesce(u.role,'')) <> 'ROOMMAID'
  );

-- 7) Assigned secondary ROOMMAID users must also be valid.
select r.business_date, r.site, r.room_no,
       r.secondary_roommaid_employee_no, u.role, u.enabled
from public.nova_rooms_current r
left join public.nova_users u
  on u.employee_no = r.secondary_roommaid_employee_no
where nullif(trim(coalesce(r.secondary_roommaid_employee_no,'')), '') is not null
  and (
    u.employee_no is null
    or u.enabled is distinct from true
    or upper(coalesce(u.role,'')) <> 'ROOMMAID'
  );

-- 8) Assigned QM users must exist, be enabled and have QM role.
select r.business_date, r.site, r.room_no,
       r.qm_employee_no, u.role, u.enabled
from public.nova_rooms_current r
left join public.nova_users u
  on u.employee_no = r.qm_employee_no
where nullif(trim(coalesce(r.qm_employee_no,'')), '') is not null
  and (
    u.employee_no is null
    or u.enabled is distinct from true
    or upper(coalesce(u.role,'')) <> 'QM'
  );

-- 9) Request-dedup rows must not disagree with room events for the same request id.
select d.request_id, d.employee_no as dedup_employee_no, d.action as dedup_action,
       e.employee_no as event_employee_no, e.action as event_action
from public.nova_request_dedup d
join public.nova_room_events e using (request_id)
where d.employee_no is distinct from e.employee_no
   or d.action is distinct from e.action;

-- 10) Completed cleaning rows should have a completion timestamp.
select business_date, site, room_no, cleaning_status,
       cleaning_started_at, cleaning_completed_at, version
from public.nova_rooms_current
where upper(coalesce(cleaning_status,'')) in ('COMPLETED','QM_WAITING','QM_CHECKING','QM_COMPLETED')
  and cleaning_completed_at is null;

-- 11) Cleaning rows should not have completion before start.
select business_date, site, room_no, cleaning_started_at, cleaning_completed_at
from public.nova_rooms_current
where cleaning_started_at is not null
  and cleaning_completed_at is not null
  and cleaning_completed_at < cleaning_started_at;

-- 12) Recent API processing-time distribution for START/COMPLETE.
select action,
       count(*) as events,
       percentile_cont(0.50) within group (order by nullif(detail->>'totalMs','')::numeric) as p50_ms,
       percentile_cont(0.95) within group (order by nullif(detail->>'totalMs','')::numeric) as p95_ms,
       max(nullif(detail->>'totalMs','')::numeric) as max_ms
from public.nova_room_events
where action in ('CLEANING_START','CLEANING_COMPLETE')
  and nullif(detail->>'totalMs','') is not null
group by action
order by action;

-- 13) Houseman photo metadata orphan candidates. Read-only; never delete here.
select p.photo_id, p.order_id, p.status, p.created_at, p.uploaded_at, p.object_path
from public.nova_houseman_order_photos p
where p.status = 'PENDING'
  and p.created_at < now() - interval '10 minutes'
order by p.created_at;

-- 14) QM photo pending candidates. Read-only; never delete here.
select p.photo_id, p.draft_id, p.status, p.created_at, p.uploaded_at, p.object_path
from public.nova_qm_inspection_photos p
where p.status = 'PENDING'
  and p.created_at < now() - interval '10 minutes'
order by p.created_at;
