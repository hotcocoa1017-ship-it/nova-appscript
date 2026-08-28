from pathlib import Path

client_path = Path('Client.html')
cloud_path = Path('cloudrun/index.js')
client = client_path.read_text(encoding='utf-8')
cloud = cloud_path.read_text(encoding='utf-8')

# 1) Cloud Run: allow ADMIN/ORDER to use the same date/site Houseman DB read,
# while HOUSEMAN remains restricted to own assigned/processed/shared-candidate orders.
old = r'''      if (String(user.role || '').toUpperCase() !== 'HOUSEMAN') {
        throw httpError(403, 'FORBIDDEN', '하우스맨 오더 조회 권한이 없습니다.');
      }

      const businessDate = cleanText_(req.query.businessDate, 20);
      const site = cleanText_(req.query.site || user.default_site, 80);
      if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(businessDate)) {
        throw httpError(400, 'INVALID_REQUEST', '업무일자가 필요합니다.');
      }
      if (!site) {
        throw httpError(400, 'INVALID_REQUEST', '사업장이 필요합니다.');
      }
      if (!allowedForSite(user, site)) {
        throw httpError(403, 'FORBIDDEN', '해당 사업장 조회 권한이 없습니다.');
      }

      const employeeNo = String(user.employee_no || '');
      const { rows } = await client.query(
        `select *
           from public.nova_houseman_orders
          where business_date=$1::date
            and site=$2
            and (
              assigned_employee_no=$3
              or processor_employee_no=$3
              or (
                route_locked is false
                and $3 = any(coalesce(route_candidate_employee_nos, '{}'::text[]))
              )
            )
          order by updated_at desc, order_id desc`,
        [businessDate, site, employeeNo]
      );
'''
new = r'''      const role = String(user.role || '').toUpperCase();
      if (!['HOUSEMAN', 'ADMIN', 'ORDER'].includes(role)) {
        throw httpError(403, 'FORBIDDEN', '하우스맨 오더 조회 권한이 없습니다.');
      }

      const businessDate = cleanText_(req.query.businessDate, 20);
      const site = cleanText_(req.query.site || user.default_site, 80);
      if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(businessDate)) {
        throw httpError(400, 'INVALID_REQUEST', '업무일자가 필요합니다.');
      }
      if (!site) {
        throw httpError(400, 'INVALID_REQUEST', '사업장이 필요합니다.');
      }
      if (!allowedForSite(user, site)) {
        throw httpError(403, 'FORBIDDEN', '해당 사업장 조회 권한이 없습니다.');
      }

      const employeeNo = String(user.employee_no || '');
      const result = role === 'HOUSEMAN'
        ? await client.query(
            `select *
               from public.nova_houseman_orders
              where business_date=$1::date
                and site=$2
                and (
                  assigned_employee_no=$3
                  or processor_employee_no=$3
                  or (
                    route_locked is false
                    and $3 = any(coalesce(route_candidate_employee_nos, '{}'::text[]))
                  )
                )
              order by updated_at desc, order_id desc`,
            [businessDate, site, employeeNo]
          )
        : await client.query(
            `select *
               from public.nova_houseman_orders
              where business_date=$1::date
                and site=$2
              order by updated_at desc, order_id desc`,
            [businessDate, site]
          );
      const rows = result.rows;
'''
if old not in cloud:
    raise SystemExit('houseman GET role/query target not found')
cloud = cloud.replace(old, new, 1)

# 2) Dedicated Houseman worker action endpoint. Never route worker actions through /v1/rooms.
anchor = r'''/**
 * 관리자/오더테이커 하우스맨 등록취소 Realtime 확정.
 * 접수/처리 시작 전 REGISTERED/ASSIGNED 오더만 PostgreSQL에서 제거한다.
 * Sheet는 Apps Script의 deleteMonthlyHousemanOrder가 감사이력과 함께 소프트삭제한다.
 */
app.post(
  '/v1/houseman-orders/:orderId/cancel','''
