import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';
const base=process.argv[2]||'public',host=process.argv[3]||'events.promedia.report';
const key=process.argv[4]||'promedia.analytics.v1',prefix=process.argv[5]||'promedia';
const html=readFileSync(`${base}/analytics-frame-v2.html`,'utf8');
function run(choice,hostname=host){
 const scripts=[];
 const c={Date,location:{hostname},localStorage:{getItem:k=>{assert.equal(k,key);return choice}},document:{documentElement:{dataset:{}},head:{appendChild:e=>scripts.push(e)},createElement:()=>({})}};c.window=c;
 runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],c);
 return {c,scripts,calls:(c.dataLayer||[]).map(a=>Array.from(a))};
}
for(const value of [null,'granted']){
 const {c,scripts,calls}=run(value);assert.equal(scripts.length,1);assert.match(scripts[0].src,/G-D8TM22QR9R$/);
 const config=calls.find(a=>a[0]==='config')[2];assert.equal(config.send_page_view,false);assert.equal(config.cookie_domain,host);assert.equal(config.cookie_prefix,prefix);assert.equal(config.cookie_expires,86400);assert.equal(config.cookie_update,false);assert.equal(config.allow_google_signals,false);assert.equal(config.allow_ad_personalization_signals,false);
 const events=calls.filter(a=>a[0]==='event');assert.equal(events.length,1);assert.equal(events[0][1],'page_view');assert.equal(events[0][2].page_location,`https://${host}/`);assert.equal(events[0][2].page_referrer,'');
 const consent=calls.find(a=>a[0]==='consent')[2];for(const p of ['ad_storage','ad_user_data','ad_personalization'])assert.equal(consent[p],'denied');
 c.stopProMediaAnalytics();assert.equal(c['ga-disable-G-D8TM22QR9R'],true);
}
assert.equal(run('denied').scripts.length,0);assert.equal(run('denied').calls.length,0);
assert.equal(run(null,'preview.example.org').scripts.length,0);
assert(!/parent\.|top\.|location\.(href|hash|search)|sessionStorage/.test(html));
class Element{
 constructor(tag){assert(!['aside','dialog'].includes(tag),'Analytics must not create a prompt');this.tagName=tag;this.children=[];this.attrs={};}
 appendChild(e){this.children.push(e);return e;}setAttribute(k,v){this.attrs[k]=v;}
 remove(){body.children=body.children.filter(e=>e!==this);}
}
let stored=null,writes=0;const body=new Element('body'),settings=new Element('button');settings.id='analytics-settings';body.appendChild(settings);
const doc={body,cookie:'',getElementById:id=>[settings,...body.children].find(e=>e.id===id),createElement:t=>new Element(t)};
const context={window:{addEventListener(){}},document:doc,location:{hostname:host},localStorage:{getItem:k=>{assert.equal(k,key);return stored},setItem:(k,v)=>{assert.equal(k,key);writes++;stored=v}}};
const loader=readFileSync(`${base}/analytics.js`,'utf8');runInNewContext(loader,context);
assert.equal(writes,0,'Do not manufacture a stored consent choice');assert.equal(body.children.filter(e=>e.tagName==='iframe').length,1);
assert.equal(settings.textContent,'Вимкнути аналітику');const frame=body.children.find(e=>e.tagName==='iframe');assert.equal(frame.src,'/analytics-frame-v2.html');assert.equal(frame.referrerPolicy,'no-referrer');assert.equal(frame.attrs.sandbox,'allow-scripts allow-same-origin');
let stopped=false;frame.contentWindow={stopProMediaAnalytics:()=>stopped=true};settings.onclick();assert(stopped);assert.equal(stored,'denied');assert(!body.children.some(e=>e.tagName==='iframe'));assert.equal(settings.textContent,'Увімкнути аналітику');
runInNewContext(loader,context);assert(!body.children.some(e=>e.tagName==='iframe'),'Preserve a previous opt-out after reload');
settings.onclick();assert.equal(stored,'granted');assert.equal(body.children.filter(e=>e.tagName==='iframe').length,1);
runInNewContext(loader,context);assert.equal(body.children.filter(e=>e.tagName==='iframe').length,1,'Prevent duplicate page_view frames');
assert(!/show\(|Дозволити Google Analytics|analytics-consent-actions/.test(loader));
console.log(`PASS ${host}: automatic start without prompts; no fabricated consent; persistent opt-out; one frame/event; no private URLs, fields or advertising signals.`);
