from pathlib import Path
import re
import subprocess
import sys

errors=[]
checks=[]


def read(path):
    p=Path(path)
    if not p.exists():
        errors.append(f'MISSING FILE: {path}')
        return ''
    return p.read_text(encoding='utf-8')


def require(text,needle,label):
    ok=needle in text
    checks.append((label,ok))
    if not ok: errors.append(f'MISSING: {label} :: {needle}')


def forbid(text,needle,label):
    ok=needle not in text
    checks.append((label,ok))
    if not ok: errors.append(f'FORBIDDEN: {label} :: {needle}')


def order(text,left,right,label):
    li=text.find(left); ri=text.find(right)
    ok=li>=0 and ri>=0 and li<ri
    checks.append((label,ok))
    if not ok: errors.append(f'ORDER: {label}')


def node_check(path,label):
    r=subprocess.run(['node','--check',path],text=True,capture_output=True,check=False)
    ok=r.returncode==0; checks.append((label,ok))
    if not ok: errors.append(f'SYNTAX: {label} :: {(r.stderr or r.stdout).strip()}')


def html_check(path,label):
    text=read(path); blocks=re.findall(r'<script[^>]*>(.*?)</script>',text,flags=re.S|re.I)
    if not blocks:
        checks.append((label,False)); errors.append(f'SYNTAX: {label} :: no script block'); return
    r=subprocess.run(['node','--check','-'],input='\n'.join(blocks),text=True,capture_output=True,check=False)
    ok=r.returncode==0; checks.append((label,ok))
    if not ok: errors.append(f'SYNTAX: {label} :: {(r.stderr or r.stdout).strip()}')


bridge=read('QmChecklistDbFirstBridge.js')
db_bridge=read('DbFirstBridge.js')
server=read('16_QmChecklist.js')
client=read('Client.html')
patcher=read('scripts/patch_qm_checklist_codes_dbfirst_v1_20260908.py')
canonical=read('scripts/fix_patch_site_scope_v2.py')
sql=read('supabase/migrations/20260908_qm_checklist_codes_db_first_v1.sql')

# Migration preserves current Sheet state exactly.
require(sql,'NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1','migration marker')
require(sql,"values('QM_CHECKLIST',true,20,'SHEET_VERIFIED_20260908'",'20-row verified state')
require(sql,"('QM체크리스트','QMCL-08','최종 객실 전체 확인',1,true",'QMCL-08 remains active')
for code in ['QMCL-01','QMCL-02','QMCL-03','QMCL-04','QMCL-05','QMCL-06','QMCL-07','QMCL-09','QMCL-10']:
    require(sql,f"('QM체크리스트','{code}'",f'{code} seed present')
require(sql,"upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER','QM')",'read role parity ADMIN/ORDER/QM')
require(sql,"upper(coalesce(v_user.role,'')) not in ('ADMIN','ORDER')",'write role parity ADMIN/ORDER')
require(sql,"group_code='QM체크리스트' and enabled=true",'active item rules in DB')
require(sql,"해당 장소를 사용하는 체크리스트 %개가 있습니다.",'place-in-use delete guard')
require(sql,"count(*) from public.nova_code_settings where group_code='QM점검장소' and enabled)>=30",'place max 30')
require(sql,"count(*) from public.nova_code_settings where group_code='QM체크리스트' and enabled)>=100",'item max 100')
for rpc in ['nova_qm_checklist_codes_read_v1','nova_qm_checklist_place_save_v1','nova_qm_checklist_item_save_v1','nova_qm_checklist_item_disable_v1','nova_qm_checklist_place_disable_v1']:
    require(sql,rpc,f'migration RPC {rpc}')
    require(db_bridge,f"'{rpc}'",f'RPC allowlist {rpc}')
require(sql,'revoke all on function public.nova_qm_checklist_codes_read_v1() from public,anon','read RPC anon revoked')

# Runtime bridge: DB read authority, fail-closed writes, Sheet compatibility mirror.
require(bridge,'NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1','runtime marker')
require(bridge,'function novaQmChecklistDefinitionFromDb_','DB definition builder')
require(bridge,'function getQmChecklistForSubmitDbFirst_','submit DB read wrapper')
require(bridge,'function getQmChecklistForMobileDbFirst_','mobile DB read wrapper')
require(bridge,"error.code = 'QM_CHECKLIST_DB_UNAVAILABLE'",'DB write fail-closed')
require(bridge,'novaQmChecklistMarkMirrorPending_','Sheet mirror pending')
require(bridge,'novaQmChecklistRetryPendingMirrors_','Sheet mirror retry')
require(bridge,'function getQmChecklistManagementDataDbFirst','management DB read')
for fn in ['saveQmChecklistPlaceDbFirst','deleteQmChecklistPlaceDbFirst','saveQmChecklistItemDbFirst','deleteQmChecklistItemDbFirst']:
    require(bridge,f'function {fn}',f'wrapper {fn}')
