'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Topbar } from '@/components/Topbar';
import { Sidebar, ActiveTab } from '@/components/Sidebar';
import { HousemanOrderBar } from '@/components/HousemanOrderBar';
import { IndicatorTab } from '@/components/IndicatorTab';
import { HousekeepingTab } from '@/components/HousekeepingTab';
import { MobileSimulator } from '@/components/MobileSimulator';
import { RoomActionModal } from '@/components/RoomActionModal';
import { RoomHistoryModal } from '@/components/RoomHistoryModal';
import { QmInspectionModal } from '@/components/QmInspectionModal';
import { ReportTab } from '@/components/ReportTab';
import { LoginModal } from '@/components/LoginModal';
import { HousemanCategory, HousemanOrder, NovaUser, RoomActionType, RoomEntity, UserRole } from '@/lib/types';
import { getSupabaseClient, RealtimeConnectionStatus, subscribeToSiteRooms } from '@/lib/supabase';
import { AlertCircle, CheckCircle2, Info } from 'lucide-react';

const INITIAL_DEFAULT_USER: NovaUser = {
  employeeNo: 'ADMIN-01',
  name: '총괄관리자',
  role: 'SUPER_ADMIN',
  enabled: true,
  defaultSite: 'SORA',
  allowedSites: ['SORA']
};

