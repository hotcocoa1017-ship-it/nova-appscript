from pathlib import Path

path = Path('cloudrun/index.js')
text = path.read_text(encoding='utf-8')

anchor = """const pool = new Pool(poolConfig);
let ROOM_EVENTS_CURSOR_SCHEMA_READY = false;
"""
insert = r"""const pool = new Pool(poolConfig);
let ROOM_EVENTS_CURSOR_SCHEMA_READY = false;
let APP_NOTIFICATIONS_SCHEMA_READY = false;

async function ensureAppNotificationsSchema_() {
  const client = await pool.connect();
  try {
    await client.query(`
      create table if not exists public.nova_app_notifications(
        notification_id bigserial primary key,
        employee_no text not null,
        event_key text not null,
        notification_type text not null,
        title text not null,
        message text not null default '',
        business_date date,
        site text,
        room_no text,
        created_at timestamptz not null default now(),
        unique(employee_no, event_key)
      )
    `);
    await client.query(`
      create index if not exists idx_nova_app_notifications_employee_created
      on public.nova_app_notifications(employee_no, created_at desc, notification_id desc)
    `);
    // 개인 참고용 알림은 장기 업무이력이 아니므로 오래된 레코드는 자동 정리한다.
    await client.query(`
      delete from public.nova_app_notifications
      where created_at < now() - interval '90 days'
    `);
    APP_NOTIFICATIONS_SCHEMA_READY = true;
    console.log('[NOVA Realtime] app notification schema ready');
  } finally {
    client.release();
  }
}

function appNotificationRoleAllowed_(role) {
  return ['HOUSEMAN', 'ROOMMAID', 'QM'].includes(String(role || '').trim().toUpperCase());
}

function roommaidCleaningTypeAppLabel_(value) {
  const code = String(value || '').trim().toUpperCase();
  const labels = {
    NORMAL: '일반정비',
    DS: 'D/S',
    '5S': '5S',
    EVALUATION: '평가원',
    STAFF_DORM: '직원숙소',
    DEEP_CLEANING: '딥크리닝'
  };
  return labels[code] || code || '정비';
}

async function addAppNotification_(client, payload) {
  const safe = payload || {};
  const employeeNo = cleanText_(safe.employeeNo, 80);
  const role = cleanText_(safe.role, 20).toUpperCase();
  const eventKey = cleanText_(safe.eventKey, 240);
  const notificationType = cleanText_(safe.notificationType, 80);
  const title = cleanText_(safe.title, 160);
  const message = String(safe.message || '').trim().slice(0, 2000);
  const businessDate = cleanText_(safe.businessDate, 20);
  const site = cleanText_(safe.site, 80);
  const roomNo = cleanText_(safe.roomNo, 40);

  if (!employeeNo || !eventKey || !notificationType || !title || !appNotificationRoleAllowed_(role)) {
    return false;
  }

  const result = await client.query(
    `insert into public.nova_app_notifications(
       employee_no,event_key,notification_type,title,message,business_date,site,room_no
     ) values($1,$2,$3,$4,$5,nullif($6,'')::date,nullif($7,''),nullif($8,''))
     on conflict(employee_no,event_key) do nothing`,
    [employeeNo, eventKey, notificationType, title, message, businessDate, site, roomNo]
  );
  return Number(result.rowCount || 0) > 0;
}

async function addAppNotifications_(client, employeeNos, payload) {
  const unique = Array.from(new Set(
    (Array.isArray(employeeNos) ? employeeNos : [employeeNos])
      .map(value => cleanText_(value, 80))
      .filter(Boolean)
  ));
  let inserted = 0;
  for (const employeeNo of unique) {
    if (await addAppNotification_(client, { ...(payload || {}), employeeNo })) inserted += 1;
  }
  return inserted;
}

function appNotificationDto_(row) {
  return {
    id: Number(row?.notification_id || 0),
    type: String(row?.notification_type || ''),
    title: String(row?.title || ''),
    message: String(row?.message || ''),
    businessDate: dateOnlyText_(row?.business_date),
    site: String(row?.site || ''),
    roomNo: String(row?.room_no || ''),
    createdAt: koreaDateTimeText_(row?.created_at)
  };
}
"""
if anchor not in text:
    raise SystemExit('pool anchor not found')
text = text.replace(anchor, insert, 1)

