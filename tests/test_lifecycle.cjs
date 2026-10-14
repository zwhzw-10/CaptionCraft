const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const delay = () => new Promise(resolve => setImmediate(resolve));
let listener, node, track, requests = [], events = [], mode = 'normal';
class Context {
  constructor() { this.audioWorklet = {addModule: async () => {}}; this.destination = {}; }
  createMediaStreamSource() { return {connect() {}, disconnect() {}}; }
  createGain() { return {gain: {}, connect() {}, disconnect() {}}; }
  async resume() {} async close() {}
}
class Recorder {
  constructor() { node = this; this.port = {postMessage: data => this.lastReset = data}; }
  connect() {} disconnect() {}
}
const sandbox = {
  LOCAL_CONFIG: {token: 'test', endpoint: 'http://127.0.0.1:8765'},
  navigator: {mediaDevices: {getUserMedia: async () => {
    track = {stopped: false, stop() { this.stopped = true; }};
    return {getTracks: () => [track], getAudioTracks: () => [track]};
  }}},
  // Match real offscreen API limits: no chrome.storage exists here.
  chrome: {runtime: {sendMessage: async m => { if(m.type==='local-config') return {ok:true,token:'saved-token',endpoint:'http://127.0.0.1:41234'}; events.push(m); }, onMessage: {addListener: f => listener = f}}},
  AudioContext: Context, AudioWorkletNode: Recorder, Float32Array, AbortController, AbortSignal, setTimeout, clearTimeout, performance,
  fetch: async (url, options) => {
    assert.equal(options.headers['X-Local-Token'], 'saved-token');
    if (url.endsWith('/health')) return {ok: true, json: async () => ({ok: true,live:true})};
    if (url.endsWith('/live/config'))return {ok:true,json:async()=>({state:'ready',engine:'whisper',session:'test-session'})};
    if (url.endsWith('/live/stop'))return {ok:true,json:async()=>({ok:true})};
    if (url.endsWith('/prepare/status')) return {ok: true, json: async () => ({revision:1,complete:true,readyRanges:[[0,30]],state: 'ready', message: 'ready', progress:100, videoId:'abcdefghijk', cues:[{start:1,end:2,text:'Hello'}]})};
    if (url.endsWith('/prepare') || url.endsWith('/prepare/cancel')) return {ok:true,json:async()=>({ok:true})};
    if (mode === 'error') throw new Error('helper unreachable');
    return new Promise((resolve, reject) => {
      requests.push({resolve: text => resolve({ok: true, json: async () => ({text, seconds: .2})})});
      options.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), {name: 'AbortError'})));
    });
  }
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../extension/caption-state.js'), 'utf8'), sandbox);
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../extension/live-state.js'), 'utf8'), sandbox);
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../extension/offscreen.js'), 'utf8'), sandbox);
const command = m => new Promise(resolve => listener({target: 'offscreen', ...m}, {}, resolve));
let clock = 0;
const chunk = generation => { clock += 1.5; node.port.onmessage({data: {buffer: new Float32Array(19200).buffer, generation, start: Math.max(0, clock - 3), end: clock}}); };
(async () => {
  assert.equal((await command({type: 'health'})).ok, true);
  assert.equal((await command({type:'prepare-live',tabId:12,settings:{source:'en',display:'original',liveEngine:'whisper'}})).ok,true);
  assert.equal((await command({type: 'start', tabId: 12, streamId: 'sample'})).ok, true);
  assert.equal((await command({type: 'status'})).active, true);
  const epoch = node.lastReset.generation;
  chunk(epoch); await delay();
  chunk(epoch); chunk(epoch); // only newest pending chunk retained
  assert.equal((await command({type:'status'})).metrics.skipped,1);
  requests[0].resolve('first result'); await delay(); await delay();
  assert.ok(events.some(e => e.liveCaption?.original === 'first result'));
  assert.equal(requests.length, 2);
  await command({type: 'reset', tabId: 12, paused: true});
  await delay(); await delay();
  const count = requests.length;
  chunk(epoch); await delay();
  assert.equal(requests.length, count, 'old worklet generation ignored');
  await command({type: 'reset', tabId: 12, paused: false});
  chunk(node.lastReset.generation); await delay();
  await command({type: 'stop'}); await delay();
  assert.equal(track.stopped, true); assert.equal((await command({type: 'status'})).active, false);
  assert.equal((await command({type:'prepare-live',tabId:12,settings:{source:'en',display:'original',liveEngine:'whisper'}})).ok,true);
  assert.equal((await command({type: 'start', tabId: 12, streamId: 'sample'})).ok, true);
  mode = 'error'; chunk(node.lastReset.generation); await delay(); await delay();
  const state = await command({type: 'status'});
  assert.equal(state.active, false); assert.ok(events.some(e=>e.error==='helper unreachable'));
  mode = 'normal';
  assert.equal((await command({type:'prepare',tabId:12,url:'https://youtube.com/watch?v=abcdefghijk'})).ok,true);
  assert.equal((await command({type:'status'})).mode,'prepared');
  assert.ok(events.some(e=>e.prepared?.cues[0].text==='Hello'));
  await command({type:'reset',tabId:12,paused:true});
  assert.equal((await command({type:'status'})).mode,'prepared');
  await command({type:'offset',seconds:-.5});
  assert.equal((await command({type:'status'})).offset,-.5);
  await command({type:'stop'});
  console.log('PASS: start/stop, bounded queue, reset cancellation, stale chunks, connection failure cleanup');
})().catch(e => { console.error(e); process.exitCode = 1; });
