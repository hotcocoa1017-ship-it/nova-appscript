'use client';

import React, { useState } from 'react';
import { RoomActionType, RoomEntity, UserRole } from '@/lib/types';
import { X, Play, Check, ShieldCheck, AlertOctagon, UserPlus, LogOut, Wrench, Moon, History, AlertCircle } from 'lucide-react';

interface RoomActionModalProps {
  room: RoomEntity | null;
  onClose: () => void;
  onExecuteAction: (action: RoomActionType, expectedVersion: number) => Promise<boolean>;
  onOpenHistory?: (room: RoomEntity) => void;
  currentUserRole: UserRole;
}

export const RoomActionModal: React.FC<RoomActionModalProps> = ({
  room,
  onClose,
  onExecuteAction,
  onOpenHistory,
  currentUserRole
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!room) return null;

  const handleActionClick = async (action: RoomActionType) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const success = await onExecuteAction(action, room.version);
      if (success) {
        onClose();
      }
    } catch (err: any) {
      setErrorMessage(err.message || '작업 처리 중 오류가 발생했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div className="flex items-center gap-2.5">
            <span className="text-2xl font-black text-slate-900">{room.roomNo}호</span>
            <span className="text-xs px-2.5 py-1 rounded-full font-bold bg-slate-200 text-slate-700">
              {room.building} · {room.roomType}
            </span>
            <span className="text-[11px] font-semibold text-slate-500">
              (버전: v{room.version})
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body: Current Details */}
        <div className="p-5 space-y-4">
          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-500 mt-0.5" />
              <div>{errorMessage}</div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 p-3.5 bg-slate-50 rounded-xl text-xs">
            <div>
              <span className="text-slate-400 block mb-0.5">객실 상태</span>
              <span className="font-extrabold text-slate-900">{room.roomStatus}</span>
            </div>
            <div>
              <span className="text-slate-400 block mb-0.5">정비 상태</span>
              <span className="font-extrabold text-slate-900">{room.cleaningStatus}</span>
            </div>
            <div>
              <span className="text-slate-400 block mb-0.5">담당 룸메이드</span>
              <span className="font-bold text-slate-800">{room.roommaidName || '미배정'}</span>
            </div>
            <div>
              <span className="text-slate-400 block mb-0.5">담당 QM</span>
              <span className="font-bold text-purple-700">{room.qmName || '미배정'}</span>
            </div>
            {room.guestName && (
              <div className="col-span-2">
                <span className="text-slate-400 block mb-0.5">투숙객 정보</span>
                <span className="font-bold text-slate-800">{room.guestName} (퇴실예정: {room.checkOutTime})</span>
              </div>
            )}
            {room.operationalStatus && (
              <div className="col-span-2">
                <span className="text-rose-500 font-bold block mb-0.5">특이사항 / 고장내역</span>
                <span className="font-medium text-rose-700">{room.operationalStatus}</span>
              </div>
            )}
          </div>

          {/* Action Buttons Section */}
          <div className="space-y-2">
            <span className="text-xs font-extrabold text-slate-700 block">원클릭 운영 작업 선택</span>

            <div className="grid grid-cols-2 gap-2.5">
              {/* Maid Actions */}
              <button
                disabled={isSubmitting || (room.cleaningStatus !== 'ASSIGNED' && room.cleaningStatus !== 'WAITING' && room.cleaningStatus !== 'REWORK')}
                onClick={() => handleActionClick('CLEANING_START')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl border border-amber-300 bg-amber-50 hover:bg-amber-100 text-amber-900 text-xs font-extrabold transition-all disabled:opacity-40 disabled:pointer-events-none active:scale-95"
              >
                <Play className="w-4 h-4 text-amber-600 fill-amber-600" />
                <span>청소 시작</span>
              </button>

              <button
                disabled={isSubmitting || room.cleaningStatus !== 'CLEANING'}
                onClick={() => handleActionClick('CLEANING_COMPLETE')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl border border-purple-300 bg-purple-50 hover:bg-purple-100 text-purple-900 text-xs font-extrabold transition-all disabled:opacity-40 disabled:pointer-events-none active:scale-95"
              >
                <Check className="w-4 h-4 text-purple-600" />
                <span>청소 완료 (검수요청)</span>
              </button>

              {/* QM Actions */}
              <button
                disabled={isSubmitting || (room.cleaningStatus !== 'QM_WAITING' && room.cleaningStatus !== 'QM_INSPECTING')}
                onClick={() => handleActionClick('INSPECTION_PASS')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 text-emerald-900 text-xs font-extrabold transition-all disabled:opacity-40 disabled:pointer-events-none active:scale-95"
              >
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>QM 점검 합격 (공실)</span>
              </button>

              <button
                disabled={isSubmitting || (room.cleaningStatus !== 'QM_WAITING' && room.cleaningStatus !== 'QM_INSPECTING')}
                onClick={() => handleActionClick('INSPECTION_REWORK')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl border border-rose-300 bg-rose-50 hover:bg-rose-100 text-rose-900 text-xs font-extrabold transition-all disabled:opacity-40 disabled:pointer-events-none active:scale-95"
              >
                <AlertOctagon className="w-4 h-4 text-rose-600" />
                <span>재정비 지시</span>
              </button>

              {/* Front / Admin Operations */}
              <button
                disabled={isSubmitting || room.roomStatus !== 'STOCK'}
                onClick={() => handleActionClick('CHANGE_STATUS_CHECKOUT')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-800 text-xs font-bold transition-all disabled:opacity-40 disabled:pointer-events-none active:scale-95"
              >
                <LogOut className="w-4 h-4 text-rose-500" />
                <span>체크아웃 (퇴실)</span>
              </button>

              <button
                disabled={isSubmitting || room.roomStatus !== 'VACANT_CLEAN'}
                onClick={() => handleActionClick('CHANGE_STATUS_CHECKIN')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-800 text-xs font-bold transition-all disabled:opacity-40 disabled:pointer-events-none active:scale-95"
              >
                <UserPlus className="w-4 h-4 text-blue-500" />
                <span>체크인 (입실)</span>
              </button>

              <button
                disabled={isSubmitting}
                onClick={() => handleActionClick('CHANGE_STATUS_OOO')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-800 text-xs font-bold transition-all disabled:opacity-40 disabled:pointer-events-none active:scale-95"
              >
                <Wrench className="w-4 h-4 text-slate-600" />
                <span>고장/수리 전환 (OOO)</span>
              </button>

              <button
                disabled={isSubmitting}
                onClick={() => handleActionClick('TOGGLE_DND')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-800 text-xs font-bold transition-all disabled:opacity-40 disabled:pointer-events-none active:scale-95"
              >
                <Moon className="w-4 h-4 text-amber-500" />
                <span>DND 토글 ({room.dnd ? '해제' : '설정'})</span>
              </button>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          {onOpenHistory && (
            <button
              type="button"
              onClick={() => onOpenHistory(room)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-100 text-slate-700 font-bold transition-all active:scale-95"
            >
              <History className="w-3.5 h-3.5 text-blue-600" />
              <span>이력 보기</span>
            </button>
          )}

          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-200 hover:bg-slate-300 font-bold text-slate-700 transition-all ml-auto"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
};
