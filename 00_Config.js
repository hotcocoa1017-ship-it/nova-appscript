/**
 * NOVA 공통 설정 (전체 시스템 기준)
 */
const NOVA = Object.freeze({
  APP_NAME: 'NOVA',
  VERSION: '1.0.0-RC6.4.42',
  TIMEZONE: 'Asia/Seoul',
  DATE_FORMAT: 'yyyy-MM-dd',
  DATETIME_FORMAT: 'yyyy-MM-dd HH:mm:ss',
  LOGIN_TOKEN_HOURS: 12,
  CACHE_SECONDS: 600,
  CODE_CACHE_SECONDS: 900,
  CURRENT_INDEX_CACHE_SECONDS: 300,
  HISTORY_INDEX_CACHE_SECONDS: 600,
  CACHE_MAX_CHARS: 90000,
  PERFORMANCE_LIMIT_MS: 3000,
  INDICATOR_SYNC_MS: 6000,
  MOBILE_SYNC_MS: 10000,
  SYNC_JITTER_RATIO: 0.35,
  WRITE_LOCK_TIMEOUT_MS: 2500,
  DELTA_CACHE_SECONDS: 30,
  SNAPSHOT_CACHE_SECONDS: 45,
  ORDER_VISIBLE_ROWS: 3,
  HOUSEMAN_TELEGRAM_REMINDER_MINUTES: 3,
  SHEETS: Object.freeze({
    USERS: '사용자계정',
    ROOMS: '객실마스터',
    CURRENT: '현재객실현황',
    HISTORY: '업무이력',
    CODES: '코드설정',
    MONTHLY: '월별조회'
  }),
  USER_HEADERS: Object.freeze([
    '사번', '이름', '직무', '채용구분', '권한', '사용여부',
    '텔레그램ID', '텔레그램알림', '연락처',
    '기본사업장', '기본담당동', '비고', '수정일시',
    '텔레그램연결키', '텔레그램연결링크', '텔레그램연결상태', '텔레그램연결일시'
  ]),
  ROOM_HEADERS: Object.freeze([
    '객실번호', '사업장', '동', '객실타입', '정비타입',
    '사용여부', '수정일시'
  ]),
  CURRENT_HEADERS: Object.freeze([
    '업무일자', '객실번호', '사업장', '객실상태', '청소상태',
    '정비유형', '배정유형', '룸메이드사번', '보조룸메이드사번', 'QM사번', '마지막변경버전', '수정일시',
    '동', '하우스맨상태', '하우스맨미완료수', '객실운영상태'
  ]),
  HISTORY_HEADERS: Object.freeze([
    '기록ID', '기록구분', '업무일자', '사업장', '객실번호',
    '대상사번', '처리상태', '세부내용JSON', '등록사번',
    '등록일시', '수정일시',
    '파트', '품목', '수량', '추가내용', '요청자',
    '배정사번', '처리자사번', '중요여부', '인수인계여부',
    '접수일시', '처리시작일시', '완료일시', '처리불가사유',
    '변경버전', '삭제여부'
  ]),
  CODE_HEADERS: Object.freeze([
    '코드그룹', '코드', '표시명', '정렬순서', '사용여부', '비고'
  ]),
  MONTHLY_HEADERS: Object.freeze([
    '조회연도', '조회월', '조회구분', '조회일시'
  ]),
  RECORD_TYPES: Object.freeze({
    HOUSEMAN_ORDER: 'HOUSEMAN_ORDER',
    HOUSEMAN_AUDIT: 'HOUSEMAN_AUDIT',
    CLEANING: 'CLEANING',
    QM: 'QM',
    TELEGRAM_QUEUE: 'TELEGRAM_QUEUE',
    ROOM_STATUS_UPLOAD: 'ROOM_STATUS_UPLOAD',
    ROOM_STATUS_CHANGE: 'ROOM_STATUS_CHANGE',
    TELEGRAM_NOTICE: 'TELEGRAM_NOTICE',
    SHIFT_ASSIGNMENT: 'SHIFT_ASSIGNMENT',
    HOUSEMAN_ZONE_ASSIGNMENT: 'HOUSEMAN_ZONE_ASSIGNMENT',
    DEPARTURE_DELAY: 'DEPARTURE_DELAY',
    DAILY_CLOSE: 'DAILY_CLOSE',
    ROOMMAID_CLOSE_AUDIT: 'ROOMMAID_CLOSE_AUDIT',
    ADMIN_SETTING: 'ADMIN_SETTING',
    QM_CHECKLIST: 'QM_CHECKLIST'
  }),
  CLEANING_TYPES: Object.freeze({
    NORMAL: 'NORMAL',
    DS: 'DS',
    FIVE_S: '5S',
    EVALUATION: 'EVALUATION',
    STAFF_DORM: 'STAFF_DORM',
    DEEP_CLEANING: 'DEEP_CLEANING'
  }),
  ROOMMAID_ASSIGNMENT_TYPES: Object.freeze({
    SOLO: 'SOLO',
    PAIR: 'PAIR',
    PAIR_TRAINING: 'PAIR_TRAINING'
  }),
  SHIFTS: Object.freeze({
    A: Object.freeze({ code: 'A', label: 'A조', start: '08:30', end: '17:30', order: 1 }),
    B: Object.freeze({ code: 'B', label: 'B조', start: '14:30', end: '23:30', order: 2 }),
    C: Object.freeze({ code: 'C', label: 'C조', start: '23:30', end: '08:30', order: 3 })
  }),
  MAX_SHIFT_STAFF: 10,
  DEPARTURE_DELAY: Object.freeze({
    WEEKDAY_CHECKOUT: '12:00',
    WEEKDAY_ALERT: '13:00',
    WEEKEND_CHECKOUT: '11:00',
    WEEKEND_ALERT: '12:00',
    TRIGGER_MINUTES: 5,
    HISTORY_SCAN_ROWS: 20000
  }),
  ORDER_STATUS: Object.freeze({
    REGISTERED: '등록',
    ASSIGNED: '배정',
    ACCEPTED: '접수',
    PROCESSING: '처리중',
    COMPLETED: '완료',
    UNABLE: '처리불가'
  })
});

