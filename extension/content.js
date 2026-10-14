(() => {
  if (globalThis.__localCaptions) return;
  globalThis.__localCaptions = true;
  const host = document.createElement('div'); host.id = 'local-english-captions';
  const root = host.attachShadow({mode: 'closed'});
  root.innerHTML = `<style>:host{position:fixed!important;z-index:2147483647!important;pointer-events:none!important;text-align:center!important;width:max-content!important;max-width:90vw!important}span{display:inline-block;max-width:100%;font:600 28px/1.4 Arial,sans-serif;padding:7px 14px;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;pointer-events:auto;cursor:grab;touch-action:none;user-select:none}span:empty{display:none}span:active{cursor:grabbing}span[data-phase]::after{content:attr(data-phase);display:block;font:400 10px/1.5 Arial,sans-serif;opacity:.65;margin-top:3px}</style><span></span>`;
  const label = root.querySelector('span');
  let style = {...CAPTION_DEFAULTS}, previewUntil = 0, drag = null, dead = false, waitingForBuffer = false;
  function saveStyle() { if (chrome.runtime?.id) chrome.storage.local.set({captionStyle:style}).catch(()=>{}); }
  function position() {
    const rect=label.getBoundingClientRect(), w=innerWidth, h=innerHeight;
    let x,y;
    if(style.position){x=style.position.x*w;y=style.position.y*h;}
    else{const r=(document.querySelector('#movie_player')||video)?.getBoundingClientRect();x=r?r.left+r.width/2:w/2;y=r?r.bottom-r.height*.15:h*.8;}
    x=Math.max(rect.width/2+8,Math.min(w-rect.width/2-8,x));y=Math.max(8,Math.min(h-rect.height-8,y));
    host.style.setProperty('left',x+'px','important');host.style.setProperty('top',y+'px','important');host.style.setProperty('transform','translateX(-50%)','important');
  }
  function applyStyle(){const c=style.background;label.style.fontSize=style.fontSize+'px';label.style.color=`rgba(255,255,255,${style.textOpacity/100})`;label.style.background=`rgba(${parseInt(c.slice(1,3),16)},${parseInt(c.slice(3,5),16)},${parseInt(c.slice(5,7),16)},${style.backgroundOpacity/100})`;position();}
  chrome.storage.local.get('uiLocale').then(d=>{if(UI_LOCALES.includes(d.uiLocale))uiLocale=d.uiLocale;}).catch(()=>{});
  chrome.storage.local.get('captionStyle').then(d=>{style=normalizeCaptionStyle(d.captionStyle);applyStyle();}).catch(()=>{});
  chrome.storage.onChanged.addListener((c,a)=>{if(a==='local'&&c.uiLocale&&UI_LOCALES.includes(c.uiLocale.newValue))uiLocale=c.uiLocale.newValue;if(a==='local'&&c.captionStyle){style=normalizeCaptionStyle(c.captionStyle.newValue);applyStyle();}});
  label.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();const r=host.getBoundingClientRect();drag={dx:e.clientX-(r.left+r.width/2),dy:e.clientY-r.top};label.setPointerCapture(e.pointerId);});
  label.addEventListener('pointermove',e=>{if(!drag)return;e.stopPropagation();style.position={x:Math.max(0,Math.min(1,(e.clientX-drag.dx)/innerWidth)),y:Math.max(0,Math.min(1,(e.clientY-drag.dy)/innerHeight))};position();});
  function endDrag(){if(!drag)return;drag=null;saveStyle();}
  label.addEventListener('pointerup',endDrag);label.addEventListener('pointercancel',endDrag);label.addEventListener('lostpointercapture',endDrag);
  window.addEventListener('resize',position);document.addEventListener('fullscreenchange',()=>{mount();position();});window.addEventListener('scroll',()=>{if(!style.position)position();},{passive:true});
  let timer, video, enabled = false, lastUrl = location.href;
  let prepared = null, offset = 0;
  function renderPrepared() {
    if(previewUntil>Date.now()){label.textContent=t('previewText');position();return;}
    if (!prepared || !enabled || !video) { if(!enabled) label.textContent=''; return; }
    const id = new URL(location.href).searchParams.get('v') || location.pathname.split('/')[2];
    if (id !== prepared.videoId || document.querySelector('#movie_player.ad-showing')) { label.textContent = ''; return; }
    const ranges=prepared.display==='translation'?prepared.translationRanges:prepared.readyRanges;
    const covered=!ranges || ranges.some(([a,b])=>video.currentTime>=a && video.currentTime<b+.05);
    if(!covered && !prepared.complete){
      label.textContent=t(prepared.failed?'partialError':'buffering');
      if(!video.paused){waitingForBuffer=true;video.pause();}
      return;
    }
    if(waitingForBuffer && video.paused){label.textContent=t('playNow');return;}
    waitingForBuffer=false;
    const cue=findCaptionCueData(prepared.cues,video.currentTime,offset);
    label.textContent=!cue?'':prepared.display==='translation'?(cue.translation||''):
      prepared.display==='bilingual'&&cue.translation?cue.text+'\n'+cue.translation:cue.text;
  }
  function clear() { clearTimeout(timer); label.textContent = ''; }
  function reset() {
    if(enabled&&video?.seeking&&chrome.runtime?.id)chrome.runtime.sendMessage({target:'background',type:'seek',seconds:video.currentTime}).catch(()=>{});
    if(prepared){renderPrepared();return;}
    clear();
    if (enabled && chrome.runtime?.id) chrome.runtime.sendMessage({target: 'background', type: 'reset', paused: !!video && (video.paused || video.seeking)}).catch(() => {});
  }
  function mount() {
    const parent=document.fullscreenElement || document.body;
    if(parent && host.parentElement!==parent)parent.append(host);
    const videos=[...document.querySelectorAll('video')];
    const next=videos.sort((a,b)=>{const x=a.getBoundingClientRect(),y=b.getBoundingClientRect();return y.width*y.height-x.width*x.height;})[0];
    if (next !== video) {
      if (video) for (const event of ['pause', 'playing', 'seeking', 'seeked', 'ended']) video.removeEventListener(event, reset);
      video = next;
      if (video) for (const event of ['pause', 'playing', 'seeking', 'seeked', 'ended']) video.addEventListener(event, reset);
      reset();
    }
    if (lastUrl !== location.href) { lastUrl = location.href; reset(); }
  }
  mount();
  const observer=new MutationObserver(mount);observer.observe(document.documentElement,{childList:true,subtree:true});
  const tick=setInterval(()=>{if(!chrome.runtime?.id){dead=true;clearInterval(tick);observer.disconnect();clear();host.remove();return;}renderPrepared();if(!drag)position();},80);
  chrome.runtime.onMessage.addListener(m => {
    if(m.type==='caption-preview'){previewUntil=Date.now()+15000;mount();renderPrepared();return;}
    if(m.type==='prepare-wait'||m.type==='caption-event')previewUntil=0;
    if (m.type === 'prepare-wait') { prepared = null;waitingForBuffer=false;clear();video?.pause(); return; }
    if (m.type === 'caption-offset') { offset = Number(m.seconds) || 0; renderPrepared(); return; }
    if (m.type !== 'event' && m.type !== 'caption-event') return;
    enabled=m.active;mount();
    if (m.stopped || !enabled) { prepared = null; clear(); }
    if (m.prepared) {label.removeAttribute('data-phase');label.removeAttribute('data-final');clear(); prepared = m.prepared; offset = m.prepared.offset || 0; renderPrepared(); return; }
    if(m.liveCaption&&enabled){
      prepared=null;clear();const c=m.liveCaption;
      if(!video?.paused&&!video?.seeking){
        label.textContent=c.display==='translation'?(c.translation||t('translationPending')):c.display==='bilingual'?(c.original+(c.translation?'\n'+c.translation:c.original?'\n'+t('translationPending'):'')):c.original;
        label.title=t(c.final?'liveConfirmed':'liveTentative');label.dataset.phase=label.title;
        label.dataset.final=String(c.final);position();
      }
      timer=setTimeout(clear,7000);return;
    }
    if (m.text !== undefined && enabled) {
      clear();
      if (!video?.paused && !video?.seeking) label.textContent = m.text;
      timer = setTimeout(clear, 7000);
    }
  });
})();
