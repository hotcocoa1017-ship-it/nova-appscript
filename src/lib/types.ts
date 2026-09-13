/**
 * NOVA ROOM MANAGEMENT SYSTEM - Core Domain Types and Enumerations
 * Strict typing across Database, API, and UI state.
 */

// ==========================================
// 1. User & RBAC Types
// ==========================================
export type UserRole =
  | 'SUPER_ADMIN'
  | 'ADMIN'
  | 'MANAGER'
  | 'QM'
  | 'INSPECTOR'
  | 'HOUSEMAN'
  | 'ROOM_MAID'
  | 'PUBLIC'
  | 'DELIVERY'
  | 'OUTSOURCE'
  | 'PART_TIME';

export interface NovaUser {
  employeeNo: string;
  name: string;
  role: UserRole;
  enabled: boolean;
  defaultSite?: string;
  allowedSites: string[];
  department?: string;
  phone?: string;
  updatedAt?: string;
}

export interface AuthSession {
  user: NovaUser;
  token: string;
  expiresAt: number;
}

// ==========================================
// 2. Room State & Status Enums
// ==========================================
export type RoomStatus =
  | 'STOCK'          // 재실 (투숙중)
  | 'OCCUPIED'       // 재실 (동의어)
  | 'CHECKED_OUT'    // 퇴실 (청소 필요)
  | 'VACANT_DIRTY'   // 퇴실 (동의어)
  | 'VACANT_CLEAN'   // 공실/판매가능 (정비 및 점검 완료)
  | 'READY'          // 공실/판매가능 (동의어)
  | 'OOO'            // 고장/수리중 (Out of Order)
  | 'OUT_OF_ORDER';  // 고장/수리중 (동의어)

export type CleaningStatus =
  | 'WAITING'                // 미청소 / 청소대기
  | 'ASSIGNED'               // 청소배정 완료
  | 'CLEANING_ASSIGNED'      // 청소배정 완료 (동의어)
  | 'CLEANING'               // 청소 진행중
  | 'CLEANING_IN_PROGRESS'   // 청소 진행중 (동의어)
  | 'COMPLETED'              // 청소 완료
  | 'CLEANING_COMPLETED'     // 청소 완료 (동의어)
  | 'QM_WAITING'             // QM 점검 대기
  | 'INSPECTION_WAITING'     // QM 점검 대기 (동의어)
  | 'QM_INSPECTING'          // QM 점검 진행중
  | 'INSPECTION_IN_PROGRESS' // QM 점검 진행중 (동의어)
  | 'QM_COMPLETED'           // 점검 완료
  | 'INSPECTION_COMPLETED'   // 점검 완료 (동의어)
  | 'REWORK'                 // 점검 불합격 (재정비 지시)
  | 'NOT_REQUIRED';          // 청소 불필요

export type CleaningType =
  | 'NORMAL'         // 일반정비 (퇴실정비)
  | 'DS'             // D/S (재실정비)
  | 'FIVE_S'         // 5S 특별정비
  | 'EVALUATION'     // 평가원 점검 대비
  | 'STAFF_DORM'     // 직원숙소
  | 'DEEP_CLEANING'; // 딥크리닝

export type AssignmentType = 'SOLO' | 'PAIR' | 'PAIR_TRAINING';

