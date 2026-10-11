globalThis.findCaptionCueData = function(cues, time, offset = 0) {
  time -= offset;
  let lo = 0, hi = cues.length - 1, index = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (cues[mid].start <= time) { index = mid; lo = mid + 1; } else hi = mid - 1;
  }
  const cue = cues[index];
  return cue && time < cue.end ? cue : null;
};

globalThis.findCaptionCue=(cues,time,offset=0)=>findCaptionCueData(cues,time,offset)?.text||'';
