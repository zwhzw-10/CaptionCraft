// Streaming weighted-average resampling, arbitrary input rate -> 16000 Hz mono.
class PCMRecorder extends AudioWorkletProcessor {
  constructor() {
    super(); this.paused = false; this.generation = 0; this.clear();
    this.port.onmessage = e => { this.paused = e.data.paused; this.generation = e.data.generation; this.clear(); };
  }
  clear() {
    this.buffer = new Float32Array(48000); this.index = 0; this.total = 0;
    this.next = 19200; this.weight = 0; this.sum = 0;
  }
  process(inputs) {
    const channels = inputs[0];
    if (this.paused || !channels?.length) return true;
    const ratio = sampleRate / 16000;
    for (let i = 0; i < channels[0].length; i++) {
      let mono = 0;
      for (const channel of channels) mono += channel[i] / channels.length;
      let remaining = 1;
      while (remaining > 1e-8) {
        const amount = Math.min(remaining, ratio - this.weight);
        this.sum += mono * amount; this.weight += amount; remaining -= amount;
        if (this.weight >= ratio - 1e-8) {
          this.buffer[this.index] = this.sum / ratio;
          this.index = (this.index + 1) % this.buffer.length;
          this.total++; this.weight = 0; this.sum = 0;
          if (this.total === this.next) {
            const length = Math.min(this.total, this.buffer.length);
            const frame = new Float32Array(length);
            const oldest = this.total < this.buffer.length ? 0 : this.index;
            for (let j = 0; j < length; j++) frame[j] = this.buffer[(oldest + j) % this.buffer.length];
            this.port.postMessage({buffer: frame.buffer, generation: this.generation,
              start: (this.total - length) / 16000, end: this.total / 16000}, [frame.buffer]);
            this.next += 12800;
          }
        }
      }
    }
    return true;
  }
}
registerProcessor('pcm-recorder', PCMRecorder);
