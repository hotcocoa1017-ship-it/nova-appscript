/**
 * NOVA State Machine Engine
 * Strictly validates room state transitions and role-based permissions on the server.
 */

import { CleaningStatus, NovaUser, RoomActionType, RoomEntity, RoomStatus } from './types';

export interface TransitionValidationResult {
  valid: boolean;
  errorCode?: string;
  errorMessage?: string;
  nextRoomStatus?: RoomStatus;
  nextCleaningStatus?: CleaningStatus;
}

/**
 * Validates if the given user can perform the requested action on the current room state.
 */
export function validateStateTransition(
  room: RoomEntity,
  action: RoomActionType,
  user: NovaUser
): TransitionValidationResult {
  // 1. Role Permission Check
  if (!hasRolePermissionForAction(user, action)) {
    return {
      valid: false,
      errorCode: 'FORBIDDEN_ROLE',
      errorMessage: `현재 권한(${user.role})으로는 해당 작업(${action})을 수행할 수 없습니다.`
    };
  }

  // 2. Specific Maid Assignment Check
  if (user.role === 'ROOM_MAID') {
    const isAssigned =
      room.roommaidEmployeeNo === user.employeeNo ||
      room.secondaryRoommaidEmployeeNo === user.employeeNo;
    if (!isAssigned) {
      return {
        valid: false,
        errorCode: 'ROOM_NOT_ASSIGNED',
        errorMessage: '본인에게 배정되지 않은 객실은 청소 상태를 변경할 수 없습니다.'
      };
    }
  }

  // 3. State Machine Transition Verification
  switch (action) {
    case 'ASSIGN_ROOMMAID': {
      // Can assign maid when room is checked out or needs cleaning
      return {
        valid: true,
        nextCleaningStatus: 'ASSIGNED',
        nextRoomStatus: room.roomStatus
      };
    }

    case 'CLEANING_START': {
      // Must be in ASSIGNED, WAITING, or REWORK
      const validFrom: CleaningStatus[] = ['ASSIGNED', 'WAITING', 'REWORK'];
      if (!validFrom.includes(room.cleaningStatus)) {
        return {
          valid: false,
          errorCode: 'INVALID_CLEANING_START',
          errorMessage: `현재 '${room.cleaningStatus}' 상태에서는 청소를 시작할 수 없습니다. (대기/배정/재정비 상태 필요)`
        };
      }
      return {
        valid: true,
        nextCleaningStatus: 'CLEANING',
        nextRoomStatus: room.roomStatus
      };
    }

    case 'CLEANING_COMPLETE': {
      // Must be currently in CLEANING status
      if (room.cleaningStatus !== 'CLEANING') {
        return {
          valid: false,
          errorCode: 'INVALID_CLEANING_COMPLETE',
          errorMessage: `현재 '${room.cleaningStatus}' 상태에서는 청소완료 처리를 할 수 없습니다. (청소 진행중 상태 필요)`
        };
      }
      return {
        valid: true,
        nextCleaningStatus: 'QM_WAITING', // Cleaned -> Ready for QM Inspection
        nextRoomStatus: room.roomStatus
      };
    }

    case 'QM_ASSIGN':
    case 'QM_UNASSIGN': {
      return {
        valid: true,
        nextCleaningStatus: room.cleaningStatus,
        nextRoomStatus: room.roomStatus
      };
    }

    case 'INSPECTION_START': {
      // Must be in QM_WAITING or COMPLETED
      if (room.cleaningStatus !== 'QM_WAITING' && room.cleaningStatus !== 'COMPLETED') {
        return {
          valid: false,
          errorCode: 'INVALID_INSPECTION_START',
          errorMessage: `현재 '${room.cleaningStatus}' 상태에서는 점검을 시작할 수 없습니다. (점검대기 필요)`
        };
      }
      return {
        valid: true,
        nextCleaningStatus: 'QM_INSPECTING',
        nextRoomStatus: room.roomStatus
      };
    }

    case 'INSPECTION_PASS': {
      // Pass inspection -> room becomes VACANT_CLEAN / QM_COMPLETED
      if (room.cleaningStatus !== 'QM_INSPECTING' && room.cleaningStatus !== 'QM_WAITING') {
        return {
          valid: false,
          errorCode: 'INVALID_INSPECTION_PASS',
          errorMessage: `현재 '${room.cleaningStatus}' 상태에서는 점검 완료(합격) 처리를 할 수 없습니다.`
        };
      }
      return {
        valid: true,
        nextCleaningStatus: 'QM_COMPLETED',
        nextRoomStatus: 'VACANT_CLEAN'
      };
    }

    case 'INSPECTION_REWORK': {
      // Fail inspection -> room goes to REWORK
      if (room.cleaningStatus !== 'QM_INSPECTING' && room.cleaningStatus !== 'QM_WAITING') {
        return {
          valid: false,
          errorCode: 'INVALID_INSPECTION_REWORK',
          errorMessage: `점검 진행 중인 객실만 재정비 지시를 내릴 수 있습니다.`
        };
      }
      return {
        valid: true,
        nextCleaningStatus: 'REWORK',
        nextRoomStatus: room.roomStatus
      };
    }

    case 'CHANGE_STATUS_CHECKIN': {
      // Must be VACANT_CLEAN to check in
      if (room.roomStatus !== 'VACANT_CLEAN') {
        return {
          valid: false,
          errorCode: 'CANNOT_CHECKIN_UNCLEAN',
          errorMessage: `정비 및 점검이 완료된 공실(VACANT_CLEAN)만 입실 처리할 수 있습니다. (현재: ${room.roomStatus})`
        };
      }
      return {
        valid: true,
        nextRoomStatus: 'STOCK',
        nextCleaningStatus: 'NOT_REQUIRED'
      };
    }

    case 'CHANGE_STATUS_CHECKOUT': {
      // Checked out -> needs cleaning
      return {
        valid: true,
        nextRoomStatus: 'CHECKED_OUT',
        nextCleaningStatus: 'WAITING'
      };
    }

    case 'CHANGE_STATUS_OOO': {
      return {
        valid: true,
        nextRoomStatus: 'OOO',
        nextCleaningStatus: 'NOT_REQUIRED'
      };
    }

    case 'CHANGE_STATUS_READY': {
      return {
        valid: true,
        nextRoomStatus: 'VACANT_CLEAN',
        nextCleaningStatus: 'QM_COMPLETED'
      };
    }

    case 'TOGGLE_DND': {
      return {
        valid: true,
        nextRoomStatus: room.roomStatus,
        nextCleaningStatus: room.cleaningStatus
      };
    }

    default:
      return {
        valid: false,
        errorCode: 'UNSUPPORTED_ACTION',
        errorMessage: `지원하지 않는 객실 변경 작업입니다: ${action}`
      };
  }
}

/**
 * Role-based Action Permission Table
 */
function hasRolePermissionForAction(user: NovaUser, action: RoomActionType): boolean {
  const role = user.role;

  // Super admins & Admins can perform any room operations
  if (role === 'SUPER_ADMIN' || role === 'ADMIN' || role === 'MANAGER') {
    return true;
  }

  switch (action) {
    case 'CLEANING_START':
    case 'CLEANING_COMPLETE':
      return role === 'ROOM_MAID' || role === 'PART_TIME' || role === 'OUTSOURCE';

    case 'QM_ASSIGN':
    case 'QM_UNASSIGN':
    case 'INSPECTION_START':
    case 'INSPECTION_PASS':
    case 'INSPECTION_REWORK':
      return role === 'QM' || role === 'INSPECTOR';

    case 'ASSIGN_ROOMMAID':
    case 'CHANGE_STATUS_CHECKIN':
    case 'CHANGE_STATUS_CHECKOUT':
    case 'CHANGE_STATUS_OOO':
    case 'CHANGE_STATUS_READY':
    case 'TOGGLE_DND':
      return false; // Only Admin/Manager permitted

    default:
      return false;
  }
}
