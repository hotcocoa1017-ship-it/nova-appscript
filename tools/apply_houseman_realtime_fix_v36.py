from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"SKIP {label}: already applied")
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"PATCH FAIL {label}: expected 1 match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"PATCH OK {label}")


client = Path("Client.html")
houseman = Path("07_Houseman.js")

# 1) Houseman START/COMPLETE must remain houseman actions.
# Previously the shared helper translated every START/COMPLETE into room-cleaning
# actions, so HOUSEMAN mobile requests were sent to /v1/rooms/<empty>/action and
# could return 404 instead of calling updateHousemanOrder.
old_mapping = """  async function saveRoomActionRealtimeOrLegacy_(legacyMethod, payload) {
    const safe = Object.assign({}, payload || {});
    const rawAction = String(safe.action || '').trim().toUpperCase();
    const mappedAction = rawAction === 'START' ? 'CLEANING_START'
      : rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'
      : rawAction;
    const legacySafe = Object.assign({}, safe);
"""
new_mapping = """  async function saveRoomActionRealtimeOrLegacy_(legacyMethod, payload) {
    const safe = Object.assign({}, payload || {});
    const rawAction = String(safe.action || '').trim().toUpperCase();
    // START/COMPLETE 이름은 객실정비와 하우스맨 오더가 함께 사용합니다.
    // 객실작업 메서드일 때만 Realtime 청소 액션으로 변환하고,
    // updateHousemanOrder는 기존 START/COMPLETE 액션을 그대로 보존합니다.
    const isRoomOperationMethod = legacyMethod === 'updateRoomOperation'
      || legacyMethod === 'updateMobileRoomOperation';
    const mappedAction = isRoomOperationMethod && rawAction === 'START' ? 'CLEANING_START'
      : isRoomOperationMethod && rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'
      : rawAction;
    const legacySafe = Object.assign({}, safe);
"""
replace_once(client, old_mapping, new_mapping, "Client houseman action isolation")

# 2) ASSIGN must not wait for Telegram network I/O while the Apps Script write lock
# is held. Prepare queue/reminder rows only; Client dispatches the queue in a
# separate non-blocking server call, same pattern already used by CREATE.
old_assign_telegram = """      if (action === 'ASSIGN') {
        queueHousemanOrderTelegram_(
          order,
          action
        );
      }

      return {
        ok: true,
        version,
        order
      };
"""
new_assign_telegram = """      let telegramDispatch = {
        queued: false,
        queueRecordId: '',
        queueRowNumber: 0,
        reminderScheduled: false,
        reminderRecordId: ''
      };

      if (action === 'ASSIGN') {
        // Telegram 네트워크 발송은 사용자 저장 응답과 분리합니다.
        // 여기서는 CREATE와 동일하게 큐/재알림 행만 빠르게 준비하고,
        // 실제 즉시발송은 Client의 별도 비동기 호출에서 처리합니다.
        const firstRowNumber = sheet.getLastRow() + 1;
        const telegramPrepared = prepareHousemanOrderFastTelegramRows_(
          sheet,
          order,
          action,
          { firstRowNumber }
        );
        const telegramRows = telegramPrepared.rows || [];
        if (telegramRows.length) {
          ensureSheetRowCapacity_(
            sheet,
            firstRowNumber + telegramRows.length - 1
          );
          sheet
            .getRange(
              firstRowNumber,
              1,
              telegramRows.length,
              telegramRows[0].length
            )
            .setValues(telegramRows);
        }
        telegramDispatch = {
          queued: Boolean(telegramPrepared.queueRecordId),
          queueRecordId: telegramPrepared.queueRecordId || '',
          queueRowNumber: Number(telegramPrepared.queueRowNumber || 0),
          reminderScheduled: Boolean(telegramPrepared.reminderRecordId),
          reminderRecordId: telegramPrepared.reminderRecordId || ''
        };
      }

      return {
        ok: true,
        version,
        order,
        telegram: telegramDispatch
      };
"""
replace_once(houseman, old_assign_telegram, new_assign_telegram, "Houseman ASSIGN nonblocking Telegram queue")

# 3) After the fast ASSIGN response, dispatch Telegram in the background.
# This keeps the existing immediate Telegram behavior without making the manager
# wait for UrlFetchApp/Telegram while assigning the order.
old_manager_result = """      const result = await callServer('updateHousemanOrder', state.token, payload);
      if (!result?.ok) throw new Error(result?.message || '오더를 변경하지 못했습니다.');
      upsertOrderLocal_(result.order, result.version);
      closeModal();
      showToast(`${result.order.roomNo}호 오더: ${result.order.statusLabel}`);
"""
new_manager_result = """      const result = await callServer('updateHousemanOrder', state.token, payload);
      if (!result?.ok) throw new Error(result?.message || '오더를 변경하지 못했습니다.');
      upsertOrderLocal_(result.order, result.version);
      const telegram = result.telegram || {};
      if (action === 'ASSIGN' && telegram.queued && telegram.queueRecordId) {
        void callServer('dispatchHousemanOrderTelegramFast', state.token, {
          recordId: telegram.queueRecordId,
          rowNumber: telegram.queueRowNumber || 0
        }).catch(error => {
          console.warn('하우스맨 배정 텔레그램 즉시발송은 큐 재시도로 전환됩니다.', error?.message || error);
        });
      }
      closeModal();
      showToast(`${result.order.roomNo}호 오더: ${result.order.statusLabel}`);
"""
replace_once(client, old_manager_result, new_manager_result, "Client ASSIGN background Telegram dispatch")

# Guard rails: fail the deployment if any required invariant is missing.
client_text = client.read_text(encoding="utf-8")
houseman_text = houseman.read_text(encoding="utf-8")
required_client = [
    "const isRoomOperationMethod = legacyMethod === 'updateRoomOperation'",
    "action === 'ASSIGN' && telegram.queued && telegram.queueRecordId",
    "dispatchHousemanOrderTelegramFast"
]
required_houseman = [
    "let telegramDispatch = {",
    "prepareHousemanOrderFastTelegramRows_(",
    "telegram: telegramDispatch"
]
for marker in required_client:
    if marker not in client_text:
        raise SystemExit(f"VERIFY FAIL Client marker missing: {marker}")
for marker in required_houseman:
    if marker not in houseman_text:
        raise SystemExit(f"VERIFY FAIL Houseman marker missing: {marker}")

print("VERIFY PASS houseman realtime action isolation + nonblocking assignment Telegram")
