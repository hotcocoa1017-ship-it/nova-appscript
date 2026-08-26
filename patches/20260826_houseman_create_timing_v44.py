from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

marker = """      setSyncStatus(`${realtime.order.roomNo}호 오더 DB 저장 완료 · ${elapsed}ms`);\n      return;"""
replacement = """      setSyncStatus(`${realtime.order.roomNo}호 오더 DB 저장 완료 · ${elapsed}ms`);\n      const assignedDisplay = String(realtime.order.assignedName || realtime.order.assignedEmployeeNo || '').trim();\n      const registrationTimingMessage = realtime.order.autoAssigned\n        ? `${realtime.order.roomNo}호 · ${assignedDisplay || '하우스맨'}님 자동배정 완료 · Realtime ${elapsed}ms`\n        : realtime.order.assignedEmployeeNo\n          ? `${realtime.order.roomNo}호 · ${assignedDisplay || '하우스맨'}님 배정완료 · Realtime ${elapsed}ms`\n          : `${realtime.order.roomNo}호 · 오더 등록 완료 · Realtime ${elapsed}ms`;\n      showToast(registrationTimingMessage);\n      return;"""

if 'registrationTimingMessage' in text:
    print('Houseman create timing toast already applied')
elif marker not in text:
    raise SystemExit('Expected Realtime houseman create timing marker not found')
else:
    text = text.replace(marker, replacement, 1)
    path.write_text(text, encoding='utf-8')
    print('Applied visible Realtime timing toast to houseman order registration')
