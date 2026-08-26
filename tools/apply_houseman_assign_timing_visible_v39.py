from pathlib import Path

client = Path("Client.html")
text = client.read_text(encoding="utf-8")

old = """      if (action === 'ASSIGN' && result.timing) {
        const t = result.timing;
        setSyncStatus(`하우스맨 배정 성능 · 총 ${Number(t.totalMs || result.performance?.elapsedMs || 0)}ms · 인증 ${Number(t.authMs || 0)} · 잠금 ${Number(t.lockWaitMs || 0)} · 행찾기 ${Number(t.findMs || 0)} · 조회 ${Number(t.lookupMs || 0)} · 저장 ${Number(t.writeMs || 0)} · 버전 ${Number(t.publishMs || 0)} · 감사 ${Number(t.auditMs || 0)} · 알림준비 ${Number(t.telegramMs || 0)}ms`);
      }
"""

new = """      if (action === 'ASSIGN') {
        const t = result.timing || {};
        const perfText = result.timing
          ? `하우스맨 배정 성능 · 총 ${Number(t.totalMs || result.performance?.elapsedMs || 0)}ms · 인증 ${Number(t.authMs || 0)} · 잠금 ${Number(t.lockWaitMs || 0)} · 행찾기 ${Number(t.findMs || 0)} · 조회 ${Number(t.lookupMs || 0)} · 저장 ${Number(t.writeMs || 0)} · 버전 ${Number(t.publishMs || 0)} · 감사 ${Number(t.auditMs || 0)} · 알림준비 ${Number(t.telegramMs || 0)}ms`
          : `하우스맨 배정 성능 · 서버 계측값 없음 · API ${Number(result.performance?.elapsedMs || 0)}ms`;
        setSyncStatus(perfText);
        showToast(perfText);
        window.__novaLastHousemanAssignTiming = {
          text: perfText,
          timing: result.timing || null,
          performance: result.performance || null,
          capturedAt: new Date().toISOString()
        };
      }
"""

if new in text:
    print("SKIP visible houseman timing: already applied")
elif text.count(old) == 1:
    client.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("PATCH OK visible houseman timing toast")
else:
    raise SystemExit(f"PATCH FAIL visible houseman timing: expected 1 match, found {text.count(old)}")

verify = client.read_text(encoding="utf-8")
for marker in [
    "showToast(perfText);",
    "window.__novaLastHousemanAssignTiming",
    "서버 계측값 없음"
]:
    if marker not in verify:
        raise SystemExit(f"VERIFY FAIL visible timing marker missing: {marker}")

print("VERIFY PASS houseman ASSIGN timing is forced to visible toast; no business logic changed")