rooms_anchor = """app.get(
  '/v1/rooms',
"""
notification_endpoints = r"""/**
 * HOUSEMAN / ROOMMAID / QM 개인 참고용 앱 알림.
 * 업무이력과 완전히 분리하며, 본인 알림만 조회/전체삭제할 수 있다.
 */
app.get(
  '/v1/notifications',
  async (req, res, next) => {
    let client;
    try {
      client = await pool.connect();
      const auth = authBearer(req);
      const user = await loadUser(client, auth.employeeNo);
      if (!appNotificationRoleAllowed_(user.role)) {
        throw httpError(403, 'FORBIDDEN', '앱 알림 조회 대상 계정이 아닙니다.');
      }
      const limit = Math.max(1, Math.min(200, Number(req.query.limit || 100)));
      const employeeNo = String(user.employee_no || '');
      const [listResult, countResult] = await Promise.all([
        client.query(
          `select * from public.nova_app_notifications
           where employee_no=$1
           order by created_at desc, notification_id desc
           limit $2`,
          [employeeNo, limit]
        ),
        client.query(
          `select count(*)::int as count from public.nova_app_notifications where employee_no=$1`,
          [employeeNo]
        )
      ]);
      res.json({
        ok: true,
        count: Number(countResult.rows[0]?.count || 0),
        notifications: listResult.rows.map(appNotificationDto_),
        serverTime: new Date().toISOString()
      });
    } catch (e) {
      next(e);
    } finally {
      if (client) client.release();
    }
  }
);

app.post(
  '/v1/notifications/clear',
  async (req, res, next) => {
    let client;
    try {
      client = await pool.connect();
      const auth = authBearer(req);
      const user = await loadUser(client, auth.employeeNo);
      if (!appNotificationRoleAllowed_(user.role)) {
        throw httpError(403, 'FORBIDDEN', '앱 알림 삭제 대상 계정이 아닙니다.');
      }
      const deleted = await client.query(
        `delete from public.nova_app_notifications where employee_no=$1`,
        [String(user.employee_no || '')]
      );
      res.json({
        ok: true,
        cleared: Number(deleted.rowCount || 0),
        serverTime: new Date().toISOString()
      });
    } catch (e) {
      next(e);
    } finally {
      if (client) client.release();
    }
  }
);

app.get(
  '/v1/rooms',
"""
if rooms_anchor not in text:
    raise SystemExit('rooms endpoint anchor not found')
text = text.replace(rooms_anchor, notification_endpoints, 1)

# Roommaid assignment notification (covers new/change and D/S/other cleaning types).
old = r"""        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            'ASSIGNED',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const response = {
"""
new = r"""        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            'ASSIGNED',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const cleaningTypeLabel = roommaidCleaningTypeAppLabel_(cleaningType);
        await addAppNotifications_(client, employeeNos, {
          role: 'ROOMMAID',
          eventKey: `ROOMMAID_ASSIGN:${requestId}`,
          notificationType: cleaningType === 'DS' ? 'ROOMMAID_DS_ASSIGNMENT' : 'ROOMMAID_ASSIGNMENT',
          title: cleaningType === 'DS' ? 'D/S 객실 배정' : '객실 배정',
          message: `${site} / ${roomNo}호 · ${cleaningTypeLabel}`,
          businessDate,
          site,
          roomNo
        });

        const response = {
"""
if old not in text:
    raise SystemExit('roommaid assignment event block not found')
text = text.replace(old, new, 1)

# QM assignment notification.
old = r"""        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            'QM_WAITING',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const response = {
"""
new = r"""        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            'QM_WAITING',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        await addAppNotification_(client, {
          employeeNo: qmEmployeeNo,
          role: 'QM',
          eventKey: `QM_ASSIGN:${requestId}`,
          notificationType: 'QM_ASSIGNMENT',
          title: 'QM 점검객실 배정',
          message: `${site} / ${roomNo}호`,
          businessDate,
          site,
          roomNo
        });

        const response = {
"""
if old not in text:
    raise SystemExit('qm assignment event block not found')
text = text.replace(old, new, 1)

# QM rework -> assigned roommaid(s) notification.
old = r"""        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            target,
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const response = {
"""
new = r"""        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            target,
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        if (action === 'QM_REWORK') {
          await addAppNotifications_(client, [room.roommaid_employee_no, room.secondary_roommaid_employee_no], {
            role: 'ROOMMAID',
            eventKey: `ROOMMAID_REWORK:${requestId}`,
            notificationType: 'ROOMMAID_REWORK',
            title: '재정비 요청',
            message: `${site} / ${roomNo}호 · QM 재정비 요청`,
            businessDate,
            site,
            roomNo
          });
        }

        const response = {
"""
if old not in text:
    raise SystemExit('qm action event block not found')
text = text.replace(old, new, 1)

