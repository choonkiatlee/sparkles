// C3b: buffered original-image comparison. Never replace a displayed frame
// until every requested next frame has finished loading/decoding.
import { FRAME_PREFETCH, createFramePreloader, createBufferedFrameCoordinator,
  frameIndexAt,stepPosition } from "./rotation.mjs";

const el=(tag,className="",text=null)=>{
  const node=document.createElement(tag);
  if(className)node.className=className;
  if(text!==null)node.textContent=String(text);
  return node;
};

export function createRotationPlayer({host,slots,config=FRAME_PREFETCH}) {
  const stones=new Map();
  let position=0, timer=null, playToken=0, destroyed=false;
  let preloader, unsubscribe;
  const coordinator=createBufferedFrameCoordinator(urls=>preloader.focus(urls));

  const top=el("div","motion-toolbar-main");
  const intro=el("div","motion-toolbar-intro");
  intro.append(el("strong","", "Synchronized original rotations"),
    el("p","subtle","Relative sequence position only · physical angles and crown phase are not aligned"));
  top.append(intro);
  const controls=el("div","motion-controls");
  const back=el("button","motion-step","← Step");
  const play=el("button","motion-play","Play");
  const forward=el("button","motion-step","Step →");
  for(const button of [back,play,forward])button.type="button";
  const sliderLabel=el("label","motion-range-label","Position");
  const slider=el("input","motion-slider");
  slider.type="range";slider.min="0";slider.max="1000";slider.step="1";slider.value="0";
  slider.setAttribute("aria-label","Shared relative rotation position");
  const positionText=el("span","motion-position","0%");
  sliderLabel.append(slider,positionText);
  controls.append(back,play,forward,sliderLabel);
  top.append(controls);
  host.append(top);

  const loadBar=el("div","motion-prefetch-row");
  const prefetchLabel=el("label","motion-prefetch-label");
  const prefetchToggle=el("input");
  prefetchToggle.type="checkbox";
  prefetchToggle.checked=config.mode==="all";
  prefetchToggle.setAttribute("aria-label","Preload every original rotation frame for selected stones");
  prefetchLabel.append(prefetchToggle,
    el("span","", "Preload all frames (uses more data)"));
  const progress=el("span","motion-prefetch-progress","Waiting for saved rotations");
  progress.setAttribute("role","status");
  progress.setAttribute("aria-live","off");
  loadBar.append(prefetchLabel,progress);host.append(loadBar);

  const ready=()=>[...stones.values()].filter(item=>item.rotation?.status==="available");
  const steps=()=>Math.max(1,...ready().map(item=>item.rotation.frameCount));
  const allUrls=()=>ready().map(item=>item.rotation);
  const bytes=()=>ready().reduce((sum,item)=>sum+(item.rotation.totalBytes||0),0);
  function updateProgress(state) {
    if(destroyed)return;
    if(!ready().length){
      progress.textContent="Waiting for usable saved rotations";
      return;
    }
    if(state.mode==="all"){
      const size=bytes();
      const sizeText=size ? " · ~"+(size/1048576).toFixed(1)+" MiB source media" : "";
      progress.textContent="Preloaded "+state.completed+" / "+state.total+" frames"+
        (state.failed ? " · "+state.failed+" failed" : "")+sizeText;
    }else if(state.mode==="nearby"){
      progress.textContent="Nearby prefetch enabled · "+state.completed+" frames loaded";
    }else{
      progress.textContent="Loading frames on demand";
    }
  }
  function installPreloader(mode) {
    unsubscribe?.();
    preloader?.stop();
    preloader=createFramePreloader({mode,nearbyRadius:config.nearbyRadius,
      maxConcurrent:config.maxConcurrent,maxDecoded:config.maxDecoded});
    unsubscribe=preloader.subscribe(updateProgress);
  }
  function syncControls() {
    const enabled=ready().length>0;
    for(const control of [play,back,forward,slider])control.disabled=!enabled;
    positionText.textContent=Math.round(position*100)+"%";
    slider.value=String(Math.round(position*1000));
  }
  function pause() {
    playToken++;
    if(timer!==null){clearTimeout(timer);timer=null;}
    play.textContent="Play";
    play.setAttribute("aria-label","Play synchronized original rotations");
  }
  function present(item,frame,index,image) {
    // This is an already-decoded <img>. The old frame stays in place until this
    // synchronous replacement, so there is no blank intermediary src change.
    image.className="motion-image";
    image.alt="Original frame "+(index+1)+" of "+item.rotation.frameCount+
      " for "+item.report+"; camera angle not calibrated";
    image.draggable=false;
    item.stage.replaceChildren(image);
    item.currentURL=frame.url;
    item.currentIndex=index;
    item.error.hidden=true;
    item.caption.textContent="Frame "+(index+1)+" / "+item.rotation.frameCount+
      " · source "+frame.sourceIndex;
  }
  async function seek(next) {
    if(destroyed || !Number.isFinite(next))return false;
    position=Math.max(0,Math.min(0.999999,next));
    syncControls();
    const selected=ready();
    if(!selected.length)return false;
    const targets=selected.map(item=>{
      const index=frameIndexAt(position,item.rotation.frameCount);
      return {item,index,frame:item.rotation.frames[index]};
    });
    for(const {item,index} of targets) {
      if(item.currentIndex!==index){
        item.caption.textContent="Loading frame "+(index+1)+" / "+item.rotation.frameCount+
          " · previous frame held";
      }
    }
    const promise=coordinator.seek(targets.map(x=>x.frame.url),images=>{
      targets.forEach(({item,index,frame},i)=>{
        const image=images[i];
        if(image)present(item,frame,index,image);
        else {
          // Preserve the last successfully decoded frame on all network errors.
          item.error.hidden=false;
          item.caption.textContent="Frame "+(index+1)+" unavailable · previous frame retained";
        }
      });
    });
    // Make the requested frames high priority before scheduling bulk work.
    preloader.observe(allUrls(),position);
    return promise;
  }
  async function playNext(token) {
    if(destroyed || token!==playToken)return;
    const target=stepPosition(position,steps(),1);
    await seek(target);
    if(destroyed || token!==playToken)return;
    // Wait for all selected next frames before advancing. Slow networking
    // reduces frame rate instead of presenting blank/mismatched columns.
    timer=setTimeout(()=>playNext(token),105);
  }
  function togglePlay() {
    if(timer!==null || play.textContent==="Pause"){pause();return;}
    if(!ready().length)return;
    pause();
    play.textContent="Pause";
    play.setAttribute("aria-label","Pause synchronized original rotations");
    const token=playToken;
    timer=setTimeout(()=>playNext(token),0);
  }
  slider.addEventListener("input",()=>{
    pause();seek(Number(slider.value)/1000);
  });
  back.addEventListener("click",()=>{pause();seek(stepPosition(position,steps(),-1));});
  forward.addEventListener("click",()=>{pause();seek(stepPosition(position,steps(),1));});
  play.addEventListener("click",togglePlay);
  prefetchToggle.addEventListener("change",()=>{
    pause();coordinator.invalidate();
    installPreloader(prefetchToggle.checked?"all":"nearby");
    seek(position);
  });

  function setStone(id,rotation,representative,report=id) {
    if(destroyed || !slots.has(id))return;
    const slot=slots.get(id);
    slot.replaceChildren();
    const item={rotation,slot,report,currentURL:null,currentIndex:-1};
    stones.set(id,item);
    if(rotation?.status!=="available"){
      const fallback=el("div","motion-empty");
      if(representative?.url){
        const image=el("img","motion-static");
        image.src=representative.url;
        image.alt="Original still for "+report;
        image.loading="lazy";image.decoding="async";
        fallback.append(image);
      }
      fallback.append(el("span","motion-unavailable",
        rotation?.reason || "No complete ordered original rotation"));
      slot.append(fallback);
      syncControls();updateProgress(preloader.stats());
      return;
    }
    const figure=el("figure","motion-figure");
    item.stage=el("div","motion-image-stage");
    item.stage.append(el("span","motion-unavailable","Loading original frame…"));
    item.error=el("div","motion-frame-error");
    item.error.hidden=true;
    const retry=el("button","motion-retry","Retry frame");
    retry.type="button";
    retry.addEventListener("click",async()=>{
      const index=frameIndexAt(position,item.rotation.frameCount);
      await preloader.retry(item.rotation.frames[index].url);
      if(!destroyed)seek(position);
    });
    item.error.append(el("span","", "Original frame failed to load"),retry);
    item.caption=el("figcaption","motion-frame-caption","");
    figure.append(item.stage,item.error,item.caption);
    slot.append(figure);
    syncControls();
    seek(position);
  }
  function failStone(id) {
    if(!slots.has(id) || destroyed)return;
    stones.delete(id);
    slots.get(id).replaceChildren(el("span","motion-unavailable","Motion manifest unavailable; retry this column"));
    coordinator.invalidate();
    if(!ready().length)pause();
    syncControls();
    updateProgress(preloader.stats());
  }
  function destroy() {
    if(destroyed)return;
    destroyed=true;pause();coordinator.close();
    unsubscribe?.();preloader.stop();stones.clear();
  }

  installPreloader(config.mode);
  syncControls();
  return {setStone,failStone,destroy,seek};
}
