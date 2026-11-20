const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('reader/Reader.gs','utf8');
function setup(options={}) {
  let unzips=0;
  const requests=[],storage={}, record={digest_date:'2026-11-20',subject:'Daily subject',quality:'full',text_body:'Title\n\nTL;DR: Brief\n== Top stories ==\n* Headline\n  Summary\n  Source: https://example.com/story',recipient:'PRIVATE-INBOX',html_body:'<script>unsafe()</script>'};
  const properties={OWNER_EMAIL:'owner@example.com',GITHUB_TOKEN:'PRIVATE-TOKEN'};
  const artifacts=[{id:12,name:'digest-state-final-7-1',created_at:'2026-11-20T13:55:00Z',workflow_run:{id:7,head_branch:'main'}}, {id:11,name:'digest-state-prepared-7-1',created_at:'2026-11-20T13:54:00Z',workflow_run:{id:7,head_branch:'main'}}];
  const blob=value=>({getBytes:()=>Buffer.from(value),getName:()=> 'prepared.json',getDataAsString:()=>value,setContentType(){return this;}});
  const response=(code,data,headers={})=>({getResponseCode:()=>code,getContentText:()=>JSON.stringify(data),getAllHeaders:()=>headers,getBlob:()=>blob('zip')});
  const context=vm.createContext({console:{log(){}},PropertiesService:{getScriptProperties:()=>({getProperty:k=>properties[k]})},
    Session:{getActiveUser:()=>({getEmail:()=>options.identity===undefined?'owner@example.com':options.identity})},
    CacheService:{getUserCache:()=>({get:k=>storage[k],put:(k,v)=>{storage[k]=v;}})},
    Utilities:{newBlob:blob,unzip:()=>[blob((options.corrupt || (options.corruptFirst && ++unzips===1))?'not JSON':JSON.stringify(record))],formatDate:(date,zone,pattern)=>pattern==='yyyy-MM-dd'?'2026-11-20':'Nov 20, 2026 07:55'},
    HtmlService:{createHtmlOutputFromFile:()=>({setTitle(){return this;},addMetaTag(){return this;}}),createHtmlOutput:t=>({text:t})},
    UrlFetchApp:{fetch:(url,config)=>{
      requests.push({url,config});
      if(options.down)return response(503,{});
      if(url.includes('/actions/artifacts?'))return response(200,{artifacts});
      if(url.includes('/actions/runs/'))return response(200,{head_branch:'main',path:options.otherWorkflow?'.github/workflows/tests.yml':'.github/workflows/daily-digest.yml',repository:{full_name:'Nsher02/ai-daily-news-digest'}});
      if(url.endsWith('/zip'))return response(302,{}, {Location:options.badRedirect?'https://attacker.example/zip':'https://signed.blob.core.windows.net/zip?sig=private'});
      return response(200,{});
    }}
  });vm.runInContext(source,context);return {context,requests,storage,record,options,properties,artifacts};
}
for(const identity of ['','other@example.com']) {
  const s=setup({identity});assert.throws(()=>s.context.getReaderData(),/Access denied/);assert.equal(s.requests.length,0);assert.equal(s.context.doGet().text.startsWith('Access denied'),true);
}
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
const combined=setup();vm.runInContext(fs.readFileSync('monitoring/google_apps_script.gs','utf8'),combined.context);assert.equal(typeof combined.context.checkDigest,'function');assert.equal(typeof combined.context.inspectDigest,'function');assert.equal(typeof combined.context.doGet,'function');
const html=fs.readFileSync('reader/Index.html','utf8');assert.equal(/innerHTML|document\.write/.test(html),false);
new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
console.log('Private reader checks passed: owner gate, display-only projection, redirects, archive selection, cache, stale state, manifest, and client syntax. No network or mail.');
// Exercise the actual client renderer with malicious-looking source text.
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.handlers={};}
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
const links=nodes.filter(n=>n.tag==='a');assert.equal(links.length,1);assert.equal(links[0].rel,'noopener noreferrer');
assert.equal(links[0].href,'https://example.com/article');
elements.subject.textContent='';onFailure();assert.equal(elements.status.textContent,'Reader unavailable');
console.log('Client rendering checks passed: literal untrusted text, safe source links, and clear load failure.');
