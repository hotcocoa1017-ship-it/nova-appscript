import crypto from 'crypto';
import express from 'express';
import pg from 'pg';

const { Pool } = pg;
const app = express();
app.disable('x-powered-by');
app.use(express.json({
  limit: '256kb',
  verify: (req, _res, buf) => {
    req.rawBody = buf.toString('utf8');
  }
}));

const BUILD = 'archive-gateway-v1';
const PORT = Number(process.env.PORT || 8080);
const PG_HOST = String(process.env.PG_HOST || '');
const PG_PORT = Number(process.env.PG_PORT || 6543);
const PG_DATABASE = String(process.env.PG_DATABASE || 'postgres');
const PG_USER = String(process.env.PG_USER || '');
const PG_PASSWORD = String(process.env.PG_PASSWORD || '');
const PG_POOL_MAX = Number(process.env.PG_POOL_MAX || 8);
const PG_SSL = String(process.env.PG_SSL || 'true').toLowerCase() !== 'false';
const NOVA_TOKEN_SECRET = String(process.env.NOVA_TOKEN_SECRET || '');
const SUPABASE_URL = String(process.env.SUPABASE_URL || '').replace(/\/+$/, '');

if (!PG_HOST || !PG_USER || !PG_PASSWORD || !PG_DATABASE || !NOVA_TOKEN_SECRET || !SUPABASE_URL) {
  throw new Error('Archive Gateway 필수 환경변수가 설정되지 않았습니다.');
}

const pool = new Pool({
  host: PG_HOST,
  port: PG_PORT,
  database: PG_DATABASE,
  user: PG_USER,
  password: PG_PASSWORD,
  max: Math.max(2, Math.min(PG_POOL_MAX, 12)),
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
  ssl: PG_SSL ? { rejectUnauthorized: false } : false
});

let archiveTokenCache = { value: '', expiresAt: 0 };

function httpError(status, code, message) {
  const error = new Error(message);
  error.status = status;
  error.code = code;
  return error;
}

function normalizeBase64Url_(value) {
  return String(value || '').trim().replace(/=+$/g, '');
}