route = r'''/**
 * 하우스맨 모바일 접수/처리 Realtime 확정.
 * PostgreSQL 상태를 먼저 확정하고 Sheet 업무이력/감사는 클라이언트가 백그라운드 미러한다.
 */
app.post(
  '/v1/houseman-orders/:orderId/action',
  async (req, res, next) => {
    const startedAt = Date.now();
    let db;
    try {
      db = await pool.connect();
      const auth = authBearer(req);
      const body = req.body || {};
      const orderId = cleanText_(req.params.orderId, 80).toUpperCase();
      const action = cleanText_(body.action, 30).toUpperCase();
      const reason = String(body.reason || '').trim().slice(0, 2000);
      const requestId = cleanText_(body.requestId || req.headers['x-request-id'], 200);

      if (!/^HO-\\d{8}-[A-Z0-9]{8,32}$/.test(orderId) || !requestId) {
        throw httpError(400, 'INVALID_REQUEST', '오더번호와 requestId가 필요합니다.');
      }
      if (!['ACCEPT', 'ACCEPT_START', 'START', 'COMPLETE', 'UNABLE'].includes(action)) {
        throw httpError(400, 'INVALID_ACTION', '지원하지 않는 하우스맨 처리 작업입니다.');
      }
      if (action === 'UNABLE' && !reason) {
        throw httpError(400, 'REASON_REQUIRED', '처리불가 사유를 입력하세요.');
      }

      await db.query('begin');
      const user = await loadUser(db, auth.employeeNo);
      if (String(user.role || '').toUpperCase() !== 'HOUSEMAN') {
        throw httpError(403, 'FORBIDDEN', '하우스맨 처리 권한이 없습니다.');
      }

      const dedup = await db.query(
        `insert into public.nova_request_dedup(request_id,employee_no,action)
         values($1,$2,$3)
         on conflict(request_id) do nothing
         returning request_id`,
        [requestId, user.employee_no, `HOUSEMAN_${action}`]
      );
      if (!dedup.rowCount) {
        const prior = await db.query(
          `select response_json from public.nova_request_dedup where request_id=$1`,
          [requestId]
        );
        await db.query('commit');
        if (prior.rows[0]?.response_json) {
          return res.json({ ...prior.rows[0].response_json, duplicateRequest: true });
        }
        throw httpError(409, 'REQUEST_IN_PROGRESS', '동일 하우스맨 요청이 처리 중입니다.');
      }

      const found = await db.query(
        `select * from public.nova_houseman_orders where order_id=$1 for update`,
        [orderId]
      );
      const current = found.rows[0];
      if (!current) {
        throw httpError(404, 'HOUSEMAN_ORDER_NOT_FOUND', 'Realtime 하우스맨 오더를 찾을 수 없습니다.');
      }

      const employeeNo = String(user.employee_no || '');
      const status = String(current.status_code || '').trim().toUpperCase();
      const assignedEmployeeNo = String(current.assigned_employee_no || '');
      const processorEmployeeNo = String(current.processor_employee_no || '');
      const candidates = Array.isArray(current.route_candidate_employee_nos)
        ? current.route_candidate_employee_nos.map(String)
        : [];
      const sharedClaimable = status === 'ASSIGNED'
        && current.route_locked === false
        && candidates.includes(employeeNo);
      const assignedToMe = assignedEmployeeNo === employeeNo;
      const processingByMe = processorEmployeeNo === employeeNo;

      if (['ACCEPT', 'ACCEPT_START'].includes(action)) {
        if (status !== 'ASSIGNED') {
          const target = action === 'ACCEPT' ? 'ACCEPTED' : 'PROCESSING';
          if (status === target && (assignedToMe || processingByMe)) {
            const response = {
              ok: true, action, requestId, idempotent: true,
              order: housemanOrderDto_(current),
              orderVersion: Number(current.version || 0),
              timing: { totalMs: Date.now() - startedAt }
            };
            await db.query(
              `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
              [requestId, JSON.stringify(response)]
            );
            await db.query('commit');
            return res.json(response);
          }
          throw httpError(409, 'HOUSEMAN_ORDER_STATE_CONFLICT', '배정 상태의 오더만 접수할 수 있습니다.');
        }
        if (!assignedToMe && !sharedClaimable) {
          throw httpError(403, 'FORBIDDEN', '본인에게 배정되거나 공동 전달된 오더만 접수할 수 있습니다.');
        }
      } else {
        if (!assignedToMe && !processingByMe) {
          throw httpError(403, 'FORBIDDEN', '본인에게 배정된 오더만 처리할 수 있습니다.');
        }
        const required = action === 'START' ? 'ACCEPTED' : 'PROCESSING';
        const target = action === 'START' ? 'PROCESSING' : (action === 'COMPLETE' ? 'COMPLETED' : 'UNABLE');
        if (status !== required) {
          if (status === target) {
            const response = {
              ok: true, action, requestId, idempotent: true,
              order: housemanOrderDto_(current),
              orderVersion: Number(current.version || 0),
              timing: { totalMs: Date.now() - startedAt }
            };
            await db.query(
              `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
              [requestId, JSON.stringify(response)]
            );
            await db.query('commit');
            return res.json(response);
          }
          throw httpError(
            409,
            'HOUSEMAN_ORDER_STATE_CONFLICT',
            `현재 ${status || '-'} 상태에서는 ${action} 처리를 할 수 없습니다.`
          );
        }
      }

      const startImmediately = action === 'ACCEPT_START';
      const targetStatus = action === 'ACCEPT' ? 'ACCEPTED'
        : (['ACCEPT_START', 'START'].includes(action) ? 'PROCESSING'
          : (action === 'COMPLETE' ? 'COMPLETED' : 'UNABLE'));
      const released = ['ACCEPT', 'ACCEPT_START'].includes(action)
        ? candidates.filter(value => value !== employeeNo)
        : (Array.isArray(current.released_candidate_employee_nos) ? current.released_candidate_employee_nos : []);
      const lockToEmployee = ['ACCEPT', 'ACCEPT_START'].includes(action);

      const updated = await db.query(
        `update public.nova_houseman_orders
            set status_code=$2,
                assigned_employee_no=case when $3::boolean then $4 else assigned_employee_no end,
                assigned_name=case when $3::boolean then $5 else assigned_name end,
                processor_employee_no=$4,
                processor_name=$5,
                route_locked=case when $3::boolean then true else route_locked end,
                accepted_by_employee_no=case when $3::boolean then $4 else accepted_by_employee_no end,
                released_candidate_employee_nos=case when $3::boolean then $6::text[] else released_candidate_employee_nos end,
                accepted_at=case when $3::boolean then coalesce(accepted_at,now()) else accepted_at end,
                started_at=case when $7::boolean then coalesce(started_at,now()) else started_at end,
                completed_at=case when $8::boolean then now() else completed_at end,
                unable_reason=case when $2='UNABLE' then $9 when $2='COMPLETED' then '' else unable_reason end,
                version=version+1,
                updated_at=now()
          where order_id=$1
          returning *`,
        [
          orderId,
          targetStatus,
          lockToEmployee,
          employeeNo,
          String(user.name || employeeNo),
          released,
          startImmediately || action === 'START',
          action === 'COMPLETE' || action === 'UNABLE',
          reason
        ]
      );
      const nextOrder = updated.rows[0];
      const response = {
        ok: true,
        action,
        requestId,
        order: housemanOrderDto_(nextOrder),
        orderVersion: Number(nextOrder.version || 0),
        timing: { totalMs: Date.now() - startedAt }
      };
      await db.query(
        `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
        [requestId, JSON.stringify(response)]
      );
      await db.query('commit');
      res.json(response);
    } catch (e) {
      if (db) {
        try { await db.query('rollback'); } catch {}
      }
      next(e);
    } finally {
      if (db) db.release();
    }
  }
);

'''
if "'/v1/houseman-orders/:orderId/action'" not in cloud:
    if anchor not in cloud:
        raise SystemExit('houseman worker action insertion anchor not found')
    cloud = cloud.replace(anchor, route + anchor, 1)

