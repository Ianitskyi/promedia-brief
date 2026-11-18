// BRIEF підключає спільну аналітику ПроМедіа; тест перевіряє адаптер analytics.js.
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';
const base=process.argv[2]||'.',host=process.argv[3]||'brief.promedia.report';
const SRC='https://news.promedia.report/js/promedia-analytics.js';
const loader=readFileSync(`${base}/analytics.js`,'utf8');

class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.attrs={};}
 appendChild(e){this.children.push(e);return e;}setAttribute(k,v){this.attrs[k]=v;}
}
function run(legacy){
 const head=new Element('head'),body=new Element('body'),settings=new Element('button');settings.id='analytics-settings';body.appendChild(settings);
 let stored=legacy,removed=false;const timers=[];
 const c={location:{hostname:host},document:{head,body,getElementById:id=>id==='analytics-settings'?settings:null,createElement:t=>new Element(t),
   querySelector:sel=>head.children.find(e=>sel.includes(e.src))||null},
  localStorage:{getItem:()=>stored,removeItem:()=>{removed=true;stored=null}},
  setInterval:f=>{timers.push(f);return timers.length},clearInterval:()=>{timers.length=0}};
 c.window=c;
 runInNewContext(loader,c);
 return {c,head,settings,timers,get removed(){return removed}};
}

// Підключає спільний скрипт рівно один раз.
let r=run(null);
assert.equal(r.head.children.length,1);assert.equal(r.head.children[0].src,SRC);assert.equal(r.head.children[0].async,true);
runInNewContext(loader,r.c);assert.equal(r.head.children.length,1,'No duplicate shared analytics script');
// Кнопка стає спільним перемикачем.
assert('data-pm-analytics-toggle' in r.settings.attrs);assert.equal(r.settings.textContent,'Вимкнути аналітику');

// Події до завантаження спільного скрипта чекають у черзі; дозволені лише події прослуховування без персональних даних.
const sent=[];
r.c.briefTrack('brief_play',{brief_edition:'2026-11-18',brief_place:'home',percent:0,email:'x@y.z'});
r.c.briefTrack('something_else',{});
r.c.ProMediaAnalytics={started:true,isEnabled:()=>true,optOut(){},track:(n,p)=>sent.push([n,p])};
r.timers.slice().forEach(f=>f());
assert.equal(sent.length,1);assert.equal(sent[0][0],'brief_play');
assert.deepEqual(Object.keys(sent[0][1]).sort(),['brief_edition','brief_place','percent']);

// Попереднє вимкнення переноситься в спільне налаштування.
r=run('denied');let optedOut=false;
assert.equal(r.settings.textContent,'Увімкнути аналітику');
r.c.ProMediaAnalytics={started:true,isEnabled:()=>true,optOut:()=>{optedOut=true},track(){}};
r.timers.slice().forEach(f=>f());assert(optedOut);assert(r.removed);

assert(!/googletagmanager|gtag\(|G-D8TM22QR9R|iframe/.test(loader),'GA4 is configured only in the shared script');
console.log(`PASS ${host}: shared ProMedia analytics, one script, queued allowed listening events only, legacy opt-out kept.`);
