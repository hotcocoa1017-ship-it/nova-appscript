from pathlib import Path

path = Path('cloudrun/index.js')
text = path.read_text(encoding='utf-8')

old = """  // Phase 1의 ROOMMAID/QM 객실 접근권한은 '기본사업장'이 아니라
  // 실제 객실 배정정보로 판정합니다.
  if (['ROOMMAID', 'QM'].includes(user.role)) {
    return Boolean(String(site || '').trim());
  }
"""
new = """  // ROOMMAID/QM/HOUSEMAN의 업무 접근은 기본사업장 문자열이 아니라
  // 실제 본인 배정정보로 최종 판정합니다. HOUSEMAN 오더 조회도 SQL에서
  // 본인 배정/처리/공동후보만 반환하므로 여기서 default_site로 중복 차단하지 않습니다.
  if (['ROOMMAID', 'QM', 'HOUSEMAN'].includes(user.role)) {
    return Boolean(String(site || '').trim());
  }
"""
if old not in text:
    raise SystemExit('allowedForSite target not found')
text = text.replace(old, new, 1)

anchor = """function appNotificationDto_(row) {
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
insert = anchor + r'''

/**
 * 알림 기능 도입 직전 또는 legacy 미러 경로에서 이미 확정된 현재 배정을
 * 개인 참고 알림으로 1회 보완한다. 업무이력에는 쓰지 않으며 stable eventKey로
 * 같은 현재 배정을 반복 조회해도 중복 생성되지 않는다.
 */
async function ensureCurrentAppNotificationBackfill_(client, user) {
  const role = String(user?.role || '').trim().toUpperCase();
  const employeeNo = String(user?.employee_no || '').trim();
  if (!employeeNo || !appNotificationRoleAllowed_(role)) return 0;

  let inserted = 0;
  const kstTodaySql = `(now() at time zone 'Asia/Seoul')::date`;

  if (role === 'HOUSEMAN') {
    const { rows } = await client.query(
      `select *
         from public.nova_houseman_orders
        where business_date=${kstTodaySql}
          and upper(coalesce(status_code,'')) not in ('COMPLETED','CANCELLED','DELETED')
          and (
            assigned_employee_no=$1
            or processor_employee_no=$1
            or (route_locked=false and $1=any(coalesce(route_candidate_employee_nos,'{}'::text[])))
          )
        order by updated_at desc, order_id desc
        limit 100`,
      [employeeNo]
    );
    for (const order of rows) {
      const orderId = String(order.order_id || '');
      if (!orderId) continue;
      if (await addAppNotification_(client, {
        employeeNo,
        role: 'HOUSEMAN',
        eventKey: `HOUSEMAN_CURRENT:${orderId}:${employeeNo}`,
        notificationType: 'HOUSEMAN_ORDER',
        title: '하우스맨 오더 배정',
        message: `${String(order.site || '')} / ${String(order.room_no || '')}호 · ${String(order.part || '')} · ${String(order.item_summary || '')}`,
        businessDate: dateOnlyText_(order.business_date),
        site: String(order.site || ''),
        roomNo: String(order.room_no || '')
      })) inserted += 1;
    }
    return inserted;
  }

  if (role === 'ROOMMAID') {
    const { rows } = await client.query(
      `select business_date,site,room_no,cleaning_type,roommaid_employee_no,secondary_roommaid_employee_no
         from public.nova_rooms_current
        where business_date=${kstTodaySql}
          and ($1=roommaid_employee_no or $1=secondary_roommaid_employee_no)
        order by site,room_no
        limit 200`,
      [employeeNo]
    );
    for (const room of rows) {
      const cleaningType = String(room.cleaning_type || 'NORMAL').trim().toUpperCase();
      const roomNo = String(room.room_no || '');
      const site = String(room.site || '');
      if (!roomNo || !site) continue;
      if (await addAppNotification_(client, {
        employeeNo,
        role: 'ROOMMAID',
        eventKey: `ROOMMAID_CURRENT:${dateOnlyText_(room.business_date)}:${site}:${roomNo}:${employeeNo}:${cleaningType}`,
        notificationType: cleaningType === 'DS' ? 'ROOMMAID_DS_ASSIGNMENT' : 'ROOMMAID_ASSIGNMENT',
        title: cleaningType === 'DS' ? 'D/S 객실 배정' : '객실 배정',
        message: `${site} / ${roomNo}호 · ${roommaidCleaningTypeAppLabel_(cleaningType)}`,
        businessDate: dateOnlyText_(room.business_date),
        site,
        roomNo
      })) inserted += 1;
    }
    return inserted;
  }

  if (role === 'QM') {
    const { rows } = await client.query(
      `select business_date,site,room_no,qm_employee_no
         from public.nova_rooms_current
        where business_date=${kstTodaySql}
          and qm_employee_no=$1
        order by site,room_no
        limit 200`,
      [employeeNo]
    );
    for (const room of rows) {
      const roomNo = String(room.room_no || '');
      const site = String(room.site || '');
      if (!roomNo || !site) continue;
      if (await addAppNotification_(client, {
        employeeNo,
        role: 'QM',
        eventKey: `QM_CURRENT:${dateOnlyText_(room.business_date)}:${site}:${roomNo}:${employeeNo}`,
        notificationType: 'QM_ASSIGNMENT',
        title: 'QM 점검객실 배정',
        message: `${site} / ${roomNo}호`,
        businessDate: dateOnlyText_(room.business_date),
        site,
        roomNo
      })) inserted += 1;
    }
  }
  return inserted;
}
'''
if anchor not in text:
    raise SystemExit('notification dto anchor not found')
text = text.replace(anchor, insert, 1)

old = """      const limit = Math.max(1, Math.min(200, Number(req.query.limit || 100)));
      const employeeNo = String(user.employee_no || '');
      const [listResult, countResult] = await Promise.all([
"""
new = """      const limit = Math.max(1, Math.min(200, Number(req.query.limit || 100)));
      const employeeNo = String(user.employee_no || '');
      // 신규 이벤트 훅 이전/legacy 확정분도 현재 배정 기준으로 1회 보완합니다.
      await ensureCurrentAppNotificationBackfill_(client, user);
      const [listResult, countResult] = await Promise.all([
"""
if old not in text:
    raise SystemExit('notification GET anchor not found')
text = text.replace(old, new, 1)

checks = [
    "['ROOMMAID', 'QM', 'HOUSEMAN'].includes(user.role)",
    'async function ensureCurrentAppNotificationBackfill_(client, user)',
    'HOUSEMAN_CURRENT:',
    'ROOMMAID_CURRENT:',
    'QM_CURRENT:',
    'await ensureCurrentAppNotificationBackfill_(client, user);'
]
for marker in checks:
    if marker not in text:
        raise SystemExit(f'missing marker: {marker}')

path.write_text(text, encoding='utf-8')
print('NOTIFICATION_BACKFILL_HOUSEMAN_SITE_V90_OK')
