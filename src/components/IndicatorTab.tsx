'use client';

import React, { useState, useMemo } from 'react';
import { RoomEntity } from '@/lib/types';
import { RoomCard } from './RoomCard';
import { Search, RefreshCw } from 'lucide-react';

interface IndicatorTabProps {
  rooms: RoomEntity[];
  onRoomClick: (room: RoomEntity) => void;
}

export const IndicatorTab: React.FC<IndicatorTabProps> = ({ rooms, onRoomClick }) => {
  const [selectedFloor, setSelectedFloor] = useState<string>('ALL');
  const [selectedBuilding, setSelectedBuilding] = useState<string>('ALL');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [searchInput, setSearchInput] = useState<string>('');
  const [debouncedQuery, setDebouncedQuery] = useState<string>('');

  // Debounce search input
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchInput.trim().toLowerCase());
    }, 120);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Status Filter Counts for Live Dashboard Ribbon
  const statusCounts = useMemo(() => {
    return {
      ALL: rooms.length,
      STOCK: rooms.filter(r => r.roomStatus === 'STOCK').length,
      CHECKED_OUT: rooms.filter(r => r.roomStatus === 'CHECKED_OUT').length,
      WAITING: rooms.filter(r => r.cleaningStatus === 'WAITING').length,
      CLEANING: rooms.filter(r => r.cleaningStatus === 'CLEANING').length,
      QM_WAITING: rooms.filter(r => r.cleaningStatus === 'QM_WAITING').length,
      VACANT_CLEAN: rooms.filter(r => r.roomStatus === 'VACANT_CLEAN').length,
      OOO: rooms.filter(r => r.roomStatus === 'OOO').length,
      DND: rooms.filter(r => r.dnd).length
    };
  }, [rooms]);

  // Dynamic Filtering
  const filteredRooms = useMemo(() => {
    return rooms.filter(room => {
      if (selectedFloor !== 'ALL' && String(room.floor) !== selectedFloor) return false;
      if (selectedBuilding !== 'ALL' && room.building !== selectedBuilding) return false;

      if (selectedStatus === 'STOCK' && room.roomStatus !== 'STOCK') return false;
      if (selectedStatus === 'CHECKED_OUT' && room.roomStatus !== 'CHECKED_OUT') return false;
      if (selectedStatus === 'WAITING' && room.cleaningStatus !== 'WAITING') return false;
      if (selectedStatus === 'CLEANING' && room.cleaningStatus !== 'CLEANING') return false;
      if (selectedStatus === 'QM_WAITING' && room.cleaningStatus !== 'QM_WAITING') return false;
      if (selectedStatus === 'VACANT_CLEAN' && room.roomStatus !== 'VACANT_CLEAN') return false;
      if (selectedStatus === 'OOO' && room.roomStatus !== 'OOO') return false;
      if (selectedStatus === 'DND' && !room.dnd) return false;

      if (debouncedQuery) {
        const matchNo = room.roomNo.toLowerCase().includes(debouncedQuery);
        const matchGuest = room.guestName?.toLowerCase().includes(debouncedQuery);
        const matchMaid = room.roommaidName?.toLowerCase().includes(debouncedQuery);
        if (!matchNo && !matchGuest && !matchMaid) return false;
      }
      return true;
    });
  }, [rooms, selectedFloor, selectedBuilding, selectedStatus, debouncedQuery]);

  const floors = useMemo(() => {
    const set = new Set<number>();
    filteredRooms.forEach(r => set.add(r.floor));
    return Array.from(set).sort((a, b) => b - a); // 6F down to 2F
  }, [filteredRooms]);

  return (
    <div className="space-y-4 px-2 py-4 sm:px-4">
      {/* 1. Flat Filter Ribbon (Reference UI Style) */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setSelectedStatus('ALL')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold border transition-colors ${
            selectedStatus === 'ALL'
              ? 'bg-slate-800 text-white border-slate-800'
              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
          }`}
        >
          전체 <span className={`px-1.5 py-0.5 rounded-full text-[9px] ${selectedStatus === 'ALL' ? 'bg-slate-600' : 'bg-slate-100 text-slate-500'}`}>{statusCounts.ALL}</span>
        </button>

        <button
          onClick={() => setSelectedStatus('STOCK')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold border transition-colors ${
            selectedStatus === 'STOCK' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
          }`}
        >
          재실 <span className={`px-1.5 py-0.5 rounded-full text-[9px] ${selectedStatus === 'STOCK' ? 'bg-blue-500' : 'bg-slate-100 text-slate-500'}`}>{statusCounts.STOCK}</span>
        </button>

        <button
          onClick={() => setSelectedStatus('CHECKED_OUT')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold border transition-colors ${
            selectedStatus === 'CHECKED_OUT' ? 'bg-rose-500 text-white border-rose-500' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
          }`}
        >
          퇴실 <span className={`px-1.5 py-0.5 rounded-full text-[9px] ${selectedStatus === 'CHECKED_OUT' ? 'bg-rose-400' : 'bg-slate-100 text-slate-500'}`}>{statusCounts.CHECKED_OUT}</span>
        </button>

        <button
          onClick={() => setSelectedStatus('VACANT_CLEAN')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold border transition-colors ${
            selectedStatus === 'VACANT_CLEAN' ? 'bg-emerald-500 text-white border-emerald-500' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
          }`}
        >
          공실 <span className={`px-1.5 py-0.5 rounded-full text-[9px] ${selectedStatus === 'VACANT_CLEAN' ? 'bg-emerald-400' : 'bg-slate-100 text-slate-500'}`}>{statusCounts.VACANT_CLEAN}</span>
        </button>

        <button
          onClick={() => setSelectedStatus('WAITING')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold border transition-colors ${
            selectedStatus === 'WAITING' ? 'bg-orange-500 text-white border-orange-500' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
          }`}
        >
          청소대기 <span className={`px-1.5 py-0.5 rounded-full text-[9px] ${selectedStatus === 'WAITING' ? 'bg-orange-400' : 'bg-slate-100 text-slate-500'}`}>{statusCounts.WAITING}</span>
        </button>

        <button
          onClick={() => setSelectedStatus('CLEANING')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold border transition-colors ${
            selectedStatus === 'CLEANING' ? 'bg-purple-600 text-white border-purple-600' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
          }`}
        >
          청소진행중 <span className={`px-1.5 py-0.5 rounded-full text-[9px] ${selectedStatus === 'CLEANING' ? 'bg-purple-500' : 'bg-slate-100 text-slate-500'}`}>{statusCounts.CLEANING}</span>
        </button>
      </div>

      {/* 2. Flat Search & Utilities Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 w-full max-w-md">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="객실번호/담당자 검색"
              className="w-full pl-8 pr-3 py-1.5 rounded-md border border-slate-200 text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-300"
            />
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-600">
          <select
            value={selectedBuilding}
            onChange={(e) => setSelectedBuilding(e.target.value)}
            className="border border-slate-200 rounded-md px-2 py-1.5 bg-white text-slate-700 outline-none"
          >
            <option value="ALL">전체 동</option>
            <option value="2동">2동</option>
            <option value="3동">3동</option>
            <option value="4동">4동</option>
            <option value="5동">5동</option>
            <option value="6동">6동</option>
          </select>

          <select
            value={selectedFloor}
            onChange={(e) => setSelectedFloor(e.target.value)}
            className="border border-slate-200 rounded-md px-2 py-1.5 bg-white text-slate-700 outline-none"
          >
            <option value="ALL">전체 층</option>
            <option value="6">6층</option>
            <option value="5">5층</option>
            <option value="4">4층</option>
            <option value="3">3층</option>
            <option value="2">2층</option>
          </select>

          <button className="flex items-center gap-1 px-3 py-1.5 border border-slate-200 rounded-md bg-white hover:bg-slate-50 text-slate-600 transition-colors ml-1">
            <RefreshCw className="w-3.5 h-3.5" /> 새로고침
          </button>
        </div>
      </div>

      {/* 3. Room Grid by Floors (Flat layout) */}
      <div className="space-y-6 pt-2">
        {floors.map((floor) => {
          const floorRooms = filteredRooms.filter(r => r.floor === floor);
          return (
            <div key={floor} className="space-y-2">
              <div className="room-indicator-grid">
                {floorRooms.map((room) => (
                  <RoomCard
                    key={room.roomNo}
                    room={room}
                    onClick={onRoomClick}
                  />
                ))}
              </div>
            </div>
          );
        })}

        {filteredRooms.length === 0 && (
          <div className="p-12 text-center text-slate-400">
            <p className="text-sm font-bold text-slate-500">검색된 객실이 없습니다.</p>
          </div>
        )}
      </div>
    </div>
  );
};
