from pathlib import Path
import re
import sys

FAIL = []

def need(cond, msg):
    if not cond:
        FAIL.append(msg)

index = Path('Index.html').read_text(encoding='utf-8')
auth = Path('03_Auth.js').read_text(encoding='utf-8')
repo = Path('02_Repository.js').read_text(encoding='utf-8')
mobile = Path('10_Mobile.js').read_text(encoding='utf-8')
qm = Path('QmMobileBrowse.js').read_text(encoding='utf-8')
client = Path('Client.html').read_text(encoding='utf-8')
close = Path('19_RoommaidCloseJournal.js').read_text(encoding='utf-8')
realtime = Path('RealtimeDailySync.js').read_text(encoding='utf-8')

# Login UI order and server scope.
site_pos = index.find('id="loginSite"')
name_pos = index.find('id="loginName"')
emp_pos = index.find('id="loginEmployeeNo"')
need(site_pos >= 0 and site_pos < name_pos < emp_pos, 'login input order must be site -> name -> employeeNo')
need('관리자·오더테이커는 선택하지 않음' in index, 'admin/order site omission option missing')
need('function loginNovaBootstrap(name, employeeNo, clientType, site)' in auth, 'login bootstrap site argument missing')
need("const token = createLoginToken_(user.employeeNo, user.sessionSite);" in auth, 'session site not embedded in token')
need("if (!site) throw new Error('사업장을 선택하세요.');" in auth, 'non admin/order site requirement missing')
need("if (!['ADMIN', 'ORDER'].includes" in auth or "!['ADMIN', 'ORDER'].includes" in auth, 'admin/order exemption missing')
need('function resolveUserSessionSite_' in auth, 'server session-site enforcement helper missing')
need("employmentType: value('채용구분')" in repo, 'employment type user-index cache field missing')
need('sessionSite:' in repo and 'siteScopeLocked:' in repo, 'public bootstrap site scope missing')
need("resolveUserSessionSite_(user, safe.site)" in mobile, 'mobile request site scope missing')
need("resolveUserSessionSite_(user, safe.site)" in qm, 'QM browse site scope missing')
need("resolveUserSessionSite_(auth.user, safe.site)" in realtime, 'Realtime JIT site scope missing')

# Pure policy simulation: mirrors server helper semantics.
SITES = {'쏘라노', '별관'}
def login_site(role, selected, configured=''):
    role = role.upper()
    if role in {'ADMIN', 'ORDER'}:
        return ''
    if not selected:
        raise ValueError('site required')
    if selected not in SITES:
        raise ValueError('invalid site')
    if configured and configured != selected:
        raise ValueError('configured mismatch')
    return selected

need(login_site('ADMIN', '') == '', 'ADMIN blank-site simulation failed')
need(login_site('ORDER', '') == '', 'ORDER blank-site simulation failed')
need(login_site('ROOMMAID', '쏘라노') == '쏘라노', 'ROOMMAID scoped-site simulation failed')
try:
    login_site('QM', '')
    need(False, 'QM blank site should fail')
except ValueError:
    pass
try:
    login_site('ROOMMAID', '쏘라노', '별관')
    need(False, 'configured-site mismatch should fail')
except ValueError:
    pass

# Indicator must query only after date + site + button.
need(client.count('id="indicatorQueryButton"') == 1, 'indicator query button must exist exactly once')
need("if (!businessDate) return showToast('업무일자를 선택하세요.');" in client, 'indicator date validation missing')
need("if (!site) return showToast('사업장을 선택하세요.');" in client, 'indicator site validation missing')
need("loadIndicatorSnapshot({ force: true, silent: false });" in client, 'explicit indicator query call missing')
need('renderIndicatorAwaitingQuery_' in client and 'markIndicatorQueryDirty_' in client, 'indicator pending-query helpers missing')
need("if (!state.indicator.queryApplied || state.indicator.queryDirty || !state.indicator.loaded) return [];" in client, 'Realtime indicator pre-query gate missing')
need("state.indicator.queryApplied && state.indicator.loaded && !state.indicator.queryDirty" in client, 'Realtime init query gate missing')

for control in ('indicatorDate', 'indicatorSite'):
    m = re.search(r"\$\('%s'\)\.addEventListener\('change', event => \{(.*?)\n\s*\}\);" % control, client, re.S)
    need(bool(m), f'{control} change listener missing')
    if m:
        need('loadIndicatorSnapshot' not in m.group(1), f'{control} must not auto-query')
        need('markIndicatorQueryDirty_' in m.group(1), f'{control} must mark pending query')

# Entering indicator may not auto-query when no previously applied query.
need('renderIndicatorAwaitingQuery_();' in client, 'indicator initial waiting state missing')

# Close journal V2: Realtime current rooms for live reads, TextFinder history, Sheet fallback for safety.
need('ROOMMAID_CLOSE_READ_ACCEL_V2' in close, 'close journal V2 marker missing')
need('readRoommaidCloseRealtimeCurrentRows_' in close, 'close journal Realtime current-room helper missing')
need("historyLookup: 'DATE_TEXTFINDER'" in close, 'close journal TextFinder marker missing')
need('.createTextFinder(String(businessDate || \'\'))' in close, 'history date TextFinder missing')
need('readRoommaidCloseHistoryBundle_(businessDate, site)' in close, 'history fallback missing')
need('readRoommaidCloseCurrentSelection_(businessDate, preferredSite, defaultSite)' in close, 'current Sheet fallback missing')
need("if (!saved)" in close and "currentSource = 'REALTIME_DB'" in close, 'Realtime current rows must be live/unclosed only')
need("currentSource = 'SHEET'" in close, 'saved/fallback Sheet source missing')
need('function saveRoommaidCloseJournal(token, payload)' in close, 'close save function must remain')
need('saveDailyCloseSnapshotForSite_' in close, 'official close save path must remain unchanged')
need('function resetRoommaidCloseJournal(token, payload)' in close, 'close reset function must remain')
need("users[employeeNo].employmentType" in close, 'employment index must reuse cached users')

# Syntax-level sanity for accidental malformed patches.
need(client.count("function bindIndicatorShellEvents()") == 1, 'indicator bind function duplication')
need(client.count("function loadIndicatorSnapshot(") == 1, 'indicator loader duplication')
need(auth.count('function verifyNovaToken(') == 1, 'verifyNovaToken duplication')
need(close.count('function getRoommaidCloseJournal(') == 1, 'close journal getter duplication')

if FAIL:
    print('SITE_SCOPE_INDICATOR_CLOSE_V2 validation FAILED:', file=sys.stderr)
    for item in FAIL:
        print(f' - {item}', file=sys.stderr)
    sys.exit(91)

print('SITE_SCOPE_INDICATOR_CLOSE_V2 validation PASS')
