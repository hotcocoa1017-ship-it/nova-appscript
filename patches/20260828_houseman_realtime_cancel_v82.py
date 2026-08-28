from pathlib import Path

path = Path('cloudrun/index.js')
text = path.read_text(encoding='utf-8')
marker = """/**
 * 미배정 하우스맨 오더 수동배정 Realtime 확정.
 * PostgreSQL 배정을 먼저 확정하고 Sheet 감사/Telegram은 Apps Script가 백그라운드 미러합니다.
 */
app.post(
  '/v1/houseman-orders/:orderId/assign',
"""
if marker not in text:
    raise SystemExit('HOUSEMAN_ASSIGN_MARKER_NOT_FOUND')

endpoint = r"""
/**
 * 관리자/오더테이커 하우스맨 등록취소 Realtime 확정.
 * 접수/처리 시작 전 REGISTERED/ASSIGNED 오더만 PostgreSQL에서 제거한다.
 * Sheet는 Apps Script의 deleteMonthlyHousemanOrder가 감사이력과 함께 소프트삭제한다.
 */
app.post(
  '/v1/houseman-orders/:orderId/cancel',
  async (req, res, next) => {
    const startedAt = Date.now();
    let client;

    try {
      client = await pool.connect();
      const auth = authBearer(req);
      const body = req.body || {};
      const orderId = cleanText_(req.params.orderId, 80).toUpperCase();
      const requestId = cleanText_(
        body.requestId || req.headers['x-request-id'],
        200
      );

      if (!/^HO-\d{8}-[A-Z0-9]{8,32}$/.test(orderId) || !requestId) {
        throw httpError(
          400,
          'INVALID_REQUEST',
          '오더번호와 requestId가 필요합니다.'
        );
      }

      await client.query('begin');
      const user = await loadUser(client, auth.employeeNo);
      if (!['ADMIN', 'ORDER'].includes(String(user.role || '').toUpperCase())) {
        throw httpError(403, 'FORBIDDEN', '오더 등록취소 권한이 없습니다.');
      }

      const dedup = await client.query(
        `insert into public.nova_request_dedup(request_id,employee_no,action)
         values($1,$2,'HOUSEMAN_CANCEL')
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
        throw httpError(409, 'REQUEST_IN_PROGRESS', '동일 등록취소 요청이 처리 중입니다.');
      }

      const found = await client.query(
        `select * from public.nova_houseman_orders where order_id=$1 for update`,
        [orderId]
      );
      const order = found.rows[0] || null;

      if (!order) {
        const response = {
          ok: true,
          action: 'HOUSEMAN_CANCEL',
          requestId,
          orderId,
          idempotent: true,
          deleted: true,
          timing: { totalMs: Date.now() - startedAt }
        };
        await client.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await client.query('commit');
        return res.json(response);
      }

      if (!allowedForSite(user, String(order.site || ''))) {
        throw httpError(403, 'FORBIDDEN', '해당 사업장 처리 권한이 없습니다.');
      }

      const statusCode = String(order.status_code || '').trim().toUpperCase();
      const acceptedAt = order.accepted_at || null;
      const startedAtValue = order.started_at || null;
      if (!['REGISTERED', 'ASSIGNED'].includes(statusCode) || acceptedAt || startedAtValue) {
        throw httpError(
          409,
          'HOUSEMAN_ORDER_STATE_CONFLICT',
          '이미 접수 또는 처리가 시작된 오더는 등록취소할 수 없습니다.'
        );
      }

      await client.query(
        `delete from public.nova_houseman_orders where order_id=$1`,
        [orderId]
      );

      const response = {
        ok: true,
        action: 'HOUSEMAN_CANCEL',
        requestId,
        orderId,
        deleted: true,
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


"""
text = text.replace(marker, endpoint + marker, 1)
path.write_text(text, encoding='utf-8')

check = path.read_text(encoding='utf-8')
required = [
    "'/v1/houseman-orders/:orderId/cancel'",
    "'HOUSEMAN_CANCEL'",
    "delete from public.nova_houseman_orders where order_id=$1",
    "이미 접수 또는 처리가 시작된 오더는 등록취소할 수 없습니다."
]
for token in required:
    if token not in check:
        raise SystemExit(f'V82_VALIDATION_MISSING:{token}')
print('HOUSEMAN_REALTIME_CANCEL_V82_OK')
