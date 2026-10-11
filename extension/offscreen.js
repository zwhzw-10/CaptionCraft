let stream, context, source, recorder, mute, controller;
let tabId = null, active = false, generation = 0, pending = null, processing = false;
let message = '尚未开启', sequence = 0;
let mode = 'live', preparationTimer;
let offset = 0, preparation = null, captionSettings={source:'auto',target:'zh',display:'original',preferExisting:true}, messageKey='idle';
const captions = new CaptionState();
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
  clearTimeout(preparationTimer);
  if (mode === 'preparing' || mode === 'partial-error') await request('/prepare/cancel', {method: 'POST'}).catch(() => {});
  mode = 'live';
  generation++;
  active = false;
  pending = null;
  captions.clear();
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
  if (processing) return;
  processing = true;
  try {
    while (pending && active) {
      const frame = pending; pending = null;
      const current = generation;
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 30000);
      try {
        const result = await request('/transcribe', {method: 'POST', body: frame.samples.buffer, headers: {'Content-Type': 'application/octet-stream','X-Caption-Options':JSON.stringify(captionSettings)}, signal: controller.signal});
        if (!active || current !== generation) continue;
        const lag = (performance.now() - frame.received) / 1000;
        message = `快速字幕 · 识别 ${result.seconds.toFixed(2)} 秒 · 更新间隔 0.8 秒`;
        if (lag > 5) { message = '识别落后，已丢弃过期结果；建议使用 tiny'; await emit({warning: true}); continue; }
        const text = captions.update(result, frame);
        if (text !== null) await emit({text, sequence: ++sequence});
        else await emit();
      } catch (e) {
        if (!active || current !== generation) continue;
        if (e.status === 429) { pending = null; message = '等待上一次识别结束…'; await emit(); continue; }
        const errorMessage = e.name === 'AbortError' ? '识别超过 30 秒：请查看助手日志或重新连接' : `本地识别失败：${e.message}。请查看助手日志或重新连接`;
        await stop();
        message = errorMessage;
        await emit({message, error: true});
        break;
      } finally { clearTimeout(timeout); }
    }
  } finally { processing = false; }
}
async function start(m) {
  await stop();
  tabId = m.tabId; captionSettings=m.settings||captionSettings; messageKey='liveActive';
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: {mandatory: {chromeMediaSource: 'tab', chromeMediaSourceId: m.streamId}}, video: false});
    context = new AudioContext();
    await context.audioWorklet.addModule('pcm-worklet.js');
    source = context.createMediaStreamSource(stream);
    source.connect(context.destination);
    recorder = new AudioWorkletNode(context, 'pcm-recorder');
    mute = context.createGain(); mute.gain.value = 0;
    source.connect(recorder); recorder.connect(mute); mute.connect(context.destination);
    active = true; message = '已开启 · 约 1.2 秒后开始识别，字幕可逐步修正';
    recorder.port.postMessage({type: 'reset', paused: false, generation});
    recorder.port.onmessage = e => {
      if (!active || e.data.generation !== generation) return;
      if (pending) { message = '电脑识别较慢，已跳过旧音频；可改用 tiny'; emit({warning: true}); }
      pending = {samples: new Float32Array(e.data.buffer), start: e.data.start, end: e.data.end, received: performance.now()};
      drain();
    };
    stream.getAudioTracks()[0].onended = () => { if (active) stop(); };
    await context.resume();
    await emit({text: ''});
    return {ok: true};
  } catch (e) { await stop(); throw e; }
}
chrome.runtime.onMessage.addListener((m, sender, reply) => {
  if (m.target !== 'offscreen') return;
  (async () => {
    if (m.type === 'status') return {active, tabId, message, messageKey, mode, offset, preparation};
    if (m.type === 'offset') { offset = Math.max(-5, Math.min(5, Number(m.seconds) || 0)); return {ok: true}; }
    if(m.type==='seek'&&m.tabId===tabId&&mode==='preparing'){await request('/prepare/seek',{method:'POST',body:JSON.stringify({seconds:m.seconds}),headers:{'Content-Type':'application/json'}});return {ok:true};}
    if (m.type === 'health') { await request('/health'); return {ok: true}; }
    if (m.type === 'start') return start(m);
    if (m.type === 'prepare') return prepare(m);
    if (m.type === 'stop') { await stop(); return {ok: true}; }
    if (m.type === 'reset' && m.tabId === tabId && mode === 'live') {
      generation++; pending = null; captions.clear(); controller?.abort();
      recorder?.port.postMessage({type: 'reset', paused: !!m.paused, generation});
      await emit({text: ''});
      return {ok: true};
    }
  })().then(reply).catch(e => reply({ok: false, error: e.message}));
  return true;
});
