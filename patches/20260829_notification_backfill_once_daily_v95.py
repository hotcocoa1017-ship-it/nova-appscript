from pathlib import Path

PATH = Path('cloudrun/index.js')
text = PATH.read_text(encoding='utf-8')

# 1) Persist employee/day backfill completion state so 5-second badge polling does not repeat heavy current-assignment scans.
schema_anchor = """    await client.query(`
      create index if not exists idx_nova_app_notifications_employee_created
      on public.nova_app_notifications(employee_no, created_at desc, notification_id desc)
    `);
    // 개인 참고용 알림은 장기 업무이력이 아니므로 오래된 레코드는 자동 정리한다.
"""
schema_new = """    await client.query(`
      create index if not exists idx_nova_app_notifications_employee_created
      on public.nova_app_notifications(employee_no, created_at desc, notification_id desc)
    `);
    await client.query(`
      create table if not exists public.nova_app_notification_backfill_state(
        employee_no text not null,
        business_date date not null,
        completed_at timestamptz not null default now(),
        primary key(employee_no, business_date)
      )
    `);
    // 개인 참고용 알림은 장기 업무이력이 아니므로 오래된 레코드는 자동 정리한다.
"""
if 'nova_app_notification_backfill_state' not in text:
    if schema_anchor not in text:
        raise SystemExit('notification schema anchor not found')
    text = text.replace(schema_anchor, schema_new, 1)

cleanup_anchor = """    await client.query(`
      delete from public.nova_app_notifications
      where created_at < now() - interval '90 days'
    `);
    APP_NOTIFICATIONS_SCHEMA_READY = true;
"""
cleanup_new = """    await client.query(`
      delete from public.nova_app_notifications
      where created_at < now() - interval '90 days'
    `);
    await client.query(`
      delete from public.nova_app_notification_backfill_state
      where business_date < (now() at time zone 'Asia/Seoul')::date - 30
    `);
    APP_NOTIFICATIONS_SCHEMA_READY = true;
"""
if cleanup_new not in text:
    if cleanup_anchor not in text:
        raise SystemExit('notification cleanup anchor not found')
    text = text.replace(cleanup_anchor, cleanup_new, 1)

# 2) Before heavy role-specific backfill, check/claim once per employee per KST business day.
fn_anchor = """  let inserted = 0;
  const kstTodaySql = `(now() at time zone 'Asia/Seoul')::date`;

  if (role === 'HOUSEMAN') {
"""
fn_new = """  let inserted = 0;
  const kstTodaySql = `(now() at time zone 'Asia/Seoul')::date`;

  // 알림뱃지는 5초마다 조회되므로 현재배정 백필을 매번 반복하면 대량 중복 INSERT가 발생한다.
  // 직원별·KST 업무일자별 최초 1회만 백필하고, 이후 신규 배정은 Realtime 이벤트 알림이 담당한다.
  const backfillDone = await client.query(
    `select 1
       from public.nova_app_notification_backfill_state
      where employee_no=$1
        and business_date=${kstTodaySql}
      limit 1`,
    [employeeNo]
  );
  if (backfillDone.rowCount) return 0;

  const backfillClaim = await client.query(
    `insert into public.nova_app_notification_backfill_state(employee_no,business_date,completed_at)
     values($1,${kstTodaySql},now())
     on conflict(employee_no,business_date) do nothing
     returning employee_no`,
    [employeeNo]
  );
  if (!backfillClaim.rowCount) return 0;

  if (role === 'HOUSEMAN') {
"""
if fn_new not in text:
    if fn_anchor not in text:
        raise SystemExit('notification backfill function anchor not found')
    text = text.replace(fn_anchor, fn_new, 1)

# 3) Clear only notifications; keep backfill state so current assignments are not recreated on next 5-second poll.
clear_marker = "'/v1/notifications/clear'"
clear_pos = text.find(clear_marker)
if clear_pos < 0:
    raise SystemExit('notification clear route not found')
clear_slice = text[clear_pos:clear_pos + 5000]
if 'nova_app_notification_backfill_state' in clear_slice:
    raise SystemExit('clear route must not delete backfill state')

# Validation
for token in [
    'create table if not exists public.nova_app_notification_backfill_state',
    'primary key(employee_no, business_date)',
    'if (backfillDone.rowCount) return 0;',
    'if (!backfillClaim.rowCount) return 0;',
    '신규 배정은 Realtime 이벤트 알림이 담당한다.'
]:
    if token not in text:
        raise SystemExit(f'v95 validation failed: {token}')

PATH.write_text(text, encoding='utf-8')
print('NOTIFICATION_BACKFILL_ONCE_DAILY_V95_OK')
