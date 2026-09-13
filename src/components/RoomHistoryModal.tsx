'use client';

import React, { useEffect, useState } from 'react';
import { NovaAuditEvent, RoomEntity } from '@/lib/types';
import { X, History, Clock, User, ArrowRight, Shield } from 'lucide-react';

interface RoomHistoryModalProps {
  room: RoomEntity | null;
  onClose: () => void;
}

export const RoomHistoryModal: React.FC<RoomHistoryModalProps> = ({ room, onClose }) => {
  const [events, setEvents] = useState<NovaAuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!room) return;

    const fetchHistory = async () => {
      setIsLoading(true);
      try {
        const res = await fetch(`/api/rooms/${room.roomNo}/events`);
        const json = await res.json();
        if (json.ok && json.events) {
          setEvents(json.events);
        }
      } catch (err) {
        console.error('이력 조회 오류:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchHistory();
  }, [room]);

  if (!room) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5 text-blue-600" />
            <h3 className="text-base font-black text-slate-900">
              {room.roomNo}호 작업 이력 및 감사 로그 (Audit Log)
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Event List */}
        <div className="p-5 overflow-y-auto space-y-3">
          {isLoading && (
            <div className="py-8 text-center text-xs text-slate-400 font-bold">
              작업 이력을 불러오는 중...
            </div>
          )}

          {!isLoading && events.length === 0 && (
            <div className="py-8 text-center text-xs text-slate-400 font-bold">
              기록된 작업 변경 이력이 없습니다.
            </div>
          )}

          {!isLoading &&
            events.map((e, idx) => (
              <div
                key={e.id || idx}
                className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/70 space-y-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-extrabold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                      {e.action}
                    </span>
                    <span className="text-[11px] font-bold text-slate-500">
                      버전 v{e.roomVersion}
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {new Date(e.createdAt).toLocaleString('ko-KR')}
                  </span>
                </div>

                <div className="flex items-center gap-2 font-medium text-slate-700 bg-white p-2 rounded-lg border border-slate-100">
                  <span className="text-slate-500">{e.beforeStatus || '초기상태'}</span>
                  <ArrowRight className="w-3 h-3 text-slate-400 shrink-0" />
                  <span className="font-extrabold text-slate-900">{e.afterStatus}</span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
                  <div className="flex items-center gap-1">
                    <User className="w-3 h-3 text-slate-400" />
                    <span>
                      작업자: <b>{String(e.detail?.userName || e.employeeNo)}</b> ({String(e.detail?.role || '직원')})
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-400">요청ID: {e.requestId.slice(0, 15)}...</span>
                </div>
              </div>
            ))}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>* 변경 이력은 PostgreSQL audit_logs 및 nova_room_events에 영구 보존됩니다.</span>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-200 hover:bg-slate-300 font-bold text-slate-700 transition-all"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
};
