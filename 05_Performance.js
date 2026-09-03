/**
 * 핵심 API의 3초 성능 기준, 변경버전 분리, 동시 저장 보호
 */
function measureResponse_(name, callback) { // (API 처리시간 측정)
  const startedAt = Date.now();
  try {
    const result = callback();
    const elapsedMs = Date.now() - startedAt;
    return Object.assign({}, result, {
      performance: {
        api: name,
        elapsedMs,
        targetMs: NOVA.PERFORMANCE_LIMIT_MS,
        passed: elapsedMs <= NOVA.PERFORMANCE_LIMIT_MS
      }
    });
  } catch (error) {
    const elapsedMs = Date.now() - startedAt;
    return {
      ok: false,
      message: error && error.message ? error.message : String(error),
      code: error && error.code ? error.code : '',
      performance: {
        api: name,
        elapsedMs,
        targetMs: NOVA.PERFORMANCE_LIMIT_MS,
        passed: elapsedMs <= NOVA.PERFORMANCE_LIMIT_MS
      }
    };
  }
}

function getDataVersion_() { // (전체 업무데이터 변경버전 조회·통계/캐시 호환)
  const properties = PropertiesService.getScriptProperties();
  const value = Number(properties.getProperty('NOVA_DATA_VERSION') || 0);
  return Number.isFinite(value) ? value : 0;
}

function bumpDataVersion_(context) { // (호환용: 전체버전 예약 후 즉시 동기화영역 공개)
  const safe = context || {};
  const version = reserveDataVersion_({ lockHeld: Boolean(safe.lockHeld) });
  publishDataVersion_(version, safe);
  return version;
}

function reserveDataVersion_(context) { // (쓰기 전에 전체 변경번호만 원자적으로 예약)
  const safe = context || {};
  const update = () => {
    const properties = PropertiesService.getScriptProperties();
    const next = Number(properties.getProperty('NOVA_DATA_VERSION') || 0) + 1;
    properties.setProperty('NOVA_DATA_VERSION', String(next));
    return next;
  };
  if (safe.lockHeld) return update();
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) {
    const error = new Error('동시 요청이 많아 변경버전을 확보하지 못했습니다. 잠시 후 다시 시도하세요.');
    error.code = 'BUSY_RETRY';
    throw error;
  }
  try { return update(); } finally { lock.releaseLock(); }
}

function publishDataVersion_(version, context) { // (기준 데이터 저장 후 업무영역 변경 공개)
  const safe = context || {};
  const publish = () => {
    const numericVersion = Number(version || 0);
    if (!numericVersion) return 0;
    const properties = PropertiesService.getScriptProperties();
    const current = properties.getProperties();
    const domains = normalizeSyncDomains_(safe.domains || safe.domain);
    const keys = domains.length
      ? domains.flatMap(domain => scopedVersionKeysForWrite_(domain, safe.businessDate, safe.site))
      : [buildSyncVersionKey_('SYSTEM', '', '')];
    const updates = {};
    Array.from(new Set(keys)).forEach(key => {
      updates[key] = String(Math.max(Number(current[key] || 0), numericVersion));
    });
    if (Object.keys(updates).length) properties.setProperties(updates, false);
    return numericVersion;
  };
  if (safe.lockHeld) return publish();
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) {
    const error = new Error('변경사항은 저장되었지만 동기화 공개가 지연되었습니다. 새로고침하여 확인하세요.');
    error.code = 'SYNC_PUBLISH_DELAYED';
    throw error;
  }
  try { return publish(); } finally { lock.releaseLock(); }
}

function getIndicatorSyncVersion_(request) { // (통합 인디게이터에 필요한 영역 버전)
  const safe = request || {};
  return getSyncVersion_(['ROOM', 'ORDER', 'SHIFT'], safe.businessDate, safe.site);
}

function getMobileSyncVersion_(role, request) { // (직무별 모바일에 필요한 영역 버전)
  const safe = request || {};
  const normalizedRole = String(role || '').trim().toUpperCase();
  const domains = normalizedRole === 'HOUSEMAN' ? ['ORDER', 'SHIFT'] : ['ROOM'];
  return getSyncVersion_(domains, safe.businessDate, safe.site);
}

function getSyncVersion_(domains, businessDate, site) { // (시스템·설정·업무영역 조합버전)
  const properties = PropertiesService.getScriptProperties().getProperties();
  const keys = [
    buildSyncVersionKey_('SYSTEM', '', ''),
    buildSyncVersionKey_('CONFIG', '', '')
  ];
  normalizeSyncDomains_(domains).forEach(domain => {
    keys.push(buildSyncVersionKey_(domain, '', ''));
    const date = normalizeSyncDate_(businessDate);
    const normalizedSite = String(site || '').trim();
    if (date) {
      keys.push(buildSyncVersionKey_(domain, date, normalizedSite || '*'));
    }
  });
  return keys.reduce((max, key) => {
    const value = Number(properties[key] || 0);
    return Number.isFinite(value) ? Math.max(max, value) : max;
  }, 0);
}

