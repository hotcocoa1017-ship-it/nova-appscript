import { NextRequest, NextResponse } from 'next/server';
import { getRoomsForSite } from '@/lib/room-service';
import { NovaUser } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const businessDate = searchParams.get('businessDate') || '2026-09-13';
    const site = searchParams.get('site') || 'SORA';

    // Mock/Auth User context from headers or query (Supports admin, maid, qm)
    const roleHeader = request.headers.get('x-nova-role') || 'SUPER_ADMIN';
    const employeeNoHeader = request.headers.get('x-nova-employee-no') || 'ADMIN-01';

    const currentUser: NovaUser = {
      employeeNo: employeeNoHeader,
      name: '시스템 관리자',
      role: roleHeader as any,
      enabled: true,
      defaultSite: site,
      allowedSites: [site]
    };

    const rooms = await getRoomsForSite(businessDate, site, currentUser);

    return NextResponse.json({
      ok: true,
      businessDate,
      site,
      count: rooms.length,
      rooms,
      serverTime: new Date().toISOString()
    });
  } catch (error: any) {
    console.error('[GET /api/rooms Error]:', error);
    return NextResponse.json(
      { ok: false, message: error.message || '객실 목록 조회에 실패했습니다.' },
      { status: 500 }
    );
  }
}
