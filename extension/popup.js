const label=document.querySelector('#status');
const buttons=[...document.querySelectorAll('button')];
const languageNames=CAPTION_LANGUAGES.names;
const videoLanguages=CAPTION_LANGUAGES.source;
let preferences={source:'auto',target:'zh',display:'original',preferExisting:true,mode:'sync',liveEngine:'auto'};
let lastState={};
for(const code of videoLanguages) document.querySelector('#source').add(new Option(languageNames[code],code));
for(const code of CAPTION_LANGUAGES.target) document.querySelector('#target').add(new Option(languageNames[code],code));
for(const code of UI_LOCALES) document.querySelector('#uiLocale').add(new Option(UI_NAMES[code],code));
function syncPreferences(){
  if(!['sync','live'].includes(preferences.mode))preferences.mode='sync';
  if(!['auto','sherpa','whisper'].includes(preferences.liveEngine))preferences.liveEngine='auto';
  const live=preferences.mode==='live';
  for(const [id,value] of [['sync-mode','sync'],['live-mode','live']]){document.getElementById(id).classList.toggle('selected',preferences.mode===value);document.getElementById(id).setAttribute('aria-pressed',String(preferences.mode===value));}
  document.getElementById('existing-row').hidden=live;document.getElementById('live-options').hidden=!live;
  document.getElementById('liveEngine').value=preferences.liveEngine;document.getElementById('mode-help').textContent=t(live?'liveIntro':'syncIntro');
  document.getElementById('prepare').textContent=t(live?'beginLive':'prepare');
  document.querySelector('[data-i18n="intro"]').hidden=live;

  for(const key of ['source','target','display']) document.getElementById(key).value=preferences[key];
  document.getElementById('preferExisting').checked=preferences.preferExisting;
  document.getElementById('target-row').hidden=preferences.display==='original';
  document.getElementById('uiLocale').value=uiLocale;
}
function renderState(state){
  lastState=state||{};
  const p=state?.preparation;
  let text=t(state?.messageKey||'idle');
  if(p){
    text=t(p.messageKey||'gettingAudio');
    if(p.progress!=null) text+=` · ${p.progress}%`;
    if(p.language) text+=`\n${languageNames[p.language]||p.language}`;
    if(p.detail) text+=` · ${p.detail}`;
    if(p.downloadMB!=null) text+=` · ${p.downloadMB} MB`;
    if(p.pivot) text+='\n'+t('pivot');
    if(p.error) text+='\n'+p.error;
  } else if(state?.error){text=t('error')+'\n'+state.error;}
  if(state?.liveSetup){text=t('liveModelLoading');if(state.liveSetup.downloadMB!=null)text+=` · ${state.liveSetup.downloadMB} MB`;}
  if(state?.metrics){const m=state.metrics;text+=`\n${m.engine==='sherpa'?t('engineEnglish'):t('engineWhisper')} · ${t('processingTime')} ${m.inferenceMs} ms`;if(m.skipped)text+=` · ${t('skippedUpdates')} ${m.skipped}`;if(m.translationState==='working'||m.translationState==='model-download')text+='\n'+t('translationPending');if(m.translationDownloadMB!=null)text+=` · ${m.translationDetail||''} ${m.translationDownloadMB} MB`;if(m.translationError)text+='\n'+t('liveTranslationError')+': '+m.translationError;}
  label.textContent=text;
  label.dataset.error=String(!!(state?.error||p?.state==='error'));
}
function showError(e){label.textContent=(/assistantMissing/.test(e.message)?t('assistantMissing'):/assistantTimeout/.test(e.message)?t('assistantTimeout'):/fetch|connect|unreachable/i.test(e.message)?t('unreachable'):t('error')+'\n'+e.message);label.dataset.error='true';}
async function command(type){
  buttons.forEach(b=>b.disabled=true);
  try{
    if(type!=='stop')document.getElementById('stop').disabled=false;
    const result=await chrome.runtime.sendMessage({target:'background',type,settings:preferences});
    if(result?.error)throw new Error(result.error);
    const state=await chrome.runtime.sendMessage({target:'background',type:'status'});
    renderState(state);document.querySelector('#offset').value=state?.offset||0;
  }catch(e){showError(e);}
  finally{buttons.forEach(b=>b.disabled=false);}
}
const initialized=chrome.storage.local.get(['captionPreferences','uiLocale']).then(data=>{
  if(data.captionPreferences)preferences={...preferences,...data.captionPreferences};
  if(UI_LOCALES.includes(data.uiLocale))uiLocale=data.uiLocale;
  translatePage();syncPreferences();renderState(lastState);
});
for(const key of ['source','target','display','preferExisting'])document.getElementById(key).onchange=async e=>{
  preferences[key]=key==='preferExisting'?e.target.checked:e.target.value;
  syncPreferences();await chrome.storage.local.set({captionPreferences:preferences});
};
document.getElementById('uiLocale').onchange=async e=>{
  uiLocale=e.target.value;translatePage();syncPreferences();renderState(lastState);await chrome.storage.local.set({uiLocale});
};
document.querySelector('#start').onclick=()=>command('start');
document.querySelector('#prepare').onclick=()=>command(preferences.mode==='live'?'start':'prepare');
for(const [id,value] of [['sync-mode','sync'],['live-mode','live']])document.getElementById(id).onclick=async()=>{preferences.mode=value;syncPreferences();await chrome.storage.local.set({captionPreferences:preferences});};
document.getElementById('liveEngine').onchange=async e=>{preferences.liveEngine=e.target.value;await chrome.storage.local.set({captionPreferences:preferences});};
document.getElementById('caption-window').onclick=()=>chrome.runtime.sendMessage({target:'background',type:'caption-window'}).catch(showError);
document.querySelector('#stop').onclick=()=>command('stop');
document.querySelector('#offset').onchange=e=>chrome.runtime.sendMessage({target:'background',type:'offset',seconds:Math.max(-5,Math.min(5,Number(e.target.value)||0))}).catch(showError);
document.querySelector('#file').onchange=async e=>{
  const file=e.target.files[0];if(!file)return;
  document.querySelector('#file-name').textContent=file.name;
  if(file.size>200*1024*1024){label.textContent=t('fileTooLarge');return;}
  buttons.forEach(b=>b.disabled=true);
  try{
    const target=await chrome.runtime.sendMessage({target:'background',type:'upload-init',settings:preferences});
    if(target.error)throw new Error(target.error);
    label.textContent=t('uploading');
    const saved=await chrome.runtime.sendMessage({target:'background',type:'local-config'});
    if(saved.error)throw new Error(saved.error);
    const response=await fetch(saved.endpoint+'/prepare/upload',{method:'POST',body:file,
      headers:{'X-Local-Token':saved.token,'X-Video-URL':target.url,'X-Caption-Options':JSON.stringify({settings:preferences,position:target.position||0}),'Content-Type':'application/octet-stream'},signal:AbortSignal.timeout(60000)});
    const result=await response.json();if(!response.ok)throw new Error(result.error);
    const watching=await chrome.runtime.sendMessage({target:'offscreen',type:'prepare',tabId:target.tabId,alreadyStarted:true,settings:preferences});
    if(watching.error)throw new Error(watching.error);
    label.textContent=t('working');
  }catch(e){showError(e);}
  finally{buttons.forEach(b=>b.disabled=false);}
};
document.getElementById('assistant-retry').onclick=async()=>{await chrome.runtime.sendMessage({target:'background',type:'assistant-reset'});await command('health');};
document.getElementById('assistant-diagnostics').onclick=async()=>{try{const result=await chrome.runtime.sendMessage({target:'background',type:'assistant-diagnostics'});if(result.error)throw new Error(result.error);label.textContent=result.log||'';}catch(e){showError(e);}};
function srtTime(seconds){const ms=Math.max(0,Math.round(seconds*1000)),h=Math.floor(ms/3600000),m=Math.floor(ms/60000)%60,s=Math.floor(ms/1000)%60;return [h,m,s].map(n=>String(n).padStart(2,'0')).join(':')+','+String(ms%1000).padStart(3,'0');}
document.getElementById('export').onclick=async()=>{
  try{
    const state=await chrome.runtime.sendMessage({target:'background',type:'status'}),p=state?.preparation;
    if(!p?.cues?.length)throw new Error(t('noExport'));
    const mode=p.display||'original';
    const cues=p.cues.filter(c=>mode!=='translation'||c.translation);
    const body=cues.map((c,i)=>`${i+1}\n${srtTime(c.start)} --> ${srtTime(c.end)}\n${mode==='translation'?c.translation:mode==='bilingual'&&c.translation?c.text+'\n'+c.translation:c.text}\n`).join('\n');
    const url=URL.createObjectURL(new Blob(['\ufeff'+body],{type:'text/plain;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`CaptionCraft-${p.videoId}-${p.language||'auto'}-${mode}.srt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){showError(e);}
};
initialized.then(async()=>{await command('status');if(!lastState.active){const health=await chrome.runtime.sendMessage({target:'background',type:'health'});if(health?.error)showError(new Error(health.error));else if(!lastState.active)renderState({active:false,messageKey:'idle'});}});
chrome.runtime.onMessage.addListener(m=>{if(m.type==='event')renderState(m);});
