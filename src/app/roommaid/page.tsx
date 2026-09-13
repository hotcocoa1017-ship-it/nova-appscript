'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function RoommaidDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [rooms, setRooms] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem('nova_user');
    if (!stored) {
      router.push('/');
      return;
    }
    const parsedUser = JSON.parse(stored);
    setUser(parsedUser);
    fetchRooms(parsedUser);
  }, [router]);

  const fetchRooms = async (currentUser: any) => {
    try {
      setLoading(true);
      const res = await fetch(`/api/rooms?site=${currentUser.site}`);
      const data = await res.json();
      if (data.ok) {
        // 본인 배정 객실만 필터링
        const myRooms = (data.data || []).filter((r: any) => 
          r.roommaidEmployeeNo === currentUser.employeeNo || 
          r.secondaryRoommaidEmployeeNo === currentUser.employeeNo
        );
        setRooms(myRooms);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (roomNo: string, action: string, currentVersion: number) => {
    try {
      setActionLoading(roomNo);
      const res = await fetch(`/api/rooms/${roomNo}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          expectedVersion: currentVersion,
          site: user.site,
          employeeNo: user.employeeNo,
          userRole: user.role,
          userName: user.name
        })
      });
      const data = await res.json();
      if (data.ok) {
        alert('처리되었습니다.');
        fetchRooms(user);
      } else {
        alert(`오류: ${data.message}`);
      }
    } catch (err) {
      alert('네트워크 오류가 발생했습니다.');
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch(status) {
      case 'WAITING': return <span className="px-2 py-1 bg-amber-100 text-amber-700 rounded text-xs font-bold">청소대기</span>;
      case 'CLEANING': return <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-bold">청소중</span>;
      case 'COMPLETED': return <span className="px-2 py-1 bg-teal-100 text-teal-700 rounded text-xs font-bold">청소완료</span>;
      case 'QM_WAITING': return <span className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs font-bold">점검대기</span>;
      case 'REWORK': return <span className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-bold">재정비</span>;
      default: return <span className="px-2 py-1 bg-slate-100 text-slate-700 rounded text-xs font-bold">{status}</span>;
    }
  };

  if (!user) return null;

  return (
    <div className="min-h-screen bg-slate-50 pb-20">
      <header className="bg-teal-600 text-white p-4 sticky top-0 z-10 shadow-md">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="font-bold text-lg">나의 작업 목록</h1>
            <p className="text-teal-100 text-sm">{user.site} · {user.name} 님</p>
          </div>
          <button onClick={() => { localStorage.removeItem('nova_user'); router.push('/'); }} className="text-sm bg-teal-700 px-3 py-1 rounded">
            로그아웃
          </button>
        </div>
      </header>

      <main className="p-4 space-y-4">
        {loading ? (
          <div className="text-center py-10 text-slate-500">목록을 불러오는 중...</div>
        ) : rooms.length === 0 ? (
          <div className="text-center py-10 text-slate-500">배정된 객실이 없습니다.</div>
        ) : (
          rooms.map(room => (
            <div key={room.roomNo} className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2">
                  <h2 className="text-2xl font-bold text-slate-800">{room.roomNo}</h2>
                  {getStatusBadge(room.cleaningStatus)}
                </div>
                <div className="text-right">
                  <div className="text-xs font-bold text-slate-500">{room.cleaningType === 'NORMAL' ? '일반정비' : '특별정비'}</div>
                  <div className="text-xs text-slate-400 mt-1">{room.roomStatus === 'CHECKED_OUT' ? '퇴실완료' : '투숙중'}</div>
                </div>
              </div>

              <div className="flex gap-2 mt-4">
                {room.cleaningStatus === 'WAITING' || room.cleaningStatus === 'REWORK' ? (
                  <button 
                    onClick={() => handleAction(room.roomNo, 'CLEANING_START', room.version)}
                    disabled={actionLoading === room.roomNo}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg font-bold"
                  >
                    {actionLoading === room.roomNo ? '처리중...' : '청소 시작'}
                  </button>
                ) : room.cleaningStatus === 'CLEANING' ? (
                  <button 
                    onClick={() => handleAction(room.roomNo, 'CLEANING_COMPLETE', room.version)}
                    disabled={actionLoading === room.roomNo}
                    className="flex-1 bg-teal-600 hover:bg-teal-700 text-white py-3 rounded-lg font-bold"
                  >
                    {actionLoading === room.roomNo ? '처리중...' : '청소 완료'}
                  </button>
                ) : (
                  <button disabled className="flex-1 bg-slate-100 text-slate-400 py-3 rounded-lg font-bold">
                    작업 완료됨
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </main>
    </div>
  );
}
