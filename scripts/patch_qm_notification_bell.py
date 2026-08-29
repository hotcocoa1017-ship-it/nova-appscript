from pathlib import Path
import sys

path = Path('HousemanUiPerformancePatch.html')
text = path.read_text(encoding='utf-8')
marker = 'QM_NOTIFICATION_BELL_V1'

if marker in text:
    print('QM notification bell patch already applied.')
    sys.exit(0)

old_decl = "const o=document.getElementById('orderScroll'),h=document.querySelector('#mobilePage[data-mobile-menu=\"houseman\"]');"
new_decl = "const o=document.getElementById('orderScroll'),h=document.querySelector('#mobilePage[data-mobile-menu=\"houseman\"]'),q=document.querySelector('#mobilePage[data-mobile-menu=\"qm\"]');/* QM_NOTIFICATION_BELL_V1 */"
if text.count(old_decl) != 1:
    print(f'ERROR: notification refresh declaration anchor count={text.count(old_decl)}', file=sys.stderr)
    sys.exit(60)
text = text.replace(old_decl, new_decl, 1)

old_refresh_end = "}render()}\nfunction indItem"
qm_branch = "}else if(q){S.userKey=user;const browse=!!q.querySelector('#mobileList .qm-browse-inspection');if(!(browse&&S.mode==='QM')){S.mode='QM';const list=[...q.querySelectorAll('#mobileList .mobile-room-card')].map(qmItem).filter(Boolean);const n=qmSummaryCount();if(list.length||n===0)S.items=list;S.count=Math.max(n,list.length);if(S.count>S.items.length&&!S.items.some(x=>x.placeholder))S.items=S.items.concat([{room:'추가 점검대상',item:`${S.count-S.items.length}건의 점검할 객실이 더 있습니다.`,sub:'점검대상 탭에서 확인',status:'점검대기',placeholder:true}])}}render()}\nfunction indItem"
if text.count(old_refresh_end) != 1:
    print(f'ERROR: notification refresh end anchor count={text.count(old_refresh_end)}', file=sys.stderr)
    sys.exit(61)
text = text.replace(old_refresh_end, qm_branch, 1)

old_item_anchor = "function mobItem(r){const c=r.querySelector('.status-chip');return{key:r.dataset.mobileOrderId,room:t(r.querySelector('.mobile-card-top strong')),item:t(r.querySelector('.mobile-task-title')),sub:t(r.querySelector('.mobile-task-meta')),status:t(c),code:status(c),el:r}}\nfunction summaryCount()"
new_item_anchor = "function mobItem(r){const c=r.querySelector('.status-chip');return{key:r.dataset.mobileOrderId,room:t(r.querySelector('.mobile-card-top strong')),item:t(r.querySelector('.mobile-task-title')),sub:t(r.querySelector('.mobile-task-meta')),status:t(c),code:status(c),el:r}}\nfunction qmItem(r){const a=r.querySelector('[data-room-action=\"START\"],[data-room-action=\"CONTINUE\"]');if(!a)return null;const room=t(r.querySelector('.mobile-card-top strong')),loc=t(r.querySelector('.mobile-card-top span')),maid=t(r.querySelector('.mobile-room-status b'));const checking=String(a.dataset.roomAction||'').toUpperCase()==='CONTINUE';return{key:`QM-${room}`,room,item:checking?'QM 점검 계속':'QM 점검 시작',sub:[loc,maid&&maid!=='-'?`정비 ${maid}`:''].filter(Boolean).join(' · '),status:checking?'점검중':'점검대기',code:checking?'QM_CHECKING':'QM_WAITING',el:a}}\nfunction qmSummaryCount(){let n=0;document.querySelectorAll('#mobileSummary .mobile-summary-card').forEach(c=>{const l=t(c.querySelector('span')),v=Number(t(c.querySelector('strong')).replace(/\\D/g,'')||0);if(l==='점검대기'||l==='점검중')n+=v});return n}\nfunction summaryCount()"
if text.count(old_item_anchor) != 1:
    print(f'ERROR: mobile item anchor count={text.count(old_item_anchor)}', file=sys.stderr)
    sys.exit(62)
text = text.replace(old_item_anchor, new_item_anchor, 1)

old_ok = "const ok=S.mode==='INDICATOR'||S.mode==='HOUSEMAN';"
new_ok = "const ok=S.mode==='INDICATOR'||S.mode==='HOUSEMAN'||S.mode==='QM';"
if text.count(old_ok) != 1:
    print(f'ERROR: notification visible-mode anchor count={text.count(old_ok)}', file=sys.stderr)
    sys.exit(63)
text = text.replace(old_ok, new_ok, 1)

old_empty = ":'<div class=\"nova-notification-empty\">현재 처리할 하우스맨 알림이 없습니다.</div>';"
new_empty = ":`<div class=\"nova-notification-empty\">${S.mode==='QM'?'현재 점검할 QM 객실이 없습니다.':'현재 처리할 하우스맨 알림이 없습니다.'}</div>`;"
if text.count(old_empty) != 1:
    print(f'ERROR: notification empty-message anchor count={text.count(old_empty)}', file=sys.stderr)
    sys.exit(64)
text = text.replace(old_empty, new_empty, 1)

path.write_text(text, encoding='utf-8')
print('Applied QM notification bell patch.')