# 3) Client helper + serialized Sheet mirror queue.
helper_anchor = r'''  async function mirrorRealtimeClearAssignmentToSheet_(payload) { // (DB 배정초기화 성공 후 이력/Sheet 보조 미러)'''
helpers = r'''  const novaRealtimeHousemanMirrorChains_ = new Map();

  async function novaRealtimeHousemanWorkerAction_(payload) { // (하우스맨 접수/처리 Cloud Run 전용 경로)
    const safe = Object.assign({}, payload || {});
    const orderId = String(safe.orderId || '').trim();
    const action = String(safe.action || '').trim().toUpperCase();
    if (!orderId || !['ACCEPT', 'ACCEPT_START', 'START', 'COMPLETE', 'UNABLE'].includes(action)) {
      throw new Error('하우스맨 처리 요청을 확인하세요.');
    }
    const requestId = novaRealtimeRequestId_(`HOUSEMAN_${action}`, orderId);
    const result = await novaRealtimeFetch_(
      `/v1/houseman-orders/${encodeURIComponent(orderId)}/action`,
      {
        method: 'POST',
        headers: { 'X-Request-Id': requestId },
        body: JSON.stringify({ action, reason: String(safe.reason || ''), requestId })
      }
    );
    const mapped = novaRealtimeMapHousemanOrder_(result.order) || result.order || {};
    const dbVersion = Number(result.orderVersion || result.order?.version || mapped.version || 0);
    // Sheet 변경버전과 DB 버전은 다른 도메인이므로 기존 Sheet 식별값을 보존한다.
    mapped.rowNumber = Number(safe.rowNumber || 0);
    mapped.version = Number(safe.expectedVersion || 0);
    mapped.__dbVersion = dbVersion;
    mapped.__dbAssignmentTracked = true;
    mapped.__localProtectUntil = Date.now() + 30000;
    queueRealtimeHousemanWorkerMirror_(safe);
    return {
      ok: true,
      realtime: true,
      order: mapped,
      version: Number(safe.expectedVersion || 0),
      timing: result.timing || {},
      requestId
    };
  }

  function queueRealtimeHousemanWorkerMirror_(payload) { // (DB 처리 순서대로 Sheet 업무이력 미러 직렬화)
    const safe = Object.assign({}, payload || {});
    const orderId = String(safe.orderId || '').trim();
    if (!orderId) return;
    const previous = novaRealtimeHousemanMirrorChains_.get(orderId) || Promise.resolve();
    const next = previous
      .catch(() => null)
      .then(() => mirrorRealtimeHousemanWorkerActionToSheet_(safe));
    novaRealtimeHousemanMirrorChains_.set(orderId, next);
    void next.finally(() => {
      if (novaRealtimeHousemanMirrorChains_.get(orderId) === next) {
        novaRealtimeHousemanMirrorChains_.delete(orderId);
      }
    });
  }

  async function mirrorRealtimeHousemanWorkerActionToSheet_(payload) { // (Realtime 하우스맨 상태를 기존 업무이력/감사에 보완)
    const safe = Object.assign({}, payload || {}, { expectedVersion: 0 });
    const delays = [0, 650, 1600, 3600, 7000];
    let lastError = null;
    for (let index = 0; index < delays.length; index += 1) {
      if (delays[index]) await novaRealtimeSleep_(delays[index]);
      try {
        const mirrored = await callServer('updateHousemanOrder', state.token, safe);
        if (!mirrored?.ok) throw new Error(mirrored?.message || '하우스맨 이력 동기화 실패');
        // 모바일은 DB 상태가 이미 확정됐으므로 이 결과를 기다리지 않는다.
        setSyncStatus(`${mirrored.order?.roomNo || ''}호 하우스맨 이력 동기화 완료`);
        return mirrored;
      } catch (error) {
        lastError = error;
      }
    }
    console.error('[NOVA Realtime] 하우스맨 상태 Sheet 미러 실패:', lastError);
    setSyncStatus(`${safe.orderId || ''} Realtime 처리 완료 · 기존 이력 동기화 재확인 필요`);
    return null;
  }

'''
if 'async function novaRealtimeHousemanWorkerAction_(' not in client:
    if helper_anchor not in client:
        raise SystemExit('client houseman helper insertion anchor not found')
    client = client.replace(helper_anchor, helpers + helper_anchor, 1)

