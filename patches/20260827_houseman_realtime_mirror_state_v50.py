from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

mapper_old = """      version: Number(row.version || 0),
      __sheetMirrorPending: true,
      __localProtectUntil: Date.now() + 30000
"""
mapper_new = """      version: Number(row.version || 0),
      __localProtectUntil: Date.now() + 30000
"""

if text.count(mapper_old) != 1:
    raise SystemExit(f'Expected exactly one unconditional Realtime houseman pending marker, found {text.count(mapper_old)}')
text = text.replace(mapper_old, mapper_new, 1)

broadcast_old = """    const order = novaRealtimeMapHousemanOrder_(raw);
    if (!order?.orderId || !order.roomNo || !order.site) return;
    if (String(order.businessDate) !== String(state.indicator.businessDate || '')) return;
    if (state.indicator.site && String(order.site) !== String(state.indicator.site)) return;
    upsertOrderLocal_(order, state.indicator.version);
    setSyncStatus(`${order.roomNo}호 하우스맨 오더 실시간 반영`);
"""

broadcast_new = """    const order = novaRealtimeMapHousemanOrder_(raw);
    if (!order?.orderId || !order.roomNo || !order.site) return;
    if (String(order.businessDate) !== String(state.indicator.businessDate || '')) return;
    if (state.indicator.site && String(order.site) !== String(state.indicator.site)) return;

    // Realtime DB version과 Sheet 변경버전은 서로 다른 버전 도메인입니다.
    // 이미 Sheet 이력이 확인된 오더는 rowNumber/Sheet version을 유지해야
    // 접수·처리·완료 및 재배정 시 기존 이력 동기화 대기 상태로 되돌아가지 않습니다.
    const existing = (state.indicator.data.orders || [])
      .find(item => String(item?.orderId || '') === String(order.orderId || ''));
    const existingRowNumber = Number(existing?.rowNumber || 0);

    if (existingRowNumber > 0) {
      order.rowNumber = existingRowNumber;
      order.version = Number(existing?.version || 0);
      delete order.__sheetMirrorPending;
      delete order.__sheetMirrorStartedAt;
    } else if (existing?.__sheetMirrorPending) {
      // 이 브라우저가 방금 Realtime 선저장을 시작한 경우에는
      // 실제 Sheet 미러 완료 전까지만 pending을 유지합니다.
      order.rowNumber = existingRowNumber;
      order.version = Number(existing?.version || order.version || 0);
      order.__sheetMirrorPending = true;
      order.__sheetMirrorStartedAt = Number(existing?.__sheetMirrorStartedAt || Date.now());
    } else {
      // 다른 브라우저에서 방금 생성/배정된 오더는 Sheet 행이 확인될 때까지만 보호합니다.
      order.__sheetMirrorPending = true;
      order.__sheetMirrorStartedAt = Date.now();
    }

    upsertOrderLocal_(order, state.indicator.version);
    setSyncStatus(`${order.roomNo}호 하우스맨 오더 실시간 반영`);
"""

if text.count(broadcast_old) != 1:
    raise SystemExit(f'Expected exactly one Realtime houseman broadcast block, found {text.count(broadcast_old)}')
text = text.replace(broadcast_old, broadcast_new, 1)

# Guardrails: Realtime create/manual assignment must still explicitly mark only the local in-flight mirror as pending.
if "order.__sheetMirrorPending = true;" not in text:
    raise SystemExit('Realtime create explicit mirror pending marker was lost')
if "__sheetMirrorStartedAt: Date.now()" not in text:
    raise SystemExit('Realtime manual assignment explicit mirror pending marker was lost')
if "오더는 저장되었습니다. 기존 이력 동기화가 완료된 뒤 처리할 수 있습니다." not in text:
    raise SystemExit('Existing processing safety guard was lost')

path.write_text(text, encoding='utf-8')
print('Fixed Realtime houseman pending-state merge without changing order workflow permissions or audit/Telegram flow')
