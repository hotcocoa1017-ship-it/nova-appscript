import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createSupabaseRoomActionClient,
  SupabaseRpcError,
} from '../src/supabase-room-action-client.mjs';

function input() {
  return {
    authToken: 'employee.jwt',
    businessDate: '2026-09-06',
    site: '쏘라노',
    roomNo: '7217',
    action: 'CLEANING_START',
    expectedVersion: 3,
    requestId: 'NOVA-CORE3-RPC-0001',
  };
}

test('calls v2 mutation RPC with employee JWT and publishable key', async () => {
  const calls = [];
  const client = createSupabaseRoomActionClient({
    supabaseUrl: 'https://example.supabase.co/',
    apiKey: 'publishable-key',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return new Response(JSON.stringify({ ok: true, requestId: 'NOVA-CORE3-RPC-0001' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });

  const result = await client.executeRoommaidAction(input());
  assert.equal(result.ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://example.supabase.co/rest/v1/rpc/nova_roommaid_action_v2');
  assert.equal(calls[0].options.headers.apikey, 'publishable-key');
  assert.equal(calls[0].options.headers.Authorization, 'Bearer employee.jwt');
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.p_request_id, 'NOVA-CORE3-RPC-0001');
  assert.equal(body.p_room_no, '7217');
});

test('calls authoritative room list RPC with same employee JWT', async () => {
  const calls = [];
  const client = createSupabaseRoomActionClient({
    supabaseUrl: 'https://example.supabase.co',
    apiKey: 'publishable-key',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return new Response(JSON.stringify({ ok: true, rooms: [{ roomNo: '7217' }] }), { status: 200 });
    },
  });

  const result = await client.listRoommaidRooms({
    authToken: 'employee.jwt',
    businessDate: '2026-09-06',
    site: '쏘라노',
  });
  assert.equal(result.rooms[0].roomNo, '7217');
  assert.equal(calls[0].url, 'https://example.supabase.co/rest/v1/rpc/nova_roommaid_rooms_v1');
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.p_business_date, '2026-09-06');
  assert.equal(body.p_site, '쏘라노');
});

test('retries transient 5xx using exactly the same mutation request body', async () => {
  const bodies = [];
  let attempt = 0;
  const client = createSupabaseRoomActionClient({
    supabaseUrl: 'https://example.supabase.co',
    apiKey: 'publishable-key',
    maxAttempts: 3,
    fetchImpl: async (_url, options) => {
      attempt += 1;
      bodies.push(options.body);
      if (attempt < 3) {
        return new Response(JSON.stringify({ message: 'temporary' }), { status: 503 });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    },
  });

  const result = await client.executeRoommaidAction(input());
  assert.equal(result.ok, true);
  assert.equal(attempt, 3);
  assert.equal(new Set(bodies).size, 1);
});

test('does not retry authorization failure', async () => {
  let attempt = 0;
  const client = createSupabaseRoomActionClient({
    supabaseUrl: 'https://example.supabase.co',
    apiKey: 'publishable-key',
    maxAttempts: 3,
    fetchImpl: async () => {
      attempt += 1;
      return new Response(JSON.stringify({ code: '42501', message: 'forbidden' }), { status: 403 });
    },
  });

  await assert.rejects(
    () => client.executeRoommaidAction(input()),
    error => error instanceof SupabaseRpcError && error.code === '42501' && error.status === 403,
  );
  assert.equal(attempt, 1);
});