# 4) Route Houseman worker actions before generic room-action decision.
old = r'''    delete legacySafe.sheetExpectedVersion;
    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)
'''
new = r'''    delete legacySafe.sheetExpectedVersion;

    const currentRole = String(state.bootstrap?.user?.role || '').trim().toUpperCase();
    const housemanWorkerAction = legacyMethod === 'updateHousemanOrder'
      && currentRole === 'HOUSEMAN'
      && ['ACCEPT', 'ACCEPT_START', 'START', 'COMPLETE', 'UNABLE'].includes(rawAction);
    if (housemanWorkerAction) {
      if (!novaRealtime_.configLoaded) await initNovaRealtime_();
      if (novaRealtimeIsEnabled_()) {
        try {
          return await novaRealtimeHousemanWorkerAction_(legacySafe);
        } catch (error) {
          const code = String(error?.code || '').trim().toUpperCase();
          // DB에 아직 없는 legacy/미러대기 오더만 기존 Sheet 경로로 안전 폴백한다.
          if (Number(error?.status || 0) !== 404 && code !== 'HOUSEMAN_ORDER_NOT_FOUND') throw error;
          console.warn('[NOVA Realtime] DB 미존재 하우스맨 오더는 기존 경로로 처리합니다.', error?.message || error);
        }
      }
      return callServer(legacyMethod, state.token, legacySafe);
    }

    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)
'''
if old not in client:
    raise SystemExit('client generic realtime route target not found')
