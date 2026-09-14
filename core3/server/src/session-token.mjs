import crypto from 'node:crypto';

function base64UrlJson(value) {
  return Buffer.from(JSON.stringify(value), 'utf8').toString('base64url');
}

function safeText(value) {
  return String(value ?? '').trim();
}

export function createSessionTokenSigner({ secret, ttlSeconds = 12 * 60 * 60, now = () => Date.now() } = {}) {
  const safeSecret = safeText(secret);
  const ttl = Math.max(300, Math.min(7 * 24 * 60 * 60, Number(ttlSeconds || 43200)));
  if (!safeSecret) throw new Error('SUPABASE_JWT_SECRET is required');

  function sign(user) {
    const employeeNo = safeText(user?.employeeNo);
    const name = safeText(user?.name);
    const role = safeText(user?.role).toUpperCase();
    const site = safeText(user?.sessionSite);
    if (!employeeNo || !role) throw new Error('session identity is incomplete');

    const issuedAt = Math.floor(Number(now()) / 1000);
    const expiresAt = issuedAt + ttl;
    const header = { alg: 'HS256', typ: 'JWT' };
    const payload = {
      aud: 'authenticated',
      role: 'authenticated',
      sub: employeeNo,
      employee_no: employeeNo,
      name,
      nova_role: role,
      site,
      iat: issuedAt,
      exp: expiresAt,
      iss: 'nova-core3',
    };
    const encodedHeader = base64UrlJson(header);
    const encodedPayload = base64UrlJson(payload);
    const signingInput = `${encodedHeader}.${encodedPayload}`;
    const signature = crypto.createHmac('sha256', safeSecret).update(signingInput).digest('base64url');
    return {
      accessToken: `${signingInput}.${signature}`,
      expiresAt: new Date(expiresAt * 1000).toISOString(),
      expiresIn: ttl,
      claims: payload,
    };
  }

  return { sign };
}

export function decodeJwtPayloadUnsafe(token) {
  const parts = safeText(token).split('.');
  if (parts.length !== 3) throw new Error('invalid jwt');
  return JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
}
