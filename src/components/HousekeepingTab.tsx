'use client';

import React, { useState } from 'react';
import { RoomEntity } from '@/lib/types';
import { Sparkles, Users, CheckCircle2, PlayCircle, Clock } from 'lucide-react';

interface HousekeepingTabProps {
  rooms: RoomEntity[];
  onBatchAssign: (assignments: { roomNo: string; maidId: string; maidName: string }[]) => Promise<void>;
}

export const HOUSEKEEPERS = [
  { id: '1001', name: '김순자', floors: [2, 3], phone: '010-3456-1001', maxCap: 14 },
  { id: '1002', name: '박영희', floors: [3, 4], phone: '010-3456-1002', maxCap: 14 },
  { id: '1003', name: '이정숙', floors: [4, 5], phone: '010-3456-1003', maxCap: 14 },
  { id: '1004', name: '최미경', floors: [5, 6], phone: '010-3456-1004', maxCap: 14 }
];

export const HousekeepingTab: React.FC<HousekeepingTabProps> = ({ rooms, onBatchAssign }) => {
  const [selectedMaid, setSelectedMaid] = useState<string>('1001');
  const [isAssigning, setIsAssigning] = useState(false);

  // Unassigned dirty rooms
  const unassignedRooms = rooms.filter(
    r => (r.roomStatus === 'CHECKED_OUT' || r.cleaningStatus === 'WAITING') && !r.roommaidEmployeeNo
  );

  // Compute maid progress statistics
  const maidStats = HOUSEKEEPERS.map(maid => {
    const maidRooms = rooms.filter(r => r.roommaidEmployeeNo === maid.id);
    const completed = maidRooms.filter(r => r.cleaningStatus === 'QM_WAITING' || r.cleaningStatus === 'QM_COMPLETED' || r.cleaningStatus === 'COMPLETED').length;
    const inProgress = maidRooms.filter(r => r.cleaningStatus === 'CLEANING').length;
    const waiting = maidRooms.filter(r => r.cleaningStatus === 'WAITING' || r.cleaningStatus === 'ASSIGNED').length;
    const total = maidRooms.length;
    const progressPercent = total > 0 ? Math.round((completed / total) * 100) : 0;

    return {
      ...maid,
      total,
      completed,
      inProgress,
      waiting,
      progressPercent,
      rooms: maidRooms
    };
  });

  // Smart Auto-Assign Algorithm (Floor affinity & equal distribution)
  const handleAutoAssign = async () => {
    if (unassignedRooms.length === 0 || isAssigning) return;
    setIsAssigning(true);

    try {
      const assignments: { roomNo: string; maidId: string; maidName: string }[] = [];
      const statsCopy = [...maidStats];

      unassignedRooms.forEach(room => {
        // Prioritize maids with assigned floor affinity
        const preferredMaids = statsCopy.filter(m => m.floors.includes(room.floor));
        const candidatePool = preferredMaids.length > 0 ? preferredMaids : statsCopy;

        // Pick maid with lowest current workload
        candidatePool.sort((a, b) => a.total - b.total);
        const bestMaid = candidatePool[0];

        assignments.push({
          roomNo: room.roomNo,
          maidId: bestMaid.id,
          maidName: bestMaid.name
        });

        bestMaid.total += 1;
      });

      await onBatchAssign(assignments);
    } finally {
      setIsAssigning(false);
    }
  };

  return (
    <div className="p-4 space-y-4">
      {/* Top Banner & Auto-Assign Action */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-2xs flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-black text-slate-900 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-amber-500 fill-amber-500" />
            <span>룸메이드 청소 배정 및 작업 현황 관리</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            미배정 퇴실 객실({unassignedRooms.length}실)을 담당 층 동선과 업무 부하에 맞춰 원클릭으로 균등 자동 배정합니다.
          </p>
        </div>

        <button
          onClick={handleAutoAssign}
          disabled={unassignedRooms.length === 0 || isAssigning}
          className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-xs flex items-center gap-2 shadow-xs transition-all active:scale-95 disabled:opacity-40"
        >
          <Sparkles className="w-4 h-4" />
          <span>{isAssigning ? '배정 처리중...' : `미배정 ${unassignedRooms.length}실 스마트 자동배정`}</span>
        </button>
      </div>

      {/* Maid Progress Dashboard Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {maidStats.map(stat => (
          <div key={stat.id} className="bg-white p-4 rounded-2xl border border-slate-200 shadow-2xs space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm font-black text-slate-900">{stat.name} 메이드</span>
                <span className="block text-[11px] font-semibold text-slate-400">전담: {stat.floors.join(', ')}층</span>
              </div>
              <span className="text-xs px-2 py-0.5 rounded-full font-extrabold bg-emerald-50 text-emerald-700 border border-emerald-200">
                근무중
              </span>
            </div>

            {/* Progress Bar */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs font-bold text-slate-700">
                <span>진행률 ({stat.progressPercent}%)</span>
                <span>{stat.completed} / {stat.total} 완료</span>
              </div>
              <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                  style={{ width: `${stat.progressPercent}%` }}
                ></div>
              </div>
            </div>

            {/* Micro Stats */}
            <div className="grid grid-cols-3 gap-1 pt-1 text-center text-xs">
              <div className="p-1.5 rounded-lg bg-slate-50">
                <span className="block text-[10px] text-slate-400">대기</span>
                <span className="font-extrabold text-slate-700">{stat.waiting}</span>
              </div>
              <div className="p-1.5 rounded-lg bg-amber-50">
                <span className="block text-[10px] text-amber-600">청소중</span>
                <span className="font-extrabold text-amber-800">{stat.inProgress}</span>
              </div>
              <div className="p-1.5 rounded-lg bg-emerald-50">
                <span className="block text-[10px] text-emerald-600">완료</span>
                <span className="font-extrabold text-emerald-800">{stat.completed}</span>
              </div>
            </div>

            {/* Assigned Rooms Chips */}
            <div className="pt-2 border-t border-slate-100">
              <span className="text-[10px] font-bold text-slate-400 block mb-1.5">배정 객실 목록:</span>
              <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                {stat.rooms.map(r => (
                  <span
                    key={r.roomNo}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                      r.cleaningStatus === 'QM_COMPLETED' || r.cleaningStatus === 'QM_WAITING'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : r.cleaningStatus === 'CLEANING'
                        ? 'bg-amber-50 text-amber-800 border-amber-300 animate-pulse'
                        : 'bg-slate-50 text-slate-700 border-slate-200'
                    }`}
                  >
                    {r.roomNo}
                  </span>
                ))}
                {stat.rooms.length === 0 && (
                  <span className="text-slate-400 text-xs italic">배정된 객실 없음</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
