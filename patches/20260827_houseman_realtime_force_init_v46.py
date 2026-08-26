from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

if 'realtimeFallbackReason' in text and 'legacyTimingDetails' in text:
    print('Houseman realtime-preference diagnostics already applied')
    raise SystemExit(0)

start_marker = """    setOrderFormBusy(true);\n    const clickedAt = performance.now();\n    try {\n      if (novaRealtimeIsEnabled_()) {"""
start_replacement = """    setOrderFormBusy(true);\n    const clickedAt = performance.now();\n    try {\n      let realtimeFallbackReason = '';\n      // 로그인 직후 Realtime 설정 비동기 초기화가 끝나기 전에 등록을 누르더라도\n      // 느린 Apps Script 경로로 바로 추락하지 않고 설정 확인을 먼저 완료합니다.\n      if (!novaRealtime_.configLoaded) {\n        const realtimeReady = await initNovaRealtime_();\n        if (!realtimeReady && !novaRealtime_.configLoaded) realtimeFallbackReason = 'REALTIME_CONFIG_UNAVAILABLE';\n      }\n      if (novaRealtimeIsEnabled_()) {"""

catch_marker = """        } catch (realtimeError) {\n          console.warn('[NOVA Realtime] 하우스맨 등록은 기존 저장경로로 자동 전환합니다.', realtimeError);\n        }\n      }\n\n      // Realtime 비활성/오류 시 기존 동작을 그대로 유지합니다."""
catch_replacement = """        } catch (realtimeError) {\n          realtimeFallbackReason = String(realtimeError?.code || realtimeError?.message || 'REALTIME_ERROR')\n            .replace(/\\s+/g, ' ').trim().slice(0, 80);\n          console.warn('[NOVA Realtime] 하우스맨 등록은 기존 저장경로로 자동 전환합니다.', realtimeError);\n        }\n      } else if (!realtimeFallbackReason) {\n        realtimeFallbackReason = novaRealtime_.configLoaded ? 'REALTIME_DISABLED' : 'REALTIME_CONFIG_UNAVAILABLE';\n      }\n\n      // Realtime 비활성/오류 시 기존 동작을 그대로 유지합니다."""

legacy_marker = """      const legacyElapsed = Math.round(performance.now() - clickedAt);\n      const legacyServerMs = Math.max(0, Number(result.timing?.totalMs || result.performance?.elapsedMs || 0));\n      const legacyPathLabel = `Apps Script ${legacyElapsed}ms${legacyServerMs > 0 ? ` · 서버 ${legacyServerMs}ms` : ''}`;\n      showToast(result.order.assignedName\n        ? `${result.order.roomNo}호 · ${result.order.assignedName}님 자동배정 완료 · ${legacyPathLabel}`\n        : `${result.order.roomNo}호 미배정 오더 등록 완료 · ${legacyPathLabel}`);\n      setSyncStatus(`${result.order.roomNo}호 오더 저장 완료 · ${legacyPathLabel}`);"""
legacy_replacement = """      const legacyElapsed = Math.round(performance.now() - clickedAt);\n      const legacyServerMs = Math.max(0, Number(result.timing?.totalMs || result.performance?.elapsedMs || 0));\n      const legacyPathLabel = `Apps Script ${legacyElapsed}ms${legacyServerMs > 0 ? ` · 서버 ${legacyServerMs}ms` : ''}`;\n      const legacyTiming = result.timing || {};\n      const legacyTimingDetails = [\n        `잠금 ${Math.max(0, Number(legacyTiming.lockWaitMs || 0))}ms`,\n        `자동배정 ${Math.max(0, Number(legacyTiming.autoAssignMs || 0))}ms`,\n        `쓰기 ${Math.max(0, Number(legacyTiming.writeMs || 0))}ms`,\n        `flush ${Math.max(0, Number(legacyTiming.flushMs || 0))}ms`\n      ].join(' · ');\n      const legacyDiagnosticLabel = `${legacyPathLabel} · 우회 ${realtimeFallbackReason || 'UNKNOWN'} · ${legacyTimingDetails}`;\n      showToast(result.order.assignedName\n        ? `${result.order.roomNo}호 · ${result.order.assignedName}님 자동배정 완료 · ${legacyDiagnosticLabel}`\n        : `${result.order.roomNo}호 미배정 오더 등록 완료 · ${legacyDiagnosticLabel}`);\n      setSyncStatus(`${result.order.roomNo}호 오더 저장 완료 · ${legacyDiagnosticLabel}`);"""

for label, marker in [
    ('registration start', start_marker),
    ('realtime fallback catch', catch_marker),
    ('legacy timing', legacy_marker),
]:
    if marker not in text:
        raise SystemExit(f'Expected {label} marker not found')

text = text.replace(start_marker, start_replacement, 1)
text = text.replace(catch_marker, catch_replacement, 1)
text = text.replace(legacy_marker, legacy_replacement, 1)
path.write_text(text, encoding='utf-8')
print('Applied Realtime-first init and fallback/subtiming diagnostics to houseman registration')
