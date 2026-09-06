import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { createAuthService } from '../src/auth-service.mjs';
import { createSessionTokenSigner, decodeJwtPayloadUnsafe } from '../src/session-token.mjs';
import { SupabaseRpcError } from '../src/supabase-room-action-client.mjs';

function client(overrides = {}) {
  return {
    async loginIdentity({ name, employeeNo, site }) {
      return { ok: true, name, employeeNo, role: 'ROOMMAID', sessionSite: site, defaultSite: '', allowedSites: [] };
    },
    async me() { return { ok: true, employeeNo: '321516', role: 'ROOMMAID', sessionSite: '쏘라노' }; },
    ...overrides,
  };
}

test('session signer creates HS256 Supabase-compatible authenticated claims', () => {
  const signer = createSessionTokenSigner({
    secret: 'unit-test-secret',
    ttlSeconds: 3600,
    now: () => 1_800_000_000_000,
  });
  const signed = signer.sign({ employeeNo: '321516', name: '박옥자', role: 'ROOMMAID', sessionSite: '쏘라노' });
  const claims = decodeJwtPayloadUnsafe(signed.accessToken);
  assert.equal(claims.aud, 'authenticated');
  assert.equal(claims.role, 'authenticated');
  assert.equal(claims.employee_no, '321516');
  assert.equal(claims.nova_role, 'ROOMMAID');
  assert.equal(claims.site, '쏘라노');
  assert.equal(claims.exp - claims.iat, 3600);

  const [head, payload, signature] = signed.accessToken.split('.');
  const expected = crypto.createHmac('sha256', 'unit-test-secret').update(`${head}.${payload}`).digest('base64url');
  assert.equal(signature, expected);
});

test('login returns access token and normalized public user', async () => {
  const signer = createSessionTokenSigner({ secret: 'unit-test-secret', ttlSeconds: 3600 });
  const service = createAuthService({ authClient: client(), tokenSigner: signer });
  const result = await service.login({ name: '박옥자', employeeNo: '321516', site: '쏘라노' });
  assert.equal(result.status, 200);
  assert.equal(result.body.ok, true);
  assert.equal(result.body.tokenType, 'Bearer');
  assert.equal(result.body.user.employeeNo, '321516');
  assert.equal(result.body.user.sessionSite, '쏘라노');
  assert.equal(result.body.accessToken.split('.').length, 3);
});

test('login rejects missing credentials before DB call', async () => {
  let calls = 0;
  const signer = createSessionTokenSigner({ secret: 'unit-test-secret' });
  const service = createAuthService({ authClient: client({ async loginIdentity() { calls += 1; } }), tokenSigner: signer });
  const result = await service.login({ name: '', employeeNo: '', site: '쏘라노' });
  assert.equal(result.status, 400);
  assert.equal(result.body.code, 'INVALID_LOGIN_INPUT');
  assert.equal(calls, 0);
});

test('invalid login identity maps to forbidden without leaking internals', async () => {
  const signer = createSessionTokenSigner({ secret: 'unit-test-secret' });
  const service = createAuthService({
    authClient: client({
      async loginIdentity() {
        throw new SupabaseRpcError('이름 또는 사번이 일치하지 않습니다.', { status: 400, code: '42501' });
      },
    }),
    tokenSigner: signer,
  });
  const result = await service.login({ name: '잘못됨', employeeNo: 'x', site: '쏘라노' });
  assert.equal(result.status, 403);
  assert.equal(result.body.code, 'INVALID_CREDENTIALS');
});

test('me requires bearer token and forwards token only', async () => {
  let captured;
  const signer = createSessionTokenSigner({ secret: 'unit-test-secret' });
  const service = createAuthService({
    authClient: client({ async me(arg) { captured = arg; return { ok: true }; } }),
    tokenSigner: signer,
  });
  const noAuth = await service.me({});
  assert.equal(noAuth.status, 401);
  const result = await service.me({ authorization: 'Bearer abc.def.ghi' });
  assert.equal(result.status, 200);
  assert.equal(captured.authToken, 'abc.def.ghi');
});
