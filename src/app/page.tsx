'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const router = useRouter();
  const [employeeNo, setEmployeeNo] = useState('');
  const [site, setSite] = useState('SORA');
  const [role, setRole] = useState('ROOM_MAID');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      const user = {
        employeeNo: employeeNo || (role === 'ROOM_MAID' ? '1001' : 'ADMIN-01'),
        name: role === 'ROOM_MAID' ? '김순자' : '관리자',
        role,
        site
      };
      localStorage.setItem('nova_user', JSON.stringify(user));
      if (role === 'ROOM_MAID') {
        router.push('/roommaid');
      } else if (role === 'QM_INSPECTOR') {
        router.push('/qm');
      } else {
        router.push('/admin');
      }
    } catch (err) {
      setError('로그인 실패');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl overflow-hidden">
        <div className="bg-teal-600 p-8 text-center">
          <h1 className="text-3xl font-bold text-white tracking-tight">NOVA</h1>
          <p className="text-teal-100 mt-2">차세대 객실관리 시스템</p>
        </div>
        <form onSubmit={handleLogin} className="p-8 space-y-6">
          {error && <div className="p-3 bg-red-50 text-red-600 rounded-lg text-sm">{error}</div>}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">사업장</label>
            <select value={site} onChange={(e) => setSite(e.target.value)} className="w-full border border-slate-300 rounded-lg px-4 py-2.5 bg-slate-50 focus:ring-2 focus:ring-teal-500">
              <option value="SORA">한화리조트 쏘라노</option>
              <option value="HAEUNDAE">한화리조트 해운대</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">접속 역할 (테스트용)</label>
            <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full border border-slate-300 rounded-lg px-4 py-2.5 bg-slate-50 focus:ring-2 focus:ring-teal-500">
              <option value="ROOM_MAID">룸메이드 (Roommaid)</option>
              <option value="QM_INSPECTOR">퀄리티매니저 (QM)</option>
              <option value="SUPER_ADMIN">관리자 (Admin)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">사번</label>
            <input type="text" value={employeeNo} onChange={(e) => setEmployeeNo(e.target.value)} placeholder={role === 'ROOM_MAID' ? '1001 (기본값)' : 'ADMIN-01'} className="w-full border border-slate-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-teal-500" />
          </div>
          <button type="submit" disabled={isLoading} className="w-full bg-teal-600 hover:bg-teal-700 text-white font-bold py-3 px-4 rounded-lg">
            {isLoading ? '접속 중...' : '로그인'}
          </button>
        </form>
      </div>
    </div>
  );
}