client = client.replace(old, new, 1)

# 5) Broadcast UPDATE must also process Houseman order records.
old = r'''.on('broadcast', { event: 'UPDATE' }, payload => novaRealtimeHandleBroadcast_(payload))
        .on('broadcast', { event: 'INSERT' }, payload => {
'''
new = r'''.on('broadcast', { event: 'UPDATE' }, payload => {
          novaRealtimeHandleBroadcast_(payload);
          novaRealtimeHandleHousemanOrderBroadcast_(payload);
        })
        .on('broadcast', { event: 'INSERT' }, payload => {
'''
if old not in client:
    raise SystemExit('broadcast UPDATE anchor not found')
client = client.replace(old, new, 1)

# 6) Admin/ORDER indicator direct Houseman DB fallback, preserving Sheet row/version domain and Sheet-newer rows.
fallback_anchor = r'''  async function novaRealtimeHydrateIndicatorFallback_() {'''
admin_helper = r'''  async function novaRealtimeHydrateIndicatorHousemanOrders_() { // (관리자/오더테이커 하우스맨 상태 DB 직접 보정)
    if (!novaRealtimeIsEnabled_() || document.hidden || state.activeMenu !== 'indicator' || !state.indicator.data) return 0;
    const role = String(state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (!['ADMIN', 'ORDER'].includes(role)) return 0;
    const businessDate = String(state.indicator.businessDate || state.bootstrap?.app?.businessDate || '').trim();
    const sites = novaRealtimeRelevantSites_();
    if (!businessDate || !sites.length) return 0;

    const lists = await Promise.all(sites.map(site =>
      novaRealtimeLoadHousemanOrders_(businessDate, site)
        .catch(error => { console.warn('[NOVA Realtime] 하우스맨 관리자 DB 조회 실패', site, error); return []; })
    ));
    const orders = state.indicator.data.orders || (state.indicator.data.orders = []);
    let changed = 0;

    lists.flat().forEach(raw => {
      const mapped = novaRealtimeMapHousemanOrder_(raw);
      if (!mapped?.orderId) return;
      const index = orders.findIndex(item => String(item?.orderId || '') === mapped.orderId);
      if (index < 0) {
        mapped.__dbVersion = Number(mapped.version || 0);
        mapped.version = 0;
        mapped.rowNumber = 0;
        mapped.__sheetMirrorPending = true;
        mapped.__sheetMirrorStartedAt = Date.now();
        orders.unshift(mapped);
        changed += 1;
        return;
      }

      const previous = orders[index];
      const dbUpdatedMs = novaRealtimeUpdatedAtMs_(mapped.updatedAt);
      const previousUpdatedMs = novaRealtimeUpdatedAtMs_(previous.updatedAt);
      // 관리자 EDIT/REOPEN 등 Sheet 쪽이 더 최신이면 DB의 이전 상태로 되돌리지 않는다.
      if (previousUpdatedMs && dbUpdatedMs && previousUpdatedMs > dbUpdatedMs) return;

      const dbVersion = Number(mapped.version || 0);
      const next = Object.assign({}, previous, mapped, {
        rowNumber: Number(previous.rowNumber || 0),
        version: Number(previous.version || 0),
        __dbVersion: dbVersion
      });
      if (Number(previous.rowNumber || 0) > 0) {
        delete next.__sheetMirrorPending;
        delete next.__sheetMirrorStartedAt;
      }
      const beforeSig = JSON.stringify([
        previous.statusCode, previous.assignedEmployeeNo, previous.processorEmployeeNo,
        previous.acceptedAt, previous.startedAt, previous.completedAt, previous.unableReason, previous.updatedAt
      ]);
      const afterSig = JSON.stringify([
        next.statusCode, next.assignedEmployeeNo, next.processorEmployeeNo,
        next.acceptedAt, next.startedAt, next.completedAt, next.unableReason, next.updatedAt
      ]);
      if (beforeSig !== afterSig) {
        orders[index] = next;
        changed += 1;
      }
    });

    if (changed) {
      orders.sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')) || String(b.registeredAt || '').localeCompare(String(a.registeredAt || '')));
      renderOrderList();
      renderIndicatorSummary();
    }
    return changed;
  }

'''
if 'async function novaRealtimeHydrateIndicatorHousemanOrders_()' not in client:
    if fallback_anchor not in client:
        raise SystemExit('indicator fallback helper anchor not found')
    client = client.replace(fallback_anchor, admin_helper + fallback_anchor, 1)