function timingSafeTextEqual_(a, b) {
  const left = Buffer.from(String(a || ''), 'utf8');
  const right = Buffer.from(String(b || ''), 'utf8');
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

function verifyNovaToken_(token) {
  const parts = String(token || '').trim().split('.');
  if (parts.length !== 2) throw httpError(401, 'UNAUTHORIZED', '로그인이 필요합니다.');
  const [body, rawSig] = parts;
  const sig = normalizeBase64Url_(rawSig);
  const expected = normalizeBase64Url_(
    crypto.createHmac('sha256', NOVA_TOKEN_SECRET).update(body).digest('base64url')
  );
  if (!timingSafeTextEqual_(sig, expected)) {
    throw httpError(401, 'UNAUTHORIZED', '로그인 정보가 올바르지 않습니다.');
  }

  let payload;
  try {
    payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
  } catch {
    throw httpError(401, 'UNAUTHORIZED', '로그인 정보가 올바르지 않습니다.');
  }
  if (!payload?.employeeNo || !payload?.expiresAt || Date.now() > Number(payload.expiresAt)) {
    throw httpError(401, 'UNAUTHORIZED', '로그인 시간이 만료되었습니다.');
  }
  return payload;
}

function authBearer_(req) {
  const value = String(req.headers.authorization || '');
  if (!value.startsWith('Bearer ')) throw httpError(401, 'UNAUTHORIZED', '로그인이 필요합니다.');
  return verifyNovaToken_(value.slice(7));
}

function verifySignedRequest_(req) {
  const timestamp = String(req.headers['x-nova-timestamp'] || '').trim();
  const signature = String(req.headers['x-nova-signature'] || '').trim().toLowerCase();
  const ts = Number(timestamp);
  if (!timestamp || !signature || !Number.isFinite(ts)) {
    throw httpError(401, 'ARCHIVE_UNAUTHORIZED', 'Archive 인증정보가 없습니다.');
  }
  if (Math.abs(Date.now() - ts) > 5 * 60 * 1000) {
    throw httpError(401, 'ARCHIVE_AUTH_EXPIRED', 'Archive 인증시간이 만료되었습니다.');
  }
  const rawBody = typeof req.rawBody === 'string' ? req.rawBody : JSON.stringify(req.body || {});
  const expected = crypto
    .createHmac('sha256', NOVA_TOKEN_SECRET)
    .update(`${timestamp}.${rawBody}`)
    .digest('hex');
  if (!timingSafeTextEqual_(signature, expected)) {
    throw httpError(401, 'ARCHIVE_UNAUTHORIZED', 'Archive 인증정보가 올바르지 않습니다.');
  }
}

async function loadAdmin_(employeeNo) {
  const { rows } = await pool.query(
    `select employee_no, role, enabled
       from public.nova_users
      where employee_no=$1
      limit 1`,
    [String(employeeNo || '')]
  );
  const user = rows[0];
  if (!user || !user.enabled) throw httpError(401, 'UNAUTHORIZED', '사용할 수 없는 계정입니다.');
  if (String(user.role || '').toUpperCase() !== 'ADMIN') {
    throw httpError(403, 'ARCHIVE_ADMIN_ONLY', '관리자만 사용할 수 있습니다.');
  }
  return user;
}

async function requireArchiveAdmin_(req, _res, next) {
  try {
    verifySignedRequest_(req);
    const auth = authBearer_(req);
    req.novaAdmin = await loadAdmin_(auth.employeeNo);
    next();
  } catch (error) {
    next(error);
  }
}

async function getArchiveRestoreToken_() {
  if (archiveTokenCache.value && Date.now() < archiveTokenCache.expiresAt) {
    return archiveTokenCache.value;
  }
  const { rows } = await pool.query(
    `select decrypted_secret
       from vault.decrypted_secrets
      where name='nova_archive_restore_token'
      limit 1`
  );
  const token = String(rows[0]?.decrypted_secret || '').trim();
  if (token.length < 40) throw httpError(503, 'ARCHIVE_SECRET_UNAVAILABLE', 'Archive 인증 구성을 확인할 수 없습니다.');
  archiveTokenCache = { value: token, expiresAt: Date.now() + 5 * 60 * 1000 };
  return token;
}

async function callArchiveEdge_(slug, body, timeoutMs) {
  const token = await getArchiveRestoreToken_();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${SUPABASE_URL}/functions/v1/${slug}`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-nova-archive-restore-token': token
      },
      body: JSON.stringify(body || {}),
      signal: controller.signal
    });
    const text = await response.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      throw httpError(502, 'ARCHIVE_INVALID_RESPONSE', 'Archive 서버 응답을 확인할 수 없습니다.');
    }
    if (!response.ok) {
      const error = httpError(response.status, data?.code || 'ARCHIVE_UPSTREAM_ERROR', data?.message || 'Archive 요청을 처리할 수 없습니다.');
      error.upstream = true;
      throw error;
    }
    return data;
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw httpError(504, 'ARCHIVE_TIMEOUT', 'Archive 응답시간이 초과되었습니다.');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function text_(value, maxLength) {
  return String(value ?? '').trim().slice(0, maxLength);
}

function normalizeQuery_(body) {
  const raw = body && typeof body === 'object' ? body : {};
  const businessDate = text_(raw.businessDate, 10);
  if (businessDate && !/^\d{4}-\d{2}-\d{2}$/.test(businessDate)) {
    throw httpError(400, 'INVALID_BUSINESS_DATE', '영업일 형식을 확인해주세요.');
  }
  return {
    sourceType: text_(raw.sourceType || 'WORK_HISTORY', 40),
    businessDate,
    site: text_(raw.site, 80),
    roomNo: text_(raw.roomNo, 40),
    employeeNo: text_(raw.employeeNo, 50),
    recordType: text_(raw.recordType, 80),
    archiveKey: text_(raw.archiveKey, 160),
    limit: Math.max(1, Math.min(Number(raw.limit || 100) || 100, 200))
  };
}

app.get('/health', async (_req, res) => {
  let dbOk = false;
  let vaultAccess = false;
  try {
    await pool.query('select 1');
    dbOk = true;
    const token = await getArchiveRestoreToken_();
    vaultAccess = token.length >= 40;
  } catch (error) {
    console.error('[archive-gateway] health:', error?.message || error);
  }
  const ok = dbOk && vaultAccess;
  res.status(ok ? 200 : 503).json({ ok, build: BUILD, db: dbOk, vaultAccess });
});

app.post('/v1/archive/status', requireArchiveAdmin_, async (_req, res, next) => {
  try {
    const result = await callArchiveEdge_('nova-archive-status-v1', {}, 20000);
    res.json(result);
  } catch (error) {
    next(error);
  }
});

app.post('/v1/archive/query', requireArchiveAdmin_, async (req, res, next) => {
  try {
    const filters = normalizeQuery_(req.body);
    const result = await callArchiveEdge_('nova-archive-query-v1', filters, 25000);
    res.json(result);
  } catch (error) {
    next(error);
  }
});

app.post('/v1/archive/restore', requireArchiveAdmin_, async (req, res, next) => {
  try {
    const archiveKey = text_(req.body?.archiveKey, 160);
    if (!archiveKey) throw httpError(400, 'ARCHIVE_KEY_REQUIRED', 'Archive Key가 필요합니다.');
    const result = await callArchiveEdge_('nova-archive-restore-v1', { archiveKey }, 60000);
    res.json(result);
  } catch (error) {
    next(error);
  }
});

app.use((err, _req, res, _next) => {
  const status = Number(err?.status || 500);
  if (status >= 500) console.error('[archive-gateway]', err);
  res.status(status).json({
    ok: false,
    code: err?.code || 'INTERNAL_ERROR',
    message: status >= 500 ? '서버 처리 중 오류가 발생했습니다.' : String(err?.message || '요청을 처리할 수 없습니다.')
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`NOVA Archive Gateway ${BUILD} :${PORT}`);
});
