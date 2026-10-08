// Buffered original-image comparison. Keep prior decoded frames visible until
// every selected next frame is ready; avoid frame-by-frame DOM status updates.
import { FRAME_PREFETCH, createFramePreloader, createBufferedFrameCoordinator,
  frameIndexAt,stepPosition } from "./rotation.mjs";
import {createPreviewCache,createCanvasSurface} from "./rotation-canvas.mjs";

const el=(tag,className="",text=null)=>{
  const node=document.createElement(tag);
  if(className)node.className=className;
  if(text!==null)node.textContent=String(text);
  return node;
};

export function createRotationPlayer({host,slots,config=FRAME_PREFETCH}) {
  const stones=new Map();
  let position=0, timer=null, playToken=0, destroyed=false;
  let preloader,frameUnsubscribe;
  const previews=createPreviewCache();
  let scrubRaf=null, pendingScrub=null, drag=null;
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
  sliderLabel.append(slider);
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
  // The old rapidly changing preload counter competed with the diamonds.
  // Keep the user-controlled preload switch, not per-download status text.
  loadBar.append(prefetchLabel);host.append(loadBar);

  const ready=()=>[...stones.values()].filter(item=>item.rotation?.status==="available");
  const steps=()=>Math.max(1,...ready().map(item=>item.rotation.frameCount));
  const allUrls=()=>ready().map(item=>item.rotation);
  function installPreloader(mode) {
    frameUnsubscribe?.();
    preloader?.stop();
    preloader=createFramePreloader({mode,nearbyRadius:config.nearbyRadius,
      maxConcurrent:config.maxConcurrent,maxDecoded:config.maxDecoded});
    frameUnsubscribe=preloader.subscribeFrames((url,image)=>previews.add(url,image));
  }
  function syncControls() {
    const enabled=ready().length>0;
    for(const control of [play,back,forward,slider])control.disabled=!enabled;
     slider.value=String(Math.round(position*1000));
  }
  // Pointer/slider events may arrive many times between repaints. Fetch and
  // render only the most recent requested position once per animation frame.
  function cancelScrub() {
    if(scrubRaf!==null)globalThis.cancelAnimationFrame?.(scrubRaf);
    scrubRaf=null;pendingScrub=null;
  }
  function queueScrub(next) {
    if(destroyed || !Number.isFinite(next))return;
    pendingScrub=next;
    if(scrubRaf!==null)return;
    if(typeof globalThis.requestAnimationFrame!=="function"){
      pendingScrub=null;seek(next,{interactive:true});return;
    }
    scrubRaf=globalThis.requestAnimationFrame(()=>{
      scrubRaf=null;
      const latest=pendingScrub;
      pendingScrub=null;
      if(latest!==null)seek(latest,{interactive:true});
    });
  }
  function pause() {
    playToken++;
    if(timer!==null){clearTimeout(timer);timer=null;}
    play.textContent="Play";
    play.setAttribute("aria-label","Play synchronized original rotations");
  }
  function present(item,frame,index,image) {
    if(item.surface){
      if(!item.surface.draw(image))return false;
    }else{
      // Canvas2D unavailable: retain the original decoded <img> fallback.
      image.className="motion-image";
      image.alt="Original frame "+(index+1)+" of "+item.rotation.frameCount+
        " for "+item.report+"; camera angle not calibrated";
      image.draggable=false;
      item.stage.replaceChildren(image);
    }
    item.currentURL=frame.url;
    item.currentIndex=index;
    item.error.hidden=true;
    return true;
  }
  // The preview cache stores downscaled canvases derived from source frames
  // as full-resolution downloads finish. Both columns must have previews
  // before we display either, preserving the aligned ordinal comparison.
  function showPreviews(targets) {
    if(!targets.every(({item})=>Boolean(item.surface)))return false;
    const images=targets.map(({frame})=>previews.get(frame.url));
    if(images.some(image=>!image))return false;
    coordinator.invalidate();
    return targets.every(({item,index,frame},i)=>
      present(item,frame,index,images[i]));
  }
  async function seek(next,{interactive=false}={}) {
    if(destroyed || !Number.isFinite(next))return false;
    position=Math.max(0,Math.min(0.999999,next));
    syncControls();
    const selected=ready();
    if(!selected.length)return false;
    const targets=selected.map(item=>{
      const index=frameIndexAt(position,item.rotation.frameCount);
      return {item,index,frame:item.rotation.frames[index]};
    });
    const previewShown=showPreviews(targets);
    // While dragging or playing, a cached small preview is enough. When the
    // user releases the gesture (or steps), seek originals for full detail.
    // If any preview is missing, wait for all original frames as before.
    if(previewShown && interactive){
      preloader.observe(allUrls(),position);
      return true;
    }
    const promise=coordinator.seek(targets.map(x=>x.frame.url),images=>{
      targets.forEach(({item,index,frame},i)=>{
        const image=images[i];
        if(image)present(item,frame,index,image);
        else if(!previews.get(frame.url)){
          // Keep the last successfully painted frame, even on network errors.
          item.error.hidden=false;
        }
      });
    });
    preloader.observe(allUrls(),position);
    return promise;
  }
  async function playNext(token) {
    if(destroyed || token!==playToken)return;
    const target=stepPosition(position,steps(),1);
    await seek(target,{interactive:true});
    if(destroyed || token!==playToken)return;
    // Wait for all selected next frames before advancing. Slow networking
    // reduces frame rate instead of presenting blank/mismatched columns.
    timer=setTimeout(()=>playNext(token),55);
  }
  function togglePlay() {
    if(timer!==null || play.textContent==="Pause"){
      pause();cancelScrub();seek(position);return;
    }
    if(!ready().length)return;
    pause();cancelScrub();
    play.textContent="Pause";
    play.setAttribute("aria-label","Pause synchronized original rotations");
    const token=playToken;
    timer=setTimeout(()=>playNext(token),0);
  }
  slider.addEventListener("input",()=>{
    pause();queueScrub(Number(slider.value)/1000);
  });
  back.addEventListener("click",()=>{pause();cancelScrub();seek(stepPosition(position,steps(),-1));});
  forward.addEventListener("click",()=>{pause();cancelScrub();seek(stepPosition(position,steps(),1));});
  slider.addEventListener("change",()=>{
    const latest=pendingScrub;
    cancelScrub();seek(latest===null?position:latest);
  });
  play.addEventListener("click",togglePlay);
  prefetchToggle.addEventListener("change",()=>{
    pause();cancelScrub();coordinator.invalidate();
    installPreloader(prefetchToggle.checked?"all":"nearby");
    seek(position);
  });

  // Familiar product-spin interaction: horizontal drag on any image controls
  // the shared normalized position; vertical touch scrolling stays available.
  function installDrag(item) {
    const stage=item.stage;
    stage.setAttribute("aria-label","Drag horizontally to rotate "+item.report);
    stage.addEventListener("pointerdown",event=>{
      if(drag || !Number.isFinite(event.clientX) ||
         (event.pointerType==="mouse" && event.button!==0))return;
      pause();cancelScrub();
      drag={item,pointerId:event.pointerId,startX:event.clientX,startPosition:position};
      stage.setPointerCapture?.(event.pointerId);
    });
    stage.addEventListener("pointermove",event=>{
      if(drag?.item!==item || drag.pointerId!==event.pointerId ||
         !Number.isFinite(event.clientX))return;
      const turns=(event.clientX-drag.startX)/450;
      queueScrub(((drag.startPosition+turns)%1+1)%1);
    });
    const finish=event=>{
      if(drag?.item!==item || drag.pointerId!==event.pointerId)return;
      drag=null;
      const latest=pendingScrub;
      cancelScrub();
      // A release may arrive before the queued animation-frame callback.
      // Always paint its latest target, then refine from the original.
      seek(latest===null?position:latest);
      if(event.type!=="lostpointercapture")stage.releasePointerCapture?.(event.pointerId);
    };
    for(const type of ["pointerup","pointercancel","lostpointercapture"])
      stage.addEventListener(type,finish);
  }

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
      syncControls();
      return;
    }
    const figure=el("figure","motion-figure");
    item.stage=el("div","motion-image-stage");
    item.stage.append(el("span","motion-unavailable","Loading original frame…"));
    item.surface=createCanvasSurface(item.stage,report);
    installDrag(item);
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
    figure.append(item.stage,item.error);
    slot.append(figure);
    syncControls();
    seek(position);
  }
  function failStone(id) {
    if(!slots.has(id) || destroyed)return;
    if(drag?.item===stones.get(id))drag=null;
    stones.delete(id);
    slots.get(id).replaceChildren(el("span","motion-unavailable","Motion manifest unavailable; retry this column"));
    coordinator.invalidate();
    if(!ready().length)pause();
    syncControls();
   }
  function destroy() {
    if(destroyed)return;
    destroyed=true;pause();cancelScrub();coordinator.close();
    frameUnsubscribe?.();preloader.stop();previews.clear();stones.clear();drag=null;
  }

  installPreloader(config.mode);
  syncControls();
  return {setStone,failStone,destroy,seek};
}
