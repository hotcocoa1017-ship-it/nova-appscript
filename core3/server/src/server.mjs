import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { createRoomActionService } from './room-action-service.mjs';
import { createSupabaseRoomActionClient } from './supabase-room-action-client.mjs';

const MAX_BODY_BYTES = 64 * 1024;

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(payload),
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  res.end(payload);
}

async function readJsonBody(req) {
  const declared = Number(req.headers['content-length'] || 0);
  if (declared > MAX_BODY_BYTES) {
    const error = new Error('request body too large');
    error.status = 413;
    throw error;
  }

  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      const error = new Error('request body too large');
      error.status = 413;
      throw error;
    }
    chunks.push(chunk);
  }

  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    const error = new Error('invalid json');
    error.status = 400;
    throw error;
  }
}

export function createNovaCoreServer({ roomActionService, revision = 'dev' } = {}) {
  if (!roomActionService
      || typeof roomActionService.mutateRoom !== 'function'
      || typeof roomActionService.listRooms !== 'function') {
    throw new Error('roomActionService.listRooms and mutateRoom are required');
  }

  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', 'http://localhost');

      if (req.method === 'GET' && url.pathname === '/health') {
        sendJson(res, 200, {
          ok: true,
          service: 'nova-core3',
          revision,
        });
        return;
      }

      if (req.method === 'GET' && url.pathname === '/v1/rooms') {
        const result = await roomActionService.listRooms({
          authorization: req.headers.authorization,
          businessDate: url.searchParams.get('businessDate'),
          site: url.searchParams.get('site'),
        });
        sendJson(res, result.status, result.body);
        return;
      }

      const match = /^\/v1\/rooms\/([^/]+)\/actions$/.exec(url.pathname);
      if (match && req.method === 'POST') {
        const body = await readJsonBody(req);
        const result = await roomActionService.mutateRoom({
          authorization: req.headers.authorization,
          idempotencyKey: req.headers['idempotency-key'],
          roomNo: decodeURIComponent(match[1]),
          body,
        });
        sendJson(res, result.status, result.body);
        return;
      }

      if (match || url.pathname === '/v1/rooms') {
        sendJson(res, 405, {
          ok: false,
          code: 'METHOD_NOT_ALLOWED',
          message: '지원하지 않는 HTTP 메서드입니다.',
        });
        return;
      }

      sendJson(res, 404, {
        ok: false,
        code: 'NOT_FOUND',
        message: 'API 경로를 찾을 수 없습니다.',
      });
    } catch (error) {
      if (error?.status === 413) {
        sendJson(res, 413, {
          ok: false,
          code: 'BODY_TOO_LARGE',
          message: '요청 본문이 너무 큽니다.',
        });
        return;
      }
      if (error?.status === 400) {
        sendJson(res, 400, {
          ok: false,
          code: 'INVALID_JSON',
          message: 'JSON 요청 형식을 확인하세요.',
        });
        return;
      }

      console.error('[NOVA Core 3] unhandled request error', error);
      sendJson(res, 500, {
        ok: false,
        code: 'INTERNAL_ERROR',
        message: '서버 처리 중 오류가 발생했습니다.',
      });
    }
  });
}

export function createServerFromEnvironment(env = process.env) {
  const supabaseUrl = String(env.SUPABASE_URL || '').trim();
  const apiKey = String(env.SUPABASE_PUBLISHABLE_KEY || env.SUPABASE_ANON_KEY || '').trim();
  const timeoutMs = Number(env.NOVA_CORE_RPC_TIMEOUT_MS || 2500);
  const maxAttempts = Number(env.NOVA_CORE_RPC_ATTEMPTS || 3);

  const rpcClient = createSupabaseRoomActionClient({
    supabaseUrl,
    apiKey,
    timeoutMs,
    maxAttempts,
  });
  const roomActionService = createRoomActionService({ rpcClient });
  return createNovaCoreServer({
    roomActionService,
    revision: String(env.K_REVISION || env.NOVA_CORE_REVISION || 'dev'),
  });
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const port = Number(process.env.PORT || 8080);
  const server = createServerFromEnvironment(process.env);
  server.listen(port, '0.0.0.0', () => {
    console.log(`[NOVA Core 3] listening on :${port}`);
  });
}
