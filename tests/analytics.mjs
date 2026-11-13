import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import assert from 'node:assert/strict';
const base = process.argv[2] || 'public';
const host = process.argv[3] || 'events.promedia.report';
const html = readFileSync(`${base}/analytics-frame.html`, 'utf8');
function run(choice, hostname = host) {
  const scripts = [];
  const context = {Date, location:{hostname}, localStorage:{getItem:()=>choice}, document:{documentElement:{dataset:{}},head:{appendChild:e=>scripts.push(e)},createElement:()=>({})}};
  context.window = context;
  runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
  return {context, scripts, calls:(context.dataLayer||[]).map(c=>Array.from(c))};
}
for (const choice of [null, 'denied']) {
  const off=run(choice);assert.equal(off.scripts.length,0);assert.equal(off.calls.length,0);
}
assert.equal(run('granted','preview.example.org').scripts.length,0);
const {context,scripts,calls}=run('granted');
assert.equal(scripts.length,1);assert.match(scripts[0].src,/G-D8TM22QR9R$/);
const consent=calls.find(c=>c[0]==='consent')[2];
assert.equal(consent.analytics_storage,'granted');
for(const k of ['ad_storage','ad_user_data','ad_personalization'])assert.equal(consent[k],'denied');
const config=calls.find(c=>c[0]==='config')[2];
assert.equal(config.send_page_view,false);assert.equal(config.cookie_domain,host);
assert.equal(config.cookie_prefix,'promedia');assert.equal(config.cookie_expires,86400);assert.equal(config.cookie_update,false);
assert.equal(config.allow_google_signals,false);assert.equal(config.allow_ad_personalization_signals,false);
const events=calls.filter(c=>c[0]==='event');assert.equal(events.length,1);assert.equal(events[0][1],'page_view');
assert.equal(events[0][2].page_location,`https://${host}/`);assert.equal(events[0][2].page_referrer,'');
assert(!/parent\.|top\.|location\.(href|hash|search)|sessionStorage/.test(html));
context.stopProMediaAnalytics();assert.equal(context['ga-disable-G-D8TM22QR9R'],true);
assert.equal(context.dataLayer.at(-1)[2].analytics_storage,'denied');

class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.nodes={};}
  appendChild(e){this.children.push(e);return e;}
  setAttribute(k,v){this.attrs[k]=v;}
  querySelector(s){return this.nodes[s]??=new Element('button');}
  focus(){}
  remove(){body.children=body.children.filter(e=>e!==this);}
}
let stored=null;const body=new Element('body'),settings=new Element('button'),listeners={};
const doc={body,cookie:'',getElementById:()=>settings,createElement:t=>new Element(t)};
const win={addEventListener:(type,fn)=>listeners[type]=fn};
runInNewContext(readFileSync(`${base}/analytics-consent.js`,'utf8'),{window:win,document:doc,location:{hostname:host},localStorage:{getItem:()=>stored,setItem:(k,v)=>stored=v}});
assert(!body.children.some(e=>e.tagName==='iframe'));
body.children.find(e=>e.tagName==='aside').querySelector('[data-analytics-deny]').onclick();
assert.equal(stored,'denied');assert.equal(body.children.length,0);
settings.onclick();body.children.find(e=>e.tagName==='aside').querySelector('[data-analytics-allow]').onclick();
const frame=body.children.find(e=>e.tagName==='iframe');assert(frame);assert.equal(frame.src,'/analytics-frame.html');
assert.equal(frame.referrerPolicy,'no-referrer');assert.equal(frame.attrs.sandbox,'allow-scripts allow-same-origin');
let stopped=false;frame.contentWindow={stopProMediaAnalytics:()=>stopped=true};
settings.onclick();body.children.find(e=>e.tagName==='aside').querySelector('[data-analytics-deny]').onclick();
assert(stopped);assert(!body.children.some(e=>e.tagName==='iframe'));
console.log(`PASS ${host}: consent off/on/withdrawal; one page_view; no private URLs or form fields; host cookies; no preview traffic.`);
