/**
 * NOVA 개인 알림음 설정 V2
 * - 사번별 ScriptProperties 저장
 * - 앱 실행 중 Web Audio 효과음/음량에 사용
 * - Web Push 백그라운드 알림음은 OS 정책을 따름
 */
const NOVA_NOTIFICATION_PREF_V2_PREFIX_ = 'NOVA_NOTIFICATION_PREF_V2_';
const NOVA_NOTIFICATION_SOUND_TYPES_V2_ = Object.freeze(['CHIME', 'BELL', 'DOUBLE', 'ALERT']);

function novaNotificationPreferenceKeyV2_(employeeNo) {
  const safe = String(employeeNo || '').trim();
  const digest = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    safe,
    Utilities.Charset.UTF_8
  );
  return NOVA_NOTIFICATION_PREF_V2_PREFIX_
    + Utilities.base64EncodeWebSafe(digest).replace(/=+$/g, '').slice(0, 40);
}

function defaultNovaNotificationPreferencesV2_() {
  return {
    soundEnabled: true,
    soundType: 'CHIME',
    volume: 70
  };
}

function normalizeNovaNotificationPreferencesV2_(input) {
  const source = input && typeof input === 'object' ? input : {};
  const defaults = defaultNovaNotificationPreferencesV2_();
  const rawType = String(source.soundType || defaults.soundType).trim().toUpperCase();
  const rawVolume = Number(source.volume);
  return {
    soundEnabled: source.soundEnabled == null ? defaults.soundEnabled : Boolean(source.soundEnabled),
    soundType: NOVA_NOTIFICATION_SOUND_TYPES_V2_.includes(rawType) ? rawType : defaults.soundType,
    volume: Number.isFinite(rawVolume) ? Math.max(0, Math.min(100, Math.round(rawVolume))) : defaults.volume
  };
}

function getNovaNotificationPreferences(token) { // (로그인 사용자 개인 알림 설정 조회)
  const auth = verifyNovaToken(token);
  if (!auth.ok) throw new Error(auth.message || '로그인이 필요합니다.');
  const employeeNo = String(auth.user && auth.user.employeeNo || '').trim();
  if (!employeeNo) throw new Error('사용자 사번을 확인할 수 없습니다.');

  const raw = PropertiesService.getScriptProperties().getProperty(
    novaNotificationPreferenceKeyV2_(employeeNo)
  );
  if (!raw) return Object.assign({ ok: true }, defaultNovaNotificationPreferencesV2_());

  try {
    const parsed = JSON.parse(raw);
    return Object.assign({ ok: true }, normalizeNovaNotificationPreferencesV2_(parsed));
  } catch (error) {
    return Object.assign({ ok: true }, defaultNovaNotificationPreferencesV2_());
  }
}

function saveNovaNotificationPreferences(token, preferences) { // (로그인 사용자 개인 알림 설정 저장)
  const auth = verifyNovaToken(token);
  if (!auth.ok) throw new Error(auth.message || '로그인이 필요합니다.');
  const employeeNo = String(auth.user && auth.user.employeeNo || '').trim();
  if (!employeeNo) throw new Error('사용자 사번을 확인할 수 없습니다.');

  const normalized = normalizeNovaNotificationPreferencesV2_(preferences);
  const record = Object.assign({}, normalized, { updatedAt: new Date().toISOString() });
  PropertiesService.getScriptProperties().setProperty(
    novaNotificationPreferenceKeyV2_(employeeNo),
    JSON.stringify(record)
  );
  return Object.assign({ ok: true }, normalized);
}