# Cleaning complete -> assigned QM ready notification.
old = r"""      await client.query(
        `
        insert into public.nova_room_events(
          request_id,
          business_date,
          site,
          room_no,
          action,
          before_status,
          after_status,
          employee_no,
          room_version,
          detail
        )
        values(
          $1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb
        )
        `,
        [
          requestId,
          businessDate,
          site,
          roomNo,
          action,
          before,
          target,
          user.employee_no,
          nextRoom.version,
          JSON.stringify({
            source:
              'NOVA_REALTIME',
            role:
              user.role
          })
        ]
      );

      const response = {
"""
new = r"""      await client.query(
        `
        insert into public.nova_room_events(
          request_id,
          business_date,
          site,
          room_no,
          action,
          before_status,
          after_status,
          employee_no,
          room_version,
          detail
        )
        values(
          $1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb
        )
        `,
        [
          requestId,
          businessDate,
          site,
          roomNo,
          action,
          before,
          target,
          user.employee_no,
          nextRoom.version,
          JSON.stringify({
            source:
              'NOVA_REALTIME',
            role:
              user.role
          })
        ]
      );

      if (action === 'CLEANING_COMPLETE' && String(nextRoom.qm_employee_no || '')) {
        await addAppNotification_(client, {
          employeeNo: String(nextRoom.qm_employee_no || ''),
          role: 'QM',
          eventKey: `QM_READY:${requestId}`,
          notificationType: 'QM_READY',
          title: 'QM 점검대기',
          message: `${site} / ${roomNo}호 · 룸메이드 정비완료`,
          businessDate,
          site,
          roomNo
        });
      }

      const response = {
"""
if old not in text:
    raise SystemExit('cleaning event block not found')
text = text.replace(old, new, 1)

# Houseman create/auto/manual assignment notification.
old = r"""        idempotent = true;
      }

      const response = {
"""
new = r"""        idempotent = true;
      }

      if (!idempotent) {
        const housemanTargets = orderRow.route_locked === false
          ? (Array.isArray(orderRow.route_candidate_employee_nos) ? orderRow.route_candidate_employee_nos : [])
          : [String(orderRow.assigned_employee_no || '')];
        await addAppNotifications_(client, housemanTargets, {
          role: 'HOUSEMAN',
          eventKey: `HOUSEMAN_ASSIGN:${orderId}:v${Number(orderRow.version || 0)}`,
          notificationType: 'HOUSEMAN_ORDER',
          title: '하우스맨 오더 배정',
          message: `${site} / ${roomNo}호 · ${part} · ${itemSummary}`,
          businessDate,
          site,
          roomNo
        });
      }

      const response = {
"""
if old not in text:
    raise SystemExit('houseman create response anchor not found')
text = text.replace(old, new, 1)

# Houseman manual assign notification.
old = r"""      const nextOrder = updated.rows[0];
      const response = {
"""
new = r"""      const nextOrder = updated.rows[0];
      await addAppNotification_(client, {
        employeeNo,
        role: 'HOUSEMAN',
        eventKey: `HOUSEMAN_ASSIGN:${orderId}:v${Number(nextOrder.version || 0)}`,
        notificationType: 'HOUSEMAN_ORDER',
        title: '하우스맨 오더 배정',
        message: `${String(nextOrder.site || '')} / ${String(nextOrder.room_no || '')}호 · ${String(nextOrder.part || '')} · ${String(nextOrder.item_summary || '')}`,
        businessDate: dateOnlyText_(nextOrder.business_date),
        site: String(nextOrder.site || ''),
        roomNo: String(nextOrder.room_no || '')
      });
      const response = {
"""
if old not in text:
    raise SystemExit('houseman manual assign anchor not found')
text = text.replace(old, new, 1)

# Health exposes schema readiness without changing the existing build marker expected by deployment guard.
text = text.replace(
    """      eventTimeReady:\n        ROOM_EVENTS_CURSOR_SCHEMA_READY\n""",
    """      eventTimeReady:\n        ROOM_EVENTS_CURSOR_SCHEMA_READY,\n      appNotificationsReady:\n        APP_NOTIFICATIONS_SCHEMA_READY\n""",
    2,
)

startup = """await ensureRoomEventsCursorSchema_();

app.listen(
"""
startup_new = """await ensureAppNotificationsSchema_();
await ensureRoomEventsCursorSchema_();

app.listen(
"""
if startup not in text:
    raise SystemExit('startup anchor not found')
text = text.replace(startup, startup_new, 1)

# Self-validation.
checks = [
    'create table if not exists public.nova_app_notifications',
    "'/v1/notifications'",
    "'/v1/notifications/clear'",
    'ROOMMAID_ASSIGN:${requestId}',
    'ROOMMAID_REWORK:${requestId}',
    'QM_ASSIGN:${requestId}',
    'QM_READY:${requestId}',
    'HOUSEMAN_ASSIGN:${orderId}:v${Number(orderRow.version || 0)}',
    'await ensureAppNotificationsSchema_();',
    'APP_NOTIFICATIONS_SCHEMA_READY'
]
for marker in checks:
    if marker not in text:
        raise SystemExit(f'missing marker after patch: {marker}')

path.write_text(text, encoding='utf-8')
print('PERSONAL_APP_NOTIFICATIONS_CLOUDRUN_V86_OK')
