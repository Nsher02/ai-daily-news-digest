const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('reader/Reader.gs','utf8');
function setup(options={}) {
  let unzips=0, cacheReads=0;
  const templates=[], logs=[];
  const requests=[],storage={}, record={digest_date:'2026-11-20',subject:'Daily subject',quality:'full',text_body:'Title\n\nTL;DR: Brief\n== Top stories ==\n* Headline\n  Summary\n  Source: https://example.com/story',recipient:'PRIVATE-INBOX',html_body:'<script>unsafe()</script>'};
  const properties={OWNER_EMAIL:'owner@example.com',GITHUB_TOKEN:'PRIVATE-TOKEN'};
  const artifacts=[{id:12,name:'digest-state-final-7-1',created_at:'2026-11-20T13:55:00Z',workflow_run:{id:7,head_branch:'main'}}, {id:11,name:'digest-state-prepared-7-1',created_at:'2026-11-20T13:54:00Z',workflow_run:{id:7,head_branch:'main'}}];
  const blob=value=>({getBytes:()=>Buffer.from(value),getName:()=> 'prepared.json',getDataAsString:()=>value,setContentType(){return this;}});
  const response=(code,data,headers={})=>({getResponseCode:()=>code,getContentText:()=>JSON.stringify(data),getAllHeaders:()=>headers,getBlob:()=>blob('zip')});
  const context=vm.createContext({console:{log(value){logs.push(value);},error(value){logs.push(value);}},PropertiesService:{getScriptProperties:()=>({getProperty:k=>properties[k]})},
    Session:{getActiveUser:()=>({getEmail:()=>options.identity===undefined?'owner@example.com':options.identity})},
    CacheService:{getUserCache:()=>({get:k=>{cacheReads++;return storage[k];},put:(k,v)=>{storage[k]=v;}})},
    Utilities:{newBlob:blob,unzip:()=>[blob((options.corrupt || (options.corruptFirst && ++unzips===1))?'not JSON':JSON.stringify(record))],formatDate:(date,zone,pattern)=>pattern==='yyyy-MM-dd'?'2026-11-20':'Nov 20, 2026 07:55'},
    HtmlService:{createHtmlOutputFromFile:name=>{templates.push(name);if(options.missingTemplate)throw new Error('missing Index');return {template:name,setTitle(){return this;},addMetaTag(){return this;}};},createHtmlOutput:t=>({text:t})},
    UrlFetchApp:{fetch:(url,config)=>{
      requests.push({url,config});
      if(options.down)return response(503,{});
      if(url.includes('/actions/artifacts?'))return response(200,{artifacts});
      if(url.includes('/actions/runs/'))return response(200,{head_branch:'main',path:options.otherWorkflow?'.github/workflows/tests.yml':'.github/workflows/daily-digest.yml',repository:{full_name:'Nsher02/ai-daily-news-digest'}});
      if(url.endsWith('/zip'))return response(302,{}, {Location:options.badRedirect?'https://attacker.example/zip':'https://signed.blob.core.windows.net/zip?sig=private'});
      return response(200,{});
    }}
  });vm.runInContext(source,context);return {context,requests,storage,record,options,properties,artifacts,templates,logs,cacheReads:()=>cacheReads};
}
for(const identity of ['','other@example.com']) {
  const s=setup({identity});assert.throws(()=>s.context.getReaderData(),/Access denied/);assert.equal(s.requests.length,0);assert.equal(s.context.doGet().text.startsWith('Access denied'),true);
}
assert.match(setup({missingTemplate:true}).context.doGet().text,/HTML file named Index/);
let s=setup(),data=s.context.getReaderData();assert.equal(data.edition.id,'12');assert.equal(data.editions.length,1);assert.equal(data.stale,false);
assert.equal(JSON.stringify(data).includes('PRIVATE-INBOX'),false);assert.equal(JSON.stringify(data).includes('PRIVATE-TOKEN'),false);assert.equal(JSON.stringify(data).includes('<script>'),false);
const download=s.requests.find(r=>r.url.includes('blob.core.windows.net'));assert.equal(download.config.headers,undefined);assert.equal(download.config.followRedirects,false);
s.options.down=true;assert.equal(s.context.getReaderData().cached,true);
s=setup({down:true});assert.throws(()=>s.context.getReaderData(),/temporarily unavailable/);
s=setup({corruptFirst:true});s.artifacts.push({id:10,name:'digest-state-final-6-1',created_at:'2026-11-19T13:55:00Z',workflow_run:{id:6,head_branch:'main'}});assert.equal(s.context.getReaderData().fallback,true);
for(const option of ['badRedirect','otherWorkflow','corrupt']) {s=setup({[option]:true});assert.throws(()=>s.context.getReaderData());assert.equal(s.requests.some(r=>r.url.includes('attacker.example')),false);}
s=setup();assert.throws(()=>s.context.getReaderData('../../evil'),/Invalid edition/);assert.equal(s.requests.length,0);
s=setup();s.record.digest_date='2026-11-19';assert.equal(s.context.getReaderData().stale,true);
s=setup();s.artifacts[0].expired=true;assert.equal(s.context.getReaderData().edition.id,'11');
s=setup();s.artifacts[0].workflow_run.head_branch='other';assert.equal(s.context.getReaderData().edition.id,'11');
s=setup();s.context.getReaderData();s.context.getReaderData('12');assert.ok(s.storage['last-reader-edition']);assert.ok(s.storage['reader-edition-12']);
const manifest=JSON.parse(fs.readFileSync('reader/appsscript.json','utf8'));
assert.equal(manifest.webapp.access,'MYSELF');assert.equal(manifest.webapp.executeAs,'USER_DEPLOYING');assert.equal(manifest.oauthScopes.includes('https://www.googleapis.com/auth/script.send_mail'),true);assert.equal(manifest.oauthScopes.some(x=>/auth\/(?:gmail|drive)/.test(x)),false);
const combined=setup();vm.runInContext(fs.readFileSync('reader/Monitor.gs','utf8'),combined.context);assert.equal(typeof combined.context.checkDigest_,'function');assert.equal(typeof combined.context.inspectDigestSetup_,'function');assert.equal(typeof combined.context.doGet,'function');
const html=fs.readFileSync('reader/Index.html','utf8');assert.equal(/innerHTML|document\.write/.test(html),false);
new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
console.log('Private reader checks passed: owner gate, display-only projection, redirects, archive selection, cache, stale state, manifest, and client syntax. No network or mail.');
// Exercise the actual client renderer with malicious-looking source text.
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.handlers={};}
  querySelector(selector){for(const child of this.children){if(selector.startsWith('.')?(child.className||'').split(' ').includes(selector.slice(1)):child.tag===selector)return child;const match=child.querySelector(selector);if(match)return match;}return null;}
  appendChild(node){this.children.push(node);return node;}
  replaceChildren(){this.children=[];}
  addEventListener(name,fn){this.handlers[name]=fn;}
}
const elements=Object.fromEntries(['content','subject','status','notice','editions','refresh'].map(id=>[id,new Element('div')]));
let onFailure;
const client=vm.createContext({URL,document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag)},google:{script:{run:{withSuccessHandler(){return this;},withFailureHandler(fn){onFailure=fn;return this;},getReaderData(){}}}}});
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],client);
client.render({edition:{id:'1',date:'2026-11-20',quality:'full',subject:'<script>attack()</script>',text:'Title\n* <img onerror=attack()>\n  <script>attack()</script>\n  Unsafe: javascript:attack()\n  Source: https://example.com/article'},editions:[{id:'1',label:'Today'}],stale:false,cached:false,fallback:false});
const descendants=node=>[node,...node.children.flatMap(descendants)];
const nodes=descendants(elements.content);
assert.equal(elements.subject.textContent,'<script>attack()</script>');
assert.equal(nodes.some(n=>n.tag==='img'||n.tag==='script'),false);
const links=nodes.filter(n=>n.tag==='a');assert.equal(links.length,2);assert.equal(links[0].rel,'noopener noreferrer');
assert.equal(links[0].href,'https://example.com/article');
assert.equal(links[1].href,'https://example.com/article');
assert.equal(links[0].textContent,'<img onerror=attack()>');
elements.subject.textContent='';onFailure();assert.equal(elements.status.textContent,'Reader unavailable');
console.log('Client rendering checks passed: literal untrusted text, safe source links, and clear load failure.');

