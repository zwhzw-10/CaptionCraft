const assert=require('node:assert/strict'), vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const box={};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../extension/cue-timeline.js'),'utf8'),box);
const cues=[{start:1,end:2,text:'Hello'},{start:2,end:3,text:'world'},{start:8,end:10,text:'Again'}];
for(const [time,text] of [[0,''],[1,'Hello'],[1.99,'Hello'],[2,'world'],[3,''],[9,'Again'],[1.5,'Hello'],[11,'']]) assert.equal(box.findCaptionCue(cues,time),text);
assert.equal(box.findCaptionCue(cues,1,.5),'');assert.equal(box.findCaptionCue(cues,1.5,.5),'Hello');
assert.equal(box.findCaptionCue(cues,.5,-.5),'Hello');assert.equal(box.findCaptionCue([],1),'');
console.log('PASS: exact cue boundaries, gaps, seek backwards/forwards, offset signs, empty track');
