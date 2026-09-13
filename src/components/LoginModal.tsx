'use client';

import React, { useState } from 'react';
import { NovaUser, UserRole } from '@/lib/types';
import { X, KeyRound, Check, ShieldCheck, User } from 'lucide-react';

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: NovaUser | null;
  onLoginSuccess: (user: NovaUser, token: string) => void;
}

const PRESET_ACCOUNTS = [
  { employeeNo: 'ADMIN-01', name: '총괄관리자', role: 'SUPER_ADMIN' as UserRole, desc: '전체 관리 및 권한' },
  { employeeNo: 'MGR-01', name: '객실지배인', role: 'MANAGER' as UserRole, desc: '지배인 운영 관리' },
  { employeeNo: 'QM-2001', name: '강QM', role: 'QM' as UserRole, desc: '점검 합격 / 재정비 지시' },
  { employeeNo: '1001', name: '김순자', role: 'ROOM_MAID' as UserRole, desc: '2~3F 룸메이드 (청소)' },
  { employeeNo: '1002', name: '박영희', role: 'ROOM_MAID' as UserRole, desc: '3~4F 룸메이드 (청소)' },
  { employeeNo: 'hm-1', name: '강민우', role: 'HOUSEMAN' as UserRole, desc: '2F 하우스맨 (오더)' },
  { employeeNo: 'hm-3', name: '한지훈', role: 'HOUSEMAN' as UserRole, desc: '3F 하우스맨 (오더)' }
];

export const LoginModal: React.FC<LoginModalProps> = ({
  isOpen,
  onClose,
  currentUser,
  onLoginSuccess
}) => {
  const [employeeNo, setEmployeeNo] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleLogin = async (empNo: string) => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employeeNo: empNo })
      });

      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.message || '로그인에 실패했습니다.');
      }

      onLoginSuccess(data.user, data.token);
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || '로그인 오류');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div className="flex items-center gap-2">
            <KeyRound className="w-5 h-5 text-blue-600" />
            <h3 className="text-base font-black text-slate-900">현장 작업자 로그인 및 역할 전환</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold">
              {errorMessage}
            </div>
          )}

          {/* Quick Preset Selector */}
          <div className="space-y-2">
            <span className="text-xs font-bold text-slate-700 block">원클릭 빠른 사번 전환:</span>
            <div className="grid grid-cols-1 gap-1.5 max-h-56 overflow-y-auto pr-1">
              {PRESET_ACCOUNTS.map((acc) => {
                const isCurrent = currentUser?.employeeNo === acc.employeeNo;
                return (
                  <button
                    key={acc.employeeNo}
                    onClick={() => handleLogin(acc.employeeNo)}
                    disabled={isLoading}
                    className={`w-full flex items-center justify-between p-2.5 rounded-xl border text-left transition-all active:scale-98 ${
                      isCurrent
                        ? 'border-blue-500 bg-blue-50/70 text-blue-900'
                        : 'border-slate-200 bg-white hover:bg-slate-50 text-slate-800'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <div
                        className={`w-7 h-7 rounded-full flex items-center justify-center font-black text-xs ${
                          isCurrent ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {acc.role.charAt(0)}
                      </div>
                      <div>
                        <div className="text-xs font-extrabold flex items-center gap-1.5">
                          <span>{acc.name}</span>
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-200 text-slate-700">
                            사번: {acc.employeeNo}
                          </span>
                        </div>
                        <span className="text-[11px] text-slate-500">{acc.desc}</span>
                      </div>
                    </div>

                    {isCurrent && <Check className="w-4 h-4 text-blue-600 shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Custom Employee No Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (employeeNo) handleLogin(employeeNo);
            }}
            className="pt-2 border-t border-slate-100 space-y-2"
          >
            <span className="text-xs font-bold text-slate-700 block">직접 사번 입력:</span>
            <div className="flex gap-2">
              <input
                type="text"
                value={employeeNo}
                onChange={(e) => setEmployeeNo(e.target.value)}
                placeholder="사번 입력 (예: 1001, ADMIN-01)"
                className="flex-1 px-3 py-2 rounded-xl border border-slate-300 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="submit"
                disabled={!employeeNo || isLoading}
                className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-xs transition-all disabled:opacity-50"
              >
                로그인
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
