import { performance } from 'node:perf_hooks';

const baseUrl = text(process.env.NOVA_LOAD_BASE_URL).replace(/\/+$/, '');
const mode = text(process.env.NOVA_LOAD_MODE).toLowerCase();
const count = int(process.env.NOVA_LOAD_COUNT, 200);
const employeeNo = text(process.env.NOVA_LOAD_EMPLOYEE_NO);
const name = text(process.env.NOVA_LOAD_NAME || 'NOVA LOAD');
const site = text(process.env.NOVA_LOAD_SITE || '쏘라노');
const businessDate = text(process.env.NOVA_LOAD_BUSINESS_DATE || '2099-01-01');
const prefix = text(process.env.NOVA_LOAD_PREFIX);
const requestTimeoutMs = int(process.env.NOVA_LOAD_REQUEST_TIMEOUT_MS, 20000);
const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

function text(value) {
  return String(value ?? '').trim();
}

function int(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return Math.round(sorted[index] * 10) / 10;
}

async function jsonFetch(path, {
  method = 'GET',
  token = '',
  idempotencyKey = '',
  body,
  timeoutMs = requestTimeoutMs,
} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const started = performance.now();
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
        'X-NOVA-Client': 'core3-load-harness/1.0',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const latencyMs = performance.now() - started;
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    return { response, payload, latencyMs };
  } finally {
    clearTimeout(timer);
  }
}

async function login() {
  const { response, payload } = await jsonFetch('/v1/session/login', {
    method: 'POST',
    body: { name, employeeNo, site },
  });
  assert(response.status === 200 && payload?.ok === true, `login failed: HTTP ${response.status} ${payload?.code || ''} ${payload?.message || ''}`);
  assert(text(payload.accessToken), 'login did not return accessToken');
  return payload.accessToken;
}

function roomNoAt(index) {
  return `${prefix}${String(index + 1).padStart(4, '0')}`;
}

async function mutate(token, roomNo, action, expectedVersion, requestId) {
  try {
    const result = await jsonFetch(`/v1/rooms/${encodeURIComponent(roomNo)}/actions`, {
      method: 'POST',
      token,
      idempotencyKey: requestId,
      body: { businessDate, site, action, expectedVersion },
    });
    return {
      ok: result.response.status === 200 && result.payload?.ok === true,
      status: result.response.status,
      payload: result.payload,
      latencyMs: result.latencyMs,
      roomNo,
      requestId,
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      payload: { code: error?.name || 'NETWORK_ERROR', message: error?.message || String(error) },
      latencyMs: 0,
      roomNo,
      requestId,
    };
  }
}

async function listStageRooms(token) {
  const query = new URLSearchParams({ businessDate, site });
  const { response, payload } = await jsonFetch(`/v1/rooms?${query}`, { token });
  assert(response.status === 200 && payload?.ok === true, `room reconcile failed: HTTP ${response.status} ${payload?.code || ''}`);
  const rooms = Array.isArray(payload.rooms) ? payload.rooms : [];
  return rooms.filter(room => text(room?.roomNo).startsWith(prefix));
}

function summarize(results) {
  const latency = results.filter(item => item.ok).map(item => item.latencyMs);
  const statusCounts = {};
  const codeCounts = {};
  for (const item of results) {
    statusCounts[item.status] = (statusCounts[item.status] || 0) + 1;
    const code = text(item.payload?.code || (item.ok ? 'OK' : 'UNKNOWN'));
    codeCounts[code] = (codeCounts[code] || 0) + 1;
  }
  return {
    total: results.length,
    ok: results.filter(item => item.ok).length,
    failed: results.filter(item => !item.ok).length,
    changedTrue: results.filter(item => item.payload?.changed === true).length,
    alreadyAppliedTrue: results.filter(item => item.payload?.alreadyApplied === true).length,
    duplicateTrue: results.filter(item => item.payload?.duplicate === true).length,
    statusCounts,
    codeCounts,
    latencyMs: {
      p50: percentile(latency, 50),
      p95: percentile(latency, 95),
      p99: percentile(latency, 99),
      max: latency.length ? Math.round(Math.max(...latency) * 10) / 10 : 0,
    },
  };
}

