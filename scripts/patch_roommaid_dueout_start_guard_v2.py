from pathlib import Path

MARKER = 'ROOMMAID_DUE_OUT_START_GUARD_V2'


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if new in text:
        return False
    if old not in text:
        raise SystemExit(f'{path}: patch anchor not found')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')
    return True


# Client: render DUE_OUT by status code, keep button visible but disabled, and block action before optimistic/Realtime path.
replace_once(
    'Client.html',
    "    const mobileCleaningActive = role === 'ROOMMAID' && isCleaningActiveStatus_(room.cleaningStatus, state.mobile.data?.codes?.cleaningStatuses);\n    if (role === 'ROOMMAID') {",
    "    const mobileCleaningActive = role === 'ROOMMAID' && isCleaningActiveStatus_(room.cleaningStatus, state.mobile.data?.codes?.cleaningStatuses);\n    const mobileRoomDueOut = role === 'ROOMMAID' && String(room.roomStatus || '').trim().toUpperCase() === 'DUE_OUT'; // ROOMMAID_DUE_OUT_START_GUARD_V2\n    if (role === 'ROOMMAID') {"
)

replace_once(
    'Client.html',
    "        if (['ASSIGNED', 'WAITING', 'REWORK'].includes(room.cleaningStatus)) actions += `<button class=\"primary\" data-room-action=\"START\" data-room-no=\"${escapeAttr(room.roomNo)}\">${room.cleaningType === 'DS' ? 'D/S 시작' : '청소 시작'}</button>`;",
    "        if (['ASSIGNED', 'WAITING', 'REWORK'].includes(room.cleaningStatus)) actions += `<button class=\"primary\" data-room-action=\"START\" data-room-no=\"${escapeAttr(room.roomNo)}\"${mobileRoomDueOut ? ' disabled data-due-out-start-guard=\"Y\" aria-disabled=\"true\" title=\"퇴실 확인 후 청소를 시작할 수 있습니다.\"' : ''}>${room.cleaningType === 'DS' ? 'D/S 시작' : '청소 시작'}</button>`; // ROOMMAID_DUE_OUT_START_GUARD_V2"
)

replace_once(
    'Client.html',
    "    return `<article class=\"mobile-room-card${roommaidMobileCardClass_(room, role)}${mobileCleaningActive ? ' mobile-card-cleaning' : ''}\">",
    "    return `<article class=\"mobile-room-card${roommaidMobileCardClass_(room, role)}${mobileCleaningActive ? ' mobile-card-cleaning' : ''}\" data-room-status=\"${escapeAttr(String(room.roomStatus || '').trim().toUpperCase())}\">` // ROOMMAID_DUE_OUT_START_GUARD_V2"
)

replace_once(
    'Client.html',
    "      const mobileRoomAction = String(safePayload.action || '').trim().toUpperCase();\n      const roommaidCleaningAction = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase() === 'ROOMMAID'\n        && ['START', 'COMPLETE'].includes(mobileRoomAction);",
    "      const mobileRoomAction = String(safePayload.action || '').trim().toUpperCase();\n      const mobileRoomRole = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();\n      if (mobileRoomRole === 'ROOMMAID' && mobileRoomAction === 'START'\n          && String(room?.roomStatus || '').trim().toUpperCase() === 'DUE_OUT') { // ROOMMAID_DUE_OUT_START_GUARD_V2\n        if (button) {\n          button.disabled = true;\n          button.dataset.dueOutStartGuard = 'Y';\n          button.setAttribute('aria-disabled', 'true');\n          button.setAttribute('title', '퇴실 확인 후 청소를 시작할 수 있습니다.');\n        }\n        showToast('퇴실예정 객실은 퇴실 전환 후 청소를 시작할 수 있습니다.');\n        return;\n      }\n      const roommaidCleaningAction = mobileRoomRole === 'ROOMMAID'\n        && ['START', 'COMPLETE'].includes(mobileRoomAction);"
)

