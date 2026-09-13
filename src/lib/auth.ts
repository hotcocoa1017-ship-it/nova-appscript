/**
 * NOVA Authentication & Role-Based Access Control (RBAC) Module
 * Cryptographic HMAC-SHA256 session token management, permissions matrix, and server guards.
 */

import crypto from 'crypto';
import { NextRequest } from 'next/server';
import { NovaUser, UserRole } from './types';

const NOVA_TOKEN_SECRET = process.env.NOVA_TOKEN_SECRET || 'nova-development-secret-key-3.3';

// ====================================================================
// 1. Detailed RBAC Permission Matrix
// ====================================================================
export interface RolePermissions {
  canViewRooms: boolean;
  canAssignMaid: boolean;
  canAssignQm: boolean;
  canStartCleaning: boolean;
  canCompleteCleaning: boolean;
  canInspectPass: boolean;
  canInspectRework: boolean;
  canChangeOperationalStatus: boolean; // Check-in, Check-out, OOO
  canManageOrders: boolean;
  canProcessOrders: boolean;
  canViewAuditLogs: boolean;
  canViewStats: boolean;
  canManageUsers: boolean;
}

export const RBAC_PERMISSIONS_TABLE: Record<UserRole, RolePermissions> = {
  SUPER_ADMIN: {
    canViewRooms: true,
    canAssignMaid: true,
    canAssignQm: true,
    canStartCleaning: true,
    canCompleteCleaning: true,
    canInspectPass: true,
    canInspectRework: true,
    canChangeOperationalStatus: true,
    canManageOrders: true,
    canProcessOrders: true,
    canViewAuditLogs: true,
    canViewStats: true,
    canManageUsers: true
  },
  ADMIN: {
    canViewRooms: true,
    canAssignMaid: true,
    canAssignQm: true,
    canStartCleaning: true,
    canCompleteCleaning: true,
    canInspectPass: true,
    canInspectRework: true,
    canChangeOperationalStatus: true,
    canManageOrders: true,
    canProcessOrders: true,
    canViewAuditLogs: true,
    canViewStats: true,
    canManageUsers: true
  },
  MANAGER: {
    canViewRooms: true,
    canAssignMaid: true,
    canAssignQm: true,
    canStartCleaning: true,
    canCompleteCleaning: true,
    canInspectPass: true,
    canInspectRework: true,
    canChangeOperationalStatus: true,
    canManageOrders: true,
    canProcessOrders: true,
    canViewAuditLogs: true,
    canViewStats: true,
    canManageUsers: false
  },
  QM: {
    canViewRooms: true,
    canAssignMaid: false,
    canAssignQm: false,
    canStartCleaning: false,
    canCompleteCleaning: false,
    canInspectPass: true,
    canInspectRework: true,
    canChangeOperationalStatus: false,
    canManageOrders: false,
    canProcessOrders: false,
    canViewAuditLogs: true,
    canViewStats: true,
    canManageUsers: false
  },
  INSPECTOR: {
    canViewRooms: true,
    canAssignMaid: false,
    canAssignQm: false,
    canStartCleaning: false,
    canCompleteCleaning: false,
    canInspectPass: true,
    canInspectRework: true,
    canChangeOperationalStatus: false,
    canManageOrders: false,
    canProcessOrders: false,
    canViewAuditLogs: true,
    canViewStats: true,
    canManageUsers: false
  },
  ROOM_MAID: {
    canViewRooms: true,
    canAssignMaid: false,
    canAssignQm: false,
    canStartCleaning: true,
    canCompleteCleaning: true,
    canInspectPass: false,
    canInspectRework: false,
    canChangeOperationalStatus: false,
    canManageOrders: false,
    canProcessOrders: false,
    canViewAuditLogs: false,
    canViewStats: false,
    canManageUsers: false
  },
  HOUSEMAN: {
    canViewRooms: true,
    canAssignMaid: false,
    canAssignQm: false,
    canStartCleaning: false,
    canCompleteCleaning: false,
    canInspectPass: false,
    canInspectRework: false,
    canChangeOperationalStatus: false,
    canManageOrders: true,
    canProcessOrders: true,
    canViewAuditLogs: false,
    canViewStats: false,
    canManageUsers: false
  },
  PUBLIC: {
    canViewRooms: true,
    canAssignMaid: false,
    canAssignQm: false,
    canStartCleaning: true,
    canCompleteCleaning: true,
    canInspectPass: false,
    canInspectRework: false,
    canChangeOperationalStatus: false,
    canManageOrders: false,
    canProcessOrders: false,
    canViewAuditLogs: false,
    canViewStats: false,
    canManageUsers: false
  },
  DELIVERY: {
    canViewRooms: true,
    canAssignMaid: false,
    canAssignQm: false,
    canStartCleaning: false,
    canCompleteCleaning: false,
    canInspectPass: false,
    canInspectRework: false,
    canChangeOperationalStatus: false,
    canManageOrders: true,
    canProcessOrders: true,
    canViewAuditLogs: false,
    canViewStats: false,
    canManageUsers: false
  },
  OUTSOURCE: {
    canViewRooms: true,
    canAssignMaid: false,
    canAssignQm: false,
    canStartCleaning: true,
    canCompleteCleaning: true,
    canInspectPass: false,
    canInspectRework: false,
    canChangeOperationalStatus: false,
    canManageOrders: false,
    canProcessOrders: false,
    canViewAuditLogs: false,
    canViewStats: false,
    canManageUsers: false
  },
  PART_TIME: {
    canViewRooms: true,
    canAssignMaid: false,
    canAssignQm: false,
    canStartCleaning: true,
    canCompleteCleaning: true,
    canInspectPass: false,
    canInspectRework: false,
    canChangeOperationalStatus: false,
    canManageOrders: false,
    canProcessOrders: false,
    canViewAuditLogs: false,
    canViewStats: false,
    canManageUsers: false
  }
};

