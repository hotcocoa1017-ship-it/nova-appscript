# ?? NOVA ROOM MANAGEMENT SYSTEM (NOVA RMS)

> **호텔/리조트 실시간 반응형 객실운영 엔터프라이즈 Web Application**  
> 단순 데모(Mock)가 아닌, 현장 다중 직원(룸메이드, QM, 하우스맨, 프론트, 관리자)이 동시 접속하여 실시간으로 작업할 수 있는 프로덕션 시스템입니다.

---

## ?? 핵심 엔지니어링 특징

1. **상태 머신 (State Machine) 강제**
   - 클라이언트 화면만 바뀌는 것이 아니라, 서버(`validateStateTransition`)에서 엄격한 비즈니스 규칙 검증.
   - 예: 배정되지 않은 객실 임의 조작 차단, 정비 시작 전 완료 처리 차단, QM 승인 권한 분리.
2. **낙관적 동시성 제어 (Optimistic Concurrency Control - OCC)**
   - 객실 테이블의 `version` 컬럼을 통한 정합성 보장.
   - 2명 이상의 직원이 동일 객실을 동시 수정 시 409 Conflict 발생 및 최신 데이터 즉시 반환.
3. **네트워크 단절/중복 클릭 멱등성 (Idempotency)**
   - 클라이언트 `requestId` 디듀플리케이션 테이블(`nova_request_dedup`) 기반 안전한 재시도 지원.
4. **실시간 Realtime 브로드캐스트 & 복구 회복력**
   - Supabase Realtime / PostgreSQL WAL 트리거 연동으로 실시간 증분 패치.
   - 브라우저 Sleep/Wake 및 네트워크 재연결 시 상태 자동 대조(Reconciliation).
5. **지능형 하우스맨 디스패치 라우팅 엔진**
   - 층간 거리(40%), 가용성(25%), 현재 작업부하(20%), 전문분야(15%) 가중 평가로 최적 작업자 1초 내 자동 배정.
6. **모바일 현장 최적화 (PWA Ready)**
   - 모바일 화면 분할, 44px 이상 터치 타겟, 오프라인 내구력 및 현장 사번 원클릭 전환 모달.

---

## ?? 기본 현장 시드 계정 (원클릭 전환 가능)

| 사번 | 이름 | 역할 (Role) | 주요 권한 |
|---|---|---|---|
| **ADMIN-01** | 총괄관리자 | SUPER_ADMIN | 전체 권한, 직원 배정, 객실 상태 강제 조정, 시스템 설정 |
| **MGR-01** | 객실지배인 | MANAGER | 현황 모니터링, 마감 리포트, 오더 승인 |
| **QM-2001** | 강QM | QM | 5대 점검 체크리스트 검수, 점검 합격(공실 승인), 재정비 지시 |
| **QM-2002** | 이인스펙터 | INSPECTOR | 정비 완료 객실 검수 및 재정비 지시 |
| **1001** | 김순자 | ROOM_MAID | 본인 배정 객실 정비 시작/완료, 물품 추가 요청 |
| **1002** | 박영희 | ROOM_MAID | 본인 배정 객실 정비 시작/완료, 물품 추가 요청 |
| **hm-1** | 강민우 | HOUSEMAN | 2층 담당 물품/어메니티/린넨 신속 배달 및 처리 |
| **hm-2** | 정태양 | HOUSEMAN | 5층 담당 물품/어메니티/린넨 신속 배달 및 처리 |

---

## ?? 빠른 시작 (Quick Start)

### 1. 로컬 개발 환경 가동
```bash
# 의존성 설치
npm install

# 단위/통합 테스트 (13개 핵심 시나리오 검증)
npm test

# 프로덕션 빌드
npm run build

# 서버 실행 (포트 3000)
npm start
```

### 2. 라이브 E2E 테스트 실행
가동 중인 서버(`http://localhost:3000`)에 대해 실제 HTTP 요청 및 동시성 트랜잭션을 검증합니다:
```bash
node scripts/e2e-server-test.mjs
```

### 3. Docker 컨테이너 1분 구동 (PostgreSQL + Next.js App)
```bash
docker-compose up -d --build
```
- Web Application: `http://localhost:3000`
- PostgreSQL Database: `localhost:5432` (DB: `nova_rms`)

---

## ??? 데이터베이스 스키마 및 마이그레이션

- `sql/001_create_database.sql`: 테이블, 복합 인덱스, 트리거 함수 DDL
  - `nova_rooms_current` (객실 현재 상태 및 version)
  - `nova_users` (직원 및 RBAC 권한)
  - `nova_room_events` (모든 상태 변경 감사 로그)
  - `nova_request_dedup` (멱등성 보장 디듀플리케이션)
  - `nova_houseman_orders` (실시간 오더 및 작업자 배정)
- `sql/002_seed_initial_data.sql`: 60개 초기 객실(2~6층) 및 현장 계정

실제 외부 PostgreSQL / Supabase에 적용할 경우:
```bash
# .env.local에 DATABASE_URL 설정 후:
npm run db:migrate
npm run db:seed
```

---

## ?? 자동화 테스트 스위트 결과

- **단위/통합 테스트 (`npm test`)**: 13/13 통과 (100% PASS)
- **라이브 서버 E2E 트랜잭션 테스트 (`node scripts/e2e-server-test.mjs`)**: 12/12 통과 (100% PASS)
  - 다중 사용자(ADMIN, QM, MAID) 동시 접속 인증
  - 객실 배정 -> 정비 시작 -> 정비 완료 -> QM 점검 워크플로
  - 동일 객실 동시 수정 시 OCC (200 OK vs 409 Conflict) 완벽 차단
  - 실시간 감사 로그 누적 확인

---

## ?? 지원 환경

- **Desktop & Dashboard**: 대형 모니터 및 태블릿 가로 모드 (1200px+)
- **Mobile & Tablet PWA**: 현장 스마트폰(iPhone, Galaxy), 갤럭시 탭, 아이패드 (360px~768px 터치 최적화)
