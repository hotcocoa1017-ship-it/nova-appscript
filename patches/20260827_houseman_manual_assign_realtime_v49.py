from pathlib import Path

CLIENT = Path('Client.html')
CLOUDRUN = Path('cloudrun/index.js')

client = CLIENT.read_text(encoding='utf-8')
cloudrun = CLOUDRUN.read_text(encoding='utf-8')

old_build = "const NOVA_REALTIME_BUILD = 'phase1-v3.8-houseman-create';"
new_build = "const NOVA_REALTIME_BUILD = 'phase1-v3.9-houseman-manual-assign';"
if new_build not in cloudrun:
    if old_build not in cloudrun:
        raise SystemExit('Cloud Run build marker not found')
    cloudrun = cloudrun.replace(old_build, new_build, 1)

route_anchor = "\napp.post(\n  '/v1/auth/realtime-token',"
if "'/v1/houseman-orders/:orderId/assign'" not in cloudrun:
    if route_anchor not in cloudrun:
        raise SystemExit('Cloud Run houseman assignment insertion anchor not found')
    route = r'''

/**
 * 미배정 하우스맨 오더 수동배정 Realtime 확정.
 * PostgreSQL 배정을 먼저 확정하고 Sheet 감사/Telegram은 Apps Script가 백그라운드 미러합니다.
 */
app.post(
  '/v1/houseman-orders/:orderId/assign',
  async (req, res, next) => {
    const startedAt = Date.now();
    let client;

    try {
      client = await pool.connect();
      const auth = authBearer(req);
      const body = req.body || {};
      const orderId = cleanText_(req.params.orderId, 80).toUpperCase();
      const employeeNo = cleanText_(body.employeeNo, 80);
      const requestId = cleanText_(
        body.requestId || req.headers['x-request-id'],
        200
      );

      if (!/^HO-\d{8}-[A-Z0-9]{8,32}$/.test(orderId) || !employeeNo || !requestId) {
        throw httpError(
          400,
          'INVALID_REQUEST',
          '오더번호·배정직원·requestId가 필요합니다.'
        );
      }

      await client.query('begin');

      const user = await loadUser(client, auth.employeeNo);
      if (!['ADMIN', 'ORDER'].includes(String(user.role || '').toUpperCase())) {
        throw httpError(403, 'FORBIDDEN', '직원배정 권한이 없습니다.');
      }

      const dedup = await client.query(
        `insert into public.nova_request_dedup(request_id,employee_no,action)
         values($1,$2,'HOUSEMAN_ASSIGN')
         on conflict(request_id) do nothing
         returning request_id`,
        [requestId, user.employee_no]
      );

      if (!dedup.rowCount) {
        const prior = await client.query(
          `select response_json from public.nova_request_dedup where request_id=$1`,
          [requestId]
        );
        await client.query('commit');
        if (prior.rows[0]?.response_json) {
          return res.json({
            ...prior.rows[0].response_json,
            duplicateRequest: true
          });
        }
        throw httpError(409, 'REQUEST_IN_PROGRESS', '동일 배정 요청이 처리 중입니다.');
      }

      const found = await client.query(
        `select * from public.nova_houseman_orders where order_id=$1 for update`,
        [orderId]
      );
      const order = found.rows[0];
      if (!order) {
        throw httpError(404, 'HOUSEMAN_ORDER_NOT_FOUND', 'Realtime 하우스맨 오더를 찾을 수 없습니다.');
      }

      if (!allowedForSite(user, String(order.site || ''))) {
        throw httpError(403, 'FORBIDDEN', '해당 사업장 처리 권한이 없습니다.');
      }

      const staffResult = await client.query(
        `select employee_no,name,role,enabled
           from public.nova_users
          where employee_no=$1
          limit 1`,
        [employeeNo]
      );
      const assigned = staffResult.rows[0];
      if (
        !assigned
        || assigned.enabled !== true
        || String(assigned.role || '').toUpperCase() !== 'HOUSEMAN'
      ) {
        throw httpError(409, 'HOUSEMAN_NOT_AVAILABLE', '사용 가능한 하우스맨 계정이 아닙니다.');
      }

      const currentStatus = String(order.status_code || '').toUpperCase();
      const currentEmployeeNo = String(order.assigned_employee_no || '');

      if (currentStatus === 'ASSIGNED' && currentEmployeeNo === employeeNo) {
        const response = {
          ok: true,
          action: 'HOUSEMAN_ASSIGN',
          requestId,
          idempotent: true,
          order: housemanOrderDto_(order),
          orderVersion: Number(order.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
        await client.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await client.query('commit');
        return res.json(response);
      }

      if (currentStatus !== 'REGISTERED') {
        throw httpError(
          409,
          'HOUSEMAN_ORDER_STATE_CONFLICT',
          '미배정 상태의 오더만 Realtime 수동배정할 수 있습니다.'
        );
      }

      const assignedBuilding = cleanText_(
        order.assigned_building || `${String(order.room_no || '').charAt(0)}동`,
        40
      );

      const updated = await client.query(
        `update public.nova_houseman_orders
            set assigned_employee_no=$2,
                assigned_name=$3,
                status_code='ASSIGNED',
                assignment_mode='MANUAL',
                auto_assigned=false,
                assigned_building=$4,
                assigned_shift_code='',
                assigned_shift_codes='{}'::text[],
                route_candidate_employee_nos=$5::text[],
                route_candidate_names=$6::text[],
                route_locked=true,
                version=version+1,
                updated_at=now()
          where order_id=$1
          returning *`,
        [
          orderId,
          employeeNo,
          String(assigned.name || employeeNo),
          assignedBuilding,
          [employeeNo],
          [String(assigned.name || employeeNo)]
        ]
      );

      const nextOrder = updated.rows[0];
      const response = {
        ok: true,
        action: 'HOUSEMAN_ASSIGN',
        requestId,
        order: housemanOrderDto_(nextOrder),
        orderVersion: Number(nextOrder.version || 0),
        timing: { totalMs: Date.now() - startedAt }
      };

      await client.query(
        `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
        [requestId, JSON.stringify(response)]
      );
      await client.query('commit');
      return res.json(response);

    } catch (e) {
      if (client) {
        try { await client.query('rollback'); } catch {}
      }
      next(e);
    } finally {
      if (client) client.release();
    }
  }
);
'''
    cloudrun = cloudrun.replace(route_anchor, route + route_anchor, 1)

