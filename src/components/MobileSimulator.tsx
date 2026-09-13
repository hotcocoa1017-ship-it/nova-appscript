'use client';

import React, { useState } from 'react';
import { HousemanOrder, RoomActionType, RoomEntity } from '@/lib/types';
import { Play, Check, AlertCircle, Smartphone, User, ShieldCheck, ArrowRight, Package } from 'lucide-react';
import { HOUSEKEEPERS } from './HousekeepingTab';

interface MobileSimulatorProps {
  rooms: RoomEntity[];
  orders: HousemanOrder[];
  onExecuteRoomAction: (roomNo: string, action: RoomActionType, version: number) => Promise<boolean>;
  onUpdateOrderStatus: (orderId: string, status: any) => Promise<void>;
}

export const MobileSimulator: React.FC<MobileSimulatorProps> = ({
  rooms,
  orders,
  onExecuteRoomAction,
  onUpdateOrderStatus
}) => {
  const [activeMode, setActiveMode] = useState<'maid' | 'houseman'>('maid');
  const [selectedMaidId, setSelectedMaidId] = useState<string>('1001'); // 김순자
  const [selectedHousemanId, setSelectedHousemanId] = useState<string>('hm-3'); // 한지훈
  const [operatingRoomNo, setOperatingRoomNo] = useState<string | null>(null);

  const currentMaid = HOUSEKEEPERS.find(m => m.id === selectedMaidId) || HOUSEKEEPERS[0];

  // Maid assigned rooms
  const maidRooms = rooms.filter(r => r.roommaidEmployeeNo === selectedMaidId);

  // Houseman assigned orders
  const housemanOrders = orders.filter(o => o.assignedEmployeeNo === selectedHousemanId);

  const handleMaidAction = async (room: RoomEntity, action: RoomActionType) => {
    setOperatingRoomNo(room.roomNo);
    try {
      await onExecuteRoomAction(room.roomNo, action, room.version);
    } finally {
      setOperatingRoomNo(null);
    }
  };

  return (
    <div className="p-4 flex flex-col items-center justify-center min-h-[calc(100vh-140px)]">
      {/* Device Frame Simulation */}
      <div className="w-full max-w-sm bg-slate-900 rounded-[40px] p-3 shadow-2xl border-4 border-slate-700">
        {/* Device Top Speaker & Camera Notch */}
        <div className="w-full flex justify-center mb-2">
          <div className="w-24 h-4 bg-slate-800 rounded-full flex items-center justify-center">
            <div className="w-2.5 h-2.5 rounded-full bg-slate-900 border border-slate-700"></div>
          </div>
        </div>

        {/* Device Screen */}
        <div className="bg-slate-50 rounded-[32px] overflow-hidden flex flex-col h-[650px] border border-slate-300">
          {/* Mobile Top Header */}
          <div className="bg-white px-4 py-3 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></div>
              <span className="text-xs font-black text-slate-900">NOVA MOBILE</span>
            </div>

            {/* Mode Switcher Tabs */}
            <div className="flex bg-slate-100 p-0.5 rounded-lg text-[11px] font-extrabold">
              <button
                onClick={() => setActiveMode('maid')}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  activeMode === 'maid' ? 'bg-white text-blue-700 shadow-2xs' : 'text-slate-500'
                }`}
              >
                룸메이드
              </button>
              <button
                onClick={() => setActiveMode('houseman')}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  activeMode === 'houseman' ? 'bg-white text-blue-700 shadow-2xs' : 'text-slate-500'
                }`}
              >
                하우스맨
              </button>
            </div>
          </div>

          {/* User Selector Dropdown */}
          <div className="bg-slate-100 px-4 py-2 border-b border-slate-200 flex items-center justify-between text-xs">
            <span className="font-bold text-slate-600">작업자 계정:</span>
            {activeMode === 'maid' ? (
              <select
                value={selectedMaidId}
                onChange={(e) => setSelectedMaidId(e.target.value)}
                className="bg-white border border-slate-300 font-bold rounded-md px-2 py-1 text-slate-800 text-xs"
              >
                {HOUSEKEEPERS.map(h => (
                  <option key={h.id} value={h.id}>{h.name} 메이드</option>
                ))}
              </select>
            ) : (
              <select
                value={selectedHousemanId}
                onChange={(e) => setSelectedHousemanId(e.target.value)}
                className="bg-white border border-slate-300 font-bold rounded-md px-2 py-1 text-slate-800 text-xs"
              >
                <option value="hm-1">강민우 (2F)</option>
                <option value="hm-2">정태양 (5F)</option>
                <option value="hm-3">한지훈 (3F)</option>
                <option value="hm-4">조진우 (4F)</option>
              </select>
            )}
          </div>

          {/* Mobile Screen Body */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
            {activeMode === 'maid' ? (
              // 1. Roommaid Mobile Flow
              <>
                <div className="text-xs font-bold text-slate-600 px-1 flex justify-between">
                  <span>내 배정 객실 ({maidRooms.length}실)</span>
                  <span className="text-blue-600 font-extrabold">
                    {maidRooms.filter(r => r.cleaningStatus === 'QM_WAITING' || r.cleaningStatus === 'QM_COMPLETED').length}실 완료
                  </span>
                </div>

                {maidRooms.map(room => {
                  const isOperating = operatingRoomNo === room.roomNo;
                  const isCleaning = room.cleaningStatus === 'CLEANING';
                  const isCompleted = room.cleaningStatus === 'QM_WAITING' || room.cleaningStatus === 'QM_COMPLETED';

                  return (
                    <div
                      key={room.roomNo}
                      className="bg-white p-3 rounded-xl border border-slate-200 shadow-2xs space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-base font-black text-slate-900">{room.roomNo}호</span>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-slate-100 font-bold text-slate-600">
                            {room.roomType.split(' ')[0]}
                          </span>
                        </div>
                        <span
                          className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full border ${
                            isCompleted
                              ? 'bg-purple-50 text-purple-700 border-purple-200'
                              : isCleaning
                              ? 'bg-amber-50 text-amber-700 border-amber-300 animate-pulse'
                              : 'bg-rose-50 text-rose-700 border-rose-200'
                          }`}
                        >
                          {isCompleted ? '점검대기' : isCleaning ? '청소진행중' : '청소대기'}
                        </span>
                      </div>

                      {/* Maid Large Touch Action Buttons (Min height 44px) */}
                      <div className="pt-1">
                        {!isCleaning && !isCompleted && (
                          <button
                            onClick={() => handleMaidAction(room, 'CLEANING_START')}
                            disabled={isOperating}
                            className="w-full min-h-[44px] rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-extrabold text-xs flex items-center justify-center gap-2 shadow-xs active:scale-98 transition-all"
                          >
                            <Play className="w-4 h-4 fill-white" />
                            <span>청소 시작</span>
                          </button>
                        )}

                        {isCleaning && (
                          <button
                            onClick={() => handleMaidAction(room, 'CLEANING_COMPLETE')}
                            disabled={isOperating}
                            className="w-full min-h-[44px] rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold text-xs flex items-center justify-center gap-2 shadow-xs active:scale-98 transition-all"
                          >
                            <Check className="w-4 h-4" />
                            <span>청소 완료 (점검요청)</span>
                          </button>
                        )}

                        {isCompleted && (
                          <div className="min-h-[44px] rounded-xl bg-slate-100 flex items-center justify-center text-xs font-bold text-slate-500">
                            ✓ 점검 대기중 (승인 완료 대기)
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}

                {maidRooms.length === 0 && (
                  <div className="p-8 text-center text-slate-400 text-xs font-bold">
                    배정된 객실이 없습니다.
                  </div>
                )}
              </>
            ) : (
              // 2. Houseman Mobile Flow
              <>
                <div className="text-xs font-bold text-slate-600 px-1 flex justify-between">
                  <span>내 배정 오더 ({housemanOrders.length}건)</span>
                </div>

                {housemanOrders.map(order => (
                  <div
                    key={order.orderId}
                    className="bg-white p-3 rounded-xl border border-slate-200 shadow-2xs space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-black text-slate-900">{order.roomNo}호</span>
                      <span
                        className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                          order.status === 'COMPLETED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : order.status === 'PROCESSING'
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-blue-100 text-blue-800'
                        }`}
                      >
                        {order.status}
                      </span>
                    </div>

                    <div className="text-xs font-bold text-slate-800">
                      {order.itemSummary} ({order.quantity}개)
                    </div>

                    {/* Houseman Large Buttons */}
                    <div className="pt-1 flex gap-2">
                      {order.status === 'ASSIGNED' && (
                        <button
                          onClick={() => onUpdateOrderStatus(order.orderId, 'PROCESSING')}
                          className="flex-1 min-h-[44px] rounded-xl bg-blue-600 text-white font-extrabold text-xs flex items-center justify-center gap-1 shadow-xs active:scale-98"
                        >
                          <Play className="w-3.5 h-3.5" />
                          <span>접수 및 출발</span>
                        </button>
                      )}

                      {order.status === 'PROCESSING' && (
                        <button
                          onClick={() => onUpdateOrderStatus(order.orderId, 'COMPLETED')}
                          className="flex-1 min-h-[44px] rounded-xl bg-emerald-600 text-white font-extrabold text-xs flex items-center justify-center gap-1 shadow-xs active:scale-98"
                        >
                          <Check className="w-3.5 h-3.5" />
                          <span>전달 완료</span>
                        </button>
                      )}

                      {order.status !== 'COMPLETED' && order.status !== 'UNABLE' && (
                        <button
                          onClick={() => onUpdateOrderStatus(order.orderId, 'UNABLE')}
                          className="px-3 min-h-[44px] rounded-xl bg-slate-100 hover:bg-rose-50 text-slate-600 hover:text-rose-700 font-bold text-xs"
                        >
                          불가
                        </button>
                      )}
                    </div>
                  </div>
                ))}

                {housemanOrders.length === 0 && (
                  <div className="p-8 text-center text-slate-400 text-xs font-bold">
                    현재 진행 중인 오더가 없습니다.
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
