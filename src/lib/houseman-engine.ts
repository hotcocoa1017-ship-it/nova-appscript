/**
 * NOVA Smart Houseman Dispatch Engine
 * Calculates optimal houseman routing based on floor distance, availability, workload, and specialty.
 */

import { HousemanCategory, HousemanOrder } from './types';

export interface HousemanStaff {
  id: string;
  name: string;
  phone: string;
  currentFloor: number;
  status: 'IDLE' | 'BUSY' | 'BREAK';
  specialties: HousemanCategory[];
  activeOrderCount: number;
  completedToday: number;
}

export const ACTIVE_HOUSEMEN: HousemanStaff[] = [
  {
    id: 'hm-1',
    name: '강민우',
    phone: '010-8890-2001',
    currentFloor: 2,
    status: 'IDLE',
    specialties: ['TOWEL', 'AMENITY', 'LUGGAGE'],
    activeOrderCount: 0,
    completedToday: 6
  },
  {
    id: 'hm-2',
    name: '정태양',
    phone: '010-8890-2002',
    currentFloor: 5,
    status: 'IDLE',
    specialties: ['MAINTENANCE', 'BEDDING'],
    activeOrderCount: 1,
    completedToday: 8
  },
  {
    id: 'hm-3',
    name: '한지훈',
    phone: '010-8890-2003',
    currentFloor: 3,
    status: 'BUSY',
    specialties: ['TOWEL', 'AMENITY', 'ROOM_SERVICE'],
    activeOrderCount: 2,
    completedToday: 5
  },
  {
    id: 'hm-4',
    name: '조진우',
    phone: '010-8890-2004',
    currentFloor: 4,
    status: 'IDLE',
    specialties: ['MAINTENANCE', 'LUGGAGE'],
    activeOrderCount: 0,
    completedToday: 7
  }
];

export interface HousemanScoreResult {
  houseman: HousemanStaff;
  score: number;
  distance: number;
  reasons: string[];
}

/**
 * Evaluates all active housemen and ranks them for optimal auto-assignment.
 */
export function rankHousemenForOrder(
  targetFloor: number,
  category: HousemanCategory,
  staffList: HousemanStaff[] = ACTIVE_HOUSEMEN
): HousemanScoreResult[] {
  return staffList
    .map(staff => {
      let score = 100;
      const reasons: string[] = [];

      // 1. Distance Penalty (-15 pts per floor difference)
      const distance = Math.abs(staff.currentFloor - targetFloor);
      score -= distance * 15;
      if (distance === 0) {
        reasons.push('동일 층 대기중 (+0)');
      } else {
        reasons.push(`${distance}개 층 이동 (-${distance * 15})`);
      }

      // 2. Availability (IDLE = +30, BUSY = -20, BREAK = -80)
      if (staff.status === 'IDLE') {
        score += 30;
        reasons.push('즉시 출동 가능 (+30)');
      } else if (staff.status === 'BUSY') {
        score -= 20;
        reasons.push('현재 작업중 (-20)');
      } else if (staff.status === 'BREAK') {
        score -= 80;
        reasons.push('휴식중 (-80)');
      }

      // 3. Workload balancing (-10 per active order)
      if (staff.activeOrderCount > 0) {
        score -= staff.activeOrderCount * 10;
        reasons.push(`진행중 오더 ${staff.activeOrderCount}건 (-${staff.activeOrderCount * 10})`);
      } else {
        score += 10;
        reasons.push('대기 오더 없음 (+10)');
      }

      // 4. Specialty Bonus (+25 if matches)
      if (staff.specialties.includes(category)) {
        score += 25;
        reasons.push(`카테고리(${category}) 전담 매칭 (+25)`);
      }

      return {
        houseman: staff,
        score,
        distance,
        reasons
      };
    })
    .sort((a, b) => b.score - a.score);
}

/**
 * Returns the best recommended houseman for an order.
 */
export function selectBestHouseman(
  targetFloor: number,
  category: HousemanCategory,
  staffList: HousemanStaff[] = ACTIVE_HOUSEMEN
): HousemanScoreResult {
  const ranked = rankHousemenForOrder(targetFloor, category, staffList);
  return ranked[0];
}
