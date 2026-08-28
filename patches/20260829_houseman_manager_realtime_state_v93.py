from pathlib import Path

CLIENT = Path('Client.html')
CLOUD = Path('cloudrun/index.js')
client = CLIENT.read_text(encoding='utf-8')
cloud = CLOUD.read_text(encoding='utf-8')

# ---- Cloud Run: extend existing HOUSEMAN action route to ADMIN/ORDER state actions ----
route_start = cloud.find("app.post(\n  '/v1/houseman-orders/:orderId/action',")
if route_start < 0:
    raise SystemExit('houseman action route not found')
route_end = cloud.find("\n/**\n * 관리자/오더테이커 하우스맨 등록취소 Realtime 확정.", route_start)
if route_end < 0:
    raise SystemExit('houseman action route end not found')
route = cloud[route_start:route_end]

route = route.replace(
    "if (!['ACCEPT', 'ACCEPT_START', 'START', 'COMPLETE', 'UNABLE'].includes(action)) {",
    "if (!['ACCEPT', 'ACCEPT_START', 'START', 'COMPLETE', 'UNABLE', 'REOPEN'].includes(action)) {",
    1
)

old_role = """      const user = await loadUser(db, auth.employeeNo);
      if (String(user.role || '').toUpperCase() !== 'HOUSEMAN') {
        throw httpError(403, 'FORBIDDEN', '하우스맨 처리 권한이 없습니다.');
      }
"""
new_role = """      const user = await loadUser(db, auth.employeeNo);
      const role = String(user.role || '').toUpperCase();
      const isManager = ['ADMIN', 'ORDER'].includes(role);
      if (role !== 'HOUSEMAN' && !isManager) {
        throw httpError(403, 'FORBIDDEN', '하우스맨 처리 권한이 없습니다.');
      }
"""
if new_role not in route:
    if old_role not in route:
        raise SystemExit('houseman action role guard not found')
    route = route.replace(old_role, new_role, 1)

manager_anchor = """      const sharedClaimable = status === 'ASSIGNED'
        && current.route_locked === false
        && candidates.includes(employeeNo);
      const assignedToMe = assignedEmployeeNo === employeeNo;
      const processingByMe = processorEmployeeNo === employeeNo;

      if (['ACCEPT', 'ACCEPT_START'].includes(action)) {
"""
manager_block = """      const sharedClaimable = status === 'ASSIGNED'
        && current.route_locked === false
        && candidates.includes(employeeNo);
      const assignedToMe = assignedEmployeeNo === employeeNo;
      const processingByMe = processorEmployeeNo === employeeNo;

      // ADMIN/ORDER는 기존 NOVA의 관리자 상태변경 자유도를 유지하되 DB를 먼저 확정한다.
      // 공동전달 오더의 접수만 기존과 동일하게 하우스맨 본인이 하도록 제한한다.
      if (isManager) {
        if (action === 'ACCEPT' || action === 'ACCEPT_START') {
          if (status !== 'ASSIGNED') {
            throw httpError(409, 'HOUSEMAN_ORDER_STATE_CONFLICT', '배정 상태의 오더만 접수할 수 있습니다.');
          }
          if (current.route_locked === false && candidates.length > 1) {
            throw httpError(409, 'HOUSEMAN_SHARED_ACCEPT_REQUIRED', '공동 전달 오더는 하우스맨이 직접 접수해야 합니다.');
          }
        }
        if (action === 'REOPEN' && !['COMPLETED', 'UNABLE'].includes(status)) {
          throw httpError(409, 'HOUSEMAN_ORDER_STATE_CONFLICT', '완료 또는 처리불가 오더만 다시 열 수 있습니다.');
        }

        const managerTarget = action === 'ACCEPT' ? 'ACCEPTED'
          : (action === 'ACCEPT_START' || action === 'START') ? 'PROCESSING'
          : action === 'COMPLETE' ? 'COMPLETED'
          : action === 'UNABLE' ? 'UNABLE'
          : (assignedEmployeeNo ? 'ASSIGNED' : 'REGISTERED');

        if (status === managerTarget && action !== 'REOPEN') {
          const response = {
            ok: true, action, requestId, idempotent: true,
            order: housemanOrderDto_(current), orderVersion: Number(current.version || 0),
            timing: { totalMs: Date.now() - startedAt }
          };
          await db.query(
            `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
            [requestId, JSON.stringify(response)]
          );
          await db.query('commit');
          return res.json(response);
        }

        const managerUpdated = await db.query(
          `update public.nova_houseman_orders
              set status_code=$2,
                  processor_employee_no=case when $3='REOPEN' then processor_employee_no else $4 end,
                  processor_name=case when $3='REOPEN' then processor_name else $5 end,
                  accepted_at=case when $3 in ('ACCEPT','ACCEPT_START') then coalesce(accepted_at,now()) else accepted_at end,
                  started_at=case when $3 in ('ACCEPT_START','START') then now() else started_at end,
                  completed_at=case when $3 in ('COMPLETE','UNABLE') then now() when $3='REOPEN' then null else completed_at end,
                  unable_reason=case when $3='UNABLE' then $6 when $3 in ('COMPLETE','REOPEN') then '' else unable_reason end,
                  version=version+1,
                  updated_at=now()
            where order_id=$1
            returning *`,
          [orderId, managerTarget, action, employeeNo, String(user.name || employeeNo), reason]
        );
        const managerOrder = managerUpdated.rows[0];
        const response = {
          ok: true, action, requestId,
          order: housemanOrderDto_(managerOrder), orderVersion: Number(managerOrder.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
        await db.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await db.query('commit');
        return res.json(response);
      }

      if (action === 'REOPEN') {
        throw httpError(403, 'FORBIDDEN', '오더 다시 열기는 관리자만 가능합니다.');
      }

      if (['ACCEPT', 'ACCEPT_START'].includes(action)) {
"""
if manager_block not in route:
    if manager_anchor not in route:
        raise SystemExit('manager action insertion anchor not found')
    route = route.replace(manager_anchor, manager_block, 1)

