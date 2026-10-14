const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../extension/pcm-worklet.js'), 'utf8');
for (const rate of [16000, 44100, 48000, 96000]) {
  let Processor, frames = [];
  class Base { constructor() { this.port = {postMessage: data => frames.push(data)}; } }
  vm.runInNewContext(code, {AudioWorkletProcessor: Base, sampleRate: rate, Float32Array,
    registerProcessor: (_, p) => Processor = p});
  const p = new Processor();
  p.port.onmessage({data: {paused: false, generation: 7}});
  let left = rate * 8;
  while (left) {
    const n = Math.min(128, left);
    p.process([[new Float32Array(n).fill(.5), new Float32Array(n).fill(-.25)]]);
    left -= n;
  }
  assert.equal(frames.length, 16, `${rate}Hz emits first at .5s cadence`);
  for (const [i, frame] of frames.entries()) {
    assert.equal(frame.generation, 7);
    const pcm = new Float32Array(frame.buffer);
    const end = .5 + i * .5;
    assert.ok(Math.abs(frame.end - end) < 1e-6);
    assert.equal(pcm.length, Math.min(Math.round(end * 16000), 96000));
    assert.ok(Math.abs(frame.start - Math.max(0, end - 6)) < 1e-6);
    assert.ok(pcm.every(v => Math.abs(v - .125) < 1e-6));
  }
  p.port.onmessage({data: {paused: true, generation: 8}});
  p.process([[new Float32Array(rate * 4)]]);
  assert.equal(frames.length, 16);
  p.port.onmessage({data: {paused: false, generation: 9}});
  p.process([[new Float32Array(rate * 4).fill(.25)]]);
  assert.equal(frames.length, 24); assert.equal(frames[16].generation, 9);
}
console.log('PASS: rolling 6s context, .5s first update, .5s cadence, 4 sample rates, pause/reset');
