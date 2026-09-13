'use client';

import React from 'react';
import { RefreshCw, Wifi, WifiOff, UserCheck, KeyRound } from 'lucide-react';
import { RealtimeConnectionStatus } from '@/lib/supabase';
import { NovaUser } from '@/lib/types';

interface TopbarProps {
  connectionStatus: RealtimeConnectionStatus;
  currentDateText: string;
  currentUser: NovaUser | null;
  onOpenLogin: () => void;
  onRefresh: () => void;
  isRefreshing?: boolean;
}

export const Topbar: React.FC<TopbarProps> = ({
  connectionStatus,
  currentDateText,
  currentUser,
  onOpenLogin,
  onRefresh,
  isRefreshing = false
}) => {
  const getStatusBadge = () => {
    switch (connectionStatus) {
      case 'CONNECTED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            실시간 연동 정상
          </span>
        );
      case 'CONNECTING':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-spin"></span>
            실시간 재연결중...
          </span>
        );
      case 'DISCONNECTED':
      case 'ERROR':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <WifiOff className="w-3.5 h-3.5 text-rose-500" />
            오프라인 모드
          </span>
        );
    }
  };

  return (
    <header className="sticky top-0 z-40 bg-white border-b border-slate-200 px-4 py-2.5 flex items-center justify-between shadow-xs">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="text-xl font-black tracking-tight text-slate-900">NOVA</span>
          <span className="w-2 h-2 rounded-full bg-blue-600"></span>
        </div>
        <span className="text-xs font-extrabold text-slate-600 tracking-wide">ROOM MANAGEMENT</span>
        <span className="hidden sm:inline-block px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[11px] font-bold">
          v3.0 Enterprise
        </span>
      </div>

      <div className="hidden md:flex items-center gap-2 text-xs font-semibold text-slate-600">
        <span>{currentDateText}</span>
        <span className="text-slate-300">|</span>
        <span className="text-blue-600 font-bold">주간 정규 시프트 (D-Shift)</span>
        <span className="text-slate-300">|</span>
        <span className="text-slate-500">사업장: <b>설악 쏘라노 (SORA)</b></span>
      </div>

      <div className="flex items-center gap-2.5">
        {/* User Account / Role Badge */}
        <button
          onClick={onOpenLogin}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-xs font-bold text-slate-800 transition-all active:scale-95"
          title="작업자 계정 전환"
        >
          <UserCheck className="w-3.5 h-3.5 text-blue-600" />
          <span>{currentUser?.name || '로그인 필요'}</span>
          <span className="px-1.5 py-0.2 rounded bg-blue-100 text-blue-800 text-[10px] font-extrabold">
            {currentUser?.role || 'GUEST'}
          </span>
        </button>

        {getStatusBadge()}

        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-bold text-slate-700 active:scale-95 transition-all disabled:opacity-50"
          title="최신 DB 데이터 새로고침"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          <span>동기화</span>
        </button>
      </div>
    </header>
  );
};
