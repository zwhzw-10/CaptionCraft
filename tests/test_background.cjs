const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
let listener;
const url='chrome-extension://test/offscreen.html';
const sandbox={importScripts(){},ensureAssistant:async()=>({ok:true,token:'paired-token'}),chrome:{
 runtime:{getURL:()=>url,getContexts:async()=>[],onMessage:{addListener:f=>listener=f}},
 storage:{local:{get:async()=>({localToken:'paired-token'})}},
 offscreen:{},tabs:{onRemoved:{addListener(){}},onUpdated:{addListener(){}}}
}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../extension/background.js'),'utf8'),sandbox);
const command=(type,sender)=>new Promise(r=>listener({target:'background',type},sender,r));
(async()=>{
 const allowed=await command('local-config',{url});assert.equal(allowed.token,'paired-token');
 const blocked=await command('local-config',{url:'https://youtube.com/',tab:{id:1}});assert.equal(blocked.ok,false);assert.equal(blocked.token,undefined);
 const status=await command('status',{});assert.equal(status.active,false);
 console.log('PASS: background pairing relay, sender restriction, pre-Chrome-150 offscreen detection');
})().catch(e=>{console.error(e);process.exit(1)});
