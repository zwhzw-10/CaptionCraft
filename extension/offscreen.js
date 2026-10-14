let stream, context, source, recorder, mute, controller;
let tabId = null, active = false, generation = 0, pending = null, processing = false;
let message = '尚未开启', sequence = 0;
let mode = 'live', preparationTimer;
let offset = 0, preparation = null, captionSettings={source:'auto',target:'zh',display:'original',preferExisting:true}, messageKey='idle';

const captions = new LiveCaptionState();
let liveSession=null,liveEngine='whisper',liveSetup=null,translationTimer,translationPollTimer,translationPosting=false;
let translationValue=null,translationInfo=null,translationError=null,frameSequence=0,skipped=0,inferenceMs=0,queueSeconds=0;
let lastTranslationAt=0,lastPostedRevision=-1,lastCaption=null,resetSerial=Promise.resolve();
function liveMetrics(){return {engine:liveEngine,inferenceMs,queueSeconds,skipped,translationState:translationInfo?.state||'idle',translationDownloadMB:translationInfo?.downloadMB,translationDetail:translationInfo?.detail,translationError};}
function captionView(){
 const latest=captions.latest;if(!latest)return {original:'',translation:'',display:captionSettings.display,final:false,revision:0};
 const matching=translationValue?.revision===latest.revision && translationValue?.session===liveSession;
 return {original:latest.text,translation:matching?translationValue.translation:'',display:captionSettings.display,final:latest.final,revision:latest.revision,translationPending:captionSettings.display!=='original'&&!matching};
}
async function emitLive(){lastCaption=captionView();return emit({liveCaption:lastCaption,metrics:liveMetrics()});}
function scheduleTranslation(){
 if(captionSettings.display==='original'||!captions.latest||!active)return;
 if(captions.latest.revision===lastPostedRevision)return;
 if(translationTimer)return;
 const delay=Math.max(0,1200-(performance.now()-lastTranslationAt));
 const epoch=generation;
 translationTimer=setTimeout(async()=>{
  translationTimer=null;if(!active||generation!==epoch||translationPosting)return;
  const latest=captions.latest;if(!latest||latest.revision===lastPostedRevision)return;
  translationPosting=true;lastTranslationAt=performance.now();lastPostedRevision=latest.revision;
  try{await request('/live/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session:liveSession,text:latest.text,revision:latest.revision,language:latest.language||captionSettings.source})});}
  catch(e){if(generation===epoch){translationError=e.message;await emitLive();}}
  finally{translationPosting=false;if(generation===epoch)scheduleTranslation();}
 },delay);
}
async function pollTranslation(epoch){
 if(!active||epoch!==generation||captionSettings.display==='original')return;
 try{
  const result=await request('/live/translation',{headers:{'X-Live-Session':liveSession}});
  if(!active||epoch!==generation)return;
  translationInfo=result;
  if(result.state==='ready'&&result.session===liveSession&&result.revision===captions.latest?.revision){translationValue=result;translationError=null;await emitLive();}
  if(result.state==='error'){translationError=result.error;await emitLive();}
 }catch(e){if(epoch===generation){translationError=e.message;await emitLive();}}
 if(active&&epoch===generation)translationPollTimer=setTimeout(()=>pollTranslation(epoch),700);
}
async function prepareLive(m){
 await stop();tabId=m.tabId;captionSettings=m.settings||captionSettings;mode='live-setup';liveSetup=null;
 const epoch=generation;
 let state=await request('/live/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(captionSettings)});
 if(epoch!==generation)throw new Error('Live setup cancelled');
 liveSession=state.session;
 while(state.state==='loading'){
  if(epoch!==generation)throw new Error('Live setup cancelled');
  liveSetup=state;messageKey='liveModelLoading';await emit({liveSetup});
  await new Promise(r=>setTimeout(r,700));state=await request('/live/status');
 }
 if(epoch!==generation)throw new Error('Live setup cancelled');
 if(state.state!=='ready')throw new Error(state.error||'Live recognizer not ready');
 liveSession=state.session;liveEngine=state.engine;mode='live';liveSetup=null;return {ok:true,engine:liveEngine};
}

async function emit(extra = {}) {
  return chrome.runtime.sendMessage({target: 'background', type: 'event', tabId, active, message, messageKey, preparation, ...extra}).catch(() => {});
}
async function request(path, options = {}) {
  // Offscreen documents only expose chrome.runtime, not chrome.storage.
  const saved=await chrome.runtime.sendMessage({target:'background',type:'local-config'});
  if (saved?.ok === false) throw new Error(saved.error || 'Cannot read local pairing settings');
  const localToken=saved?.token;
  if (!localToken || !saved.endpoint) throw new Error('assistantMissing');
  const response = await fetch(saved.endpoint + path, {...options, headers: {...options.headers, 'X-Local-Token': localToken}, signal: options.signal || AbortSignal.timeout(8000)});
  const data = await response.json();
  if (!response.ok) { const error = new Error(data.error || `本地服务错误 ${response.status}`); error.status = response.status; throw error; }
  return data;
}
async function stop() {
  clearTimeout(preparationTimer);clearTimeout(translationTimer);clearTimeout(translationPollTimer);translationTimer=null;
  if(liveSession)request('/live/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session:liveSession})}).catch(()=>{});
  liveSession=null;liveSetup=null;translationValue=translationInfo=translationError=lastCaption=null;
  if (mode === 'preparing' || mode === 'partial-error') await request('/prepare/cancel', {method: 'POST'}).catch(() => {});
  mode = 'live';
  generation++;
  active = false;
  pending = null;
  captions.reset();
  controller?.abort();
  recorder?.port.postMessage({type: 'reset', paused: true, generation});
  stream?.getTracks().forEach(t => t.stop());
  recorder?.disconnect(); source?.disconnect(); mute?.disconnect();
  await context?.close().catch(() => {});
  stream = context = source = recorder = mute = null;
  message = 'Stopped'; messageKey='stopped'; preparation=null;
  await emit({text: '', stopped: true});
  tabId = null;
}
async function prepare(m) {
  await stop(); tabId = m.tabId; mode = 'preparing'; active = true; captionSettings=m.settings||captionSettings; messageKey='gettingAudio';
  message = '正在获取音频，生成完成后再播放';
  await emit({text: ''});
  try {
    if (!m.alreadyStarted) await request('/prepare', {method: 'POST', body: JSON.stringify({url:m.url,settings:captionSettings,position:m.position||0}), headers: {'Content-Type': 'application/json'}});
    const epoch = generation; let lastRevision=-1;
    async function poll() {
      try {
        const state = await request('/prepare/status');
        if (!active || epoch !== generation) return;
        preparation=state;messageKey=state.messageKey||'gettingAudio';message=messageKey;
        if(state.revision!==lastRevision){
          lastRevision=state.revision;
          if(state.cues?.length || state.readyRanges?.length) await emit({prepared:{videoId:state.videoId,cues:state.cues||[],offset,readyRanges:state.readyRanges||[],translationRanges:state.translationRanges||[],complete:!!state.complete,failed:state.state==='error',display:state.display||captionSettings.display}});
        }
        if(state.state==='error'||state.state==='cancelled'){
          if(state.cues?.length){mode='partial-error';messageKey='partialError';await emit({error:state.error});return;}
          throw new Error(state.error||state.messageKey);
        }
        if(state.state==='ready'){mode='prepared';await emit();return;}
        await emit(); preparationTimer = setTimeout(poll, 1500);
      } catch (e) {
        if (epoch !== generation) return;
        await stop(); message=e.message;messageKey='error';await emit({error:e.message});
      }
    }
    await poll();
    return {ok: true};
  } catch (e) { await stop(); throw e; }
}
async function drain() {
 if(processing)return;processing=true;
 try{
  while(pending&&active){
   const frame=pending;pending=null;const current=generation;
   if(liveEngine==='whisper'&&frame.end-frame.start<1.2)continue;
   const settings={...captionSettings,display:'original',session:liveSession,start:frame.start,end:frame.end,sequence:frameSequence++};
   const session=liveSession;controller=new AbortController();
   try{
    const wait=(performance.now()-frame.received)/1000;
    const result=await request(liveEngine==='sherpa'?'/live/audio':'/transcribe',{method:'POST',body:frame.samples.buffer,
     headers:{'Content-Type':'application/octet-stream','X-Caption-Options':JSON.stringify(settings),'X-Live-Session':session},signal:AbortSignal.any([controller.signal,AbortSignal.timeout(30000)])});
    if(!active||current!==generation)continue;
    inferenceMs=Math.round(result.seconds*1000);queueSeconds=Number(wait.toFixed(2));
    const stale=(performance.now()-frame.received)/1000>6;
    if(stale){skipped++;messageKey='liveLag';await emit({metrics:liveMetrics()});continue;}
    result.engine=liveEngine;
    const latest=captions.update(result,frame);
    messageKey=wait>1||result.gap?'liveLag':'liveActive';
    if(latest){await emitLive();scheduleTranslation();}else await emit({metrics:liveMetrics()});
   }catch(e){
    if(!active||current!==generation)continue;
    if(e.status===429){skipped++;messageKey='liveLag';await emit({metrics:liveMetrics()});continue;}
    const detail=e.message;await stop();messageKey='error';await emit({error:detail});break;
   }
  }
 }finally{processing=false;}
}
async function start(m){
 if(!liveSession)throw new Error('Live engine has not been prepared');
 tabId=m.tabId;mode='live';captionSettings=m.settings||captionSettings;messageKey='liveActive';
 try{
  stream=await navigator.mediaDevices.getUserMedia({audio:{mandatory:{chromeMediaSource:'tab',chromeMediaSourceId:m.streamId}},video:false});
  context=new AudioContext();await context.audioWorklet.addModule('pcm-worklet.js');
  source=context.createMediaStreamSource(stream);source.connect(context.destination);
  recorder=new AudioWorkletNode(context,'pcm-recorder');mute=context.createGain();mute.gain.value=0;
  source.connect(recorder);recorder.connect(mute);mute.connect(context.destination);
  active=true;frameSequence=0;skipped=0;inferenceMs=queueSeconds=0;lastPostedRevision=-1;lastTranslationAt=0;captions.reset();
  recorder.port.postMessage({type:'reset',paused:false,generation});
  recorder.port.onmessage=e=>{
   if(!active||e.data.generation!==generation)return;
   if(pending)skipped++;
   pending={samples:new Float32Array(e.data.buffer),start:e.data.start,end:e.data.end,received:performance.now()};drain();
  };
  stream.getAudioTracks()[0].onended=()=>{if(active)stop();};
  await context.resume();await emitLive();pollTranslation(generation);return {ok:true};
 }catch(e){await stop();throw e;}
}
function resetLive(paused){
 const epoch=++generation;pending=null;captions.reset();controller?.abort();
 clearTimeout(translationTimer);clearTimeout(translationPollTimer);translationTimer=null;lastPostedRevision=-1;translationValue=null;
 recorder?.port.postMessage({type:'reset',paused:true,generation:epoch});
 resetSerial=resetSerial.catch(()=>{}).then(async()=>{
  if(!active||epoch!==generation)return;
  const state=await request('/live/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(captionSettings)});
  if(!active||epoch!==generation)return;
  liveSession=state.session;frameSequence=0;
  recorder?.port.postMessage({type:'reset',paused,generation:epoch});await emitLive();
  if(!paused)pollTranslation(epoch);
 });return resetSerial;
}
chrome.runtime.onMessage.addListener((m, sender, reply) => {
  if (m.target !== 'offscreen') return;
  (async () => {
    if (m.type === 'status') return {active,tabId,message,messageKey,mode,offset,preparation,liveSetup,metrics:mode==='live'?liveMetrics():null,liveCaption:lastCaption};
    if (m.type === 'offset') { offset = Math.max(-5, Math.min(5, Number(m.seconds) || 0)); return {ok: true}; }
    if(m.type==='seek'&&m.tabId===tabId&&mode==='preparing'){await request('/prepare/seek',{method:'POST',body:JSON.stringify({seconds:m.seconds}),headers:{'Content-Type':'application/json'}});return {ok:true};}
    if (m.type === 'health') {const health=await request('/health');if(!health.live)throw new Error('请安装 CaptionCraft 0.7 完整安装包，再重新连接助手。');return {ok:true};}
    if(m.type==='prepare-live')return prepareLive(m);
    if (m.type === 'start') return start(m);
    if (m.type === 'prepare') return prepare(m);
    if (m.type === 'stop') { await stop(); return {ok: true}; }
    if(m.type==='reset'&&m.tabId===tabId&&mode==='live'){await resetLive(!!m.paused);return {ok:true};}
  })().then(reply).catch(e => reply({ok: false, error: e.message}));
  return true;
});
