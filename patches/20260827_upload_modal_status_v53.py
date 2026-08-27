from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

old = '''        <p class=\"upload-message\">${escapeHtml(result.message || '')}</p>\n        ${result.canApply ? `<div class=\"modal-actions\">'''
new = '''        <p class=\"upload-message\">${escapeHtml(result.message || '')}</p>\n        <div id=\"uploadPerformanceStatus\" class=\"upload-processing\"></div>\n        ${result.canApply ? `<div class=\"modal-actions\">'''
if old not in text:
    raise SystemExit('preview status anchor not found')
text = text.replace(old, new, 1)

old = '''        const totalMs = Math.round(performance.now() - previewStartedAt);\n        const serverMs = Number(result.performance?.elapsedMs || 0);\n        setSyncStatus(`객실현황 검증 완료 · 총 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`);'''
new = '''        const totalMs = Math.round(performance.now() - previewStartedAt);\n        const serverMs = Number(result.performance?.elapsedMs || 0);\n        const previewStatusText = `객실현황 검증 완료 · 총 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`;\n        if ($('uploadPerformanceStatus')) $('uploadPerformanceStatus').textContent = previewStatusText;\n        setSyncStatus(previewStatusText);'''
if old not in text:
    raise SystemExit('preview timing anchor not found')
text = text.replace(old, new, 1)

old = '''    if (otherButton) otherButton.disabled = true;\n    try {\n      const result = await callServer('applyRoomStatusUpload', state.token, previewId, {'''
new = '''    if (otherButton) otherButton.disabled = true;\n    if ($('uploadPerformanceStatus')) {\n      $('uploadPerformanceStatus').textContent = resetMode\n        ? '객실현황 초기화 후 반영 중…'\n        : '객실현황 반영 중…';\n    }\n    try {\n      const result = await callServer('applyRoomStatusUpload', state.token, previewId, {'''
if old not in text:
    raise SystemExit('apply progress anchor not found')
text = text.replace(old, new, 1)

old = '''      showToast(result.message || '객실현황을 반영했습니다.');\n      const totalMs = Math.round(performance.now() - clickedAt);\n      const serverMs = Number(result.performance?.elapsedMs || result.timing?.totalMs || 0);\n      const writeMs = Number(result.timing?.currentWriteMs || 0);\n      const lockMs = Number(result.timing?.lockWaitMs || 0);\n      const flushMs = Number(result.timing?.flushMs || 0);\n      setSyncStatus(\n        `객실현황 반영 완료 · 총 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`\n        + `${writeMs ? ` · 저장 ${writeMs}ms` : ''}${lockMs ? ` · 잠금 ${lockMs}ms` : ''}${flushMs ? ` · flush ${flushMs}ms` : ''}`\n      );'''
new = '''      const totalMs = Math.round(performance.now() - clickedAt);\n      const serverMs = Number(result.performance?.elapsedMs || result.timing?.totalMs || 0);\n      const writeMs = Number(result.timing?.currentWriteMs || 0);\n      const lockMs = Number(result.timing?.lockWaitMs || 0);\n      const flushMs = Number(result.timing?.flushMs || 0);\n      const applyStatusText =\n        `객실현황 반영 완료 · 총 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`\n        + `${writeMs ? ` · 저장 ${writeMs}ms` : ''}${lockMs ? ` · 잠금 ${lockMs}ms` : ''}${flushMs ? ` · flush ${flushMs}ms` : ''}`;\n      showToast(applyStatusText);\n      setSyncStatus(applyStatusText);'''
if old not in text:
    raise SystemExit('apply completion anchor not found')
text = text.replace(old, new, 1)

old = '''      if (otherButton) otherButton.disabled = false;\n      showToast(error?.message || '객실현황 반영 오류');'''
new = '''      if (otherButton) otherButton.disabled = false;\n      if ($('uploadPerformanceStatus')) {\n        $('uploadPerformanceStatus').textContent = `객실현황 반영 오류 · ${error?.message || '서버 처리 오류'}`;\n      }\n      showToast(error?.message || '객실현황 반영 오류');'''
if old not in text:
    raise SystemExit('apply failure anchor not found')
text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
print('Room upload modal progress/status patch applied')
