const CACHE='nova-pwa-v2-vercel-3';
const ICON='https://evoetxfjmkkjptucwxsv.supabase.co/storage/v1/object/public/nova-pwa-v2/icon-192.png';
const BADGE='https://evoetxfjmkkjptucwxsv.supabase.co/storage/v1/object/public/nova-pwa-v2/badge-96.png';
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['./index.html','./manifest.webmanifest'])).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(u.origin!==location.origin)return;
  if(e.request.mode==='navigate'){
    e.respondWith(fetch(e.request).then(r=>{const clone=r.clone();caches.open(CACHE).then(c=>c.put('./index.html',clone)).catch(()=>{});return r}).catch(()=>caches.match('./index.html')));
    return;
  }
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request).then(net=>{if(e.request.method==='GET'){const clone=net.clone();caches.open(CACHE).then(c=>c.put(e.request,clone)).catch(()=>{})}return net})));
});
async function setBadge(n){try{if(self.navigator?.setAppBadge){if(Number(n)>0)await self.navigator.setAppBadge(Number(n));else await self.navigator.clearAppBadge()}}catch(_){}}
self.addEventListener('push',e=>{e.waitUntil((async()=>{
  let p={title:'NOVA 알림',body:'새 알림이 도착했습니다.',data:{}};try{if(e.data)p=e.data.json()}catch(_){}
  const data=p.data||{};await setBadge(data.badgeCount||0);
  const wins=await clients.matchAll({type:'window',includeUncontrolled:true});
  const visible=wins.find(c=>c.visibilityState==='visible');
  if(visible){visible.postMessage({type:'NOVA_PUSH_FOREGROUND',badgeCount:data.badgeCount||0});return}
  await self.registration.showNotification(p.title||'NOVA 알림',{body:p.body||'',icon:p.icon||ICON,badge:p.badge||BADGE,tag:p.tag||'nova',data,requireInteraction:!!p.requireInteraction,timestamp:p.timestamp||Date.now()});
})())});
self.addEventListener('notificationclick',e=>{e.notification.close();e.waitUntil((async()=>{
  const url=e.notification.data?.url||'./index.html';
  const wins=await clients.matchAll({type:'window',includeUncontrolled:true});
  for(const c of wins){if('navigate'in c){await c.navigate(url);await c.focus();return}}
  await clients.openWindow(url);
})())});
