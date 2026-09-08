/**
 * NOVA Realtime Client 설정 브리지 v2.3
 *
 * 새 NOVA 복사본 프로젝트에만 추가합니다.
 * 이 파일은 비밀값을 브라우저에 전달하지 않습니다.
 * 브라우저에는 Realtime 사용여부와 Cloud Run 공개 URL만 전달합니다.
 *
 * Script Properties:
 *   NOVA_REALTIME_ENABLED = N 또는 Y
 *   NOVA_REALTIME_API_BASE = https://xxxx.run.app
 */
function buildNovaRealtimeClientConfig_(user, properties) { // BOOTSTRAP_REALTIME_CONFIG_PERF_V1 · 이미 검증된 사용자 재사용
  const props = properties || PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '')
    .trim()
    .replace(/\/+$/, '');
  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N')
    .trim()
    .toUpperCase() === 'Y';
  const qmDraftMode = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase();
  const qmDraftMasterEnabled = qmDraftMode === 'CANARY' || qmDraftMode === 'Y';
  const qmDraftDbFirstEnabled = Boolean(qmDraftMasterEnabled
    && user
    && String(user.role || '').trim().toUpperCase() === 'QM');

  return {
    ok: true,
    enabled: Boolean(enabled && apiBase),
    apiBase,
    mode: enabled && apiBase ? 'REALTIME' : 'LEGACY',
    qmDraftDbFirstEnabled // QM_DRAFT_DB_FIRST_V1
  };
}

function getNovaRealtimeClientConfig(token) { // QM_DRAFT_DB_FIRST_V1 · QM_DRAFT_PROMOTE_ALL_20260905
  const props = PropertiesService.getScriptProperties();
  const qmDraftMode = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase();
  const qmDraftMasterEnabled = qmDraftMode === 'CANARY' || qmDraftMode === 'Y';
  let user = null;
  if (qmDraftMasterEnabled && token) {
    const verified = verifyNovaToken(token);
    user = verified && verified.ok ? verified.user : null;
  }
  return buildNovaRealtimeClientConfig_(user, props);
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
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED', 'Y');
  }
  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES', '');
  }
  return {
    ok: true,
    enabled: String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N'),
    apiBase: String(props.getProperty('NOVA_REALTIME_API_BASE') || ''),
    message: 'Realtime 설정을 확인했습니다. 검증 전에는 ENABLED=N을 유지하세요.'
  };
}