// Public deployment safety: inspect the whole shared-project callable surface.
const standaloneMonitor=fs.readFileSync('monitoring/google_apps_script.gs','utf8');
const sharedMonitor=fs.readFileSync('reader/Monitor.gs','utf8');
const stripHeader=text=>text.slice(text.indexOf('const DIGEST_REPOSITORY'));
assert.equal(stripHeader(sharedMonitor),stripHeader(standaloneMonitor)
  .replace('function inspectDigest() {','function inspectDigestSetup_() {')
  .replace('function checkDigest() {','function checkDigest_() {'));
const publicNames=Object.keys(combined.context).filter(name=>typeof combined.context[name]==='function'&&!name.endsWith('_')).sort();
assert.deepEqual(publicNames,['doGet','getReaderData','inspectReader']);
assert.equal(combined.context.checkDigest,undefined);assert.equal(combined.context.inspectDigest,undefined);
for(const identity of ['', 'other@example.com']) {
  const denied=setup({identity});
  vm.runInContext(sharedMonitor,denied.context);
  const before=JSON.stringify(denied.properties);
  denied.storage['last-reader-edition']=JSON.stringify({edition:denied.record});
  assert.equal(denied.context.doGet({parameter:{view:'safari-test'}}).template,'SafariTest');
  assert.match(denied.context.doGet().text,/Access denied/);
  assert.match(denied.context.doGet({parameter:{view:'Index',OWNER_EMAIL:identity}}).text,/Access denied/);
  assert.throws(()=>denied.context.getReaderData(),/Access denied/);
  assert.throws(()=>denied.context.getReaderData({owner:'owner@example.com',triggerUid:'forged'}),/Access denied/);
  assert.throws(()=>denied.context.inspectReader(),/Access denied/);
  assert.equal(denied.requests.length,0);assert.equal(denied.cacheReads(),0);
  assert.equal(JSON.stringify(denied.properties),before);assert.equal(denied.logs.length,0);
}
const testHtml=fs.readFileSync('reader/SafariTest.html','utf8');
assert.match(testHtml,/Digest login test/);
assert.equal(/<script\b|<form\b|<iframe\b|<img\b|\bsrc\s*=|google\.script|https?:\/\//i.test(testHtml),false);
assert.match(testHtml,/<input[^>]*type="password"[^>]*disabled/);
assert.match(testHtml,/<button[^>]*disabled/);
assert.equal(/GITHUB_TOKEN|OWNER_EMAIL|ALERT_EMAIL/.test(testHtml),false);
assert.equal(setup().context.doGet().template,'Index');
console.log('Shared-project safeguards passed: private monitor handlers, unchanged monitor logic, static Safari route, and no anonymous data/cache/network/state access.');