# Call Houseman DB hydrate each admin fallback cycle, outside room event paging.
old = r'''      if (changedCount) {
        renderIndicatorSummary();
        setSyncStatus(`DB 변경확인 · ${changedCount}실 반영`);
      }
    } finally {
'''
new = r'''      const housemanChanged = await novaRealtimeHydrateIndicatorHousemanOrders_();
      if (changedCount) {
        renderIndicatorSummary();
        setSyncStatus(`DB 변경확인 · ${changedCount}실 반영${housemanChanged ? ` · 오더 ${housemanChanged}건` : ''}`);
      } else if (housemanChanged) {
        setSyncStatus(`DB 변경확인 · 하우스맨 오더 ${housemanChanged}건 반영`);
      }
    } finally {
'''
if old not in client:
    raise SystemExit('indicator fallback call anchor not found')
client = client.replace(old, new, 1)

# Self validation: protect the roommaid/QM routes and Houseman separation.
checks_cloud = [
    "'/v1/houseman-orders/:orderId/action'",
    "['ACCEPT', 'ACCEPT_START', 'START', 'COMPLETE', 'UNABLE'].includes(action)",
    "['HOUSEMAN', 'ADMIN', 'ORDER'].includes(role)",
    "route_locked=false",
]
checks_client = [
    "async function novaRealtimeHousemanWorkerAction_",
    "legacyMethod === 'updateHousemanOrder'",
    "currentRole === 'HOUSEMAN'",
    "async function novaRealtimeHydrateIndicatorHousemanOrders_",
    "novaRealtimeHandleHousemanOrderBroadcast_(payload);",
    "const roommaidMobileOperation = legacyMethod === 'updateMobileRoomOperation';",
    "['QM_START', 'QM_COMPLETE', 'QM_REWORK'",
]
for marker in checks_cloud:
    if marker not in cloud:
        raise SystemExit(f'cloud marker missing: {marker}')
for marker in checks_client:
    if marker not in client:
        raise SystemExit(f'client marker missing: {marker}')

# Ensure Houseman worker actions are not included in room endpoint action list.
if "['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'CHANGE_ROOM_STATUS'" not in cloud:
    raise SystemExit('room action protected list changed unexpectedly')

client_path.write_text(client, encoding='utf-8')
cloud_path.write_text(cloud, encoding='utf-8')
print('HOUSEMAN_WORKER_REALTIME_INDICATOR_V91_OK')
