/**
 * NOVA Realtime Client 설정 브리지 v2.2
 *
 * 새 NOVA 복사본 프로젝트에만 추가합니다.
 * 이 파일은 비밀값을 브라우저에 전달하지 않습니다.
 * 브라우저에는 Realtime 사용여부와 Cloud Run 공개 URL만 전달합니다.
 *
 * Script Properties:
 *   NOVA_REALTIME_ENABLED = N 또는 Y
 *   NOVA_REALTIME_API_BASE = https://xxxx.run.app
 */
function getNovaRealtimeClientConfig(token) { // QM_DRAFT_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '')
    .trim()
    .replace(/\/+$/, '');
  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N')
    .trim()
    .toUpperCase() === 'Y';

  let qmDraftDbFirstEnabled = false;
  const qmDraftMode = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED') || 'CANARY').trim().toUpperCase();
  const qmDraftConfiguredEmployees = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES') || '')
    .split(',').map(value => value.trim()).filter(Boolean);
  const qmDraftCanaryEmployees = Object.freeze(['q001']); // QM_DRAFT_CANARY_Q001_V1
  const qmDraftEmployees = qmDraftMode === 'CANARY' ? Array.from(qmDraftCanaryEmployees) : qmDraftConfiguredEmployees;
  const qmDraftMasterEnabled = qmDraftMode === 'CANARY' || qmDraftMode === 'Y';
  if (qmDraftMasterEnabled && qmDraftEmployees.length && token) {
    const verified = verifyNovaToken(token);
    const user = verified && verified.ok ? verified.user : null;
    qmDraftDbFirstEnabled = Boolean(user
      && String(user.role || '').trim().toUpperCase() === 'QM'
      && qmDraftEmployees.includes(String(user.employeeNo || '').trim()));
  }

  return {
    ok: true,
    enabled: Boolean(enabled && apiBase),
    apiBase: apiBase,
    mode: enabled && apiBase ? 'REALTIME' : 'LEGACY',
    qmDraftDbFirstEnabled // QM_DRAFT_DB_FIRST_V1
  };
}

/**
 * 새 프로젝트 기본값 생성용. 이미 값이 있으면 변경하지 않습니다.
 */
function setupNovaRealtimeClientConfig() {
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('NOVA_REALTIME_ENABLED')) {
    props.setProperty('NOVA_REALTIME_ENABLED', 'N');
  }
  if (!props.getProperty('NOVA_REALTIME_API_BASE')) {
    props.setProperty('NOVA_REALTIME_API_BASE', '');
  }
  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED', 'CANARY');
  }
  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES', 'q001');
  }
  return {
    ok: true,
    enabled: String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N'),
    apiBase: String(props.getProperty('NOVA_REALTIME_API_BASE') || ''),
    message: 'Realtime 설정을 확인했습니다. 검증 전에는 ENABLED=N을 유지하세요.'
  };
}
