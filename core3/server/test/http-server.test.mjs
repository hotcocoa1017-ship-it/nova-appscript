import test from 'node:test';
import assert from 'node:assert/strict';
import { createNovaCoreServer } from '../src/server.mjs';

function service(overrides = {}) {
  return {
    async listRooms() { return { status: 200, body: { ok: true, rooms: [] } }; },
    async mutateRoom() { return { status: 200, body: { ok: true } }; },
    ...overrides,
  };
}

async function withServer(roomActionService, fn) {
  const server = createNovaCoreServer({ roomActionService, revision: 'test-revision' });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  try {
    await fn(`http://127.0.0.1:${address.port}`);
  } finally {
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
}

test('health endpoint exposes revision without auth', async () => {
  await withServer(service(), async base => {
    const response = await fetch(`${base}/health`);
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.ok, true);
    assert.equal(body.revision, 'test-revision');
  });
});

test('authoritative room list endpoint forwards auth/date/site', async () => {
  let captured;
  await withServer(service({
    async listRooms(request) {
      captured = request;
      return { status: 200, body: { ok: true, rooms: [{ roomNo: '7217' }] } };
    },
  }), async base => {
    const response = await fetch(`${base}/v1/rooms?businessDate=2026-09-06&site=${encodeURIComponent('쏘라노')}`, {
      headers: { Authorization: 'Bearer employee.jwt' },
    });
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.rooms[0].roomNo, '7217');
    assert.equal(captured.authorization, 'Bearer employee.jwt');
    assert.equal(captured.businessDate, '2026-09-06');
    assert.equal(captured.site, '쏘라노');
  });
});

test('room action endpoint forwards headers/path/body to service', async () => {
  let captured;
  await withServer(service({
    async mutateRoom(request) {
      captured = request;
      return { status: 200, body: { ok: true, requestId: request.idempotencyKey } };
    },
  }), async base => {
    const response = await fetch(`${base}/v1/rooms/7217/actions`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer employee.jwt',
        'Idempotency-Key': 'NOVA-HTTP-REQ-0001',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        businessDate: '2026-09-06',
        site: '쏘라노',
        action: 'CLEANING_START',
        expectedVersion: 3,
      }),
    });
    assert.equal(response.status, 200);
    assert.equal(captured.roomNo, '7217');
    assert.equal(captured.authorization, 'Bearer employee.jwt');
    assert.equal(captured.idempotencyKey, 'NOVA-HTTP-REQ-0001');
    assert.equal(captured.body.action, 'CLEANING_START');
  });
});

test('invalid JSON is rejected before service execution', async () => {
  let calls = 0;
  await withServer(service({ async mutateRoom() { calls += 1; } }), async base => {
    const response = await fetch(`${base}/v1/rooms/7217/actions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{broken',
    });
    const body = await response.json();
    assert.equal(response.status, 400);
    assert.equal(body.code, 'INVALID_JSON');
    assert.equal(calls, 0);
  });
});