export interface RoomEntity {
  id?: string;
  roomId?: string;                    // Alias for id
  businessDate: string;               // YYYY-MM-DD
  site: string;                       // 사업장 (예: SORA, SEOL 등)
  roomNo: string;                     // 1101, 201 등
  roomNumber?: string;                // Alias for roomNo
  building: string;                   // 1동, 본관 등
  floor: number;                      // 1, 2, 3 ...
  roomType: string;                   // Standard, Deluxe, Suite
  roomStatus: RoomStatus;
  cleaningStatus: CleaningStatus;
  inspectionStatus?: CleaningStatus;  // Inspection status
  cleaningType: CleaningType;
  assignmentType: AssignmentType;
  roommaidEmployeeNo?: string | null;
  assignedWorker?: string | null;     // Alias for roommaidEmployeeNo
  roommaidName?: string | null;
  secondaryRoommaidEmployeeNo?: string | null;
  secondaryRoommaidName?: string | null;
  qmEmployeeNo?: string | null;
  assignedQm?: string | null;         // Alias for qmEmployeeNo
  qmName?: string | null;
  assignedInspector?: string | null;
  inspectorName?: string | null;
  operationalStatus?: string;         // OOO 사유, 특이사항, DND 등
  dnd?: boolean;                      // Do Not Disturb
  guestName?: string;
  checkOutTime?: string;
  version: number;                    // Optimistic Concurrency Control (OCC)
  cleaningStartedAt?: string | null;
  startedAt?: string | null;          // Alias for cleaningStartedAt
  cleaningCompletedAt?: string | null;
  completedAt?: string | null;        // Alias for cleaningCompletedAt
  inspectedAt?: string | null;
  updatedBy?: string;
  updatedAt?: string;
}

// ==========================================
// 3. Houseman Order Types
// ==========================================
export type HousemanOrderStatus =
  | 'REGISTERED'  // 접수/등록
  | 'ASSIGNED'    // 배정
  | 'ACCEPTED'    // 담당자 수락
  | 'PROCESSING'  // 처리중
  | 'COMPLETED'   // 완료
  | 'UNABLE';     // 처리불가

export type HousemanCategory =
  | 'AMENITY'       // 생수/어메니티
  | 'TOWEL'         // 타월/린넨
  | 'BEDDING'       // 침구류
  | 'LUGGAGE'       // 수하물
  | 'ROOM_SERVICE'  // 수거
  | 'MAINTENANCE';  // 시설보수

export interface HousemanOrderItem {
  name: string;
  quantity: number;
}

export interface HousemanOrder {
  orderId: string;
  businessDate: string;
  site: string;
  roomNo: string;
  category: HousemanCategory;
  items: HousemanOrderItem[];
  itemSummary: string;
  quantity: number;
  note?: string;
  requester?: string;
  assignedEmployeeNo?: string | null;
  assignedName?: string;
  status: HousemanOrderStatus;
  important: boolean;
  version: number;
  registeredBy: string;
  registeredAt: string;
  acceptedAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  unableReason?: string;
  updatedAt?: string;
}

// ==========================================
// 4. Audit & Event Log Types
// ==========================================
export interface NovaAuditEvent {
  id?: number;
  requestId: string;
  businessDate: string;
  site: string;
  roomNo: string;
  action: string;
  beforeStatus?: string;
  afterStatus?: string;
  employeeNo: string;
  roomVersion: number;
  detail?: Record<string, unknown>;
  createdAt: string;
}

// ==========================================
// 5. API Command Payloads & Results
// ==========================================
export type RoomActionType =
  | 'ASSIGN_ROOMMAID'
  | 'CLEANING_START'
  | 'CLEANING_COMPLETE'
  | 'QM_ASSIGN'
  | 'INSPECTION_START'
  | 'INSPECTION_PASS'
  | 'INSPECTION_REWORK'
  | 'CHANGE_STATUS_CHECKIN'
  | 'CHANGE_STATUS_CHECKOUT'
  | 'CHANGE_STATUS_OOO'
  | 'CHANGE_STATUS_READY'
  | 'TOGGLE_DND';

export interface RoomCommandPayload {
  businessDate: string;
  site: string;
  roomNo: string;
  action: RoomActionType;
  expectedVersion: number;
  requestId: string;
  assigneeEmployeeNo?: string;
  secondaryAssigneeEmployeeNo?: string;
  cleaningType?: CleaningType;
  operationalNote?: string;
}

export interface CommandResponse<T = unknown> {
  ok: boolean;
  code?: string;
  message?: string;
  data?: T;
  currentRoom?: RoomEntity;
  duplicateRequest?: boolean;
  version?: number;
  requestId: string;
  timingMs?: number;
}

export interface RealtimeTokenResponse {
  ok: boolean;
  token: string;
  expiresIn: number;
  supabaseUrl: string;
  publishableKey: string;
  sites: string[];
}
