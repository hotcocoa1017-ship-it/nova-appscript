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
function getNovaRealtimeClientConfig() {
  const props = PropertiesService.getScriptProperties();
  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '')
    .trim()
    .replace(/\/+$/, '');
  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N')
    .trim()
    .toUpperCase() === 'Y';

  return {
    ok: true,
    enabled: Boolean(enabled && apiBase),
    apiBase: apiBase,
    mode: enabled && apiBase ? 'REALTIME' : 'LEGACY'
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
  return {
    ok: true,
    enabled: String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N'),
    apiBase: String(props.getProperty('NOVA_REALTIME_API_BASE') || ''),
    message: 'Realtime 설정을 확인했습니다. 검증 전에는 ENABLED=N을 유지하세요.'
  };
}
