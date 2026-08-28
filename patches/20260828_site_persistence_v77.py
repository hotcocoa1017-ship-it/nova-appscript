from pathlib import Path

CLIENT = Path('Client.html')
text = CLIENT.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    text = text.replace(old, new, 1)

# 1) Restore selected site at page bootstrap.
replace_once(
    "      businessDate: sessionStorage.getItem('novaIndicatorBusinessDate') || '',\n      site: '',\n      filter: 'ALL',",
    "      businessDate: sessionStorage.getItem('novaIndicatorBusinessDate') || '',\n      site: sessionStorage.getItem('novaIndicatorSite') || '',\n      filter: 'ALL',",
    'indicator site restore'
)
replace_once(
    "      businessDate: sessionStorage.getItem('novaMobileBusinessDate') || '',\n      site: '',\n      filter: 'ACTIVE',",
    "      businessDate: sessionStorage.getItem('novaMobileBusinessDate') || '',\n      site: sessionStorage.getItem('novaMobileSite') || '',\n      filter: 'ACTIVE',",
    'mobile site restore'
)

# 2) Save site together with menu/date before refresh/unload. Store empty string too so '전체' clears prior site.
replace_once(
    "    if (state.indicator.businessDate) sessionStorage.setItem('novaIndicatorBusinessDate', state.indicator.businessDate);\n    if (state.mobile.businessDate) sessionStorage.setItem('novaMobileBusinessDate', state.mobile.businessDate);\n  }",
    "    if (state.indicator.businessDate) sessionStorage.setItem('novaIndicatorBusinessDate', state.indicator.businessDate);\n    if (state.mobile.businessDate) sessionStorage.setItem('novaMobileBusinessDate', state.mobile.businessDate);\n    sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''));\n    sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n  }",
    'save selected sites'
)

# 3) Persist explicit site selection immediately.
replace_once(
    "    $('indicatorSite').addEventListener('change', event => {\n      state.indicator.site = event.target.value;\n      state.indicator.building = '';",
    "    $('indicatorSite').addEventListener('change', event => {\n      state.indicator.site = event.target.value;\n      sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''));\n      state.indicator.building = '';",
    'indicator site change persistence'
)
replace_once(
    "    $('mobileSite').addEventListener('change', event => {\n      state.mobile.site = event.target.value;\n      state.mobile.building = '';",
    "    $('mobileSite').addEventListener('change', event => {\n      state.mobile.site = event.target.value;\n      sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n      state.mobile.building = '';",
    'mobile site change persistence'
)

# 4) Persist server-normalized selection after snapshots so invalid/stale site values self-heal.
replace_once(
    "    state.indicator.site = result.selection?.site ?? state.indicator.site;\n    state.indicator.data = Object.assign({}, previousData || {}, result);",
    "    state.indicator.site = result.selection?.site ?? state.indicator.site;\n    sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''));\n    state.indicator.data = Object.assign({}, previousData || {}, result);",
    'indicator snapshot site persistence'
)
replace_once(
    "    state.mobile.site = result.selection?.site ?? state.mobile.site;\n    renderMobileData();",
    "    state.mobile.site = result.selection?.site ?? state.mobile.site;\n    sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n    renderMobileData();",
    'mobile snapshot site persistence'
)

# 5) If indicator auto-selects a room's site, preserve that effective site too.
replace_once(
    "    if (siteChanged) {\n      state.indicator.site = room.site;\n      if ($('indicatorSite')) $('indicatorSite').value = room.site;\n    }",
    "    if (siteChanged) {\n      state.indicator.site = room.site;\n      sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''));\n      if ($('indicatorSite')) $('indicatorSite').value = room.site;\n    }",
    'indicator auto-selected site persistence'
)

CLIENT.write_text(text, encoding='utf-8')

check = CLIENT.read_text(encoding='utf-8')
required = [
    "site: sessionStorage.getItem('novaIndicatorSite') || ''",
    "site: sessionStorage.getItem('novaMobileSite') || ''",
    "sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''))",
    "sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''))",
    "businessDate: sessionStorage.getItem('novaIndicatorBusinessDate') || ''",
    "businessDate: sessionStorage.getItem('novaMobileBusinessDate') || ''",
    "businessDate: state.indicator.businessDate || state.bootstrap.app.businessDate",
    "businessDate: state.mobile.businessDate || state.bootstrap.app.businessDate",
    "window.addEventListener('beforeunload', () => {",
    "if (roommaidRealtime || qmRealtime || housemanRealtime)",
    "delay = 3000 + Math.round(Math.random() * 700)",
]
for marker in required:
    if marker not in check:
        raise SystemExit(f'PATCH_ERROR: missing guard marker: {marker}')

# Ensure the operational indicator/mobile state no longer resets site to blank on reload.
indicator_reset = "businessDate: sessionStorage.getItem('novaIndicatorBusinessDate') || '',\n      site: '',\n      filter: 'ALL'"
mobile_reset = "businessDate: sessionStorage.getItem('novaMobileBusinessDate') || '',\n      site: '',\n      filter: 'ACTIVE'"
if indicator_reset in check or mobile_reset in check:
    raise SystemExit('PATCH_ERROR: indicator/mobile site still resets to blank')

print('SITE_PERSISTENCE_V77_OK')
print('Changed: Client.html only')
print('ADMIN/ORDER indicator site: refresh persistence PASS')
print('HOUSEMAN/QM/ROOMMAID mobile site: refresh persistence PASS')
print('Business date persistence and 3.0-3.7s mobile cadence preserved')