cloud = cloud[:route_start] + route + cloud[route_end:]

# ---- Client helper accepts REOPEN too ----
helper_old = "if (!orderId || !['ACCEPT', 'ACCEPT_START', 'START', 'COMPLETE', 'UNABLE'].includes(action)) {"
helper_new = "if (!orderId || !['ACCEPT', 'ACCEPT_START', 'START', 'COMPLETE', 'UNABLE', 'REOPEN'].includes(action)) {"
if helper_new not in client:
    if helper_old not in client:
        raise SystemExit('client houseman action helper validation not found')
    client = client.replace(helper_old, helper_new, 1)

# ---- ADMIN/ORDER runOrderAction: DB first, Sheet mirror async ----
legacy_anchor = """      const result = action === 'ASSIGN'
        ? await callServer('assignHousemanOrderFast', state.token, payload)
        : await callServer('updateHousemanOrder', state.token, payload);
"""
manager_client = """      const managerRole = String(state.bootstrap?.user?.role || '').trim().toUpperCase();
      if (
        action !== 'ASSIGN'
        && ['ADMIN', 'ORDER'].includes(managerRole)
        && ['ACCEPT', 'START', 'COMPLETE', 'UNABLE', 'REOPEN'].includes(action)
        && novaRealtimeIsEnabled_()
      ) {
        try {
          const realtime = await novaRealtimeHousemanWorkerAction_(payload);
          upsertOrderLocal_(realtime.order, state.indicator.version);
          closeModal();
          const elapsed = Math.round(performance.now() - actionStartedAt);
          showToast(action === 'REOPEN' ? '오더를 다시 열었습니다.' : `${realtime.order?.roomNo || order.roomNo}호 ${housemanActionMessage_(action)}`);
          setSyncStatus(`하우스맨 관리자 DB 확정 · ${elapsed}ms`);
          return;
        } catch (realtimeError) {
          const code = String(realtimeError?.code || '').trim().toUpperCase();
          if (Number(realtimeError?.status || 0) !== 404 && code !== 'HOUSEMAN_ORDER_NOT_FOUND') throw realtimeError;
          console.warn('[NOVA Realtime] DB 미존재 관리자 하우스맨 오더는 기존 저장경로로 처리합니다.', realtimeError?.message || realtimeError);
        }
      }

      const result = action === 'ASSIGN'
        ? await callServer('assignHousemanOrderFast', state.token, payload)
        : await callServer('updateHousemanOrder', state.token, payload);
"""
if manager_client not in client:
    if legacy_anchor not in client:
        raise SystemExit('runOrderAction legacy anchor not found')
    client = client.replace(legacy_anchor, manager_client, 1)

# Self-validation
cloud_route = cloud[cloud.find("app.post(\n  '/v1/houseman-orders/:orderId/action',"):cloud.find("\n/**\n * 관리자/오더테이커 하우스맨 등록취소 Realtime 확정.", cloud.find("app.post(\n  '/v1/houseman-orders/:orderId/action',"))]
checks = [
    "const isManager = ['ADMIN', 'ORDER'].includes(role);",
    "if (isManager) {",
    "action === 'REOPEN'",
    "공동 전달 오더는 하우스맨이 직접 접수해야 합니다.",
    "오더 다시 열기는 관리자만 가능합니다.",
]
for token in checks:
    if token not in cloud_route:
        raise SystemExit(f'cloud manager realtime validation failed: {token}')
for token in [
    "['ACCEPT', 'START', 'COMPLETE', 'UNABLE', 'REOPEN'].includes(action)",
    "하우스맨 관리자 DB 확정",
]:
    if token not in client:
        raise SystemExit(f'client manager realtime validation failed: {token}')

CLIENT.write_text(client, encoding='utf-8')
CLOUD.write_text(cloud, encoding='utf-8')
print('HOUSEMAN_MANAGER_REALTIME_STATE_V93_OK')
