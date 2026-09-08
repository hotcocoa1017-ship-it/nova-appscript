from pathlib import Path

path = Path('RealtimeDailySync.js')
text = path.read_text(encoding='utf-8')
marker = 'ADMIN_ORDER_UNSCOPED_SITE_SYNC_V1'
old = "allowedSites: ['ADMIN', 'ORDER'].includes(role) ? sites : (defaultSite ? [defaultSite] : [])"
new = "allowedSites: defaultSite ? [defaultSite] : [] // ADMIN_ORDER_UNSCOPED_SITE_SYNC_V1 · blank 기본사업장은 기존 NOVA와 동일하게 전체사업장"

if marker in text:
    print('ADMIN/ORDER site sync scope fix already applied.')
elif old not in text:
    raise SystemExit('ERROR: allowedSites sync anchor not found')
else:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')
    print('Applied ADMIN/ORDER blank-site unrestricted sync semantics.')

if old in text:
    raise SystemExit('ERROR: old knownSites-derived ADMIN/ORDER allowedSites mapping still remains')
if new not in text:
    raise SystemExit('ERROR: expected fixed allowedSites mapping missing')