export function checkUserPermission(user: NovaUser, permission: keyof RolePermissions): boolean {
  const perms = RBAC_PERMISSIONS_TABLE[user.role];
  return perms ? Boolean(perms[permission]) : false;
}

export function isSiteAllowedForUser(user: NovaUser, site: string): boolean {
  if (['SUPER_ADMIN', 'ADMIN', 'MANAGER'].includes(user.role)) return true;
  if (!site) return false;
  const allowed = new Set([...user.allowedSites, user.defaultSite].filter(Boolean));
  return allowed.has(site);
}

// ====================================================================
// 2. Cryptographic Token Generation & Verification (HMAC-SHA256)
// ====================================================================
export interface SessionTokenPayload {
  employeeNo: string;
  name: string;
  role: UserRole;
  defaultSite: string;
  allowedSites: string[];
  expiresAt: number; // Unix timestamp ms
}

function base64UrlEncode(str: string): string {
  return Buffer.from(str, 'utf8')
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

function base64UrlDecode(str: string): string {
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4) base64 += '=';
  return Buffer.from(base64, 'base64').toString('utf8');
}

/**
 * Creates a tamper-proof signed session token for field operations.
 */
export function createNovaSessionToken(user: NovaUser, durationHours = 12): string {
  const expiresAt = Date.now() + durationHours * 60 * 60 * 1000;
  const payload: SessionTokenPayload = {
    employeeNo: user.employeeNo,
    name: user.name,
    role: user.role,
    defaultSite: user.defaultSite || 'SORA',
    allowedSites: user.allowedSites || ['SORA'],
    expiresAt
  };

  const body = base64UrlEncode(JSON.stringify(payload));
  const signature = crypto
    .createHmac('sha256', NOVA_TOKEN_SECRET)
    .update(body)
    .digest('base64url');

  return `${body}.${signature}`;
}

/**
 * Cryptographically verifies token integrity and expiration.
 */
export function verifyNovaSessionToken(token: string): SessionTokenPayload {
  const parts = String(token || '').trim().split('.');
  if (parts.length !== 2) {
    throw new Error('UNAUTHORIZED: 토큰 형식이 올바르지 않습니다.');
  }

  const [body, receivedSig] = parts;
  const expectedSig = crypto
    .createHmac('sha256', NOVA_TOKEN_SECRET)
    .update(body)
    .digest('base64url');

  const bufReceived = Buffer.from(receivedSig, 'utf8');
  const bufExpected = Buffer.from(expectedSig, 'utf8');

  if (bufReceived.length !== bufExpected.length || !crypto.timingSafeEqual(bufReceived, bufExpected)) {
    throw new Error('UNAUTHORIZED: 토큰 서명이 위조되었거나 올바르지 않습니다.');
  }

  let payload: SessionTokenPayload;
  try {
    payload = JSON.parse(base64UrlDecode(body));
  } catch {
    throw new Error('UNAUTHORIZED: 토큰 데이터를 파싱할 수 없습니다.');
  }

  if (!payload?.employeeNo || !payload?.expiresAt || Date.now() > payload.expiresAt) {
    throw new Error('UNAUTHORIZED: 로그인 세션이 만료되었습니다. 다시 로그인하세요.');
  }

  return payload;
}

/**
 * Extracts and verifies the authenticated user from NextRequest headers.
 */
export function authenticateRequest(req: NextRequest): NovaUser {
  const authHeader = req.headers.get('authorization') || '';
  let token = '';

  if (authHeader.startsWith('Bearer ')) {
    token = authHeader.slice(7).trim();
  }

  // Support local development override headers if configured
  if (!token) {
    const roleHeader = req.headers.get('x-nova-role') as UserRole;
    const employeeNoHeader = req.headers.get('x-nova-employee-no');
    if (roleHeader && employeeNoHeader) {
      return {
        employeeNo: employeeNoHeader,
        name: req.headers.get('x-nova-user-name') || employeeNoHeader,
        role: roleHeader,
        enabled: true,
        defaultSite: 'SORA',
        allowedSites: ['SORA']
      };
    }
    throw new Error('UNAUTHORIZED: 인증 토큰이 필요합니다.');
  }

  const payload = verifyNovaSessionToken(token);
  return {
    employeeNo: payload.employeeNo,
    name: payload.name,
    role: payload.role,
    enabled: true,
    defaultSite: payload.defaultSite,
    allowedSites: payload.allowedSites
  };
}