order(bridge,"novaDbFirstRpc_(token, 'nova_qm_checklist_place_save_v1'","novaQmChecklistMarkMirrorPending_('PLACE_SAVE'",'place DB commit precedes mirror')
order(bridge,"novaDbFirstRpc_(token, 'nova_qm_checklist_item_save_v1'","novaQmChecklistMarkMirrorPending_('ITEM_SAVE'",'item DB commit precedes mirror')
order(bridge,"novaDbFirstRpc_(token, 'nova_qm_checklist_place_disable_v1'","novaQmChecklistMarkMirrorPending_('PLACE_DISABLE'",'place disable DB precedes mirror')
order(bridge,"novaDbFirstRpc_(token, 'nova_qm_checklist_item_disable_v1'","novaQmChecklistMarkMirrorPending_('ITEM_DISABLE'",'item disable DB precedes mirror')

# Client management routes.
require(client,"callServer('getQmChecklistManagementDataDbFirst'",'client management DB read')
require(client,"callServer('saveQmChecklistPlaceDbFirst'",'client place DB save')
require(client,"callServer('deleteQmChecklistPlaceDbFirst'",'client place DB disable')
require(client,"callServer('saveQmChecklistItemDbFirst'",'client item DB save')
require(client,"callServer('deleteQmChecklistItemDbFirst'",'client item DB disable')
for token in ['QM_PLACE_SAVE_V1','QM_PLACE_DISABLE_V1','QM_ITEM_SAVE_V1','QM_ITEM_DISABLE_V1']:
    require(client,token,f'client request id {token}')
forbid(client,"callServer('getQmChecklistManagementData', state.token)",'direct legacy management read removed')
forbid(client,"callServer('saveQmChecklistPlace', state.token, payload)",'direct legacy place save removed')
forbid(client,"callServer('deleteQmChecklistPlace', state.token, { code })",'direct legacy place delete removed')
forbid(client,"callServer('saveQmChecklistItem', state.token, payload)",'direct legacy item save removed')
forbid(client,"callServer('deleteQmChecklistItem', state.token, { code })",'direct legacy item delete removed')

# QM execution reads same DB revision, including photo-create fallback.
require(server,'getQmChecklistForSubmitDbFirst_(token)','QM submit/runtime DB checklist')
require(server,'getQmChecklistForMobileDbFirst_(token)','QM mobile DB checklist')
require(server,'getQmChecklistForSubmitDbFirst_(token).items','QM photo DB checklist')
require(server,'Array.isArray(checklistItems) ? checklistItems : getActiveQmChecklistItems_()','photo helper compatibility fallback')
forbid(server,'const checklist = getQmChecklistForSubmit_();','direct Sheet submit definition removed')
require(server,'function getQmChecklistForSubmit_()','legacy submit reader preserved')
require(server,'function getQmChecklistForMobile_()','legacy mobile reader preserved')
for fn in ['getQmChecklistManagementData','saveQmChecklistPlace','deleteQmChecklistPlace','saveQmChecklistItem','deleteQmChecklistItem']:
    require(server,f'function {fn}',f'legacy compatibility function {fn}')

# Canonical ownership and patch idempotence anchors.
require(canonical,'patch_qm_checklist_codes_dbfirst_v1_20260908.py','canonical QM patch registration')
require(canonical,'validate_qm_checklist_codes_dbfirst_v1_20260908.py','canonical QM validator registration')
require(patcher,"'nova_qm_checklist_codes_read_v1'",'patcher RPC ownership')
require(patcher,"callServer('getQmChecklistManagementDataDbFirst'",'patcher client ownership')
require(patcher,'getQmChecklistForSubmitDbFirst_(token)','patcher runtime ownership')

node_check('QmChecklistDbFirstBridge.js','QM DB bridge JavaScript syntax')
node_check('DbFirstBridge.js','DB bridge JavaScript syntax')
node_check('16_QmChecklist.js','QM server JavaScript syntax')
html_check('Client.html','Client script syntax')

if errors:
    print(f'QM checklist DB-first gate FAILED: {len(errors)} issue(s), {len(checks)} checks.',file=sys.stderr)
    for error in errors: print(f' - {error}',file=sys.stderr)
    raise SystemExit(99)
print(f'QM checklist DB-first gate passed: {len(checks)} checks.')
