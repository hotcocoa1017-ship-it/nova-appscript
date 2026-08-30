from pathlib import Path
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

marker = 'SYNC_STATUS_AUTO_HIDE_V1'
old = """  function setSyncStatus(text) { // (우측 하단 연결상태 표시)\n    if ($('syncStatus')) $('syncStatus').textContent = text;\n  }\n"""
new = """  function setSyncStatus(text) { // (우측 하단 연결상태 표시 · SYNC_STATUS_AUTO_HIDE_V1)\n    const status = $('syncStatus');\n    if (!status) return;\n\n    const message = String(text || '').trim();\n    if (status.__novaHideTimer) {\n      window.clearTimeout(status.__novaHideTimer);\n      status.__novaHideTimer = null;\n    }\n\n    status.textContent = message;\n    status.classList.toggle('hidden', !message);\n    if (!message) return;\n\n    // 정상 안내는 잠깐만 보여주고, 사용자가 조치해야 할 오류·재시도 상태는 계속 표시합니다.\n    const persistent = /오류|실패|재시도|재확인|확인 필요|복원|중단|비활성|처리불가|타임아웃|연결 끊김/.test(message);\n    if (persistent) return;\n\n    const expectedMessage = message;\n    status.__novaHideTimer = window.setTimeout(() => {\n      status.__novaHideTimer = null;\n      if (status.textContent !== expectedMessage) return;\n      status.classList.add('hidden');\n      status.textContent = '';\n    }, 3000);\n  }\n"""

if marker in text:
    print('Sync status auto-hide patch already applied.')
    sys.exit(0)

if old not in text:
    print('ERROR: Could not locate setSyncStatus block.', file=sys.stderr)
    sys.exit(2)

path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('Applied sync status auto-hide patch to Client.html.')
