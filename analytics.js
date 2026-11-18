/* Аналітика BRIEF → спільний скрипт ПроМедіа (news.promedia.report/js/promedia-analytics.js).
 * Один GA4-тег і одне cookie на всі *.promedia.report: людина, яка перейшла
 * з новин у BRIEF, рахується як один користувач, а джерело переходу не губиться.
 * Вимкнення аналітики діє на всіх сайтах ПроМедіа. Попереднє вимкнення (localStorage
 * 'promedia.analytics.v1' = 'denied') переноситься у спільне налаштування.
 * window.briefTrack надсилає лише brief_play / brief_progress / brief_complete
 * з датою випуску, місцем відтворення й відсотком — без персональних даних. */
(()=>{
 'use strict';
 const SRC='https://news.promedia.report/js/promedia-analytics.js';
 const LEGACY_KEY='promedia.analytics.v1';
 const ALLOWED={brief_play:1,brief_progress:1,brief_complete:1};
 const LABEL_ON='Вимкнути аналітику', LABEL_OFF='Увімкнути аналітику';

 if(!document.querySelector('script[src="'+SRC+'"]')){
  const s=document.createElement('script');s.async=true;s.src=SRC;document.head.appendChild(s);
 }

 // Кнопка в підвалі BRIEF стає перемикачем спільної аналітики.
 let settings=document.getElementById('analytics-settings');
 if(!settings){
  const wrap=document.createElement('div');wrap.className='analytics-settings';
  settings=document.createElement('button');settings.id='analytics-settings';settings.type='button';
  wrap.appendChild(settings);document.body.appendChild(wrap);
 }
 settings.setAttribute('data-pm-analytics-toggle','');
 settings.setAttribute('data-label-on',LABEL_ON);
 settings.setAttribute('data-label-off',LABEL_OFF);
 let legacyDenied=false;
 try{legacyDenied=localStorage.getItem(LEGACY_KEY)==='denied'}catch{}
 settings.textContent=legacyDenied?LABEL_OFF:LABEL_ON;
 settings.setAttribute('aria-pressed',String(!legacyDenied));

 const queue=[];
 const api=()=>window.ProMediaAnalytics&&window.ProMediaAnalytics.started?window.ProMediaAnalytics:null;
 function clean(name,p){
  p=p||{};
  return {brief_edition:String(p.brief_edition||'').slice(0,20),brief_place:String(p.brief_place||'').slice(0,30),percent:Number(p.percent)||0};
 }
 window.briefTrack=(name,params)=>{
  if(!ALLOWED[name])return;
  const a=api();
  if(a)a.track(name,clean(name,params));
  else if(queue.length<20)queue.push([name,params]);
 };

 let tries=0;
 const timer=setInterval(()=>{
  const a=api();
  if(!a){if(++tries>60)clearInterval(timer);return}
  clearInterval(timer);
  if(legacyDenied){
   if(a.isEnabled())a.optOut();
   try{localStorage.removeItem(LEGACY_KEY)}catch{}
  }
  queue.splice(0).forEach(([n,p])=>window.briefTrack(n,p));
 },250);
})();
