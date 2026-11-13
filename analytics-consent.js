(()=>{
 'use strict';
 const key='promedia.analytics.v1';
 let frame=null, memoryChoice;
 function choice(){if(memoryChoice!==undefined)return memoryChoice;try{return localStorage.getItem(key)}catch{return null}}
 function removeCookies(){
  for(const item of document.cookie.split(';')){
   const name=item.split('=')[0].trim();if(!/^promedia_ga(?:_|$)/.test(name))continue;
   document.cookie=name+'=; Max-Age=0; Path=/; SameSite=Lax; Secure';
   document.cookie=name+'=; Max-Age=0; Path=/; Domain='+location.hostname+'; SameSite=Lax; Secure';
  }
 }
 let settings=document.getElementById('analytics-settings');
 if(!settings){
  const wrap=document.createElement('div');wrap.className='analytics-settings';
  settings=document.createElement('button');settings.id='analytics-settings';settings.type='button';
  wrap.appendChild(settings);document.body.appendChild(wrap);
 }
 function sync(){
  const active=choice()!=='denied';
  if(active){
   if(!frame){
    frame=document.getElementById('pm-analytics-frame');
    if(!frame){frame=document.createElement('iframe');frame.id='pm-analytics-frame';frame.src='/analytics-frame-v2.html';frame.title='Статистика відвідувань';frame.hidden=true;
     frame.referrerPolicy='no-referrer';frame.setAttribute('sandbox','allow-scripts allow-same-origin');document.body.appendChild(frame)}
   }
  }else{
   if(frame){try{frame.contentWindow.stopProMediaAnalytics?.()}catch{}frame.remove();frame=null}
   removeCookies();
  }
  settings.textContent=active?'Вимкнути аналітику':'Увімкнути аналітику';
  settings.setAttribute('aria-pressed',String(active));
 }
 settings.onclick=()=>{
  memoryChoice=choice()==='denied'?'granted':'denied';
  try{localStorage.setItem(key,memoryChoice)}catch{}
  sync();
 };
 window.addEventListener('storage',event=>{if(event.key===key){memoryChoice=undefined;sync()}});
 sync();
})();
