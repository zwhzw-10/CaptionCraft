// Estimates stable prefixes; partial text remains editable until the engine's endpoint.
globalThis.LiveCaptionState = class LiveCaptionState {
  constructor(){this.reset();}
  reset(){this.previous='';this.utterance=null;this.revision=0;this.latest=null;this.whisper=new CaptionState();}
  update(result,frame){
    if(result.engine==='sherpa' && this.utterance!==result.utterance){this.previous='';this.utterance=result.utterance;}
    const text=result.engine==='sherpa'?result.text:this.whisper.update(result,frame);
    if(text==null || !text.trim())return null;
    let stable=0;while(stable<Math.min(text.length,this.previous.length)&&text[stable]===this.previous[stable])stable++;
    const changed=text!==this.previous;
    if(changed)this.revision++;
    this.previous=text;
    this.latest={text:text.slice(-600),revision:this.revision,language:result.language,
      final:!!result.final,stablePrefix:result.final?text.length:stable,engine:result.engine||'whisper'};
    return {...this.latest,changed};
  }
};
