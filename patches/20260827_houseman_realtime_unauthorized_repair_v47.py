from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

old_sig = "  async function novaRealtimeCreateHousemanOrder_(payload) { // (Cloud Run/PostgreSQL 등록 확정)"
new_sig = "  async function novaRealtimeCreateHousemanOrder_(payload, authRetry = 0) { // (Cloud Run/PostgreSQL 등록 확정)"
if old_sig not in text:
    raise SystemExit('Target function signature not found')
text = text.replace(old_sig, new_sig, 1)

old_call = """    const result = await novaRealtimeFetch_('/v1/houseman-orders', {
      method: 'POST',
      headers: { 'X-Request-Id': requestId },
      body: JSON.stringify(apiPayload)
    });
"""
new_call = """    let result;
    try {
      result = await novaRealtimeFetch_('/v1/houseman-orders', {
        method: 'POST',
        headers: { 'X-Request-Id': requestId },
        body: JSON.stringify(apiPayload)
      });
    } catch (error) {
      // Apps Script 로그인은 정상인데 Realtime DB 사용자/서명이 뒤처진 경우 1회 자가복구합니다.
      // 기존 signed JIT sync가 현재 사용자와 객실을 PostgreSQL에 맞춘 뒤 동일 등록을 재시도합니다.
      if (authRetry < 1 && String(error?.code || '').trim().toUpperCase() === 'UNAUTHORIZED') {
        await callServer('syncNovaRealtimeRoomForAction', state.token, {
          businessDate: String(payload.businessDate || ''),
          site: String(payload.site || ''),
          roomNo: String(payload.roomNo || '')
        });
        return novaRealtimeCreateHousemanOrder_(payload, authRetry + 1);
      }
      throw error;
    }
"""
if old_call not in text:
    raise SystemExit('Realtime houseman POST block not found')
text = text.replace(old_call, new_call, 1)

path.write_text(text, encoding='utf-8')
print('Applied one-time UNAUTHORIZED self-heal for realtime houseman registration')
