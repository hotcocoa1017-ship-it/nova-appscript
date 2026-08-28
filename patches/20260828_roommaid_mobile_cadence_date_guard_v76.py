from pathlib import Path

CLIENT = Path('Client.html')
text = CLIENT.read_text(encoding='utf-8')

old = """    let delay;
    if (roommaidRealtime) {
      // 검증 완료된 ROOMMAID는 기존 5.0~6.2초를 유지한다.
      delay = 5000 + Math.round(Math.random() * 1200);
    } else if (qmRealtime || housemanRealtime) {
      // QM/HOUSEMAN은 본인 배정목록만 경량조회하므로 3.0~3.7초로 분산한다.
      delay = 3000 + Math.round(Math.random() * 700);
    } else {
      delay = nextSyncDelay_(Number(state.bootstrap.app.mobileSyncMs || 16000));
    }
"""
new = """    let delay;
    if (roommaidRealtime || qmRealtime || housemanRealtime) {
      // ROOMMAID/QM/HOUSEMAN 모두 본인 배정목록만 경량조회하므로
      // 3.0~3.7초로 분산해 정상 네트워크 기준 5초 미만 반영을 목표로 한다.
      delay = 3000 + Math.round(Math.random() * 700);
    } else {
      delay = nextSyncDelay_(Number(state.bootstrap.app.mobileSyncMs || 16000));
    }
"""

count = text.count(old)
if count != 1:
    raise SystemExit(f'PATCH_ERROR: mobile cadence target expected 1 match, found {count}')
text = text.replace(old, new, 1)
CLIENT.write_text(text, encoding='utf-8')

check = CLIENT.read_text(encoding='utf-8')
required = [
    "const roommaidRealtime = novaRealtimeIsEnabled_() && role === 'ROOMMAID' && state.activeMenu === 'cleaning';",
    "const qmRealtime = novaRealtimeIsEnabled_() && role === 'QM' && state.activeMenu === 'qm';",
    "const housemanRealtime = novaRealtimeIsEnabled_() && role === 'HOUSEMAN' && state.activeMenu === 'houseman';",
    "if (roommaidRealtime || qmRealtime || housemanRealtime)",
    "delay = 3000 + Math.round(Math.random() * 700)",
    "businessDate: sessionStorage.getItem('novaIndicatorBusinessDate') || ''",
    "businessDate: sessionStorage.getItem('novaMobileBusinessDate') || ''",
    "sessionStorage.setItem('novaIndicatorBusinessDate', state.indicator.businessDate)",
    "sessionStorage.setItem('novaMobileBusinessDate', state.mobile.businessDate)",
    "businessDate: state.indicator.businessDate || state.bootstrap.app.businessDate",
    "businessDate: state.mobile.businessDate || state.bootstrap.app.businessDate",
    "window.addEventListener('beforeunload', () => {",
    "saveUiState();",
]
for marker in required:
    if marker not in check:
        raise SystemExit(f'PATCH_ERROR: missing guard marker: {marker}')

if "delay = 5000 + Math.round(Math.random() * 1200)" in check:
    raise SystemExit('PATCH_ERROR: old ROOMMAID 5.0-6.2s cadence still present')

print('ROOMMAID_MOBILE_CADENCE_DATE_GUARD_V76_OK')
print('Changed: Client.html only')
print('ROOMMAID/QM/HOUSEMAN refresh cadence: 3.0-3.7s')
print('Business date refresh guard: sessionStorage restore + beforeunload save + selected-date-first requests PASS')
