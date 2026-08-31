/**
 * NOVA 개인 홈 텔레그램 자동연결 보조 API.
 * 기존 관리자 연결관리/Webhook은 유지하고, 본인 계정에 한해 연결링크를 안전하게 준비하고
 * Telegram START 처리 후 연결완료 상태를 조회합니다.
 * TELEGRAM_SELF_CONNECT_V1
 */
function prepareMyTelegramConnection(token) { // (본인 연결링크 자동준비·기존키 재사용)
  const auth = verifyNovaToken(token);
  if (!auth.ok || !auth.user) {
    return { ok: false, code: 'UNAUTHORIZED', linked: false, connectionLink: '', message: auth.message || '다시 로그인해 주세요.' };
  }

  const employeeNo = String(auth.user.employeeNo || '').trim();
  if (!employeeNo) return { ok: false, linked: false, connectionLink: '', message: '본인 사번을 확인하지 못했습니다.' };

  const props = PropertiesService.getScriptProperties();
  const botToken = String(props.getProperty('TELEGRAM_BOT_TOKEN') || '').trim();
  const webhookUrl = String(props.getProperty('TELEGRAM_WEBHOOK_URL') || '').trim();
  if (!botToken || !webhookUrl) {
    return {
      ok: false,
      linked: false,
      connectionLink: '',
      code: 'TELEGRAM_SETUP_REQUIRED',
      message: '텔레그램 초기 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요.'
    };
  }

  let username = String(props.getProperty('TELEGRAM_BOT_USERNAME') || '').trim();
  if (!username) {
    try { username = String(getTelegramBotUsername_() || '').trim(); } catch (error) { username = ''; }
  }
  if (!username) {
    return {
      ok: false,
      linked: false,
      connectionLink: '',
      code: 'TELEGRAM_BOT_UNAVAILABLE',
      message: '텔레그램 봇 정보를 확인하지 못했습니다. 관리자에게 문의해 주세요.'
    };
  }

  const lock = acquireWriteLock_(5000);
  try {
    // 다른 실행(Webhook 포함)이 연결상태를 바꿨을 수 있으므로 잠금 획득 뒤 최신값을 다시 읽습니다.
    clearNovaCaches_();
    const user = getUserIndex_().byEmployeeNo[employeeNo];
    if (!user || !user.enabled) {
      return { ok: false, linked: false, connectionLink: '', message: '사용 중인 본인 사용자계정을 찾지 못했습니다.' };
    }
    if (user.telegramId) {
      return {
        ok: true,
        linked: true,
        alreadyLinked: true,
        connectionLink: '',
        connectionStatus: '연결완료',
        message: '이미 텔레그램 연결이 완료된 계정입니다.'
      };
    }

    let connectionKey = String(user.telegramConnectionKey || '').trim();
    if (!/^[A-Za-z0-9_-]{12}$/.test(connectionKey)) connectionKey = createTelegramConnectionKey_();
    const expectedLink = buildTelegramConnectionLink_(username, employeeNo, connectionKey);
    const currentLink = String(user.telegramConnectionLink || '').trim();
    const currentStatus = String(user.telegramConnectionStatus || '').trim();
    const needsUpdate = currentLink !== expectedLink
      || currentStatus !== '연결대기'
      || String(user.telegramConnectionKey || '').trim() !== connectionKey;

    if (needsUpdate) {
      const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
      updateRowByHeaders_(sheet, user.rowNumber, {
        '텔레그램연결키': connectionKey,
        '텔레그램연결링크': expectedLink,
        '텔레그램연결상태': '연결대기',
        '수정일시': nowText_()
      });
      SpreadsheetApp.flush();
      clearNovaCaches_();
    }

    return {
      ok: true,
      linked: false,
      alreadyLinked: false,
      connectionLink: expectedLink,
      connectionStatus: '연결대기',
      generated: needsUpdate,
      message: needsUpdate ? '텔레그램 개인 연결링크를 준비했습니다.' : '기존 텔레그램 개인 연결링크를 사용합니다.'
    };
  } finally {
    lock.releaseLock();
  }
}

function getMyTelegramConnectionStatus(token) { // (Telegram START 이후 본인 연결완료 상태 조회)
  const auth = verifyNovaToken(token);
  if (!auth.ok || !auth.user) {
    return { ok: false, code: 'UNAUTHORIZED', linked: false, connectionStatus: '', message: auth.message || '다시 로그인해 주세요.' };
  }

  // Webhook은 별도 Apps Script 실행이므로 매 확인 때 사용자 캐시를 비워 최신 Chat ID를 읽습니다.
  clearNovaCaches_();
  const employeeNo = String(auth.user.employeeNo || '').trim();
  const user = getUserIndex_().byEmployeeNo[employeeNo];
  if (!user || !user.enabled) {
    return { ok: false, linked: false, connectionStatus: '', message: '사용 중인 본인 사용자계정을 찾지 못했습니다.' };
  }

  const linked = Boolean(String(user.telegramId || '').trim());
  return {
    ok: true,
    linked,
    connectionStatus: linked ? '연결완료' : (user.telegramConnectionStatus || '연결대기'),
    telegramEnabled: Boolean(user.telegramEnabled),
    message: linked ? '텔레그램 연결이 완료되었습니다.' : '텔레그램에서 START를 눌러 연결을 완료해 주세요.'
  };
}