# Server: block DUE_OUT on both Realtime proxy and legacy Sheet path using authoritative roomStatus already read in each path.
replace_once(
    '10_Mobile.js',
    "  let qmEmployeeNo = '';\n  try {\n    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);\n    const rowInfo = findCurrentRoomRowForMobileUpdate_(sheet, businessDate, site, roomNo, safe.rowNumber);\n    qmEmployeeNo = String(rowInfo && rowInfo.data && rowInfo.data['QM사번'] || '').trim();\n  } catch (error) {}\n\n  const requestId = String(safe.requestId || '').trim() || `NOVA-GAS-${Date.now()}-${Utilities.getUuid()}`;",
    "  let qmEmployeeNo = '';\n  let currentRoomStatus = '';\n  try {\n    const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);\n    const rowInfo = findCurrentRoomRowForMobileUpdate_(sheet, businessDate, site, roomNo, safe.rowNumber);\n    qmEmployeeNo = String(rowInfo && rowInfo.data && rowInfo.data['QM사번'] || '').trim();\n    currentRoomStatus = String(rowInfo && rowInfo.data && rowInfo.data['객실상태'] || '').trim().toUpperCase();\n  } catch (error) {}\n  if (action === 'CLEANING_START' && currentRoomStatus === 'DUE_OUT') { // ROOMMAID_DUE_OUT_START_GUARD_V2\n    throw new Error('퇴실예정 객실은 퇴실 전환 후 청소를 시작할 수 있습니다.');\n  }\n\n  const requestId = String(safe.requestId || '').trim() || `NOVA-GAS-${Date.now()}-${Utilities.getUuid()}`;"
)

replace_once(
    '10_Mobile.js',
    "    if (role === 'ROOMMAID' && ![roommaidNo, secondaryRoommaidNo].includes(user.employeeNo)) throw new Error('본인에게 배정된 객실만 처리할 수 있습니다.');\n    if (role === 'QM' && qmNo !== user.employeeNo) throw new Error('본인에게 배정된 객실만 처리할 수 있습니다.');",
    "    if (role === 'ROOMMAID' && ![roommaidNo, secondaryRoommaidNo].includes(user.employeeNo)) throw new Error('본인에게 배정된 객실만 처리할 수 있습니다.');\n    const currentRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();\n    if (role === 'ROOMMAID' && action === 'START' && currentRoomStatus === 'DUE_OUT') { // ROOMMAID_DUE_OUT_START_GUARD_V2\n      throw new Error('퇴실예정 객실은 퇴실 전환 후 청소를 시작할 수 있습니다.');\n    }\n    if (role === 'QM' && qmNo !== user.employeeNo) throw new Error('본인에게 배정된 객실만 처리할 수 있습니다.');"
)

# DOM guard: use immutable room-status code carried on the card, not translated display text.
replace_once(
    'RoommaidDueOutGuard.html',
    "  // ROOMMAID_DUE_OUT_START_GUARD_V1\n  // 퇴실예정(DUE_OUT) 객실은 룸메이드 청소시작 버튼을 노출/실행하지 않습니다.\n  // 객실상태가 퇴실(CHECKED_OUT)로 갱신되면 기존 렌더링 규칙에 따라 다시 활성화됩니다.\n  function roommaidDueOutGuardStatus_(card) {\n    const status = String(card?.querySelector('.mobile-room-status b')?.textContent || '').trim().toUpperCase();\n    return status === '퇴실예정' || status === 'DUE_OUT';\n  }",
    "  // ROOMMAID_DUE_OUT_START_GUARD_V2\n  // 표시언어와 무관하게 객실상태 코드 DUE_OUT만 청소시작을 비활성화합니다.\n  // STOCK/STOCK_RC/STOCK_HU/CHECKED_OUT 및 기존 허용상태는 그대로 유지합니다.\n  function roommaidDueOutGuardStatus_(card) {\n    const status = String(card?.dataset?.roomStatus || '').trim().toUpperCase();\n    return status === 'DUE_OUT';\n  }"
)

replace_once(
    'RoommaidDueOutGuard.html',
    "        startButton.hidden = true;\n        startButton.disabled = true;\n        startButton.dataset.dueOutStartGuard = 'Y';\n        startButton.setAttribute('aria-hidden', 'true');\n        startButton.setAttribute('title', '퇴실 확인 후 청소를 시작할 수 있습니다.');",
    "        startButton.hidden = false;\n        startButton.disabled = true;\n        startButton.dataset.dueOutStartGuard = 'Y';\n        startButton.setAttribute('aria-disabled', 'true');\n        startButton.setAttribute('title', '퇴실 확인 후 청소를 시작할 수 있습니다.');"
)

replace_once(
    'RoommaidDueOutGuard.html',
    "        delete startButton.dataset.dueOutStartGuard;\n        startButton.removeAttribute('aria-hidden');\n        startButton.removeAttribute('title');",
    "        delete startButton.dataset.dueOutStartGuard;\n        startButton.removeAttribute('aria-disabled');\n        startButton.removeAttribute('title');"
)

replace_once(
    'RoommaidDueOutGuard.html',
    "    button.hidden = true;\n    button.disabled = true;\n    button.dataset.dueOutStartGuard = 'Y';",
    "    button.hidden = false;\n    button.disabled = true;\n    button.dataset.dueOutStartGuard = 'Y';\n    button.setAttribute('aria-disabled', 'true');"
)

print(f'{MARKER} applied')
