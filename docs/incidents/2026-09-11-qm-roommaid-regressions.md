# 2026-09-11 NOVA 운영 오류 재발방지 기록

이 문서는 2026-09-11 운영 중 확인된 QM/룸메이드 오류를 향후 변경 시 회귀검증 기준으로 유지하기 위한 기록이다.

## 1. QM 점검계속 버튼 깜빡임/사라짐
- 증상: DB는 `QM_CHECKING + 현재 QM`인데 목록 재렌더 시 `점검 계속` 버튼이 나타났다 사라짐.
- 원인: 기존 Sheet/snapshot 렌더와 PostgreSQL DB-authority 후행 보정이 경쟁함.
- 보호: `QmDbReadAuthorityClient.html`
  - `QM_DB_READ_AUTHORITY_V1`
  - `QM_DB_BUTTON_STABILITY_V1`
  - DB authority 30초 캐시
  - MutationObserver에서 paint 전 캐시 즉시 재적용
  - 상태변경 클릭 후 cache invalidation
- DB 무결성 보호: `QM_CHECKING` 상태에서 담당 QM 유실 방지 trigger 및 active draft owner 복구 로직 유지.

## 2. QM 임시저장/점검완료·결과저장 무반응
- 증상: 버튼을 선택해도 아무 반응이 없음.
- 원인: DB-first 점검 시작은 완료됐지만 legacy Sheet mirror가 지연/실패하면 저장/완료 버튼이 `disabled` 상태로 남음.
- 보호: `QmDbFirstControlsHotfix.html`
  - `QM_DBFIRST_SAVE_UNBLOCK_V2`
  - Sheet mirror 전용 잠금만 해제
  - 실제 점검 시작 처리 중 잠금은 유지
  - 실제 저장/완료 처리 중 중복 클릭 방지
  - 클릭 즉시 처리중 표시
- 기존 최종제출 API, 권한, DB 상태전환은 변경하지 않는다.

## 3. 룸메이드 청소시작 후 객실 카드 사라짐
- 사례: 9/11 쏘라노 1308호.
- 확인 당시 DB: `CHECKED_OUT / CLEANING / roommaid 337906`로 정상. 통합 인디케이터도 청소중 정상.
- 원인 범위: 청소시작 DB 확정 후 모바일 후속 목록 재구성에서 객실 카드가 일시 누락될 수 있음.
- 보호: `RoommaidCleaningRetentionHotfix.html`
  - `ROOMMAID_CLEANING_CARD_RETENTION_V1`
  - 청소중 카드 최대 90초 보호
  - 정상 목록에 안정적으로 재등장하면 보호 자동 해제
  - 청소완료 클릭 시 즉시 보호 해제
  - 기존 click handler를 가로채지 않음
  - DB/Cloud Run/배정/청소상태 쓰기 로직을 변경하지 않음

## 공통 회귀 금지 원칙
1. PostgreSQL current state가 확정된 뒤 legacy Sheet mirror 지연 때문에 사용자 동작을 막지 않는다.
2. `QM_CHECKING + 본인 QM`이면 점검 계속 경로가 항상 존재해야 한다.
3. `CLEANING + 본인 룸메이드 배정`이면 룸메이드 진행 화면에서 객실 카드가 유지되어야 한다.
4. 후행 UI 보정은 기존 이벤트를 `preventDefault`, `stopPropagation`, `stopImmediatePropagation`으로 가로채지 않는다.
5. 기존 기능, 화면 구성, 권한, 상태변경 API, 데이터 흐름을 필요 이상으로 수정하지 않는다.
6. 수정 시 반드시 `scripts/validate_incident_regressions_20260911.py`를 통과한다.

## 2026-09-11 사후 DB 검증
다음 항목은 운영 DB에서 0건임을 확인했다.
- `CLEANING`인데 룸메이드/보조룸메이드가 모두 없는 객실
- `QM_CHECKING`인데 QM 담당자가 없는 객실
- `QM_CHECKING`인데 active `IN_PROGRESS` draft가 없는 객실
- room QM owner와 active draft QM owner 불일치
- 동일 객실 active `IN_PROGRESS` QM draft 중복

주의: 업로드 시점부터 이미 `COMPLETED`인 객실은 당일 `CLEANING_COMPLETE` 이벤트나 룸메이드 배정이 없을 수 있으므로 이것만으로 오류로 판정하지 않는다.