helper_anchor = "\n  async function mirrorRealtimeHousemanOrderToSheet_("
if 'async function novaRealtimeAssignHousemanOrder_(' not in client:
    if helper_anchor not in client:
        raise SystemExit('Client realtime helper insertion anchor not found')
    helpers = r'''

  async function novaRealtimeAssignHousemanOrder_(order, employeeNo) { // (미배정 하우스맨 오더 Realtime 수동배정)
    if (!novaRealtimeIsEnabled_()) throw new Error('Realtime이 비활성화되어 있습니다.');
    const orderId = String(order?.orderId || '').trim();
    const assignedEmployeeNo = String(employeeNo || '').trim();
    if (!orderId || !assignedEmployeeNo) throw new Error('배정할 오더와 직원을 확인하세요.');

    const requestId = novaRealtimeRequestId_('houseman-assign');
    const result = await novaRealtimeFetch_(
      `/v1/houseman-orders/${encodeURIComponent(orderId)}/assign`,
      {
        method: 'POST',
        headers: { 'X-Request-Id': requestId },
        body: JSON.stringify({
          employeeNo: assignedEmployeeNo,
          requestId
        })
      }
    );

    const mapped = novaRealtimeMapHousemanOrder_(result.order) || result.order;
    return {
      ok: true,
      order: mapped,
      orderVersion: Number(result.orderVersion || result.order?.version || 0),
      timing: result.timing || {},
      requestId
    };
  }

  async function mirrorRealtimeHousemanAssignmentToSheet_(sourceOrder, employeeNo) { // (Realtime 수동배정 Sheet·감사·Telegram 백그라운드 미러)
    const payload = {
      orderId: String(sourceOrder?.orderId || '').trim(),
      action: 'ASSIGN',
      expectedVersion: Number(sourceOrder?.version || 0),
      rowNumber: Number(sourceOrder?.rowNumber || 0),
      employeeNo: String(employeeNo || '').trim()
    };

    try {
      const mirror = await callServer('assignHousemanOrderFast', state.token, payload);
      if (!mirror?.ok) throw new Error(mirror?.message || '수동배정 이력 동기화에 실패했습니다.');
      upsertOrderLocal_(mirror.order, mirror.version);

      const aux = await callServer('finalizeHousemanAssignmentAux', state.token, {
        orderId: mirror.order.orderId,
        employeeNo: mirror.order.assignedEmployeeNo,
        rowNumber: Number(mirror.order.rowNumber || 0),
        version: Number(mirror.version || mirror.order.version || 0)
      });
      const telegram = aux?.telegram || {};
      if (telegram.queued && telegram.queueRecordId) {
        void callServer('dispatchHousemanOrderTelegramFast', state.token, {
          recordId: telegram.queueRecordId,
          rowNumber: Number(telegram.queueRowNumber || 0)
        }).catch(error => {
          console.warn('Realtime 수동배정 텔레그램 즉시발송은 큐 재시도로 전환됩니다.', error?.message || error);
        });
      }
      setSyncStatus(`${mirror.order.roomNo}호 배정 이력 동기화 완료`);
    } catch (error) {
      console.warn('Realtime 수동배정 Sheet 미러 실패', error?.message || error);
      setSyncStatus(`${sourceOrder?.roomNo || ''}호 Realtime 배정 완료 · 기존 이력 동기화 재확인 필요`);
    }
  }
'''
    client = client.replace(helper_anchor, helpers + helper_anchor, 1)

