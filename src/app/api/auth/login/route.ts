import { NextRequest, NextResponse } from 'next/server';
import { createNovaSessionToken, RBAC_PERMISSIONS_TABLE } from '@/lib/auth';
import { getDbPool } from '@/lib/db';
import { NovaUser, UserRole } from '@/lib/types';

export const dynamic = 'force-dynamic';

// Seeded staff accounts for reliable login
const SEED_USERS: Record<string, { name: string; role: UserRole }> = {
  'ADMIN-01': { name: '총괄관리자', role: 'SUPER_ADMIN' },
  'MGR-01': { name: '객실지배인', role: 'MANAGER' },
  'QM-2001': { name: '강QM', role: 'QM' },
  'QM-2002': { name: '이인스펙터', role: 'INSPECTOR' },
  '1001': { name: '김순자', role: 'ROOM_MAID' },
  '1002': { name: '박영희', role: 'ROOM_MAID' },
  '1003': { name: '이정숙', role: 'ROOM_MAID' },
  '1004': { name: '최미경', role: 'ROOM_MAID' },
  'hm-1': { name: '강민우', role: 'HOUSEMAN' },
  'hm-2': { name: '정태양', role: 'HOUSEMAN' },
  'hm-3': { name: '한지훈', role: 'HOUSEMAN' },
  'hm-4': { name: '조진우', role: 'HOUSEMAN' }
};

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const employeeNo = String(body.employeeNo || '').trim();

    if (!employeeNo) {
      return NextResponse.json(
        { ok: false, message: '사번을 입력해 주세요.' },
        { status: 400 }
      );
    }

    let user: NovaUser | null = null;
    const pool = getDbPool();

    if (pool) {
      try {
        const client = await pool.connect();
        try {
          const { rows } = await client.query(
            `SELECT employee_no, name, role, enabled, default_site, allowed_sites
             FROM public.nova_users
             WHERE employee_no = $1`,
            [employeeNo]
          );
          if (rows[0] && rows[0].enabled) {
            user = {
              employeeNo: rows[0].employee_no,
              name: rows[0].name,
              role: rows[0].role as UserRole,
              enabled: rows[0].enabled,
              defaultSite: rows[0].default_site,
              allowedSites: rows[0].allowed_sites || ['SORA']
            };
          }
        } finally {
          client.release();
        }
      } catch (err) {
        console.warn('[DB User Login Warning, falling back to seed]:', err);
      }
    }

    // Fallback to in-memory staff seed
    if (!user) {
      const found = SEED_USERS[employeeNo];
      if (found) {
        user = {
          employeeNo,
          name: found.name,
          role: found.role,
          enabled: true,
          defaultSite: 'SORA',
          allowedSites: ['SORA']
        };
      }
    }

    if (!user) {
      return NextResponse.json(
        { ok: false, message: '등록되지 않았거나 비활성화된 사번입니다.' },
        { status: 401 }
      );
    }

    const token = createNovaSessionToken(user);
    const permissions = RBAC_PERMISSIONS_TABLE[user.role];

    return NextResponse.json({
      ok: true,
      token,
      user,
      permissions,
      expiresIn: 12 * 3600
    });
  } catch (error: any) {
    console.error('[Login Error]:', error);
    return NextResponse.json(
      { ok: false, message: error.message || '로그인 처리 중 오류가 발생했습니다.' },
      { status: 500 }
    );
  }
}
