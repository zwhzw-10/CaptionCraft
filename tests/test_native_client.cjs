const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
let ports=[],alarm,missing=false;
const sandbox={setTimeout,clearTimeout,Date,Map,Promise,chrome:{
 alarms:{create(){},onAlarm:{addListener:f=>alarm=f}},runtime:{sendMessage:async()=>{},connectNative:name=>{
  assert.equal(name,'com.captioncraft.assistant');let receive,disconnect;
  const port={onMessage:{addListener:f=>receive=f},onDisconnect:{addListener:f=>disconnect=f},
   postMessage:m=>queueMicrotask(()=>{if(missing){sandbox.chrome.runtime.lastError={message:'not found'};disconnect();delete sandbox.chrome.runtime.lastError;}else receive({id:m.id,state:'ready',token:'t'.repeat(43),endpoint:'http://127.0.0.1:41234'});}),disconnect:()=>disconnect()};ports.push(port);return port;
 }}}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../extension/native-client.js'),'utf8'),sandbox);
(async()=>{
 const [a,b]=await Promise.all([sandbox.ensureAssistant(),sandbox.ensureAssistant()]);assert.equal(a.endpoint,b.endpoint);assert.equal(ports.length,1);
 ports[0].disconnect();missing=true;await assert.rejects(sandbox.ensureAssistant(),/assistantMissing/);
 missing=false;assert.equal((await sandbox.ensureAssistant()).ok,true);
 vm.runInNewContext('nativeLastUsed=Date.now()-6*60*1000',sandbox);alarm({name:'captioncraft-idle'});
 vm.runInNewContext('if(nativePort!==null||nativeConfig!==null)throw new Error("Idle cleanup failed")',sandbox);
 console.log('PASS: native connection, startup coalescing, missing-host error, retry, idle cleanup');
})().catch(e=>{console.error(e);process.exit(1)});
