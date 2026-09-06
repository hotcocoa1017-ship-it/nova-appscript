import test from 'node:test';
import assert from 'node:assert/strict';
import { createRoomActionService } from '../src/room-action-service.mjs';
import {
  SupabaseRpcError,
  SupabaseResultUnknownError,
} from '../src/supabase-room-action-client.mjs';

function request(overrides = {}) {
  return {
    authorization: 'Bearer user.jwt.token',
    idempotencyKey: 'NOVA-CORE3-REQ-0001',
    roomNo: '7217',
    body: {
      businessDate: '2026-09-06',
      site: '쏘라노',
      action: 'CLEANING_START',
      expectedVersion: 3,
    },
    ...overrides,
  };
}

test('passes authenticated mutation to DB RPC using stable request id', async () => {
  const calls = [];
  const service = createRoomActionService({
    rpcClient: {
      async executeRoommaidAction(input) {
        calls.push(input);
        return { ok: true, requestId: input.requestId, changed: true };
      },
    },
  });

  const result = await service.mutateRoom(request());
  assert.equal(result.status, 200);
  assert.equal(result.body.ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].requestId, 'NOVA-CORE3-REQ-0001');
  assert.equal(calls[0].roomNo, '7217');
  assert.equal(calls[0].action, 'CLEANING_START');
});

test('rejects missing bearer token before DB call', async () => {
  let calls = 0;
  const service = createRoomActionService({
    rpcClient: { async executeRoommaidAction() { calls += 1; } },
  });
  const result = await service.mutateRoom(request({ authorization: '' }));
  assert.equal(result.status, 401);
  assert.equal(result.body.code, 'UNAUTHORIZED');
  assert.equal(calls, 0);
});

test('maps DB authorization and semantic conflicts without legacy fallback', async () => {
  const forbidden = createRoomActionService({
    rpcClient: {
      async executeRoommaidAction() {
        throw new SupabaseRpcError('본인에게 배정된 객실만 처리할 수 있습니다.', { status: 403, code: '42501' });
      },
    },
  });
  const forbiddenResult = await forbidden.mutateRoom(request());
  assert.equal(forbiddenResult.status, 403);
  assert.equal(forbiddenResult.body.code, 'FORBIDDEN');

  const conflict = createRoomActionService({
    rpcClient: {
      async executeRoommaidAction() {
        throw new SupabaseRpcError('현재 상태에서는 청소를 시작할 수 없습니다.', { status: 400, code: '55000' });
      },
    },
  });
  const conflictResult = await conflict.mutateRoom(request());
  assert.equal(conflictResult.status, 409);
  assert.equal(conflictResult.body.code, 'STATE_CONFLICT');
});

test('ambiguous network result instructs same idempotency-key retry', async () => {
  const service = createRoomActionService({
    rpcClient: {
      async executeRoommaidAction() {
        throw new SupabaseResultUnknownError('unknown');
      },
    },
  });
  const result = await service.mutateRoom(request());
  assert.equal(result.status, 503);
  assert.equal(result.body.code, 'RESULT_UNKNOWN');
  assert.equal(result.body.retryable, true);
  assert.equal(result.body.reuseIdempotencyKey, true);
});

test('200 unrelated room requests are not serialized by the application service', async () => {
  let inFlight = 0;
  let maxInFlight = 0;
  const seen = new Set();
  const service = createRoomActionService({
    rpcClient: {
      async executeRoommaidAction(input) {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        seen.add(input.requestId);
        await new Promise(resolve => setTimeout(resolve, 3));
        inFlight -= 1;
        return { ok: true, requestId: input.requestId, changed: true };
      },
    },
  });

  const results = await Promise.all(Array.from({ length: 200 }, (_, index) => service.mutateRoom(request({
    idempotencyKey: `NOVA-CORE3-LOAD-${String(index).padStart(4, '0')}`,
    roomNo: String(7000 + index),
  }))));

  assert.equal(results.length, 200);
  assert.equal(results.every(item => item.status === 200), true);
  assert.equal(seen.size, 200);
  assert.ok(maxInFlight > 1, `expected concurrent fanout, maxInFlight=${maxInFlight}`);
});
