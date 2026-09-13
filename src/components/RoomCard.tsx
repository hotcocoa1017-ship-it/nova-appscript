'use client';

import React from 'react';
import { RoomEntity } from '@/lib/types';
import { MoreHorizontal } from 'lucide-react';

interface RoomCardProps {
  room: RoomEntity;
  onClick: (room: RoomEntity) => void;
}

export const RoomCard: React.FC<RoomCardProps> = React.memo(({ room, onClick }) => {
  // 미니멀리즘 엔터프라이즈 UI 뱃지 결정
  const getStatusPresentation = () => {
    if (room.roomStatus === 'OOO') return { label1: '고장', label2: 'OOO', color: 'text-slate-600 bg-slate-100 border-slate-200' };
    
    if (room.cleaningStatus === 'CLEANING') return { label1: '청소', label2: '진행', color: 'text-purple-600 bg-purple-50 border-purple-200' };
    
    if (room.cleaningStatus === 'QM_WAITING') return { label1: '점검', label2: '대기', color: 'text-purple-600 bg-purple-50 border-purple-200' };

    if (room.roomStatus === 'VACANT_CLEAN') return { label1: '공실', label2: 'VC', color: 'text-emerald-600 bg-emerald-50 border-emerald-200' };

    if (room.roomStatus === 'CHECKED_OUT') return { label1: '퇴실', label2: 'VD', color: 'text-rose-600 bg-rose-50 border-rose-200' };

    const isClean = room.cleaningStatus === 'NOT_REQUIRED' || room.cleaningStatus === 'COMPLETED';
    return {
      label1: '재실',
      label2: isClean ? 'OC' : 'OD',
      color: isClean ? 'text-blue-600 bg-blue-50 border-blue-200' : 'text-orange-600 bg-orange-50 border-orange-200'
    };
  };

  const style = getStatusPresentation();

  return (
    <div
      onClick={() => onClick(room)}
      role="button"
      tabIndex={0}
      className="relative flex flex-col justify-between p-3.5 rounded-xl border border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm active:bg-slate-50 transition-all duration-150 cursor-pointer min-h-[88px]"
    >
      {/* Top Header: Room No & More Menu */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <span className="text-[17px] font-extrabold text-slate-800 tracking-tight leading-none">{room.roomNo}</span>
        </div>
        <button className="text-slate-400 hover:text-slate-600 transition-colors">
          <MoreHorizontal className="w-4 h-4" />
        </button>
      </div>

      {/* Bottom Footer: Status Badge & Assignee */}
      <div className="flex items-center justify-between mt-auto w-full gap-1 overflow-hidden">
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-[10px] font-semibold text-slate-500 whitespace-nowrap">{style.label1}</span>
          <span className={`text-[9px] font-bold px-1 py-0.5 rounded border ${style.color} whitespace-nowrap`}>
            {style.label2}
          </span>
          {room.dnd && (
            <span className="text-[9px] font-bold px-1 py-0.5 rounded border text-rose-600 bg-rose-50 border-rose-200 whitespace-nowrap">
              DND
            </span>
          )}
        </div>

        <div className="flex flex-col items-end gap-0.5 min-w-0 flex-1 text-right">
          {room.roommaidName && (
            <span className="text-[10px] font-medium text-slate-600 truncate w-full block" title={room.roommaidName}>
              {room.roommaidName}
            </span>
          )}
          {room.qmName && (
            <span className="text-[9px] font-bold text-purple-600 truncate w-full block" title={`QM: ${room.qmName}`}>
              QM:{room.qmName.replace('QM', '')}
            </span>
          )}
        </div>
      </div>
    </div>
  );
});

RoomCard.displayName = 'RoomCard';
