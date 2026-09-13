'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import imageCompression from 'browser-image-compression';

export default function QmDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [rooms, setRooms] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null);
  
  // Inspection Form State
  const [inspectionResult, setInspectionResult] = useState<'PASS' | 'FAIL' | null>(null);
  const [photoBase64, setPhotoBase64] = useState<string | null>(null);
  const [isCompressing, setIsCompressing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('nova_user');
    if (!stored) {
      router.push('/');
      return;
    }
    const parsedUser = JSON.parse(stored);
    setUser(parsedUser);
    fetchQmRooms(parsedUser);
  }, [router]);

  const fetchQmRooms = async (currentUser: any) => {
    try {
      setLoading(true);
      const res = await fetch(`/api/rooms?site=${currentUser.site}`);
      const data = await res.json();
      if (data.ok) {
        // QM 대기중 또는 재정비 중인 객실만 필터링
        const qmRooms = (data.data || []).filter((r: any) => 
          r.cleaningStatus === 'QM_WAITING' || r.cleaningStatus === 'REWORK'
        );
        setRooms(qmRooms);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setIsCompressing(true);
      
      // 초고속 사진 압축 (10MB -> 0.3MB)
      const options = {
        maxSizeMB: 0.3,
        maxWidthOrHeight: 1280,
        useWebWorker: true,
        fileType: 'image/jpeg'
      };
      
      const compressedFile = await imageCompression(file, options);
      
      // Base64 변환 (서버 전송용)
      const reader = new FileReader();
      reader.readAsDataURL(compressedFile);
      reader.onloadend = () => {
        setPhotoBase64(reader.result as string);
        setIsCompressing(false);
      };
    } catch (error) {
      console.error('사진 압축 실패:', error);
      alert('사진을 처리하는 중 오류가 발생했습니다.');
      setIsCompressing(false);
    }
  };

  const handleSubmit = async (roomNo: string, currentVersion: number) => {
    if (!inspectionResult) {
      alert('점검 결과를 선택해주세요.');
      return;
    }
    if (inspectionResult === 'FAIL' && !photoBase64) {
      alert('불량 판정 시 반드시 사진을 첨부해야 합니다.');
      return;
    }

    try {
      setIsSubmitting(true);
      const action = inspectionResult === 'PASS' ? 'INSPECTION_COMPLETED' : 'INSPECTION_REWORK';
      
      const res = await fetch(`/api/rooms/${roomNo}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          expectedVersion: currentVersion,
          site: user.site,
          employeeNo: user.employeeNo,
          userRole: user.role,
          userName: user.name,
          photos: photoBase64 ? [photoBase64] : undefined
        })
      });
      const data = await res.json();
      if (data.ok) {
        alert('점검이 완료되었습니다.');
        setSelectedRoom(null);
        setInspectionResult(null);
        setPhotoBase64(null);
        fetchQmRooms(user);
      } else {
        alert(`오류: ${data.message}`);
      }
    } catch (err) {
      alert('네트워크 오류가 발생했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!user) return null;

  return (
    <div className="min-h-screen bg-slate-50 pb-20">
      <header className="bg-purple-700 text-white p-4 sticky top-0 z-10 shadow-md">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="font-bold text-lg">QM 점검 대기목록</h1>
            <p className="text-purple-200 text-sm">{user.site} · {user.name} 님</p>
          </div>
          <button onClick={() => { localStorage.removeItem('nova_user'); router.push('/'); }} className="text-sm bg-purple-800 px-3 py-1 rounded">
            로그아웃
          </button>
        </div>
      </header>

      <main className="p-4 space-y-4">
        {loading ? (
          <div className="text-center py-10 text-slate-500">객실을 불러오는 중...</div>
        ) : rooms.length === 0 ? (
          <div className="text-center py-10 text-slate-500">점검할 객실이 없습니다. 🎉</div>
        ) : (
          rooms.map(room => (
            <div key={room.roomNo} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
              <div 
                className="p-4 flex justify-between items-center cursor-pointer hover:bg-slate-50"
                onClick={() => setSelectedRoom(selectedRoom === room.roomNo ? null : room.roomNo)}
              >
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl font-bold text-slate-800">{room.roomNo}</h2>
                  <span className={`px-2 py-1 rounded text-xs font-bold ${room.cleaningStatus === 'REWORK' ? 'bg-red-100 text-red-700' : 'bg-purple-100 text-purple-700'}`}>
                    {room.cleaningStatus === 'REWORK' ? '재정비 확인' : '점검대기'}
                  </span>
                </div>
                <div className="text-slate-400">
                  {selectedRoom === room.roomNo ? '▲' : '▼'}
                </div>
              </div>

              {selectedRoom === room.roomNo && (
                <div className="p-4 border-t border-slate-100 bg-slate-50">
                  <h3 className="font-bold text-slate-700 mb-3">점검 결과 판정</h3>
                  <div className="flex gap-3 mb-4">
                    <button 
                      onClick={() => setInspectionResult('PASS')}
                      className={`flex-1 py-3 rounded-lg font-bold border-2 transition-all ${
                        inspectionResult === 'PASS' ? 'border-teal-500 bg-teal-50 text-teal-700' : 'border-slate-200 bg-white text-slate-500'
                      }`}
                    >
                      ✅ 양호 (통과)
                    </button>
                    <button 
                      onClick={() => setInspectionResult('FAIL')}
                      className={`flex-1 py-3 rounded-lg font-bold border-2 transition-all ${
                        inspectionResult === 'FAIL' ? 'border-red-500 bg-red-50 text-red-700' : 'border-slate-200 bg-white text-slate-500'
                      }`}
                    >
                      ❌ 불량 (재정비)
                    </button>
                  </div>

                  {inspectionResult === 'FAIL' && (
                    <div className="mb-4 p-4 bg-white rounded-lg border border-slate-200">
                      <label className="block text-sm font-bold text-slate-700 mb-2">불량 사진 첨부 (필수)</label>
                      <input 
                        type="file" 
                        accept="image/*" 
                        capture="environment"
                        onChange={handlePhotoUpload}
                        className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-purple-50 file:text-purple-700 hover:file:bg-purple-100"
                      />
                      
                      {isCompressing && (
                        <p className="text-xs text-purple-600 mt-2 font-bold animate-pulse">
                          ⚡ 사진을 0.1초 만에 초고속 압축 중입니다...
                        </p>
                      )}

                      {photoBase64 && !isCompressing && (
                        <div className="mt-3 relative w-32 h-32 rounded-lg overflow-hidden border border-slate-200 shadow-sm">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={photoBase64} alt="Preview" className="object-cover w-full h-full" />
                        </div>
                      )}
                    </div>
                  )}

                  <button 
                    onClick={() => handleSubmit(room.roomNo, room.version)}
                    disabled={isSubmitting || isCompressing || (inspectionResult === 'FAIL' && !photoBase64)}
                    className="w-full bg-slate-800 hover:bg-slate-900 disabled:bg-slate-300 text-white font-bold py-3 px-4 rounded-lg mt-2"
                  >
                    {isSubmitting ? '저장 중...' : '점검 완료 저장하기'}
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </main>
    </div>
  );
}
