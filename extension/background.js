importScripts('native-client.js');
let changing = false;
async function hasOffscreen() {
  if (chrome.offscreen.hasDocument) return chrome.offscreen.hasDocument();
  const contexts = await chrome.runtime.getContexts({contextTypes:['OFFSCREEN_DOCUMENT'],documentUrls:[chrome.runtime.getURL('offscreen.html')]});
  return contexts.length > 0;
}
async function ensureOffscreen() {
  if (!(await hasOffscreen())) {
    await chrome.offscreen.createDocument({url: 'offscreen.html', reasons: ['USER_MEDIA'], justification: 'Capture tab audio and run local transcription requests.'});
  }
}
async function sendOff(message) {
  return chrome.runtime.sendMessage({...message, target: 'offscreen'});
}
async function status() {
  if (!(await hasOffscreen())) return {active:false,messageKey:'idle'};
  return sendOff({type: 'status'});
}
async function handle(message, sender) {
  if (message.type === 'assistant-diagnostics') {
    if(sender.url!==chrome.runtime.getURL('popup.html'))throw new Error('Diagnostics are restricted to the settings page');
    return assistantCommand('diagnostics');
  }
  if (message.type === 'assistant-reset') {
    if (sender.url !== chrome.runtime.getURL('popup.html')) throw new Error('Assistant reset is restricted to the settings page');
    if(nativePort)nativePort.disconnect();nativePort=null;nativeConfig=null;
    return {ok:true};
  }
  if (message.type === 'local-config') {
    if (![chrome.runtime.getURL('offscreen.html'),chrome.runtime.getURL('popup.html')].includes(sender.url)) throw new Error('Assistant settings are restricted to extension pages');
    return ensureAssistant();
  }
  if (message.type === 'event' && sender.url === chrome.runtime.getURL('offscreen.html')) {
    await chrome.action.setBadgeText({text: message.active ? 'ON' : ''});
    await chrome.action.setBadgeBackgroundColor({color: '#2563eb'});
    if (message.tabId != null) {
      await chrome.tabs.sendMessage(message.tabId, {type: 'caption-event', ...message}).catch(() => {});
    }
    return {ok: true};
  }
  if (sender.tab) {
    if(message.type==='seek') return sendOff({type:'seek',tabId:sender.tab.id,seconds:message.seconds});
    if (message.type === 'reset') return sendOff({type: 'reset', tabId: sender.tab.id, paused: message.paused});
    return;
  }
  if(message.type==='health'){await ensureOffscreen();return sendOff({type:'health'});}
  if (message.type === 'status') return status();
  if (message.type === 'stop') return sendOff({type: 'stop'});
  if (message.type === 'offset') {
    const state = await status();
    await sendOff({type: 'offset', seconds: message.seconds});
    if (state.tabId != null) await chrome.tabs.sendMessage(state.tabId, {type: 'caption-offset', seconds: message.seconds});
    return {ok: true};
  }
  if (!['start', 'prepare', 'upload-init'].includes(message.type)) return;
  if (changing) throw new Error('正在切换，请稍候');
  changing = true;
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (!tab || !/^https:\/\/(www\.)?youtube\.com\/(watch|shorts\/)/.test(tab.url || '')) throw new Error('请先打开 YouTube 视频页面');
    await ensureOffscreen();
    await sendOff({type: 'stop'});
    const health = await sendOff({type: 'health'});
    if (!health.ok) throw new Error(health.error);
    await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['cue-timeline.js', 'appearance.js', 'i18n.js', 'content.js']});
    const results=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>document.querySelector('video')?.currentTime||0});
    const position=results[0]?.result||0;
    if (message.type !== 'start') {
      await chrome.tabs.sendMessage(tab.id, {type: 'prepare-wait'});
      if (message.type === 'upload-init') return {ok:true,tabId:tab.id,url:tab.url,position};
      return sendOff({type:'prepare',tabId:tab.id,url:tab.url,position,settings:message.settings});
    }
    const streamId = await chrome.tabCapture.getMediaStreamId({targetTabId: tab.id});
    const result = await sendOff({type:'start',tabId:tab.id,streamId,settings:message.settings});
    if (!result.ok) throw new Error(result.error);
    return result;
  } finally { changing = false; }
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message.target !== 'background') return;
  handle(message, sender).then(reply).catch(e => reply({ok: false, error: e.message}));
  return true;
});
chrome.tabs.onRemoved.addListener(async tabId => {
  const state = await status();
  if (state?.tabId === tabId) await sendOff({type: 'stop'});
});
chrome.tabs.onUpdated.addListener(async (tabId, change) => {
  if (change.status === 'loading') {
    const state = await status();
    if (state?.tabId === tabId) await sendOff({type: 'stop'});
  }
});
