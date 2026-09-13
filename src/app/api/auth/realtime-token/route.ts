import { NextRequest, NextResponse } from 'next/server';
import crypto from 'crypto';
import { authenticateRequest } from '@/lib/auth';

export const dynamic = 'force-dynamic';

function createJwtHS256(payload: Record<string, unknown>, secret: string): string {
  const header = { alg: 'HS256', typ: 'JWT' };
  const encodedHeader = Buffer.from(JSON.stringify(header)).toString('base64url');
  const encodedPayload = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const signature = crypto
    .createHmac('sha256', secret)
    .update(`${encodedHeader}.${encodedPayload}`)
    .digest('base64url');

  return `${encodedHeader}.${encodedPayload}.${signature}`;
}

export async function POST(request: NextRequest) {
  try {
    const user = authenticateRequest(request);

    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
    const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';
    const jwtSecret = process.env.SUPABASE_JWT_SECRET || process.env.NOVA_TOKEN_SECRET || 'dev-secret';

    const now = Math.floor(Date.now() / 1000);
    const sites = user.allowedSites.length > 0 ? user.allowedSites : [user.defaultSite || 'SORA'];

    const token = createJwtHS256(
      {
        aud: 'authenticated',
        role: 'authenticated',
        sub: user.employeeNo,
        employee_no: user.employeeNo,
        nova_role: user.role,
        sites,
        iat: now,
        exp: now + 15 * 60 // 15 minutes
      },
      jwtSecret
    );

    return NextResponse.json({
      ok: true,
      token,
      expiresIn: 900,
      supabaseUrl,
      publishableKey,
      sites
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, message: error.message || 'Realtime 토큰 발급에 실패했습니다.' },
      { status: 401 }
    );
  }
}