function getSpreadsheet_() { // (기준 스프레드시트 조회·실행 중 재사용)
  if (typeof NOVA_RUNTIME_CACHE_ !== 'undefined' && NOVA_RUNTIME_CACHE_.spreadsheet) {
    return NOVA_RUNTIME_CACHE_.spreadsheet;
  }
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (typeof NOVA_RUNTIME_CACHE_ !== 'undefined') NOVA_RUNTIME_CACHE_.spreadsheet = spreadsheet;
  return spreadsheet;
}

function nowText_() { // (현재 시각 문자열)
  return Utilities.formatDate(new Date(), NOVA.TIMEZONE, NOVA.DATETIME_FORMAT);
}

function businessDateText_() { // (공통 업무일자 · 09:00 이전 전일 · NOVA_BUSINESS_DATE_0900_V1)
  const now = new Date();
  const localHour = Number(Utilities.formatDate(now, NOVA.TIMEZONE, 'H'));
  const businessAt = localHour < 9 ? new Date(now.getTime() - 24 * 60 * 60 * 1000) : now;
  return Utilities.formatDate(businessAt, NOVA.TIMEZONE, NOVA.DATE_FORMAT);
}

function normalizeBusinessDate_(value) { // (업무일자 형식 정리)
  const text = String(value || '').trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : businessDateText_();
}

function normalizeRoomBuilding_(building, roomNo) { // (4자리 객실번호 첫 자리 기준 동 강제 정합)
  const digits = String(roomNo || '').replace(/\D/g, '');
  if (digits.length === 4 && /^[1-9]$/.test(digits.charAt(0))) return `${digits.charAt(0)}동`;
  const text = String(building || '').trim();
  const simple = text.match(/^0?([1-9])(?:\s*동)?$/);
  if (simple) return `${Number(simple[1])}동`;
  return text;
}

