from pathlib import Path

PATH = Path('Client.html')
MARKER = 'TELEGRAM_SELF_CONNECT_V1'
START = '  async function openMyTelegramConnection_() {'
END = '\n\n\n\n  function renderDepartureDelayShell_'

text = PATH.read_text(encoding='utf-8')
if MARKER in text:
    print('Telegram self-connect patch already applied.')
    raise SystemExit(0)

start = text.find(START)
if start < 0:
    raise SystemExit('openMyTelegramConnection_ start not found')
end = text.find(END, start)
if end < 0:
    raise SystemExit('openMyTelegramConnection_ end marker not found')

replacement = r'''  async function openMyTelegramConnection_() { // (홈 본인 텔레그램 자동연결 · TELEGRAM_SELF_CONNECT_V1)
    const button = $('homeTelegramConnectButton');
    if (!button || button.disabled) return;
    const popup = window.open('', '_blank');
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = '연결 준비 중…';

    try {
      const prepared = await callServer('prepareMyTelegramConnection', state.token);
      if (!prepared?.ok) {
        if (popup && !popup.closed) popup.close();
        throw new Error(prepared?.message || '텔레그램 연결을 준비하지 못했습니다.');
      }

      if (prepared.linked || prepared.alreadyLinked) {
        if (popup && !popup.closed) popup.close();
        state.bootstrap.user.telegramLinked = true;
        state.bootstrap.user.telegramConnectionStatus = '연결완료';
        if (state.activeMenu === 'home') renderContent('home');
        showToast(prepared.message || '텔레그램 연결이 완료되어 있습니다.');
        return;
      }

      if (!prepared.connectionLink) {
        if (popup && !popup.closed) popup.close();
        throw new Error('텔레그램 연결링크를 확인하지 못했습니다.');
      }

      if (popup && !popup.closed) {
        popup.location.replace(prepared.connectionLink);
      } else {
        // 팝업이 차단된 환경은 현재 탭에서 Telegram을 열며, 복귀 후 홈에서 상태를 다시 확인할 수 있습니다.
        window.location.href = prepared.connectionLink;
        return;
      }

      button.textContent = 'Telegram에서 START 후 자동확인 중…';
      const deadline = Date.now() + 90000;
      let linked = false;
      let lastStatus = null;

      while (Date.now() < deadline) {
        await novaRealtimeSleep_(3000);
        try {
          lastStatus = await callServer('getMyTelegramConnectionStatus', state.token);
        } catch (statusError) {
          console.warn('텔레그램 연결상태 자동확인 재시도', statusError?.message || statusError);
          continue;
        }

        if (lastStatus?.code === 'UNAUTHORIZED') {
          throw new Error(lastStatus?.message || '로그인 시간이 만료되었습니다. 다시 로그인해 주세요.');
        }
        if (lastStatus?.ok && lastStatus.linked) {
          linked = true;
          break;
        }
      }

      if (linked) {
        state.bootstrap.user.telegramLinked = true;
        state.bootstrap.user.telegramConnectionStatus = '연결완료';
        state.bootstrap.user.telegramEnabled = lastStatus?.telegramEnabled !== false;
        if (state.activeMenu === 'home') renderContent('home');
        showToast('텔레그램 연결이 완료되었습니다.');
      } else {
        showToast('자동 확인 시간이 끝났습니다. Telegram에서 START를 누른 뒤 홈에서 다시 확인해 주세요.');
      }
    } catch (error) {
      if (popup && !popup.closed) popup.close();
      showToast(error?.message || '텔레그램 연결 중 오류가 발생했습니다.');
    } finally {
      const currentButton = $('homeTelegramConnectButton');
      if (currentButton) {
        currentButton.disabled = false;
        currentButton.textContent = originalText;
      }
    }
  }'''

patched = text[:start] + replacement + text[end:]
PATH.write_text(patched, encoding='utf-8')
print('Applied Telegram self-connect patch.')
