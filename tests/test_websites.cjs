const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
let listener,url='https://example.com/live',live=false,calls=[];
const origin='chrome-extension://unit/';
const context={importScripts(){},ensureAssistant:async()=>({ok:true}),chrome:{
 runtime:{getURL:p=>origin+p,getContexts:async()=>[],onMessage:{addListener:f=>listener=f},sendMessage:async m=>{calls.push(m.type);return {ok:true,active:false};}},
 offscreen:{hasDocument:async()=>true},action:{setBadgeText:async()=>{},setBadgeBackgroundColor:async()=>{}},
 tabs:{query:async()=>[{id:42,url}],sendMessage:async()=>{},onRemoved:{addListener(){}},onUpdated:{addListener(){}}},
 scripting:{executeScript:async o=>{calls.push(o.files?'inject':'video-info');return o.func?[{result:{time:1,isLive:live}}]:[];}},
 tabCapture:{getMediaStreamId:async()=>{calls.push('capture');return 'stream';}},windows:{create:async o=>o}
}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../extension/background.js'),'utf8'),context);
const command=(type,sender={url:origin+'popup.html'})=>new Promise(resolve=>listener({target:'background',type,settings:{source:'en',display:'bilingual'}},sender,resolve));
(async()=>{
 assert.equal((await command('start')).ok,true);assert(calls.indexOf('prepare-live')<calls.indexOf('capture'));
 assert.equal((await command('prepare')).ok,false,'generic synchronous mode blocked');
 url='chrome://settings';assert.equal((await command('start')).ok,false);
 url='https://youtube.com/watch?v=abcdefghijk';live=true;assert.equal((await command('prepare')).ok,false,'live page cannot enter preparation mode');
 live=false;assert.equal((await command('prepare')).ok,true);
 const window=await command('caption-window');assert.equal(window.type,'popup');assert(window.url.endsWith('caption-window.html'));
 const denied=await command('caption-window',{tab:{id:42},url:'https://example.com/'});assert.equal(denied.ok,false);
 assert.equal((await command('local-config',{tab:{id:42},url:'https://example.com/'})).ok,false);
 console.log('PASS generic live tab, prepare-before-capture ordering, restricted pages, YouTube live detection, synchronous regression and isolated caption window.');
})().catch(e=>{console.error(e);process.exit(1)});
