'use client';

import React, { useState, useEffect } from 'react';
import { HousemanCategory, HousemanOrder } from '@/lib/types';
import { ACTIVE_HOUSEMEN, selectBestHouseman } from '@/lib/houseman-engine';
import { Send, Zap, Clock, CheckCircle, AlertCircle, ArrowRight } from 'lucide-react';

interface HousemanOrderBarProps {
  orders: HousemanOrder[];
  onRegisterOrder: (payload: {
    roomNo: string;
    category: HousemanCategory;
    itemSummary: string;
    quantity: number;
    manualHousemanId?: string;
  }) => Promise<void>;
}

export const HousemanOrderBar: React.FC<HousemanOrderBarProps> = ({
  orders,
  onRegisterOrder
}) => {
  const [roomNo, setRoomNo] = useState('');
  const [category, setCategory] = useState<HousemanCategory>('TOWEL');
  const [itemSummary, setItemSummary] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [manualHousemanId, setManualHousemanId] = useState('');
  const [routingPreview, setRoutingPreview] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Update real-time smart routing preview when roomNo or category changes
  useEffect(() => {
    if (roomNo.length >= 3) {
      const floor = parseInt(roomNo.charAt(0), 10) || 2;
      const best = selectBestHouseman(floor, category);
      setRoutingPreview(`추천 배정: ${best.houseman.name} (${best.houseman.currentFloor}F, 이동 ${best.distance}개 층)`);
    } else {
      setRoutingPreview(null);
    }
  }, [roomNo, category]);

  const handleApplyPreset = (text: string, cat: HousemanCategory, qty: number) => {
    setItemSummary(text);
    setCategory(cat);
    setQuantity(qty);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!roomNo || !itemSummary || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await onRegisterOrder({
        roomNo,
        category,
        itemSummary,
        quantity,
        manualHousemanId: manualHousemanId || undefined
      });
      // Clear inputs
      setRoomNo('');
      setItemSummary('');
      setManualHousemanId('');
    } catch (err) {
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-white border-b border-slate-200 p-3 shadow-2xs space-y-2">
      {/* Row 1: Header + Quick Presets */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-black text-slate-800">
          <Zap className="w-4 h-4 text-blue-600 fill-blue-600" />
          <span>하우스맨 오더 즉시 등록 & 스마트 자동 배정</span>
          {routingPreview && (
            <span className="hidden sm:inline-block px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-[11px] font-extrabold border border-blue-200">
              ⚡ {routingPreview}
            </span>
          )}
        </div>

        {/* Preset Buttons */}
        <div className="flex items-center gap-1.5 overflow-x-auto text-[11px]">
          <span className="text-slate-400 font-semibold mr-0.5 hidden sm:inline">빠른 입력:</span>
          <button
            type="button"
            onClick={() => handleApplyPreset('배스타월 2장', 'TOWEL', 2)}
            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold transition-all"
          >
            타월 2장
          </button>
          <button
            type="button"
            onClick={() => handleApplyPreset('생수 2병', 'AMENITY', 2)}
            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold transition-all"
          >
            생수 2병
          </button>
          <button
            type="button"
            onClick={() => handleApplyPreset('침구 교체', 'BEDDING', 1)}
            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold transition-all"
          >
            침구 교체
          </button>
          <button
            type="button"
            onClick={() => handleApplyPreset('수하물 픽업', 'LUGGAGE', 1)}
            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold transition-all"
          >
            수하물
          </button>
          <button
            type="button"
            onClick={() => handleApplyPreset('전등/시설보수', 'MAINTENANCE', 1)}
            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold transition-all"
          >
            시설보수
          </button>
        </div>
      </div>

      {/* Row 2: Form Inputs */}
      <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-2 text-xs">
        <input
          type="text"
          value={roomNo}
          onChange={(e) => setRoomNo(e.target.value)}
          placeholder="객실번호"
          maxLength={4}
          required
          className="w-24 px-3 py-2 rounded-lg border border-slate-300 font-black text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <select
          value={category}
          onChange={(e) => setCategory(e.target.value as HousemanCategory)}
          className="px-3 py-2 rounded-lg border border-slate-300 font-bold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="TOWEL">타월/린넨</option>
          <option value="AMENITY">생수/어메니티</option>
          <option value="BEDDING">침구류</option>
          <option value="LUGGAGE">수하물 운반</option>
          <option value="ROOM_SERVICE">룸서비스 수거</option>
          <option value="MAINTENANCE">시설 수리</option>
        </select>

        <input
          type="text"
          value={itemSummary}
          onChange={(e) => setItemSummary(e.target.value)}
          placeholder="요청 항목 내용 입력 (예: 페이스타월 4장 추가)"
          required
          className="flex-1 min-w-[180px] px-3 py-2 rounded-lg border border-slate-300 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <input
          type="number"
          value={quantity}
          onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value, 10) || 1))}
          min={1}
          max={99}
          className="w-14 px-2 py-2 text-center rounded-lg border border-slate-300 font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <select
          value={manualHousemanId}
          onChange={(e) => setManualHousemanId(e.target.value)}
          className="px-2.5 py-2 rounded-lg border border-slate-300 text-slate-600 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">⚡ 스마트 자동배정</option>
          {ACTIVE_HOUSEMEN.map((h) => (
            <option key={h.id} value={h.id}>
              {h.name} ({h.currentFloor}F 대기)
            </option>
          ))}
        </select>

        <button
          type="submit"
          disabled={isSubmitting}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-extrabold flex items-center gap-1.5 shadow-xs transition-all active:scale-95 disabled:opacity-50"
        >
          <Send className="w-3.5 h-3.5" />
          <span>오더 등록</span>
        </button>
      </form>

      {/* Row 3: Live Order Horizontal Ribbon */}
      {orders.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pt-1 text-[11px] text-slate-600 scrollbar-none">
          <span className="font-bold text-slate-400 shrink-0">최신 오더:</span>
          {orders.slice(0, 5).map((order) => (
            <div
              key={order.orderId}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-50 border border-slate-200 shrink-0 font-medium"
            >
              <span className="font-extrabold text-slate-900">{order.roomNo}호</span>
              <span className="text-slate-400">·</span>
              <span className="truncate max-w-[120px]">{order.itemSummary}</span>
              <span className="text-slate-400">→</span>
              <span className="font-bold text-blue-600">{order.assignedName || '자동배정중'}</span>
              <span
                className={`px-1.5 py-0.2 rounded text-[10px] font-extrabold ${
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
          ))}
        </div>
      )}
    </div>
  );
};