async function runIndependent(token, action, expectedStatus) {
  const expectedVersion = 1;
  const requests = Array.from({ length: count }, (_, index) => {
    const roomNo = roomNoAt(index);
    const requestId = `LOAD-${mode}-${count}-${index + 1}-${runId}`;
    return mutate(token, roomNo, action, expectedVersion, requestId);
  });
  const results = await Promise.all(requests);
  const summary = summarize(results);
  assert(summary.failed === 0, `${mode}: ${summary.failed}/${count} requests failed`);
  assert(summary.changedTrue === count, `${mode}: expected ${count} changed responses, got ${summary.changedTrue}`);

  const rooms = await listStageRooms(token);
  assert(rooms.length === count, `${mode}: expected ${count} authoritative rooms, got ${rooms.length}`);
  const wrong = rooms.filter(room => text(room.cleaningStatus).toUpperCase() !== expectedStatus || Number(room.version) !== 2);
  assert(wrong.length === 0, `${mode}: ${wrong.length} rooms have wrong final state/version`);
  return { summary, finalRooms: rooms.length, finalStatus: expectedStatus, finalVersion: 2 };
}

async function runDuplicate(token) {
  const roomNo = roomNoAt(0);
  const requestId = `LOAD-DUPLICATE-${runId}`;
  const requests = Array.from({ length: count }, () => mutate(token, roomNo, 'CLEANING_START', 1, requestId));
  const results = await Promise.all(requests);
  const summary = summarize(results);
  assert(summary.failed === 0, `duplicate: ${summary.failed}/${count} requests failed`);
  assert(summary.duplicateTrue === count - 1, `duplicate: expected ${count - 1} duplicate responses, got ${summary.duplicateTrue}`);

  const rooms = await listStageRooms(token);
  assert(rooms.length === 1, `duplicate: expected exactly one target room, got ${rooms.length}`);
  assert(text(rooms[0].cleaningStatus).toUpperCase() === 'CLEANING', 'duplicate: final status is not CLEANING');
  assert(Number(rooms[0].version) === 2, `duplicate: final version expected 2, got ${rooms[0].version}`);
  return { summary, finalRooms: 1, finalStatus: 'CLEANING', finalVersion: 2 };
}

async function runContention(token) {
  const roomNo = roomNoAt(0);
  const requests = Array.from({ length: count }, (_, index) => mutate(
    token,
    roomNo,
    'CLEANING_START',
    1,
    `LOAD-CONTENTION-${index + 1}-${runId}`,
  ));
  const results = await Promise.all(requests);
  const summary = summarize(results);
  assert(summary.failed === 0, `contention: ${summary.failed}/${count} requests failed`);
  assert(summary.changedTrue === 1, `contention: expected exactly one real transition, got ${summary.changedTrue}`);
  assert(summary.alreadyAppliedTrue === count - 1, `contention: expected ${count - 1} converged responses, got ${summary.alreadyAppliedTrue}`);

  const rooms = await listStageRooms(token);
  assert(rooms.length === 1, `contention: expected exactly one target room, got ${rooms.length}`);
  assert(text(rooms[0].cleaningStatus).toUpperCase() === 'CLEANING', 'contention: final status is not CLEANING');
  assert(Number(rooms[0].version) === 2, `contention: final version expected 2, got ${rooms[0].version}`);
  return { summary, finalRooms: 1, finalStatus: 'CLEANING', finalVersion: 2 };
}

async function runPostCommitDiscard(token) {
  const roomNo = roomNoAt(0);
  const requestId = `LOAD-POSTCOMMIT-${runId}`;

  // First request is allowed to complete at the server. The client deliberately
  // discards the successful response and treats the result as unknown.
  const first = await mutate(token, roomNo, 'CLEANING_START', 1, requestId);
  assert(first.ok, `post-commit-discard first request failed unexpectedly: ${first.status} ${first.payload?.code || ''}`);

  // Retry the exact same user intent with the exact same idempotency key.
  const second = await mutate(token, roomNo, 'CLEANING_START', 1, requestId);
  assert(second.ok, `post-commit-discard retry failed: ${second.status} ${second.payload?.code || ''}`);
  assert(second.payload?.duplicate === true, 'post-commit-discard retry was not recognized as duplicate');

  const rooms = await listStageRooms(token);
  assert(rooms.length === 1, `post-commit-discard: expected one room, got ${rooms.length}`);
  assert(text(rooms[0].cleaningStatus).toUpperCase() === 'CLEANING', 'post-commit-discard: final status is not CLEANING');
  assert(Number(rooms[0].version) === 2, `post-commit-discard: final version expected 2, got ${rooms[0].version}`);
  return { summary: summarize([first, second]), finalRooms: 1, finalStatus: 'CLEANING', finalVersion: 2 };
}

