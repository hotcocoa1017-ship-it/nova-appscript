from pathlib import Path
import re

text = Path('Client.html').read_text(encoding='utf-8')

required = [
    'ORDER_SHARED_SITE_CONTEXT_V1',
    'function isOrderSharedSiteContext_()',
    "return String(state.bootstrap?.user?.role || '').trim().toUpperCase() === 'ORDER';",
    "sessionStorage.setItem('novaOrderWorkSite', nextSite);",
    'setOrderSharedSite_(site);',
    "applyOrderSharedSiteToMenu_(menuId);",
    "lockOrderSharedSiteSelect_(menuId);",
    "departure: 'departureSite'",
    "monthly: 'monthlySite'",
    "roommaidStats: 'roommaidPerformanceSite'",
    "roommaidClose: 'roommaidCloseSite'",
    "shifts: 'shiftSite'",
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'Missing ORDER site context marker: {marker}')

# The shared-site setter must only act for ORDER.
helper = re.search(r'function setOrderSharedSite_\(site\) \{(.*?)\n  \}', text, re.S)
if not helper or 'if (!isOrderSharedSiteContext_()) return' not in helper.group(1):
    raise SystemExit('ORDER guard missing in shared site setter.')

# All five dependent menus must apply the shared site before rendering.
for menu in ['departure', 'monthly', 'roommaidStats', 'roommaidClose', 'shifts']:
    pattern = rf"if \(menuId === '{re.escape(menu)}'\) \{{\s*applyOrderSharedSiteToMenu_\(menuId\);"
    if not re.search(pattern, text):
        raise SystemExit(f'Shared site not applied before menu render: {menu}')

# Explicit indicator query must commit the context only after date/site have been accepted into state.
query = re.search(
    r"state\.indicator\.site = site;.*?sessionStorage\.setItem\('novaIndicatorSite', site\);\s*setOrderSharedSite_\(site\);\s*loadIndicatorSnapshot",
    text,
    re.S,
)
if not query:
    raise SystemExit('Indicator query does not commit ORDER work site before loading snapshot.')

# The lock must only disable selectors for ORDER and never ADMIN.
lock = re.search(r'function lockOrderSharedSiteSelect_\(menuId\) \{(.*?)\n  \}', text, re.S)
if not lock or 'if (!isOrderSharedSiteContext_()) return;' not in lock.group(1) or 'select.disabled = true;' not in lock.group(1):
    raise SystemExit('ORDER-only select lock is not safely guarded.')

# Changing site must invalidate dependent cached datasets, preventing old-site data flash.
setter = helper.group(1)
for state_name in ['state.departure', 'state.monthly', 'state.roommaidStats', 'state.roommaidClose', 'state.shifts']:
    if state_name not in setter:
        raise SystemExit(f'Dependent state missing from invalidation: {state_name}')
if 'bucket.loaded = false;' not in setter or 'bucket.data = null;' not in setter:
    raise SystemExit('Dependent data cache invalidation missing.')

print('ORDER shared site context validation: PASS')
