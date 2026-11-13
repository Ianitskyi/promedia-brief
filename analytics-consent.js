(()=>{
 'use strict';
 const key='promedia.analytics.v1';
 let frame=null,panel=null;
 function choice(){try{return localStorage.getItem(key)}catch{return null}}
 function removeCookies(){
  for(const item of document.cookie.split(';')){
   const name=item.split('=')[0].trim();if(!/^promedia_ga(?:_|$)/.test(name))continue;
   document.cookie=name+'=; Max-Age=0; Path=/; SameSite=Lax; Secure';
   document.cookie=name+'=; Max-Age=0; Path=/; Domain='+location.hostname+'; SameSite=Lax; Secure';
  }
 }
 function sync(){
  if(choice()==='granted'){
   if(frame)return;
   frame=document.createElement('iframe');frame.src='/analytics-frame.html';frame.title='Статистика відвідувань';frame.hidden=true;
   frame.referrerPolicy='no-referrer';frame.setAttribute('sandbox','allow-scripts allow-same-origin');document.body.appendChild(frame);
  }else{
   if(frame){try{frame.contentWindow.stopProMediaAnalytics?.()}catch{}frame.remove();frame=null}
   removeCookies();
  }
 }
 function choose(value){
  try{localStorage.setItem(key,value)}catch{if(panel)panel.querySelector('[data-analytics-copy]').textContent='Браузер не дозволяє зберегти вибір. Аналітику не ввімкнено.';return}
  if(panel){panel.remove();panel=null}sync();
 }
 function show(){
  if(panel){panel.focus();return}
  panel=document.createElement('aside');panel.className='analytics-consent';panel.tabIndex=-1;
  panel.setAttribute('role','region');panel.setAttribute('aria-label','Статистика відвідувань');
  panel.innerHTML='<div><strong>Статистика відвідувань</strong><p data-analytics-copy>Дозволити Google Analytics для статистики відвідувань? Фіксуємо лише відвідування сервісу. Вміст форм та приватні посилання не передаємо. Cookie аналітики діють одну добу. Вибір можна змінити внизу сторінки.</p></div><div class="analytics-consent-actions"><button type="button" data-analytics-allow>Дозволити аналітику</button><button type="button" data-analytics-deny>Без аналітики</button></div>';
  panel.querySelector('[data-analytics-allow]').onclick=()=>choose('granted');
  panel.querySelector('[data-analytics-deny]').onclick=()=>choose('denied');document.body.appendChild(panel);
 }
 let settings=document.getElementById('analytics-settings');
 if(!settings){const wrap=document.createElement('div');wrap.className='analytics-settings';settings=document.createElement('button');settings.id='analytics-settings';settings.type='button';settings.textContent='Налаштування аналітики';wrap.appendChild(settings);document.body.appendChild(wrap)}
 settings.onclick=show;
 window.addEventListener('storage',event=>{if(event.key===key)sync()});sync();if(!choice())show();
})();