async function runTimeoutRetry(token) {
  const roomNo = roomNoAt(0);
  const requestId = `LOAD-TIMEOUT-${runId}`;
  let firstOutcome = 'UNKNOWN';
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1);
    try {
      const response = await fetch(`${baseUrl}/v1/rooms/${encodeURIComponent(roomNo)}/actions`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          'Idempotency-Key': requestId,
          'X-NOVA-Client': 'core3-load-timeout/1.0',
        },
        body: JSON.stringify({ businessDate, site, action: 'CLEANING_START', expectedVersion: 1 }),
        signal: controller.signal,
      });
      firstOutcome = `HTTP_${response.status}`;
    } finally {
      clearTimeout(timer);
    }
  } catch (error) {
    firstOutcome = error?.name || 'NETWORK_ERROR';
  }

  const retry = await mutate(token, roomNo, 'CLEANING_START', 1, requestId);
  assert(retry.ok, `timeout-retry retry failed: ${retry.status} ${retry.payload?.code || ''}`);

  const rooms = await listStageRooms(token);
  assert(rooms.length === 1, `timeout-retry: expected one room, got ${rooms.length}`);
  assert(text(rooms[0].cleaningStatus).toUpperCase() === 'CLEANING', 'timeout-retry: final status is not CLEANING');
  assert(Number(rooms[0].version) === 2, `timeout-retry: final version expected 2, got ${rooms[0].version}`);
  return {
    summary: summarize([retry]),
    firstOutcome,
    retryDuplicate: retry.payload?.duplicate === true,
    finalRooms: 1,
    finalStatus: 'CLEANING',
    finalVersion: 2,
  };
}

async function runReconcileWithoutRealtime(token) {
  const roomNo = roomNoAt(0);
  const requestId = `LOAD-RECONCILE-${runId}`;
  const mutation = await mutate(token, roomNo, 'CLEANING_START', 1, requestId);
  assert(mutation.ok, `reconcile mutation failed: ${mutation.status} ${mutation.payload?.code || ''}`);

  // No Realtime client is connected in this process. Correctness must still be
  // recovered from the authoritative current-state GET.
  const rooms = await listStageRooms(token);
  assert(rooms.length === 1, `reconcile: expected one room, got ${rooms.length}`);
  assert(text(rooms[0].cleaningStatus).toUpperCase() === 'CLEANING', 'reconcile: authoritative GET did not recover CLEANING');
  assert(Number(rooms[0].version) === 2, `reconcile: final version expected 2, got ${rooms[0].version}`);
  return { summary: summarize([mutation]), finalRooms: 1, finalStatus: 'CLEANING', finalVersion: 2 };
}

async function main() {
  assert(baseUrl.startsWith('https://'), 'NOVA_LOAD_BASE_URL must be an https URL');
  assert(employeeNo, 'NOVA_LOAD_EMPLOYEE_NO is required');
  assert(prefix, 'NOVA_LOAD_PREFIX is required');
  assert(count <= 2000, 'NOVA_LOAD_COUNT must be <= 2000');

  const health = await jsonFetch('/health');
  assert(health.response.status === 200 && health.payload?.ok === true && health.payload?.service === 'nova-core3', 'target is not a healthy NOVA Core 3 service');

  const token = await login();
  let result;
  switch (mode) {
    case 'independent-start':
      result = await runIndependent(token, 'CLEANING_START', 'CLEANING');
      break;
    case 'independent-complete':
      result = await runIndependent(token, 'CLEANING_COMPLETE', 'COMPLETED');
      break;
    case 'duplicate-start':
      result = await runDuplicate(token);
      break;
    case 'contention-start':
      result = await runContention(token);
      break;
    case 'post-commit-discard':
      result = await runPostCommitDiscard(token);
      break;
    case 'timeout-retry':
      result = await runTimeoutRetry(token);
      break;
    case 'reconcile-without-realtime':
      result = await runReconcileWithoutRealtime(token);
      break;
    default:
      throw new Error(`unsupported NOVA_LOAD_MODE: ${mode}`);
  }

  const report = {
    ok: true,
    target: new URL(baseUrl).hostname,
    mode,
    count,
    employeeNo,
    site,
    businessDate,
    prefix,
    runId,
    ...result,
  };
  console.log(JSON.stringify(report, null, 2));
}

main().catch(error => {
  console.error(JSON.stringify({
    ok: false,
    mode,
    count,
    employeeNo,
    site,
    businessDate,
    prefix,
    message: error?.message || String(error),
    stack: error?.stack || '',
  }, null, 2));
  process.exitCode = 1;
});
