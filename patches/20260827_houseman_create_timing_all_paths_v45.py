from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

if 'housemanCreatePathLabel' in text:
    print('Houseman registration timing for all paths already applied')
    raise SystemExit(0)

rt_start = text.find("          showToast(realtime.order.assignedName\n")
rt_end_marker = "      return;\n        } catch (realtimeError)"
rt_end = text.find(rt_end_marker, rt_start)
if rt_start < 0 or rt_end < 0:
    raise SystemExit('Realtime houseman registration success block not found')

rt_replacement = """          const assignedDisplay = String(realtime.order.assignedName || realtime.order.assignedEmployeeNo || '').trim();
          const realtimeServerMs = Math.max(0, Number(realtime.timing?.totalMs || 0));
          const housemanCreatePathLabel = `Realtime ${elapsed}ms${realtimeServerMs > 0 ? ` · 서버 ${realtimeServerMs}ms` : ''}`;
          const registrationTimingMessage = realtime.order.autoAssigned
            ? `${realtime.order.roomNo}호 · ${assignedDisplay || '하우스맨'}님 자동배정 완료 · ${housemanCreatePathLabel}`
            : realtime.order.assignedEmployeeNo
              ? `${realtime.order.roomNo}호 · ${assignedDisplay || '하우스맨'}님 배정완료 · ${housemanCreatePathLabel}`
              : `${realtime.order.roomNo}호 · 오더 등록 완료 · ${housemanCreatePathLabel}`;
          showToast(registrationTimingMessage);
          setSyncStatus(`${realtime.order.roomNo}호 오더 DB 저장 완료 · ${housemanCreatePathLabel}`);
"""
text = text[:rt_start] + rt_replacement + text[rt_end:]

legacy_old = """      showToast(result.order.assignedName
        ? `${result.order.roomNo}호 · ${result.order.assignedName}님에게 자동 배정했습니다.`
        : `${result.order.roomNo}호 미배정 오더를 등록했습니다.`);
      const telegram = result.telegram || {};"""
legacy_new = """      const legacyElapsed = Math.round(performance.now() - clickedAt);
      const legacyServerMs = Math.max(0, Number(result.timing?.totalMs || result.performance?.elapsedMs || 0));
      const legacyPathLabel = `Apps Script ${legacyElapsed}ms${legacyServerMs > 0 ? ` · 서버 ${legacyServerMs}ms` : ''}`;
      showToast(result.order.assignedName
        ? `${result.order.roomNo}호 · ${result.order.assignedName}님 자동배정 완료 · ${legacyPathLabel}`
        : `${result.order.roomNo}호 미배정 오더 등록 완료 · ${legacyPathLabel}`);
      setSyncStatus(`${result.order.roomNo}호 오더 저장 완료 · ${legacyPathLabel}`);
      const telegram = result.telegram || {};"""

if legacy_old not in text:
    raise SystemExit('Legacy houseman registration success block not found')
text = text.replace(legacy_old, legacy_new, 1)

path.write_text(text, encoding='utf-8')
print('Applied visible timing to Realtime and Apps Script houseman registration paths')
