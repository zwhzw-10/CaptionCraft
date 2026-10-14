let clearTimer;
chrome.storage.local.get('uiLocale').then(d=>{if(UI_LOCALES.includes(d.uiLocale))uiLocale=d.uiLocale;chrome.runtime.sendMessage({target:'background',type:'last-live-caption'}).then(paint).catch(()=>paint(null));});
function paint(c){
 clearTimeout(clearTimer);
 const original=document.getElementById('original'),translation=document.getElementById('translation');
 if(!c||c.stopped||!c.active){original.textContent=t('liveWindowIdle');translation.textContent='';document.getElementById('phase').textContent='';return;}
 original.textContent=c.display==='translation'?'':c.original||'';
 translation.textContent=c.display==='original'?'':c.translation||(c.original?t('translationPending'):'');
 document.getElementById('phase').textContent=t(c.final?'liveConfirmed':'liveTentative');
 document.getElementById('hint').textContent=t('liveWindowHint');
 clearTimer=setTimeout(()=>{original.textContent='';translation.textContent='';document.getElementById('phase').textContent='';},7000);
}
chrome.runtime.onMessage.addListener(m=>{if(m.type==='event'&&m.liveCaption)paint({...m.liveCaption,active:m.active});if(m.type==='event'&&m.stopped)paint(null);});
chrome.runtime.sendMessage({target:'background',type:'last-live-caption'}).then(paint).catch(()=>paint(null));
