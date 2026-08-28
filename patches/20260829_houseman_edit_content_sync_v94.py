from pathlib import Path

CLIENT = Path('Client.html')
CLOUD = Path('cloudrun/index.js')
client = CLIENT.read_text(encoding='utf-8')
cloud = CLOUD.read_text(encoding='utf-8')

# Cloud Run: content-only admin sync route. Never touches assignment/status/timestamps of processing state.
cancel_anchor = """/**
 * 관리자/오더테이커 하우스맨 등록취소 Realtime 확정.
 * 접수/처리 시작 전 REGISTERED/ASSIGNED 오더만 PostgreSQL에서 제거한다.
 * Sheet는 Apps Script의 deleteMonthlyHousemanOrder가 감사이력과 함께 소프트삭제한다.
 */
app.post(
  '/v1/houseman-orders/:orderId/cancel',"""
route = r'''/**
 * ADMIN/ORDER 하우스맨 오더 내용 동기화.
 * 기존 Apps Script EDIT 검증/감사를 원본으로 유지하고, 확정된 표시내용만 DB에 반영한다.
 * 처리상태·배정·처리자·접수/시작/완료 시각은 절대 변경하지 않는다.
 */
app.post(
  '/v1/houseman-orders/:orderId/content-sync',
  async (req, res, next) => {
    const startedAt = Date.now();
    let db;
    try {
      db = await pool.connect();
      const auth = authBearer(req);
      const body = req.body || {};
      const orderId = cleanText_(req.params.orderId, 80).toUpperCase();
      if (!/^HO-\d{8}-[A-Z0-9]{8,32}$/.test(orderId)) {
        throw httpError(400, 'INVALID_REQUEST', '오더번호가 올바르지 않습니다.');
      }
      const user = await loadUser(db, auth.employeeNo);
      if (!['ADMIN', 'ORDER'].includes(String(user.role || '').toUpperCase())) {
        throw httpError(403, 'FORBIDDEN', '오더 내용 동기화 권한이 없습니다.');
      }

      const part = cleanText_(body.part, 80);
      const items = normalizeHousemanItems_(body.items);
      const requester = cleanText_(body.requester, 120);
      const note = String(body.note || '').trim().slice(0, 4000);
      const important = body.important === true;
      const handover = body.handover === true;
      const handoverRaw = cleanText_(body.handoverTargetShift, 10).toUpperCase();
      const handoverTargetShift = handover && ['A', 'B', 'C'].includes(handoverRaw) ? handoverRaw : '';
      if (!part || !items.length) {
        throw httpError(400, 'INVALID_REQUEST', '파트와 품목을 확인하세요.');
      }
      const itemSummary = items.map(item => item.quantity > 1 ? `${item.name}×${item.quantity}` : item.name).join(', ');
      const quantity = items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);

      const updated = await db.query(
        `update public.nova_houseman_orders
            set part=$2,
                items=$3::jsonb,
                item_summary=$4,
                quantity=$5,
                note=$6,
                requester=$7,
                important=$8,
                handover=$9,
                handover_target_shift=$10,
                version=version+1,
                updated_at=now()
          where order_id=$1
          returning *`,
        [orderId, part, JSON.stringify(items), itemSummary, quantity, note, requester, important, handover, handoverTargetShift]
      );
      if (!updated.rowCount) {
        throw httpError(404, 'HOUSEMAN_ORDER_NOT_FOUND', 'Realtime 하우스맨 오더를 찾을 수 없습니다.');
      }
      const order = updated.rows[0];
      res.json({
        ok: true,
        action: 'HOUSEMAN_CONTENT_SYNC',
        order: housemanOrderDto_(order),
        orderVersion: Number(order.version || 0),
        timing: { totalMs: Date.now() - startedAt }
      });
    } catch (e) {
      next(e);
    } finally {
      if (db) db.release();
    }
  }
);

'''
if "'/v1/houseman-orders/:orderId/content-sync'" not in cloud:
    if cancel_anchor not in cloud:
        raise SystemExit('content sync insertion anchor not found')
    cloud = cloud.replace(cancel_anchor, route + cancel_anchor, 1)

# Client helper before clear-assignment helper area.
helper_anchor = "  async function mirrorRealtimeClearAssignmentToSheet_(payload) { // (DB 배정초기화 성공 후 이력/Sheet 보조 미러)"
helper = r'''  async function syncRealtimeHousemanEditedContent_(order, attempt = 0) { // (EDIT 확정내용만 DB 보조동기화)
    if (!novaRealtimeIsEnabled_() || !order?.orderId) return null;
    const safe = {
      part: String(order.part || ''),
      items: Array.isArray(order.items) ? order.items : [],
      requester: String(order.requester || ''),
      note: String(order.note || ''),
      important: order.important === true,
      handover: order.handover === true,
      handoverTargetShift: String(order.handoverTargetShift || '')
    };
    try {
      return await novaRealtimeFetch_(
        `/v1/houseman-orders/${encodeURIComponent(String(order.orderId))}/content-sync`,
        { method: 'POST', body: JSON.stringify(safe) }
      );
    } catch (error) {
      const code = String(error?.code || '').trim().toUpperCase();
      if (Number(error?.status || 0) === 404 || code === 'HOUSEMAN_ORDER_NOT_FOUND') return null;
      if (attempt >= 2) {
        console.warn('[NOVA Realtime] 하우스맨 내용 DB 동기화 실패', error?.message || error);
        return null;
      }
      await novaRealtimeSleep_([700, 1800, 4000][attempt] || 1800);
      return syncRealtimeHousemanEditedContent_(order, attempt + 1);
    }
  }

'''
if 'async function syncRealtimeHousemanEditedContent_(' not in client:
    if helper_anchor not in client:
        raise SystemExit('client content helper anchor not found')
    client = client.replace(helper_anchor, helper + helper_anchor, 1)

# Inject after EDIT legacy save succeeds. Scope to saveOrderEdit handler.
edit_marker = "$('saveOrderEdit').addEventListener('click', async () => {"
edit_start = client.find(edit_marker)
if edit_start < 0:
    raise SystemExit('saveOrderEdit handler not found')
edit_end = client.find("\n  }\n", edit_start)
if edit_end < 0:
    raise SystemExit('saveOrderEdit handler end not found')
edit_block = client[edit_start:edit_end]
old_success = """        upsertOrderLocal_(result.order, result.version);
        closeModal();
"""
new_success = """        upsertOrderLocal_(result.order, result.version);
        // Apps Script EDIT가 확정한 동일 내용을 DB 표시자료에만 반영한다.
        // 상태/배정 필드는 content-sync가 건드리지 않으므로 진행중 오더와 충돌하지 않는다.
        void syncRealtimeHousemanEditedContent_(result.order);
        closeModal();
"""
if new_success not in edit_block:
    if old_success not in edit_block:
        raise SystemExit('EDIT success anchor not found')
    edit_block = edit_block.replace(old_success, new_success, 1)
    client = client[:edit_start] + edit_block + client[edit_end:]

# Self-validation
for token in [
    "'/v1/houseman-orders/:orderId/content-sync'",
    "처리상태·배정·처리자·접수/시작/완료 시각은 절대 변경하지 않는다.",
    'async function syncRealtimeHousemanEditedContent_(',
    'void syncRealtimeHousemanEditedContent_(result.order);'
]:
    if token not in cloud + client:
        raise SystemExit(f'v94 validation failed: {token}')

CLIENT.write_text(client, encoding='utf-8')
CLOUD.write_text(cloud, encoding='utf-8')
print('HOUSEMAN_EDIT_CONTENT_SYNC_V94_OK')