old_action_start = r'''    const actionStartedAt = performance.now();
    try {
      const result = action === 'ASSIGN'
        ? await callServer('assignHousemanOrderFast', state.token, payload)
        : await callServer('updateHousemanOrder', state.token, payload);
      if (!result?.ok) throw new Error(result?.message || '오더를 변경하지 못했습니다.');
      upsertOrderLocal_(result.order, result.version);
      closeModal();

      if (action === 'ASSIGN') {'''

new_action_start = r'''    const actionStartedAt = performance.now();
    try {
      if (
        action === 'ASSIGN'
        && String(order?.statusCode || '').trim().toUpperCase() === 'REGISTERED'
        && novaRealtimeIsEnabled_()
      ) {
        try {
          const realtime = await novaRealtimeAssignHousemanOrder_(order, payload.employeeNo);
          const elapsed = Math.round(performance.now() - actionStartedAt);
          const serverElapsed = Number(realtime.timing?.totalMs || 0);
          const pendingOrder = Object.assign({}, realtime.order, {
            rowNumber: Number(order.rowNumber || 0),
            version: Number(order.version || 0),
            __sheetMirrorPending: true,
            __sheetMirrorStartedAt: Date.now()
          });
          upsertOrderLocal_(pendingOrder, state.indicator.version);
          closeModal();
          showToast(`${pendingOrder.roomNo}호 배정 완료 · Realtime ${elapsed}ms${serverElapsed ? ` · 서버 ${serverElapsed}ms` : ''}`);
          setSyncStatus(`하우스맨 배정 DB 확정 · ${elapsed}ms${serverElapsed ? ` · 서버 ${serverElapsed}ms` : ''}`);
          void mirrorRealtimeHousemanAssignmentToSheet_(order, payload.employeeNo);
          return;
        } catch (realtimeError) {
          console.warn('[NOVA Realtime] 미배정 수동배정은 기존 저장경로로 자동 전환합니다.', realtimeError?.message || realtimeError);
        }
      }

      const result = action === 'ASSIGN'
        ? await callServer('assignHousemanOrderFast', state.token, payload)
        : await callServer('updateHousemanOrder', state.token, payload);
      if (!result?.ok) throw new Error(result?.message || '오더를 변경하지 못했습니다.');
      upsertOrderLocal_(result.order, result.version);
      closeModal();

      if (action === 'ASSIGN') {'''

if new_action_start not in client:
    if old_action_start not in client:
        raise SystemExit('Client runOrderAction realtime replacement anchor not found')
    client = client.replace(old_action_start, new_action_start, 1)

CLIENT.write_text(client, encoding='utf-8')
CLOUDRUN.write_text(cloudrun, encoding='utf-8')
print('Applied Realtime manual houseman assignment with Apps Script background mirror')