export default function NovaMainPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('indicator');
  const [currentUser, setCurrentUser] = useState<NovaUser>(INITIAL_DEFAULT_USER);
  const [authToken, setAuthToken] = useState<string>('');
  const [isLoginModalOpen, setIsLoginModalOpen] = useState<boolean>(false);
  const [rooms, setRooms] = useState<RoomEntity[]>([]);
  const [orders, setOrders] = useState<HousemanOrder[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<RoomEntity | null>(null);
  const [historyRoom, setHistoryRoom] = useState<RoomEntity | null>(null);
  const [qmInspectRoom, setQmInspectRoom] = useState<RoomEntity | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<RealtimeConnectionStatus>('CONNECTING');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [toastMessage, setToastMessage] = useState<{ type: 'info' | 'success' | 'warning' | 'error'; text: string } | null>(null);

  const showToast = (text: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
    setToastMessage({ type, text });
    setTimeout(() => setToastMessage(null), 4000);
  };

  // 1. Fetch Rooms from API
  const fetchRooms = useCallback(async () => {
    try {
      setIsRefreshing(true);
      const headers: Record<string, string> = {};
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
      headers['x-nova-role'] = currentUser.role;
      headers['x-nova-employee-no'] = currentUser.employeeNo;

      const res = await fetch('/api/rooms?site=SORA&businessDate=2026-09-13', { headers });
      const json = await res.json();
      if (json.ok && json.rooms) {
        setRooms(json.rooms);
      }
    } catch (err) {
      console.error('Failed to fetch rooms:', err);
    } finally {
      setIsRefreshing(false);
    }
  }, [authToken, currentUser]);

  // 2. Fetch Orders from API
  const fetchOrders = useCallback(async () => {
    try {
      const res = await fetch('/api/orders');
      const json = await res.json();
      if (json.ok && json.orders) {
        setOrders(json.orders);
      }
    } catch (err) {
      console.error('Failed to fetch orders:', err);
    }
  }, []);

  // Initial Load & Realtime Setup
  useEffect(() => {
    fetchRooms();
    fetchOrders();

    // Supabase Realtime Subscription
    const client = getSupabaseClient();
    if (client) {
      const channel = subscribeToSiteRooms(client, {
        site: 'SORA',
        onRoomUpdated: (updatedRoom) => {
          setRooms((prev) =>
            prev.map((r) =>
              r.roomNo === updatedRoom.roomNo
                ? { ...r, ...updatedRoom }
                : r
            )
          );
          showToast(`${updatedRoom.roomNo}호 객실 상태가 실시간으로 갱신되었습니다.`, 'info');
        },
        onConnectionChange: (status) => {
          setConnectionStatus(status);
        },
        onReconcileNeeded: () => {
          fetchRooms();
          fetchOrders();
        }
      });

      return () => {
        channel.unsubscribe();
      };
    } else {
      setConnectionStatus('CONNECTED');
    }
  }, [fetchRooms, fetchOrders]);

  // 3. Execute Room Command Action with OCC & Optimistic UI
  const handleExecuteRoomAction = async (
    roomNo: string,
    action: RoomActionType,
    expectedVersion: number
  ): Promise<boolean> => {
    const requestId = `REQ-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json'
      };
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
      headers['x-nova-role'] = currentUser.role;
      headers['x-nova-employee-no'] = currentUser.employeeNo;
      headers['x-nova-user-name'] = currentUser.name;

      const res = await fetch(`/api/rooms/${roomNo}/action`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          businessDate: '2026-09-13',
          site: 'SORA',
          action,
          expectedVersion,
          requestId
        })
      });

      const data = await res.json();

      if (!res.ok || !data.ok) {
        if (data.code === 'VERSION_CONFLICT') {
          showToast(
            `${roomNo}호 객실 상태가 다른 사용자의 작업으로 변경되었습니다. 최신 정보를 반영합니다.`,
            'warning'
          );
          if (data.currentRoom) {
            setRooms((prev) =>
              prev.map((r) => (r.roomNo === roomNo ? data.currentRoom : r))
            );
          } else {
            fetchRooms();
          }
          return false;
        }

        throw new Error(data.message || '작업 처리에 실패했습니다.');
      }

      // Optimistic/Immediate update
      if (data.data) {
        setRooms((prev) =>
          prev.map((r) => (r.roomNo === roomNo ? data.data : r))
        );
      }

      showToast(`${roomNo}호 작업(${action})이 성공적으로 처리되었습니다.`, 'success');
      return true;
    } catch (err: any) {
      showToast(err.message || '작업 실패', 'error');
      throw err;
    }
  };

  // 4. Register Houseman Order
  const handleRegisterOrder = async (payload: {
    roomNo: string;
    category: HousemanCategory;
    itemSummary: string;
    quantity: number;
    manualHousemanId?: string;
  }) => {
    try {
      const res = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.ok) {
        setOrders((prev) => [data.order, ...prev]);
        showToast(`${payload.roomNo}호 오더가 정상 등록 및 배정되었습니다.`, 'success');
      }
    } catch (err) {
      showToast('오더 등록 실패', 'error');
    }
  };

  // 5. Update Houseman Order Status
  const handleUpdateOrderStatus = async (orderId: string, status: any) => {
    try {
      const res = await fetch('/api/orders', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orderId, status })
      });
      const data = await res.json();
      if (data.ok) {
        setOrders((prev) =>
          prev.map((o) => (o.orderId === orderId ? data.order : o))
        );
        showToast('오더 상태가 변경되었습니다.', 'success');
      }
    } catch (err) {
      showToast('오더 상태 변경 실패', 'error');
    }
  };

  // 6. Batch Assign Maid Rooms
  const handleBatchAssignMaids = async (
    assignments: { roomNo: string; maidId: string; maidName: string }[]
  ) => {
    const map = new Map(assignments.map((a) => [a.roomNo, a]));
    setRooms((prev) =>
      prev.map((r) => {
        const assign = map.get(r.roomNo);
        if (assign) {
          return {
            ...r,
            roommaidEmployeeNo: assign.maidId,
            roommaidName: assign.maidName,
            cleaningStatus: 'ASSIGNED',
            version: r.version + 1
          };
        }
        return r;
      })
    );
    showToast(`${assignments.length}개 객실이 룸메이드에게 자동 배정되었습니다.`, 'success');
  };

  // Role switch from sidebar
  const handleRoleChange = (newRole: UserRole) => {
    const mockEmployeeNo =
      newRole === 'ROOM_MAID'
        ? '1001'
        : newRole === 'QM'
        ? 'QM-2001'
        : newRole === 'HOUSEMAN'
        ? 'hm-1'
        : 'ADMIN-01';
    const mockName =
      newRole === 'ROOM_MAID'
        ? '김순자'
        : newRole === 'QM'
        ? '강QM'
        : newRole === 'HOUSEMAN'
        ? '강민우'
        : '총괄관리자';

    setCurrentUser({
      employeeNo: mockEmployeeNo,
      name: mockName,
      role: newRole,
      enabled: true,
      defaultSite: 'SORA',
      allowedSites: ['SORA']
    });
    showToast(`작업 권한이 '${newRole}'(으)로 전환되었습니다.`, 'info');
  };

  const cleaningTargetCount = rooms.filter(
    (r) => r.roomStatus === 'CHECKED_OUT' || r.cleaningStatus === 'WAITING'
  ).length;
  const activeOrdersCount = orders.filter((o) => o.status !== 'COMPLETED' && o.status !== 'UNABLE').length;

  return (
    <div className="min-h-screen flex flex-col bg-slate-100">
      {/* Global Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 animate-in fade-in slide-in-from-bottom-3 duration-200">
          <div
            className={`px-4 py-3 rounded-2xl shadow-xl border flex items-center gap-2.5 text-xs font-bold ${
              toastMessage.type === 'success'
                ? 'bg-emerald-900 text-emerald-100 border-emerald-700'
                : toastMessage.type === 'warning'
                ? 'bg-amber-900 text-amber-100 border-amber-700'
                : toastMessage.type === 'error'
                ? 'bg-rose-900 text-rose-100 border-rose-700'
                : 'bg-slate-900 text-white border-slate-700'
            }`}
          >
            {toastMessage.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            ) : toastMessage.type === 'warning' ? (
              <AlertCircle className="w-4 h-4 text-amber-400" />
            ) : (
              <Info className="w-4 h-4 text-blue-400" />
            )}
            <span>{toastMessage.text}</span>
          </div>
        </div>
      )}

      {/* Topbar Header */}
      <Topbar
        connectionStatus={connectionStatus}
        currentDateText="2026.09.13 (일)"
        currentUser={currentUser}
        onOpenLogin={() => setIsLoginModalOpen(true)}
        onRefresh={fetchRooms}
        isRefreshing={isRefreshing}
      />

      {/* Main Workspace Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          currentRole={currentUser.role}
          onRoleChange={handleRoleChange}
          roomCounts={{
            total: rooms.length,
            cleaningTarget: cleaningTargetCount,
            activeOrders: activeOrdersCount
          }}
        />

        {/* Content Body */}
        <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
          {/* Top Fixed Houseman Dispatch Row */}
          <HousemanOrderBar
            orders={orders}
            onRegisterOrder={handleRegisterOrder}
          />

          {/* TAB 1: 객실 인디케이터 */}
          {activeTab === 'indicator' && (
            <IndicatorTab
              rooms={rooms}
              onRoomClick={(r) => {
                if (currentUser.role === 'QM' || currentUser.role === 'INSPECTOR') {
                  setQmInspectRoom(r);
                } else {
                  setSelectedRoom(r);
                }
              }}
            />
          )}

          {/* TAB 2: 청소 배정 관리 */}
          {activeTab === 'housekeeping' && (
            <HousekeepingTab
              rooms={rooms}
              onBatchAssign={handleBatchAssignMaids}
            />
          )}

          {/* TAB 3: 하우스맨 오더 관제 */}
          {activeTab === 'orders' && (
            <div className="p-4 space-y-3">
              <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-2xs">
                <h2 className="text-base font-black text-slate-900 mb-1">하우스맨 오더 실시간 관제</h2>
                <p className="text-xs text-slate-500">실시간 유입된 고객 요청 및 비품 배달 현황을 관제합니다.</p>
              </div>

              <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold">
                    <tr>
                      <th className="p-3">오더번호</th>
                      <th className="p-3">객실</th>
                      <th className="p-3">요청항목</th>
                      <th className="p-3">요청자</th>
                      <th className="p-3">담당 하우스맨</th>
                      <th className="p-3">상태</th>
                      <th className="p-3">등록시각</th>
                      <th className="p-3">작업</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-medium">
                    {orders.map((o) => (
                      <tr key={o.orderId} className="hover:bg-slate-50">
                        <td className="p-3 font-bold text-slate-900">{o.orderId}</td>
                        <td className="p-3 font-extrabold text-blue-600">{o.roomNo}호</td>
                        <td className="p-3">{o.itemSummary}</td>
                        <td className="p-3 text-slate-500">{o.requester}</td>
                        <td className="p-3 font-bold text-slate-800">{o.assignedName || '미배정'}</td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold ${
                              o.status === 'COMPLETED'
                                ? 'bg-emerald-100 text-emerald-800'
                                : o.status === 'PROCESSING'
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-blue-100 text-blue-800'
                            }`}
                          >
                            {o.status}
                          </span>
                        </td>
                        <td className="p-3 text-slate-400 text-[11px]">
                          {new Date(o.registeredAt).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                        </td>
                        <td className="p-3">
                          {o.status !== 'COMPLETED' && (
                            <button
                              onClick={() => handleUpdateOrderStatus(o.orderId, 'COMPLETED')}
                              className="px-2 py-1 rounded bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-[11px] font-extrabold border border-emerald-200"
                            >
                              완료처리
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 4: 현장 모바일 뷰어 */}
          {activeTab === 'mobile' && (
            <MobileSimulator
              rooms={rooms}
              orders={orders}
              onExecuteRoomAction={(roomNo, action, ver) =>
                handleExecuteRoomAction(roomNo, action, ver)
              }
              onUpdateOrderStatus={handleUpdateOrderStatus}
            />
          )}

          {/* TAB 5: 운영 통계 및 리포트 */}
          {activeTab === 'report' && (
            <ReportTab rooms={rooms} orders={orders} />
          )}
        </main>
      </div>

      {/* Room Action Modal */}
      <RoomActionModal
        room={selectedRoom}
        onClose={() => setSelectedRoom(null)}
        onExecuteAction={(action, expectedVer) => {
          if (!selectedRoom) return Promise.resolve(false);
          return handleExecuteRoomAction(selectedRoom.roomNo, action, expectedVer);
        }}
        onOpenHistory={(r) => {
          setSelectedRoom(null);
          setHistoryRoom(r);
        }}
        currentUserRole={currentUser.role}
      />

      {/* QM Inspection Modal */}
      <QmInspectionModal
        room={qmInspectRoom}
        onClose={() => setQmInspectRoom(null)}
        onExecuteAction={(action, expectedVer) => {
          if (!qmInspectRoom) return Promise.resolve(false);
          return handleExecuteRoomAction(qmInspectRoom.roomNo, action, expectedVer);
        }}
      />

      {/* Room History Modal (Audit Log) */}
      <RoomHistoryModal
        room={historyRoom}
        onClose={() => setHistoryRoom(null)}
      />

      {/* Login & Role Switcher Modal */}
      <LoginModal
        isOpen={isLoginModalOpen}
        onClose={() => setIsLoginModalOpen(false)}
        currentUser={currentUser}
        onLoginSuccess={(user, token) => {
          setCurrentUser(user);
          setAuthToken(token);
          showToast(`'${user.name}'(${user.role}) 계정으로 로그인되었습니다.`, 'success');
        }}
      />
    </div>
  );
}