function scopedVersionKeysForWrite_(domain, businessDate, site) { // (변경영역의 정확/전체사업장 버전키)
  const normalizedDomain = String(domain || '').trim().toUpperCase();
  if (!normalizedDomain) return [];
  const date = normalizeSyncDate_(businessDate);
  const normalizedSite = String(site || '').trim();
  if (!date) return [buildSyncVersionKey_(normalizedDomain, '', '')];
  const result = [buildSyncVersionKey_(normalizedDomain, date, normalizedSite || '*')];
  if (normalizedSite) result.push(buildSyncVersionKey_(normalizedDomain, date, '*'));
  return Array.from(new Set(result));
}

function buildSyncVersionKey_(domain, businessDate, site) { // (ScriptProperties 길이 제한을 고려한 동기화버전키)
  const raw = [
    String(domain || '').trim().toUpperCase() || 'SYSTEM',
    normalizeSyncDate_(businessDate) || '*',
    String(site || '').trim() || '*'
  ].join('|');
  const digest = Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, raw)
  ).replace(/=+$/g, '').slice(0, 24);
  return `NOVA_SYNC_V2_${digest}`;
}

function normalizeSyncDomains_(domains) { // (동기화 영역 목록 정리)
  return Array.from(new Set((Array.isArray(domains) ? domains : [domains])
    .map(value => String(value || '').trim().toUpperCase())
    .filter(Boolean)));
}

function normalizeSyncDate_(value) { // (버전키용 업무일자 정리·빈값 보존)
  const text = String(value || '').trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : '';
}

function assertExpectedVersion_(expectedVersion, actualVersion, label) { // (낙관적 동시수정 충돌 검사)
  const expected = Number(expectedVersion || 0);
  const actual = Number(actualVersion || 0);
  if (expected > 0 && expected !== actual) {
    const error = new Error(`${label || '자료'}가 다른 사용자에 의해 먼저 변경되었습니다. 최신 화면을 불러온 뒤 다시 처리하세요.`);
    error.code = 'VERSION_CONFLICT';
    throw error;
  }
}

function acquireWriteLock_(timeoutMs) { // (모든 핵심 쓰기를 하나의 짧은 ScriptLock으로 직렬화)
  const lock = LockService.getScriptLock();
  const waitMs = Math.max(500, Number(timeoutMs || NOVA.WRITE_LOCK_TIMEOUT_MS || 2500));
  if (!lock.tryLock(waitMs)) {
    const error = new Error('동시 저장 요청이 많습니다. 잠시 후 다시 처리하세요.');
    error.code = 'BUSY_RETRY';
    throw error;
  }
  return lock;
}

function acquireUserWriteLock_(timeoutMs) { // CONCURRENT_WRITE_RESILIENCE_V1 · 사용자별 독립 저장 직렬화
  const lock = LockService.getUserLock();
  const waitMs = Math.max(500, Number(timeoutMs || NOVA.WRITE_LOCK_TIMEOUT_MS || 2500));
  if (!lock.tryLock(waitMs)) {
    const error = new Error('현재 계정의 저장 요청이 겹쳤습니다. 잠시 후 다시 처리하세요.');
    error.code = 'BUSY_RETRY';
    throw error;
  }
  return lock;
}

function getCachedJson_(key) { // (짧은 응답 캐시 조회)
  const cached = CacheService.getScriptCache().get(String(key || ''));
  if (!cached) return null;
  try { return JSON.parse(cached); } catch (error) { return null; }
}

function putCachedJson_(key, value, seconds) { // (용량 제한 내 짧은 응답 캐시 저장)
  const serialized = JSON.stringify(value);
  if (serialized.length > Number(NOVA.CACHE_MAX_CHARS || 90000)) return false;
  CacheService.getScriptCache().put(String(key || ''), serialized, Number(seconds || NOVA.DELTA_CACHE_SECONDS || 12));
  return true;
}

function buildDeltaCacheKey_(prefix, parts) { // (변경 스냅샷 단기 캐시키)
  const raw = [String(prefix || 'DELTA')].concat((parts || []).map(value => String(value == null ? '' : value))).join('|');
  const digest = Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, raw)
  ).replace(/=+$/g, '').slice(0, 30);
  return `NOVA_DELTA_V2_${digest}`;
}
