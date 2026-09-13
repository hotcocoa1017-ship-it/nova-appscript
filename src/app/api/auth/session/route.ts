import { NextRequest, NextResponse } from 'next/server';
import { authenticateRequest, RBAC_PERMISSIONS_TABLE } from '@/lib/auth';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  try {
    const user = authenticateRequest(request);
    const permissions = RBAC_PERMISSIONS_TABLE[user.role];

    return NextResponse.json({
      ok: true,
      user,
      permissions
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, message: error.message || '인증 세션이 유효하지 않습니다.' },
      { status: 401 }
    );
  }
}