function normalizeYesNo_(value) { // (Y/N 값 정리)
  return String(value || '').trim().toUpperCase() === 'Y' ? 'Y' : 'N';
}

function isCleaningTargetRoomStatus_(roomStatus) { // (퇴실·재고 정비대상 상태 판정)
  return ['CHECKED_OUT', 'STOCK', 'STOCK_RC', 'STOCK_HU'].includes(String(roomStatus || '').trim().toUpperCase());
}

function isCleaningCompletedStatus_(cleaningStatus) { // (정비 완료 상태 판정)
  return ['COMPLETED', 'QM_COMPLETED'].includes(String(cleaningStatus || '').trim().toUpperCase());
}

function getRoommaidCleaningTypeDefinitions_() { // (룸메이드 정비유형 공통 기준)
  return [
    { code: NOVA.CLEANING_TYPES.NORMAL, label: '일반정비', creditMultiplier: 1, stockReducing: true },
    { code: NOVA.CLEANING_TYPES.DS, label: 'D/S', creditMultiplier: 0.5, stockReducing: false },
    { code: NOVA.CLEANING_TYPES.FIVE_S, label: '5S', creditMultiplier: 1.5, stockReducing: true },
    { code: NOVA.CLEANING_TYPES.EVALUATION, label: '평가원', creditMultiplier: 1.5, stockReducing: true },
    { code: NOVA.CLEANING_TYPES.STAFF_DORM, label: '직원숙소', creditMultiplier: 1.5, stockReducing: true },
    { code: NOVA.CLEANING_TYPES.DEEP_CLEANING, label: '딥크리닝', creditMultiplier: 1.5, stockReducing: true }
  ];
}

function normalizeRoommaidCleaningType_(value) { // (룸메이드 정비유형 코드 정리)
  const raw = String(value || '').trim();
  const upper = raw.toUpperCase().replace(/\s+/g, '_');
  const aliases = {
    NORMAL: NOVA.CLEANING_TYPES.NORMAL, '일반정비': NOVA.CLEANING_TYPES.NORMAL,
    DS: NOVA.CLEANING_TYPES.DS, 'D/S': NOVA.CLEANING_TYPES.DS,
    '5S': NOVA.CLEANING_TYPES.FIVE_S,
    EVALUATION: NOVA.CLEANING_TYPES.EVALUATION, '평가원': NOVA.CLEANING_TYPES.EVALUATION,
    STAFF_DORM: NOVA.CLEANING_TYPES.STAFF_DORM, '직원숙소': NOVA.CLEANING_TYPES.STAFF_DORM,
    DEEP_CLEANING: NOVA.CLEANING_TYPES.DEEP_CLEANING, '딥크리닝': NOVA.CLEANING_TYPES.DEEP_CLEANING
  };
  return aliases[raw] || aliases[upper] || upper || NOVA.CLEANING_TYPES.NORMAL;
}

function getRoommaidCleaningTypeLabel_(value) { // (룸메이드 정비유형 표시명)
  const code = normalizeRoommaidCleaningType_(value);
  const found = getRoommaidCleaningTypeDefinitions_().find(item => item.code === code);
  return found ? found.label : code;
}

function getRoommaidCleaningCreditUnit_(value) { // (정비유형별 인정정비수 배수)
  const code = normalizeRoommaidCleaningType_(value);
  const found = getRoommaidCleaningTypeDefinitions_().find(item => item.code === code);
  return Number(found && found.creditMultiplier || 1);
}

function isRoommaidStockReducingCleaningType_(value) { // (마감 재고 차감 정비유형 판정)
  const code = normalizeRoommaidCleaningType_(value);
  const found = getRoommaidCleaningTypeDefinitions_().find(item => item.code === code);
  return found ? found.stockReducing !== false : true;
}
