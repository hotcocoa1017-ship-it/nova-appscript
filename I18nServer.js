/**
 * NOVA 다국어 서버 보조계층 // NOVA_I18N_V1
 * - UI 언어는 클라이언트에서만 처리합니다.
 * - 하우스맨 오더의 자유입력(품목/추가내용)만 한국어 운영값으로 번역합니다.
 * - 기존 상태코드·권한·시트 헤더·Realtime 구조는 변경하지 않습니다.
 */
const NOVA_I18N_SUPPORTED_LANGUAGES = Object.freeze(['ko', 'en', 'th', 'mn']);

function normalizeNovaUiLanguage_(value) { // NOVA_I18N_V1
  const normalized = String(value || 'ko').trim().toLowerCase();
  return NOVA_I18N_SUPPORTED_LANGUAGES.includes(normalized) ? normalized : 'ko';
}

function translateNovaTextToKorean_(text, sourceLanguage) { // NOVA_I18N_V1
  const source = normalizeNovaUiLanguage_(sourceLanguage);
  const value = String(text || '').trim();
  if (!value || source === 'ko') return value;
  const translated = String(LanguageApp.translate(value, source, 'ko') || '').trim();
  if (!translated) throw new Error('한국어 번역 결과가 비어 있습니다. 다시 등록해 주세요.');
  return translated;
}

function prepareNovaHousemanOrderPayloadForStorage_(payload) { // NOVA_I18N_V1
  const safe = Object.assign({}, payload || {});
  const sourceLanguage = normalizeNovaUiLanguage_(safe.sourceLanguage);
  safe.sourceLanguage = sourceLanguage;

  if (sourceLanguage === 'ko') {
    safe.translation = null;
    return safe;
  }

  const existingTranslation = safe.translation && typeof safe.translation === 'object'
    ? safe.translation
    : null;
  if (existingTranslation
      && String(existingTranslation.sourceLanguage || '').trim().toLowerCase() === sourceLanguage
      && String(existingTranslation.translatedTo || '').trim().toLowerCase() === 'ko'
      && String(existingTranslation.status || '').trim().toUpperCase() === 'SUCCESS') {
    return safe;
  }

  const originalItems = (Array.isArray(safe.items) ? safe.items : []).map(item => ({
    name: String(item && item.name || '').trim(),
    quantity: Math.max(1, Math.min(99, Number(item && item.quantity || 1)))
  })).filter(item => item.name);
  const originalNote = String(safe.note || '').trim();

  try {
    const translatedItems = originalItems.map(item => ({
      name: translateNovaTextToKorean_(item.name, sourceLanguage),
      quantity: item.quantity
    }));
    const translatedNote = originalNote
      ? translateNovaTextToKorean_(originalNote, sourceLanguage)
      : '';

    safe.items = translatedItems;
    safe.note = translatedNote;
    safe.translation = {
      sourceLanguage,
      translatedTo: 'ko',
      status: 'SUCCESS',
      originalItems,
      originalNote,
      translatedItemsKo: translatedItems,
      translatedNoteKo: translatedNote,
      translatedAt: typeof nowText_ === 'function' ? nowText_() : new Date().toISOString()
    };
    return safe;
  } catch (error) {
    const translatedError = new Error(`한국어 자동번역에 실패했습니다. 잠시 후 다시 등록해 주세요. (${error && error.message ? error.message : error})`);
    translatedError.code = 'ORDER_TRANSLATION_FAILED';
    throw translatedError;
  }
}

function translateNovaHousemanOrderPayload(token, payload) { // NOVA_I18N_V1 · Realtime 저장 직전 번역
  return measureResponse_('translateNovaHousemanOrderPayload', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const role = String(auth.user.role || '').trim().toUpperCase();
    if (!['ADMIN', 'ORDER', 'ROOMMAID', 'QM', 'PUBLIC'].includes(role)) {
      throw new Error('오더 번역 권한이 없습니다.');
    }
    return {
      ok: true,
      payload: prepareNovaHousemanOrderPayloadForStorage_(payload)
    };
  });
}
