// Copyright (c) 2026 He-Zixuan. LicenseRef-Classroom-Personal-NonCommercial-1.0; see LICENSE.
const $=id=>document.getElementById(id);
let ws,stream,ctx,node,source,analyser,mute,sid='',recording=false,stopping=false,preparing=false,startTime=0,clockId,levelId,pollBusy=false,healthError='';
const rows=new Map();
let historyLoading=false,historyRequest=0,exporting=false,followFrame=0,lastFollow=0,renaming=false,renameTarget='',sessionCatalog=[],captureEnded=false,lastHealth=null;
let audioInfo=null,audioDownloading=false;
let deleting=false,deleteTarget='',deleteClosing=false;
let catalogRequest=0;
const deletedSessions=new Set();
const setText=(id,value)=>Motion.text($(id),value);
const show=(id,visible)=>Motion.visible($(id),Boolean(visible));
function error(text){setText('error',text);show('error',Boolean(text));}
function follow(){
  if(!$('follow').checked||(!recording&&!stopping)||followFrame)return;
  followFrame=requestAnimationFrame(()=>{followFrame=0;const now=performance.now();if(now-lastFollow<200)return;lastFollow=now;$('anchor').scrollIntoView({block:'end',behavior:Motion.reduced?'instant':'smooth'});});
}
function title(text){setText('lessonName',text||'新的课堂，从这里开始');$('lessonName').title=text||'';}
function defaultTitle(){return new Date().toLocaleString('sv-SE',{hour12:false}).replace(',','');}
function updateMetadata(){
  const selected=sessionCatalog.find(s=>s.id===sid);
  if(selected){title(selected.title);setText('lessonDate',new Date(selected.created*1000).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}));}
  setText('viewKind',recording?'实时记录':sid?'已保存课堂':'课堂空间');
  if(!sid){setText('lessonDate','英文先到，中文随后');setText('savedState','字幕自动保存在本机');Motion.reset($('lessonDuration'),false);return;}
  const duration=Math.max(0,audioInfo?.duration||0,...Array.from(rows.values(),r=>r.end));
  setText('lessonDuration',formatTime(duration));Motion.reset($('lessonDuration'),true);
  if(!recording&&!stopping)setText('timer',formatTime(duration));
  const unfinished=Array.from(rows.values()).some(r=>r.status==='waiting'||r.status==='translating');
  const failed=Array.from(rows.values()).some(r=>r.status==='error');
  setText('savedState',recording?'正在录音 · 字幕自动保存':stopping?'正在保存最后一段…':unfinished?'原文已保存 · 中文处理中':failed?'原文已保存 · 部分中文需重试':rows.size?'中英字幕已保存':captureEnded?'课堂已保存 · 暂无字幕':'课堂记录已保存');
  if(captureEnded&&!recording&&!stopping&&!historyLoading)setText('sessionState',unfinished?'录音已结束 · 中文继续处理':failed?'已保存 · 部分中文需重试':'已结束并保存');
}
function selectLibrary(){for(const el of $('sessionList').children){el.setAttribute('aria-current',String(el.dataset.session===sid));el.disabled=recording||stopping||preparing||renaming||deleting||Boolean(deleteTarget);}}
function closeRename(){const update=()=>{Motion.reset($('renameForm'),false);Motion.reset($('titleDisplay'),true);};if(!$('renameForm').hidden)Motion.swap(update,document.querySelector('.identity'));else update();renameTarget='';}

