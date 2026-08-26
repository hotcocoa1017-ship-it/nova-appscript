from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

if 'registrationTimingMessage' in text:
    print('Houseman create timing toast already applied')
else:
    clicked = text.find('const clickedAt = performance.now();')
    if clicked < 0:
        raise SystemExit('Houseman create clickedAt marker not found')

    elapsed_marker = 'const elapsed = Math.round(performance.now() - clickedAt);'
    elapsed = text.find(elapsed_marker, clicked)
    if elapsed < 0:
        raise SystemExit('Houseman create elapsed marker not found')

    return_pos = text.find('return;', elapsed)
    if return_pos < 0 or return_pos - elapsed > 1400:
        raise SystemExit('Houseman create success return marker not found nearby')

    block = text[elapsed:return_pos]
    if 'realtime.order' not in block or 'showToast' not in block:
        raise SystemExit('Houseman create success block shape changed; refusing unsafe patch')

    insertion = """const assignedDisplay = String(realtime.order.assignedName || realtime.order.assignedEmployeeNo || '').trim();
      const registrationTimingMessage = realtime.order.autoAssigned
        ? `${realtime.order.roomNo}호 · ${assignedDisplay || '하우스맨'}님 자동배정 완료 · Realtime ${elapsed}ms`
        : realtime.order.assignedEmployeeNo
          ? `${realtime.order.roomNo}호 · ${assignedDisplay || '하우스맨'}님 배정완료 · Realtime ${elapsed}ms`
          : `${realtime.order.roomNo}호 · 오더 등록 완료 · Realtime ${elapsed}ms`;
      showToast(registrationTimingMessage);
      """

    text = text[:return_pos] + insertion + text[return_pos:]
    path.write_text(text, encoding='utf-8')
    print('Applied visible Realtime timing toast to houseman order registration')
