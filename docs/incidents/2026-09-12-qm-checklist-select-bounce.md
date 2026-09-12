# 2026-09-12 QM 체크리스트 양호/불량 선택 튕김

## 증상
모바일 QM 체크리스트에서 `양호/불량` select를 열거나 선택하는 순간 native picker가 닫히는 현상이 발생했다.

## 원인
체크리스트 모달이 이미 열린 상태에서 DB-first 점검 시작/기존 이력 미러 비동기 처리가 완료되면 `beginQmInspectionDraftInit_` 후속 경로가 `active.localDirty === false`인 경우 `openQmInspectionModal_()`을 다시 호출한다. 모바일 native select는 실제 change/input 이벤트가 확정되기 전까지 `localDirty`가 false이므로, picker가 열린 사이 모달 DOM이 교체되면 브라우저가 picker를 강제로 닫는다. 최근 schema-cache 지연으로 비동기 완료 시점이 길어지면서 이 race가 더 잘 드러났다.

## 수정
`QmChecklistInteractionGuard.html`에서 QM 결과 select의 첫 pointer/touch interaction 시 기존 `input` 이벤트를 한 번 선행 발생시킨다. 기존 Client의 `scheduleQmInspectionAutosave_()`가 동기적으로 `active.localDirty = true`를 설정하므로, 비동기 시작/미러 완료 콜백이 열린 모달을 다시 렌더링하지 않는다.

값 자체는 변경하지 않으며 native select 기본동작, 실제 change/input, 0.8초 자동저장, 양호/불량 판정, 최종제출, 재정비 정책은 기존 로직을 그대로 사용한다.

## 영구 불변조건
- QM 결과 select 조작 중 열린 체크리스트 모달 DOM을 비동기 초기화 완료 경로가 교체해서는 안 된다.
- 결과 select의 기본동작을 `preventDefault`, `stopPropagation`, `stopImmediatePropagation`으로 차단하지 않는다.
- select 안정화 수정은 QM 최종제출/재정비/객실 상태 정책을 변경하지 않는다.
- canonical production deploy 전에 `scripts/validate_qm_checklist_interaction_stability_20260912.py`를 통과해야 한다.
