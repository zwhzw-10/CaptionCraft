const NATIVE_HOST='com.captioncraft.assistant';
let nativePort=null,nativeConfig=null,nativeSequence=0,nativeLoading=null,nativeLastUsed=Date.now();
const nativePending=new Map();
function connectAssistant(){
 if(nativePort)return nativePort;
 const port=chrome.runtime.connectNative(NATIVE_HOST);nativePort=port;
 port.onMessage.addListener(message=>{const pending=nativePending.get(message.id);if(!pending)return;clearTimeout(pending.timer);nativePending.delete(message.id);pending.resolve(message);});
 port.onDisconnect.addListener(()=>{
  const detail=chrome.runtime.lastError?.message||'Assistant disconnected';
  if(nativePort===port){nativePort=null;nativeConfig=null;}
  for(const [id,pending] of nativePending){clearTimeout(pending.timer);pending.reject(new Error('assistantMissing: '+detail));nativePending.delete(id);}
 });
 return port;
}
function assistantCommand(type){
 return new Promise((resolve,reject)=>{
  const id=++nativeSequence;
  const timer=setTimeout(()=>{nativePending.delete(id);reject(new Error('assistantTimeout'));},12000);
  nativePending.set(id,{resolve,reject,timer});
  try{connectAssistant().postMessage({id,type});}catch(e){clearTimeout(timer);nativePending.delete(id);reject(e);}
 });
}
async function ensureAssistant(){
 nativeLastUsed=Date.now();
 if(nativeConfig)return nativeConfig;
 if(nativeLoading)return nativeLoading;
 nativeLoading=(async()=>{
  let result=await assistantCommand('ensure');const deadline=Date.now()+20*60*1000;
  while(result.state==='loading'){
   await chrome.runtime.sendMessage({type:'event',messageKey:'assistantLoading',active:false}).catch(()=>{});
   if(Date.now()>deadline)throw new Error('assistantTimeout');
   await new Promise(resolve=>setTimeout(resolve,1000));result=await assistantCommand('status');
  }
  if(result.state!=='ready')throw new Error('assistantError: '+(result.error||result.state));
  if(!/^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(result.endpoint)||!(/^[A-Za-z0-9_-]{32,128}$/.test(result.token)))throw new Error('Invalid assistant configuration');
  nativeConfig={ok:true,token:result.token,endpoint:result.endpoint};return nativeConfig;
 })();
 try{return await nativeLoading;}finally{nativeLoading=null;}
}
chrome.alarms.create('captioncraft-idle',{periodInMinutes:1});
chrome.alarms.onAlarm.addListener(alarm=>{
 if(alarm.name==='captioncraft-idle'&&!nativeLoading&&nativePort&&Date.now()-nativeLastUsed>5*60*1000){nativePort.disconnect();nativePort=null;nativeConfig=null;}
});
