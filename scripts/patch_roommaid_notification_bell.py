from pathlib import Path
import sys

path = Path('HousemanUiPerformancePatch.html')
text = path.read_text(encoding='utf-8')
marker = 'ROOMMAID_NOTIFICATION_BELL_V1'

if marker in text:
    print('Roommaid notification bell patch already applied.')
    sys.exit(0)

old_decl = "const o=document.getElementById('orderScroll'),h=document.querySelector('#mobilePage[data-mobile-menu=\"houseman\"]'),q=document.querySelector('#mobilePage[data-mobile-menu=\"qm\"]');/* QM_NOTIFICATION_BELL_V1 */"
new_decl = "const o=document.getElementById('orderScroll'),h=document.querySelector('#mobilePage[data-mobile-menu=\"houseman\"]'),r=document.querySelector('#mobilePage[data-mobile-menu=\"cleaning\"]'),q=document.querySelector('#mobilePage[data-mobile-menu=\"qm\"]');/* QM_NOTIFICATION_BELL_V1 · ROOMMAID_NOTIFICATION_BELL_V1 */"
if text.count(old_decl) != 1:
    print(f'ERROR: roommaid notification declaration anchor count={text.count(old_decl)}', file=sys.stderr)
    sys.exit(80)
text = text.replace(old_decl, new_decl, 1)

old_qm_branch = "}else if(q){S.userKey=user;const browse=!!q.querySelector('#mobileList .qm-browse-inspection');"
roommaid_branch = "}else if(r){S.userKey=user;S.mode='ROOMMAID';const list=[...r.querySelectorAll('#mobileList .mobile-room-card')].map(roommaidItem).filter(Boolean);const n=roommaidSummaryCount();if(list.length||n===0)S.items=list;S.count=Math.max(n,list.length);if(S.count>S.items.length&&!S.items.some(x=>x.placeholder))S.items=S.items.concat([{room:'추가 정비객실',item:`${S.count-S.items.length}건의 처리할 객실이 더 있습니다.`,sub:'오늘의 정비 화면에서 확인',status:'정비대기',placeholder:true}])}else if(q){S.userKey=user;const browse=!!q.querySelector('#mobileList .qm-browse-inspection');"
if text.count(old_qm_branch) != 1:
    print(f'ERROR: roommaid branch anchor count={text.count(old_qm_branch)}', file=sys.stderr)
    sys.exit(81)
text = text.replace(old_qm_branch, roommaid_branch, 1)

old_item_anchor = "function qmItem(r){const a=r.querySelector('[data-room-action=\"START\"],[data-room-action=\"CONTINUE\"]');"
new_item_anchor = "function roommaidItem(r){const a=r.querySelector('[data-room-action=\"START\"],[data-room-action=\"COMPLETE\"]');if(!a)return null;const room=t(r.querySelector('.mobile-card-top strong')),loc=t(r.querySelector('.mobile-card-top span')),statusText=t(r.querySelector('.mobile-room-status span')),typeText=t(r.querySelector('.mobile-cleaning-type')),assigned=t(r.querySelector('.mobile-assigned-names'));const action=String(a.dataset.roomAction||'').toUpperCase();const working=action==='COMPLETE';return{key:`ROOMMAID-${room}`,room,item:working?'청소 완료':'청소 시작',sub:[loc,typeText,assigned].filter(Boolean).join(' · '),status:working?'청소중':(statusText||'정비대기'),code:working?'CLEANING':'ASSIGNED',el:a}}\nfunction roommaidSummaryCount(){let n=0;document.querySelectorAll('#mobileSummary .mobile-summary-card').forEach(c=>{const l=t(c.querySelector('span')),v=Number(t(c.querySelector('strong')).replace(/\\D/g,'')||0);if(l==='대기'||l==='청소중')n+=v});return n}\nfunction qmItem(r){const a=r.querySelector('[data-room-action=\"START\"],[data-room-action=\"CONTINUE\"]');"
if text.count(old_item_anchor) != 1:
    print(f'ERROR: roommaid item anchor count={text.count(old_item_anchor)}', file=sys.stderr)
    sys.exit(82)
text = text.replace(old_item_anchor, new_item_anchor, 1)

old_ok = "const ok=S.mode==='INDICATOR'||S.mode==='HOUSEMAN'||S.mode==='QM';"
new_ok = "const ok=S.mode==='INDICATOR'||S.mode==='HOUSEMAN'||S.mode==='ROOMMAID'||S.mode==='QM';"
if text.count(old_ok) != 1:
    print(f'ERROR: roommaid visible-mode anchor count={text.count(old_ok)}', file=sys.stderr)
    sys.exit(83)
text = text.replace(old_ok, new_ok, 1)

old_empty = "${S.mode==='QM'?'현재 점검할 QM 객실이 없습니다.':'현재 처리할 하우스맨 알림이 없습니다.'}"
new_empty = "${S.mode==='QM'?'현재 점검할 QM 객실이 없습니다.':S.mode==='ROOMMAID'?'현재 처리할 룸메이드 객실이 없습니다.':'현재 처리할 하우스맨 알림이 없습니다.'}"
if text.count(old_empty) != 1:
    print(f'ERROR: roommaid empty-message anchor count={text.count(old_empty)}', file=sys.stderr)
    sys.exit(84)
text = text.replace(old_empty, new_empty, 1)

path.write_text(text, encoding='utf-8')
print('Applied roommaid notification bell patch.')
