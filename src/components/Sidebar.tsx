'use client';

import React from 'react';
import { LayoutGrid, Sparkles, Package, Smartphone, BarChart3, ShieldCheck, UserCheck } from 'lucide-react';
import { UserRole } from '@/lib/types';

export type ActiveTab = 'indicator' | 'housekeeping' | 'orders' | 'mobile' | 'report';

interface SidebarProps {
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  currentRole: UserRole;
  onRoleChange: (role: UserRole) => void;
  roomCounts: {
    total: number;
    cleaningTarget: number;
    activeOrders: number;
  };
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  currentRole,
  onRoleChange,
  roomCounts
}) => {
  const menuItems = [
    {
      id: 'indicator' as ActiveTab,
      label: '객실 인디케이터',
      icon: LayoutGrid,
      badge: roomCounts.total
    },
    {
      id: 'housekeeping' as ActiveTab,
      label: '청소 배정 관리',
      icon: Sparkles,
      badge: roomCounts.cleaningTarget
    },
    {
      id: 'orders' as ActiveTab,
      label: '하우스맨 오더 관제',
      icon: Package,
      badge: roomCounts.activeOrders
    },
    {
      id: 'mobile' as ActiveTab,
      label: '현장 모바일 뷰어',
      icon: Smartphone
    },
    {
      id: 'report' as ActiveTab,
      label: '운영 통계 및 리포트',
      icon: BarChart3
    }
  ];

  return (
    <aside className="w-56 shrink-0 bg-white border-r border-slate-200 py-6 px-3 flex flex-col justify-between hidden md:flex min-h-[calc(100vh-53px)]">
      <div className="space-y-6">
        {/* Navigation Menus */}
        <nav className="space-y-1.5">
          {menuItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center justify-between px-4 py-2.5 rounded-md text-sm font-bold transition-all ${
                  isActive
                    ? 'bg-slate-900 text-white'
                    : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <div className="flex items-center gap-0">
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && item.badge > 0 && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold ${
                      isActive ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Hotel Summary Card */}
      <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 space-y-1">
        <strong className="block text-slate-900 font-bold mb-1">설악 쏘라노 (SORA)</strong>
        <div className="flex justify-between">
          <span>전체 관리 객실:</span>
          <span className="font-bold text-slate-800">{roomCounts.total}실 (2F~6F)</span>
        </div>
        <div className="flex justify-between">
          <span>출근 룸메이드:</span>
          <span className="font-bold text-emerald-600">4명 정원</span>
        </div>
        <div className="flex justify-between">
          <span>대기 하우스맨:</span>
          <span className="font-bold text-blue-600">4명 상시</span>
        </div>
      </div>
    </aside>
  );
};
