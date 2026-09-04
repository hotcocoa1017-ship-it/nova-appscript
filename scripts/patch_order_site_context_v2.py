from pathlib import Path
import sys

MARKER = 'ORDER_SHARED_SITE_CONTEXT_V2'
path = Path('Client.html')
text = path.read_text(encoding='utf-8')

if MARKER in text:
    print('ORDER shared site context V2 already applied.')
else:
    if 'ORDER_SHARED_SITE_CONTEXT_V1' not in text:
        print('ERROR: ORDER_SHARED_SITE_CONTEXT_V1 is required before V2.', file=sys.stderr)
        raise SystemExit(80)

    old_get = """  function getOrderSharedSite_() {\n    if (!isOrderSharedSiteContext_()) return '';\n    return String(sessionStorage.getItem('novaOrderWorkSite') || '').trim();\n  }"""
    new_get = """  function getOrderSharedSite_() { // ORDER_SHARED_SITE_CONTEXT_V2 · 기존 세션도 인디케이터 사업장 승계\n    if (!isOrderSharedSiteContext_()) return '';\n    const stored = String(sessionStorage.getItem('novaOrderWorkSite') || '').trim();\n    if (stored) return stored;\n    const indicatorSite = String(state.indicator?.site || '').trim();\n    const persistedIndicatorSite = String(sessionStorage.getItem('novaIndicatorSite') || '').trim();\n    const fallback = indicatorSite || persistedIndicatorSite;\n    if (fallback) sessionStorage.setItem('novaOrderWorkSite', fallback);\n    return fallback;\n  }"""
    if old_get not in text:
        print('ERROR: V1 getOrderSharedSite_ anchor not found.', file=sys.stderr)
        raise SystemExit(81)
    text = text.replace(old_get, new_get, 1)

    # Indicator server response is authoritative. Once a query returns a site, resync ORDER shared context.
    old_result = """    state.indicator.site = result.selection?.site ?? state.indicator.site;\n    sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''));\n    state.indicator.data = Object.assign({}, previousData || {}, result);"""
    new_result = """    state.indicator.site = result.selection?.site ?? state.indicator.site;\n    sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''));\n    if (state.indicator.site) setOrderSharedSite_(state.indicator.site); // ORDER_SHARED_SITE_CONTEXT_V2\n    state.indicator.data = Object.assign({}, previousData || {}, result);"""
    if old_result not in text:
        print('ERROR: indicator result anchor not found.', file=sys.stderr)
        raise SystemExit(82)
    text = text.replace(old_result, new_result, 1)

    path.write_text(text, encoding='utf-8')
    print('Applied ORDER shared work-site context V2 fallback and authoritative resync.')

# 정식 전체 배포 체인에서 하우스맨 관련 보강을 항상 적용합니다.
# 일부 기존 패치 스크립트가 이미 적용된 경우 SystemExit(0)으로 끝나므로,
# 신규/권한 패치를 먼저 적용한 뒤 기존 Push 패치를 마지막에 호출합니다.
import patch_qm_houseman_request_parity_v1  # noqa: E402,F401
import patch_houseman_latest_first_v1  # noqa: E402,F401
import patch_houseman_realtime_push  # noqa: E402,F401