function renderRow(row,animate=true){
  if(row.session!==sid)return;
  rows.set(row.id,row);show('empty',false);
  let el=document.getElementById('segment-'+row.id),fresh=!el;
  if(fresh){
    el=document.createElement('article');el.className='row';el.id='segment-'+row.id;
    el.innerHTML='<div class="row-header"><span class="time"></span><span>英文 / 中文</span></div><p class="english" lang="en"></p><p class="chinese" lang="zh-CN" hidden></p><div class="translation-status" hidden></div><button class="retry" hidden>重试中文翻译</button>';
    $('rows').append(el);
  }
  const write=(target,value)=>animate?Motion.text(target,value):target.textContent=value;
  write(el.querySelector('.time'),formatTime(row.start));
  write(el.querySelector('.english'),row.english);
  const chinese=el.querySelector('.chinese');write(chinese,row.chinese);
  if(animate)Motion.visible(chinese,Boolean(row.chinese));else Motion.reset(chinese,Boolean(row.chinese));
  const statuses={waiting:'等待翻译',translating:'正在翻译完整句意…',error:'中文翻译失败，原文已保存'};
  const status=el.querySelector('.translation-status'),statusText=statuses[row.status]||'';status.title=row.error||'';status.dataset.value=statusText;
  if(animate){if(statusText){write(status,statusText);Motion.visible(status,true);}else Promise.resolve(Motion.visible(status,false)).then(()=>{if(!status.dataset.value)status.textContent='';});}
  else{status.textContent=statusText;Motion.reset(status,Boolean(statusText));}
  const btn=el.querySelector('.retry');if(animate)Motion.visible(btn,row.status==='error');else Motion.reset(btn,row.status==='error');
  btn.onclick=async()=>{try{btn.disabled=true;await api('/segments/'+row.id+'/retry',{method:'POST'});row.status='waiting';renderRow(row);}catch(e){error(e.message);}finally{btn.disabled=false;}};
  if(fresh&&animate)Motion.enter(el);updateMetadata();follow();
}
function formatTime(s){return String(Math.floor(s/60)).padStart(2,'0')+':'+String(Math.floor(s%60)).padStart(2,'0');}
async function api(url,opts){const r=await fetch(url,{cache:'no-store',...opts});if(!r.ok){let detail;try{detail=(await r.json()).detail;}catch{}const e=Error(typeof detail==='string'?detail:'本地服务请求失败，请查看日志或重新启动');e.status=r.status;throw e;}return r.json();}
function clearRows(){
  audioInfo=null;
  rows.clear();$('rows').replaceChildren();
  Motion.reset($('empty'),true);
  setText('emptyTitle','把注意力留给课堂');
  setText('emptyHelp','点击左侧＋，立即开始一堂新课。英文实时更新，中文随后逐段配对。');
  Motion.reset($('retryHistory'),false);Motion.reset($('live'),false);setText('liveText','');
}
function sessionControls(){
  $('export').disabled=!sid||exporting||historyLoading;
  for(const id of ['course','terms','microphone','home'])$(id).disabled=recording||stopping||preparing||renaming;
  $('rename').disabled=!sid||historyLoading||preparing||renaming;
  $('newSession').disabled=!lastHealth?.ready||lastHealth?.active||recording||stopping||preparing||renaming||historyLoading;
  $('start').disabled=$('newSession').disabled;
  if(deleting||deleteTarget){for(const id of ['export','course','terms','microphone','home','rename','newSession','start'])$(id).disabled=true;}
  $('deleteLesson').disabled=!sid||recording||stopping||preparing||renaming||historyLoading||exporting||audioDownloading||deleting||Boolean(deleteTarget)||Boolean(lastHealth?.active);
  $('downloadAudio').disabled=!sid||!audioInfo?.available||recording||stopping||preparing||historyLoading||audioDownloading||deleting||Boolean(deleteTarget);
  setText('audioStatus',!sid?'录音与字幕自动保存在本机':recording?'录音同步保存中':audioInfo?.state==='saved'?'录音已保存':audioInfo?.state==='interrupted'?'录音中断 · 已保留收到的声音':audioInfo?.state==='none'?'此课堂无录音':audioInfo?.state==='recording'?'此课堂正在录音':'正在确认录音…');
  selectLibrary();
}
async function refreshAudio(requested=sid){
  if(!requested){audioInfo=null;sessionControls();return;}
  try{const info=await api('/sessions/'+requested+'/audio/info');if(sid!==requested)return;audioInfo=info;sessionControls();updateMetadata();}
  catch(e){if(sid===requested){audioInfo=null;sessionControls();setText('audioStatus','录音状态暂时无法确认');}}
}
async function refreshHistory(){
  const ticket=++catalogRequest;
  try{
    const catalog=await api('/sessions');
    if(ticket!==catalogRequest)return;
    sessionCatalog=catalog.filter(s=>!deletedSessions.has(s.id));
    const existing=new Map(Array.from($('sessionList').children,el=>[el.dataset.session,el]));
    for(const s of sessionCatalog){
      let item=existing.get(s.id);const fresh=!item;
      if(!item){item=document.createElement('button');item.className='session-item';item.dataset.session=s.id;const name=document.createElement('span');name.className='session-name';const date=document.createElement('span');date.className='session-date';item.append(name,date);item.onclick=()=>loadHistory(s.id);}
      Motion.text(item.querySelector('.session-name'),s.title);
      Motion.text(item.querySelector('.session-date'),new Date(s.created*1000).toLocaleDateString('zh-CN',{month:'2-digit',day:'2-digit'}));
      item.title=s.title;item.setAttribute('aria-label',s.title+'，'+new Date(s.created*1000).toLocaleString('zh-CN'));$('sessionList').append(item);if(fresh)Motion.enter(item);existing.delete(s.id);
    }
    await Promise.all(Array.from(existing.values(),async item=>{await Motion.visible(item,false);if(!sessionCatalog.some(s=>s.id===item.dataset.session))item.remove();}));
    Motion.reset($('libraryEmpty'),sessionCatalog.length===0);Motion.reset($('retryList'),false);setText('libraryStatus','');sessionControls();updateMetadata();
  }catch(e){if(ticket!==catalogRequest)return;setText('libraryStatus','课堂记录未能加载，请重试。');show('retryList',true);throw e;}
}
async function forgetSession(selected){
  deletedSessions.add(selected);catalogRequest++;
  sessionCatalog=sessionCatalog.filter(s=>s.id!==selected);
  if(sid===selected){
    historyRequest++;sid='';historyLoading=false;captureEnded=false;closeRename();
    if(ws){const old=ws;ws=null;old.onmessage=null;old.onclose=null;try{if(old.readyState===1)old.send('close');old.close();}catch{}}
    await Motion.swap(()=>{clearRows();title('');setText('timer','00:00');setText('sessionState','准备开始');setText('exportStatus','');updateMetadata();},$('transcript'));
  }
  const item=Array.from($('sessionList').children).find(el=>el.dataset.session===selected);
  if(item){await Motion.visible(item,false);item.remove();}
  Motion.reset($('libraryEmpty'),sessionCatalog.length===0);sessionControls();
}
async function devices(){const list=await navigator.mediaDevices.enumerateDevices();const current=$('microphone').value;$('microphone').replaceChildren(new Option('系统默认麦克风',''));list.filter(x=>x.kind==='audioinput').forEach((x,i)=>$('microphone').add(new Option(x.label||'麦克风 '+(i+1),x.deviceId)));$('microphone').value=current;}
async function releaseAudio(flush=false){clearInterval(clockId);cancelAnimationFrame(levelId);if(flush&&node){await new Promise(resolve=>{const timeout=setTimeout(resolve,1000);node.port.onmessage=e=>{if(e.data?.flushed){clearTimeout(timeout);resolve();}else if(ws?.readyState===1)ws.send(e.data.buffer);};node.port.postMessage('flush');});}stream?.getTracks().forEach(t=>t.stop());source?.disconnect();node?.disconnect();mute?.disconnect();if(ctx&&ctx.state!=='closed')await ctx.close();stream=ctx=node=source=analyser=mute=null;$('level').value=0;$('levelFill').style.setProperty('--level','0');setText('signal','麦克风未开启');}
async function start(){if(preparing||recording||stopping||renaming||!lastHealth?.ready||lastHealth?.active)return;const newTitle=defaultTitle();closeRename();preparing=true;sessionControls();error('');$('start').disabled=true;setText('start','等待麦克风…');setText('sessionState','请在浏览器提示中允许麦克风');try{const old=ws;if(old){old.onclose=null;if(old.readyState===1)old.send('close');old.close();}const device=$('microphone').value;stream=await navigator.mediaDevices.getUserMedia({audio:{deviceId:device?{exact:device}:undefined,channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:true}});await devices();ctx=new AudioContext();await ctx.resume();await ctx.audioWorklet.addModule('/assets/pcm.js');ws=new WebSocket('ws://'+location.host+'/classroom');const socket=ws;await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('本地录音服务连接超时，请重新启动')),5000);socket.onopen=()=>{clearTimeout(timeout);resolve();};socket.onerror=()=>{clearTimeout(timeout);reject(Error('无法连接本地录音服务'));};});historyRequest++;historyLoading=false;await Motion.swap(()=>{clearRows();sid='';captureEnded=false;title(newTitle);setText('exportStatus','');setText('renameStatus','');Motion.reset($('renameStatus'),false);},$('transcript'));$('reader').scrollTop=0;setText('timer','00:00');recording=true;stopping=false;preparing=false;sessionControls();$('stop').disabled=false;setText('start','录音中');setText('sessionState','实时识别');startTime=Date.now();clockId=setInterval(()=>setText('timer',formatTime((Date.now()-startTime)/1000),500));
socket.onmessage=e=>{const msg=JSON.parse(e.data);if(msg.type==='session'){sid=msg.id;sessionCatalog.unshift({id:sid,title:newTitle,created:Date.now()/1000});sessionControls();updateMetadata();refreshHistory().catch(()=>{});}else if(msg.type==='segment')renderRow(msg.row);else if(msg.type==='english'){Motion.live($('liveText'),msg.text);show('live',Boolean(msg.text));setText('sessionState',msg.lag>4?'识别有积压，请留意字幕':'实时识别');follow();}else if(msg.type==='stopped'){stopping=false;captureEnded=true;show('live',false);$('stop').disabled=true;setText('sessionState','已结束 · 正在确认保存');sessionControls();poll();refreshHistory().catch(()=>{});updateMetadata();}else if(msg.type==='fatal'){error(msg.error);stop();}else if(msg.type==='error'){error(msg.error);stop();}};
socket.onclose=async()=>{if(socket!==ws)return;const unexpected=recording||stopping;recording=false;stopping=false;await releaseAudio();$('stop').disabled=true;sessionControls();if(unexpected)error('连接中断，已保存原文可从历史找回；请重新开始录音。');health();};
socket.send(JSON.stringify({title:newTitle,course:$('course').value,terms:$('terms').value}));source=ctx.createMediaStreamSource(stream);node=new AudioWorkletNode(ctx,'classroom-pcm');analyser=ctx.createAnalyser();analyser.fftSize=512;mute=ctx.createGain();mute.gain.value=0;source.connect(node);source.connect(analyser);node.connect(mute).connect(ctx.destination);node.port.onmessage=e=>{if(socket.readyState===1&&!e.data?.flushed){if(socket.bufferedAmount>640000){error('音频发送积压，请结束录音后重新开始。');stop();return;}socket.send(e.data.buffer);}};const wave=new Float32Array(512);let signalTime=0,smoothed=0;function volume(){if(!recording||!analyser)return;analyser.getFloatTimeDomainData(wave);const rms=Math.sqrt(wave.reduce((s,v)=>s+v*v,0)/wave.length);smoothed=smoothed*.75+rms*.25;$('level').value=Math.min(1,smoothed*8);$('levelFill').style.setProperty('--level',String($('level').value));if(performance.now()-signalTime>250){signalTime=performance.now();setText('signal',smoothed>.005?'正在收音':'收音偏弱');}levelId=requestAnimationFrame(volume);}volume();}catch(e){recording=false;stopping=false;preparing=false;await releaseAudio();ws?.close();error(e.name==='NotAllowedError'?'麦克风权限未开启。请在浏览器地址栏允许麦克风，然后重试。':e.message);sessionControls();health();}}
async function stop(){if(!recording)return;recording=false;stopping=true;$('stop').disabled=true;setText('sessionState','正在保存最后一段英文…');sessionControls();await releaseAudio(true);if(ws?.readyState===1)ws.send('stop');else{stopping=false;sessionControls();health();}}
async function health(){try{const h=await api('/health');lastHealth=h;$('statusDot').className='status-dot '+(h.error?'failed':recording?'recording':h.ready?'ready':'');setText('readiness',h.stage+(h.active&&!recording?' · 其他窗口正在录音':''));setText('queue',h.pending?'中文待处理 '+h.pending+' 段':'中文无积压');$('start').disabled=!h.ready||recording||stopping||preparing||h.active||renaming||historyLoading;sessionControls();setText('start',recording?'录音中':stopping?'保存中':preparing?'等待麦克风…':h.ready?'新建并录音':'模型加载中');if(h.error){healthError=h.error;error(h.error);}else if(healthError){if($('error').textContent===healthError)error('');healthError='';}return h;}catch(e){$('statusDot').className='status-dot failed';setText('readiness','本地服务未连接');$('start').disabled=true;$('newSession').disabled=true;lastHealth=null;}}
async function poll(){if(pollBusy)return;pollBusy=true;let requested='';try{await health();if(!recording&&!stopping&&!preparing&&!deleting&&!deleteTarget&&!renaming&&!historyLoading)await refreshHistory();if(sid&&!historyLoading&&!deleting&&!deleteTarget){requested=sid;const all=await api('/sessions/'+requested);if(sid!==requested||historyLoading)return;for(const r of all){const old=rows.get(r.id);if(!old||old.status!==r.status||old.chinese!==r.chinese)renderRow(r);}updateMetadata();await refreshAudio(requested);}}catch(e){if(e.status===404&&requested===sid&&!recording&&!stopping&&!preparing){await forgetSession(requested);setText('libraryStatus','这堂课已删除，列表已同步。');}else console.warn(e);}finally{pollBusy=false;}}
$('start').onclick=start;$('newSession').onclick=start;$('stop').onclick=stop;
async function loadHistory(requested=sid){
  if(recording||stopping||preparing||renaming||deleting||deleteTarget)return;
  const ticket=++historyRequest;closeRename();captureEnded=false;setText('exportStatus','');Motion.reset($('renameStatus'),false);
  sid=requested;audioInfo=null;historyLoading=true;error('');sessionControls();
  setText('sessionState',requested?'正在加载历史…':'准备开始');
  try{
    const saved=requested?await api('/sessions/'+requested):[];
    if(ticket!==historyRequest||recording||preparing)return;
    await Motion.swap(()=>{
      if(ticket!==historyRequest||recording||preparing)return;
      clearRows();title(requested?sessionCatalog.find(s=>s.id===requested)?.title:'新的课堂，从这里开始');updateMetadata();
      setText('sessionState',requested?'已保存课堂':'准备开始');
      if(requested){setText('emptyTitle','这堂课还没有保存的字幕');setText('emptyHelp','可以选择其他课堂，或开始一次新的录音。');}
      if(saved.length)Motion.reset($('empty'),false);
      for(const row of saved)renderRow(row,false);
      $('reader').scrollTop=0;
    },$('transcript'));
  }catch(e){
    if(ticket!==historyRequest||recording||preparing)return;
    if(e.status===404){await forgetSession(requested);setText('libraryStatus','这堂课已删除，列表已同步。');return;}
    await Motion.swap(()=>{
      if(ticket!==historyRequest||recording||preparing)return;
      clearRows();title(sessionCatalog.find(s=>s.id===requested)?.title);updateMetadata();
      setText('emptyTitle','历史字幕暂时无法加载');setText('emptyHelp','确认本地服务已启动后，点击下方按钮重试。');
      show('retryHistory',true);setText('sessionState','历史加载失败');error(e.message);
    },$('transcript'));
  }finally{if(ticket===historyRequest){historyLoading=false;sessionControls();refreshAudio(requested);}}
}
$('retryHistory').onclick=()=>loadHistory(sid);$('retryList').onclick=()=>refreshHistory().catch(()=>{});
async function exportSession(){
  if(!sid||exporting)return;
  const selected=sid;exporting=true;sessionControls();setText('exportStatus','正在生成文件…');
  try{
    const exportUrl='/sessions/'+selected+'/export';
    const response=await fetch(exportUrl);
    if(!response.ok)throw Error('导出失败，请确认本地服务已启动后重试。');
    await response.blob();const link=document.createElement('a');
    link.href=exportUrl;link.download='classroom-'+selected.slice(0,8)+'.md';document.body.append(link);link.click();link.remove();
    setText('exportStatus','中英对照文件已生成');
  }catch(e){setText('exportStatus','导出未完成');error(e.message);}finally{exporting=false;sessionControls();}
}
$('export').onclick=exportSession;
async function closeDelete(){
  if(deleting||deleteClosing)return;
  deleteClosing=true;
  const dialog=$('deleteDialog');
  const animation=Motion.animate(dialog,[{opacity:1,transform:'none'},{opacity:0,transform:Motion.reduced?'none':'translateY(6px)'}],130);
  if(animation)await animation.finished.catch(()=>{});
  dialog.close();deleteTarget='';deleteClosing=false;sessionControls();
  if(sid)$('deleteLesson').focus();else $('newSession').focus();
}
$('deleteLesson').onclick=()=>{
  if($('deleteLesson').disabled||!sid)return;
  closeRename();deleteTarget=sid;setText('deleteName',$('lessonName').textContent);setText('deleteError','');Motion.reset($('deleteError'),false);
  $('deleteConfirm').disabled=false;$('deleteCancel').disabled=false;setText('deleteConfirm','永久删除');
  $('deleteDialog').showModal();Motion.animate($('deleteDialog'),Motion.reduced?[{opacity:.5},{opacity:1}]:[{opacity:.4,transform:'translateY(8px)'},{opacity:1,transform:'none'}],180);
  sessionControls();$('deleteCancel').focus();
};
$('deleteCancel').onclick=closeDelete;
$('deleteDialog').addEventListener('cancel',e=>{e.preventDefault();if(!deleting)closeDelete();});
$('deleteConfirm').onclick=async()=>{
  if(!deleteTarget||deleting||deleteClosing)return;
  const selected=deleteTarget;deleting=true;sessionControls();$('deleteConfirm').disabled=true;$('deleteCancel').disabled=true;setText('deleteConfirm','正在删除…');
  try{
    try{await api('/sessions/'+selected,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})});}catch(e){if(e.status!==404)throw e;}
    try{await api('/sessions/'+selected);}catch(e){if(e.status!==404)throw e;await forgetSession(selected);}
    if(!deletedSessions.has(selected))throw Error('删除未完成，课堂记录仍在本机，请重试。');
    try{localStorage.setItem('classroom-catalog-change',String(Date.now()));}catch{}
    setText('libraryStatus','课堂及录音已永久删除');setText('exportStatus','');
    deleting=false;await closeDelete();refreshHistory().catch(()=>{setText('libraryStatus','已删除；课堂列表暂时无法刷新。');});
  }catch(e){setText('deleteError',e.message);show('deleteError',true);}
  finally{deleting=false;$('deleteConfirm').disabled=false;$('deleteCancel').disabled=false;setText('deleteConfirm','永久删除');sessionControls();}
};
$('downloadAudio').onclick=async()=>{
  if(!sid||audioDownloading||recording||stopping)return;
  const selected=sid;audioDownloading=true;sessionControls();setText('exportStatus','正在准备录音…');
  try{
    const info=await api('/sessions/'+selected+'/audio/info');
    if(!info.available)throw Error('录音暂不可下载，请结束录音后重试。');
    const link=document.createElement('a');link.href='/sessions/'+selected+'/audio';link.download='classroom-'+selected.slice(0,8)+'.wav';document.body.append(link);link.click();link.remove();setText('exportStatus','已开始下载 WAV 录音');
  }catch(e){setText('exportStatus','录音下载未完成');error(e.message);}
  finally{audioDownloading=false;sessionControls();}
};
$('size').oninput=()=>{document.documentElement.style.setProperty('--subtitle',$('size').value+'px');setText('sizeValue',$('size').value);};
$('rename').onclick=()=>{
  if(!sid||renaming)return;renameTarget=sid;$('renameInput').value=$('lessonName').textContent;
  Motion.swap(()=>{Motion.reset($('titleDisplay'),false);Motion.reset($('renameForm'),true);Motion.reset($('renameStatus'),false);},document.querySelector('.identity'));$('renameInput').focus();$('renameInput').select();
};
$('renameCancel').onclick=()=>{closeRename();$('rename').focus();};
$('renameInput').onkeydown=e=>{if(e.key==='Escape'){$('renameCancel').click();}};
$('renameForm').onsubmit=async e=>{
  e.preventDefault();if(renaming||!renameTarget)return;const requested=renameTarget,value=$('renameInput').value.trim();
  if(!value){setText('renameStatus','请输入课堂名称。');show('renameStatus',true);return;}
  renaming=true;sessionControls();$('renameSave').disabled=true;$('renameCancel').disabled=true;$('renameInput').disabled=true;setText('renameSave','保存中…');
  try{
    const updated=await api('/sessions/'+requested,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:value})});
    const item=sessionCatalog.find(s=>s.id===requested);if(item)item.title=updated.title;
    if(sid===requested){title(updated.title);closeRename();setText('renameStatus','名称已保存');show('renameStatus',true);}
    await refreshHistory();
  }catch(e){setText('renameStatus','改名未完成，请确认服务连接后重试。');show('renameStatus',true);}
  finally{renaming=false;$('renameSave').disabled=false;$('renameCancel').disabled=false;$('renameInput').disabled=false;setText('renameSave','保存');sessionControls();health();}
};
$('helpToggle').onclick=()=>{const expanded=$('helpToggle').getAttribute('aria-expanded')!=='true';$('helpToggle').setAttribute('aria-expanded',String(expanded));show('help',expanded);};
const mobileLayout=matchMedia('(max-width:1000px)');const narrowLayout=matchMedia('(max-width:720px)');
function syncPanel(){const mobile=mobileLayout.matches;document.querySelector('aside').classList.remove('expanded');$('panelToggle').setAttribute('aria-expanded','false');Motion.reset($('sidebarContent'),!mobile);}
mobileLayout.addEventListener('change',syncPanel);syncPanel();
$('panelToggle').onclick=()=>{
  const expanded=$('panelToggle').getAttribute('aria-expanded')!=='true';$('panelToggle').setAttribute('aria-expanded',String(expanded));
  if(expanded)document.querySelector('aside').classList.add('expanded');
  const done=Motion.visible($('sidebarContent'),expanded);
  Promise.resolve(done).then(()=>{if(!expanded&&mobileLayout.matches&&$('panelToggle').getAttribute('aria-expanded')==='false')document.querySelector('aside').classList.remove('expanded');});
};
function syncLibrary(){Motion.reset($('libraryContent'),!narrowLayout.matches);$('recordsToggle').setAttribute('aria-expanded',String(!narrowLayout.matches));}
narrowLayout.addEventListener('change',syncLibrary);syncLibrary();
$('recordsToggle').onclick=()=>{const expanded=$('recordsToggle').getAttribute('aria-expanded')!=='true';$('recordsToggle').setAttribute('aria-expanded',String(expanded));show('libraryContent',expanded);};
$('home').onclick=()=>loadHistory('');
for(const id of ['course','terms']){$(id).value=localStorage.getItem('classroom-'+id)||'';$(id).oninput=()=>localStorage.setItem('classroom-'+id,$(id).value);}
window.addEventListener('beforeunload',e=>{if(recording||stopping){e.preventDefault();e.returnValue='';}});
window.addEventListener('focus',()=>poll());
window.addEventListener('storage',e=>{if(e.key==='classroom-catalog-change')poll();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
health();refreshHistory().then(()=>{if(sessionCatalog.length&&!sid&&!recording&&!preparing)loadHistory(sessionCatalog[0].id);}).catch(()=>{});devices().catch(()=>{});setInterval(poll,2000);
