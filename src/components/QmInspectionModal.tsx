'use client';

import React, { useState } from 'react';
import { RoomActionType, RoomEntity } from '@/lib/types';
import { X, ShieldCheck, AlertOctagon, CheckSquare, Square, AlertCircle } from 'lucide-react';

interface QmInspectionModalProps {
  room: RoomEntity | null;
  onClose: () => void;
  onExecuteAction: (action: RoomActionType, expectedVersion: number, operationalNote?: string) => Promise<boolean>;
}

const CHECKLIST_ITEMS = [
  '침구류 구김 및 베개/시트 오염 상태 점검',
  '욕실 수전 물때, 배수구 머리카락 및 유리 거울 점검',
  '어메니티 비치 (타월 4장, 생수 2병, 어메니티 키트) 확인',
  '바닥 카펫/온돌 청소 상태 및 먼지 유무 점검',
  '객실 내 냄새/환기 및 에어컨/조명 정상 작동 점검'
];

export const QmInspectionModal: React.FC<QmInspectionModalProps> = ({
  room,
  onClose,
  onExecuteAction
}) => {
  const [checkedList, setCheckedList] = useState<boolean[]>(new Array(CHECKLIST_ITEMS.length).fill(false));
  const [reworkNote, setReworkNote] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!room) return null;

  const toggleCheck = (index: number) => {
    const next = [...checkedList];
    next[index] = !next[index];
    setCheckedList(next);
  };

  const allChecked = checkedList.every(Boolean);

  const handlePass = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const ok = await onExecuteAction('INSPECTION_PASS', room.version, 'QM 점검 합격 (전 항목 통과)');
      if (ok) onClose();
    } catch (err: any) {
      setErrorMessage(err.message || '점검 합격 처리 오류');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRework = async () => {
    if (!reworkNote.trim() || isSubmitting) return;
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const ok = await onExecuteAction('INSPECTION_REWORK', room.version, `재정비 지시: ${reworkNote.trim()}`);
      if (ok) onClose();
    } catch (err: any) {
      setErrorMessage(err.message || '재정비 지시 오류');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-purple-50">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-purple-700" />
            <div>
              <h3 className="text-base font-black text-slate-900">{room.roomNo}호 QM 품질 점검</h3>
              <span className="text-xs text-slate-500">
                담당 메이드: <b>{room.roommaidName || '미지정'}</b> (정비완료: {room.cleaningCompletedAt ? new Date(room.cleaningCompletedAt).toLocaleTimeString('ko-KR') : '시간 미기록'})
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs">
          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 font-semibold flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Checklist */}
          <div className="space-y-2">
            <span className="font-extrabold text-slate-700 block">QM 5대 필수 점검 체크리스트:</span>
            <div className="space-y-1.5 bg-slate-50 p-3 rounded-xl border border-slate-200">
              {CHECKLIST_ITEMS.map((item, idx) => (
                <div
                  key={idx}
                  onClick={() => toggleCheck(idx)}
                  className="flex items-center gap-2.5 p-2 rounded-lg bg-white border border-slate-200 cursor-pointer hover:bg-slate-100 transition-all select-none"
                >
                  {checkedList[idx] ? (
                    <CheckSquare className="w-4 h-4 text-purple-600 shrink-0" />
                  ) : (
                    <Square className="w-4 h-4 text-slate-400 shrink-0" />
                  )}
                  <span className={`font-semibold ${checkedList[idx] ? 'text-purple-950 font-bold' : 'text-slate-700'}`}>
                    {item}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Rework Note Input */}
          <div className="space-y-1">
            <span className="font-bold text-slate-700 block">재정비 지시 사유 (불합격 시 입력):</span>
            <input
              type="text"
              value={reworkNote}
              onChange={(e) => setReworkNote(e.target.value)}
              placeholder="예: 욕실 거울 얼룩 재청소 필요, 샤워가운 1벌 미비치"
              className="w-full px-3 py-2 rounded-xl border border-slate-300 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

          {/* Actions */}
          <div className="pt-2 grid grid-cols-2 gap-2.5">
            <button
              onClick={handlePass}
              disabled={isSubmitting}
              className="py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold flex items-center justify-center gap-2 shadow-xs active:scale-98 transition-all disabled:opacity-50"
            >
              <ShieldCheck className="w-4 h-4" />
              <span>{allChecked ? '점검 합격 (공실 승인)' : '점검 합격'}</span>
            </button>

            <button
              onClick={handleRework}
              disabled={!reworkNote.trim() || isSubmitting}
              className="py-3 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-extrabold flex items-center justify-center gap-2 shadow-xs active:scale-98 transition-all disabled:opacity-40"
            >
              <AlertOctagon className="w-4 h-4" />
              <span>재정비 지시</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
