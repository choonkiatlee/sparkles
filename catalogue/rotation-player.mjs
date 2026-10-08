// C3b flicker-resistant synchronized viewer. A frame only replaces the
// currently displayed frame after its image has loaded and decoded.
// Full prefetch is default for *selected* stones, with explicit progress.
import { FRAME_PREFETCH, createFramePreloader, frameIndexAt, stepPosition } from "./rotation.mjs";

const el=(tag,cls="",text=null)=>{
  const node=document.createElement(tag);
  if(cls) node.className=cls;
  if(text!==null) node.textContent=String(text);
  return node;
};

export function createRotationPlayer({host,slots,config=FRAME_PREFETCH}) {
  const stones=new Map();
  let position=0,clock=null,destroyed=false;
  const top=el("div","motion-toolbar-main");
  const lead=el("div","motion-toolbar-intro");
  lead.append(el("strong","","Synchronized original rotations"),
    el("p","subtle","Relative frame position only · original images · no calibrated angles or face-up phase alignment"));
  const progress=el("div","motion-load-progress");
  progress.setAttribute("role","status");
  progress.setAttribute("aria-live","polite");
  const progressTrack=el("progress","motion-progress-bar");
  const progressCaption=el("span","motion-progress-label","Waiting for selected manifests…");
  progress.append(progressTrack,progressCaption);
  lead.append(progress);
  top.append(lead);
  const controls=el("div","motion-controls");
  const back=el("button","motion-step","← Step");
  const play=el("button","motion-play","Play");
  const forward=el("button","motion-step","Step →");
  for(const button of [back,play,forward]) button.type="button";
  const sliderLabel=el("label","motion-range-label","Position");
  const slider=el("input","motion-slider");
  slider.type="range";slider.min="0";slider.max="1000";slider.step="1";slider.value="0";
  slider.setAttribute("aria-label","Shared relative rotation position");
  const valueLabel=el("span","motion-position","0%");
  sliderLabel.append(slider,valueLabel);
  controls.append(back,play,forward,sliderLabel);
  top.append(controls);
  host.append(top);

  let preloader;
  const ready=()=>[...stones.values()].filter(x=>x.rotation?.status==="available");
  const allManifestsResolved=()=>stones.size===slots.size;
  const canPlay=()=>{
    if(!allManifestsResolved() || ready().length===0) return false;
    if(config.mode!=="all") return true;
    return preloader?.stats().complete===true;
  };
  const currentStepCount=()=>Math.max(1,...ready().map(x=>x.rotation.frameCount));
  function syncControls() {
    if(destroyed) return;
    const hasMotion=ready().length>0;
    back.disabled=!hasMotion;forward.disabled=!hasMotion;slider.disabled=!hasMotion;
    play.disabled=!canPlay();
    const s=preloader.stats();
    if(config.mode==="all") {
      progress.hidden=false;
      progressTrack.max=Math.max(1,s.total);
      progressTrack.value=s.loaded+s.failed;
      if(!allManifestsResolved()) {
        progressCaption.textContent="Loading selected motion manifests… "+s.loaded+" frames cached";
      } else if(s.total===0) {
        progressCaption.textContent="No ordered rotation sequences available";
      } else if(s.complete) {
        progressCaption.textContent=s.failed ?
          "Prefetch finished: "+s.loaded+"/"+s.total+" loaded, "+s.failed+" unavailable (playback may skip frames)" :
          "Ready: "+s.loaded+"/"+s.total+" original frames prefetched";
      } else {
        progressCaption.textContent="Preparing playback: "+(s.loaded+s.failed)+"/"+s.total+
          " frames · "+s.active+" downloading";
      }
    } else {
      progress.hidden=(config.mode==="none");
      if(config.mode==="nearby") progressCaption.textContent="Prefetching nearby frames";
    }
    valueLabel.textContent=Math.round(position*100)+"%";
    slider.value=String(Math.round(position*1000));
  }
  preloader=createFramePreloader({
    mode:config.mode,nearbyRadius:config.nearbyRadius,
    maxConcurrent:config.maxConcurrent,
    onProgress:syncControls
  });

  function frameError(item,index,label) {
    item.pendingError.hidden=false;
    item.pendingErrorMessage.textContent="Frame "+(index+1)+" "+label+" · ";
    // Preserve the last good visible image, including during autoplay.
    item.placeholder.textContent=item.shownIndex<0 ? "Original frame unavailable" : "";
    item.placeholder.hidden=item.shownIndex>=0;
    item.caption.textContent=item.shownIndex<0 ?
      "Original frame could not load" :
      "Frame "+(item.shownIndex+1)+" / "+item.rotation.frameCount+" displayed · requested "+(index+1)+" unavailable";
  }

  function renderStone(item,{force=false}={}) {
    if(destroyed || item.rotation?.status!=="available") return;
    const index=frameIndexAt(position,item.rotation.frameCount);
    const frame=item.rotation.frames[index];
    if(!force && item.requestedURL===frame.url) return;
    if(!force && item.shownURL===frame.url) {
      item.pendingError.hidden=true;
      item.caption.textContent="Frame "+(index+1)+" / "+item.rotation.frameCount+
        " · source index "+frame.sourceIndex;
      return;
    }
    const serial=++item.serial;
    item.requestedURL=frame.url;
    item.requestedIndex=index;
    item.pendingError.hidden=true;
    const target=item.back;
    target.hidden=true;
    target.onload=null;target.onerror=null;
    target.alt="Original frame "+(index+1)+" / "+item.rotation.frameCount+
      " for "+item.report+"; physical angle not calibrated";
    item.caption.textContent=item.shownIndex<0 ?
      "Loading original frame "+(index+1)+" / "+item.rotation.frameCount :
      "Frame "+(item.shownIndex+1)+" displayed · preparing "+(index+1);
    item.placeholder.hidden=item.shownIndex>=0;
    const stale=()=>destroyed || serial!==item.serial ||
      item.requestedURL!==frame.url;
    function commit() {
      if(stale()) return;
      const prior=item.front;
      // Swap in one browser task; the old image remains until the new
      // source has been loaded and decoded, so requests never blank the view.
      target.hidden=false;
      prior.hidden=true;
      item.front=target;item.back=prior;
      item.back.onload=null;item.back.onerror=null;
      item.shownURL=frame.url;item.shownIndex=index;
      item.placeholder.hidden=true;item.pendingError.hidden=true;
      item.caption.textContent="Frame "+(index+1)+" / "+item.rotation.frameCount+
        " · original source index "+frame.sourceIndex;
    }
    target.onload=()=>{
      if(stale()) return;
      if(typeof target.decode==="function") {
        target.decode().then(commit,()=>{
          if(!stale()) frameError(item,index,"could not decode");
        });
      } else commit();
    };
    target.onerror=()=>{if(!stale()) frameError(item,index,"could not load");};
    target.src=frame.url;
  }

  function refresh() {
    if(destroyed) return;
    syncControls();
    for(const item of ready()) renderStone(item);
    preloader.observe(ready().map(x=>x.rotation),position);
  }
  function seek(normalized) {
    if(!Number.isFinite(normalized)) return;
    position=Math.max(0,Math.min(0.999999,normalized));
    refresh();
  }
  function step(direction) {seek(stepPosition(position,currentStepCount(),direction));}
  function pause() {
    if(clock!==null){clearInterval(clock);clock=null;}
    play.textContent="Play";
    play.setAttribute("aria-label","Play synchronized rotations");
  }
  function toggle() {
    if(clock!==null){pause();return;}
    if(!canPlay()) return;
    play.textContent="Pause";
    play.setAttribute("aria-label","Pause synchronized rotations");
    clock=setInterval(()=>step(1),120);
  }
  slider.addEventListener("input",()=>{pause();seek(Number(slider.value)/1001);});
  back.addEventListener("click",()=>{pause();step(-1);});
  forward.addEventListener("click",()=>{pause();step(1);});
  play.addEventListener("click",toggle);
  const onVisibility=()=>{if(document.hidden) pause();};
  document.addEventListener("visibilitychange",onVisibility);

  function setStone(id,rotation,representative,report=id) {
    if(destroyed || !slots.has(id)) return;
    const slot=slots.get(id);
    const previous=stones.get(id);
    if(previous) previous.serial++;
    slot.replaceChildren();
    const item={rotation,slot,report,serial:0,requestedURL:null,
      requestedIndex:-1,shownURL:null,shownIndex:-1};
    stones.set(id,item);
    if(rotation?.status!=="available") {
      const fallback=el("div","motion-empty");
      fallback.append(el("span","motion-unavailable",
        rotation?.reason || "No complete ordered rotation"));
      if(representative?.url) {
        const image=el("img","motion-static");
        image.src=representative.url;
        image.alt="Original representative still for "+report;
        image.loading="lazy";image.decoding="async";
        fallback.prepend(image);
      }
      slot.append(fallback);
      refresh();return;
    }
    const figure=el("figure","motion-figure");
    const stage=el("div","motion-stage");
    const front=el("img","motion-image");
    const backImage=el("img","motion-image");
    front.hidden=true;backImage.hidden=true;
    front.decoding="async";backImage.decoding="async";
    const placeholder=el("span","motion-placeholder","Loading first original frame…");
    stage.append(front,backImage,placeholder);
    const fail=el("div","motion-frame-error");
    fail.hidden=true;
    const failMessage=el("span");
    const retry=el("button","motion-retry","Retry frame");
    retry.type="button";
    retry.addEventListener("click",()=>{
      const index=frameIndexAt(position,item.rotation.frameCount);
      preloader.retry(item.rotation.frames[index].url);
      renderStone(item,{force:true});
    });
    fail.append(failMessage,retry);
    const caption=el("figcaption","motion-frame-caption");
    figure.append(stage,fail,caption);
    slot.append(figure);
    Object.assign(item,{front,back:backImage,placeholder,
      pendingError:fail,pendingErrorMessage:failMessage,caption});
    refresh();
  }
  function failStone(id) {
    if(!slots.has(id) || destroyed) return;
    const previous=stones.get(id);
    if(previous) previous.serial++;
    stones.delete(id);
    slots.get(id).replaceChildren(
      el("span","motion-unavailable","Motion manifest unavailable; retry this column"));
    if(!ready().length) pause();
    refresh();
  }
  function destroy() {
    if(destroyed)return;
    pause();destroyed=true;
    document.removeEventListener("visibilitychange",onVisibility);
    for(const item of stones.values()) item.serial++;
    preloader.stop();stones.clear();
  }
  syncControls();
  return {setStone,failStone,destroy,seek};
}
