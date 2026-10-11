// Replace overlapping hypothesis by audio timestamps instead of textual deduplication.
// Repeated spoken words ("very very") are preserved; recent words may be corrected.
globalThis.CaptionState = class CaptionState {
  constructor() { this.clear(); }
  clear() { this.words = []; this.end = -1; }
  update(result, frame) {
    if (frame.end <= this.end) return null;
    if (frame.start > this.end + .5) this.words = [];
    this.end = frame.end;
    if (!Array.isArray(result.words)) return result.text; // old helper compatibility
    const cutoff = frame.start === 0 ? 0 : frame.start + .15;
    const incoming = result.words.map(w => ({text: w.text, start: w.start + frame.start, end: w.end + frame.start}))
      .filter(w => w.end > cutoff && w.end <= frame.end + .1 && /[\p{L}\p{N}]/u.test(w.text));
    if (!incoming.length) return null;
    const normalize = text => text.toLowerCase().replace(/[^\p{L}\p{N}']/gu, '');
    // Left-edge word timestamps can shift. Match the overlapping first word near
    // its previous time; never globally deduplicate repeated spoken words.
    let match = -1, distance = incoming[0].start <= frame.start + .02 ? 1.2 : .4;
    for (let i = 0; i < this.words.length; i++) {
      const delta = Math.abs(this.words[i].start - incoming[0].start);
      if (delta < distance && normalize(this.words[i].text) === normalize(incoming[0].text)) {
        match = i; distance = delta;
      }
    }
    this.words = match >= 0 ? this.words.slice(0, match) : this.words.filter(w => w.end <= incoming[0].start + .01);
    // Timestamp boundary protects legitimate repeated words; overlap hypotheses replace previous ones.
    this.words.push(...incoming);
    this.words = this.words.filter(w => w.end > frame.end - 7).slice(-18);
    return ['ja','zh'].includes(result.language)?this.words.map(w=>w.text).join('').trim():this.words.map(w=>w.text.trim()).join(' ');
  }
};
