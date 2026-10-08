// C3b: atomic, flicker-free ordinal playback from original saved images.
// The frame loader finishes loading/decoding *all selected panes* before
// committing a new synchronized position. The previous images stay mounted.
import {FRAME_PREFETCH,createFramePreloader,createBufferedFrameCoordinator,
  frameIndexAt,stepPosition} from "./rotation.mjs";

const el=(tag,cls="",txt=null)=>{
  const n=document.createElement(tag);
  if(cls)n.className=cls;
  if(txt!==null)n.textContent=String(txt);
  return n;
};

export function createRotationPlayer({host,slots,config=FRAME_PREFETCH}){
  const stones=new Map();
  const preloader=createFramePreloader({
    mode:config.mode,nearbyRadius:config.nearbyRadius,
    maxConcurrent:config.maxConcurrent,maxDecoded:config.maxDecoded,
  });
  const coordinator=createBufferedFrameCoordinator(urls=>preloader.focus(urls));
  let position=0,clock=null,destroyed=false,pending=false,sequence=0,speed=1;
  const toolbar=el("div","motion-toolbar-main");
  const intro=el("div","motion-toolbar-intro");
  intro.append(el("strong","","Synchronized original rotations"),
    el("p","subtle","Shared relative frame position · no calibrated camera angle or crown-phase matching"));
  const progressLine=el("div","motion-progress-line");
  const progress=el("progress","motion-progress");
  progress.max=1;progress.value=0;
  progress.setAttribute("aria-label","Prefetch progress for original rotation images");
  const progressText=el("span","motion-progress-label","Loading selected original rotations");
  progressLine.append(progress,progressText);
  intro.append(progressLine);
  toolbar.append(intro);
  const controls=el("div","motion-controls");
  const back=el("button","motion-step","← Step");
  const play=el("button","motion-play","Play");
  const forward=el("button","motion-step","Step →");
  for(const button of [back,play,forward])button.type="button";
  const speedLabel=el("label","motion-speed-label","Speed");
  const speedSelect=el("select","motion-speed");
  speedSelect.setAttribute("aria-label","Rotation playback speed");
  for(const rate of [0.5,1,2]){
    const option=el("option","",rate+"×");
    option.value=String(rate);
    if(rate===1)option.selected=true;
    speedSelect.append(option);
  }
  speedLabel.append(speedSelect);
  const sliderLabel=el("label","motion-range-label","Position");
  const slider=el("input","motion-slider");
  slider.type="range";slider.min="0";slider.max="1000";slider.step="1";slider.value="0";
  slider.setAttribute("aria-label","Shared ordinal rotation position");
  const ordinalText=el("span","motion-position","0%");
  ordinalText.setAttribute("aria-live","off");
  sliderLabel.append(slider,ordinalText);
  controls.append(back,play,forward,speedLabel,sliderLabel);
  toolbar.append(controls);host.append(toolbar);
  const status=el("p","motion-playback-status","Original images load only for selected diamonds");
  status.setAttribute("role","status");
  host.append(status);

  const present=()=>[...stones.values()].filter(entry=>entry.rotation?.status==="available");
  const stepCount=()=>Math.max(1,...present().map(entry=>entry.rotation.frameCount));
  const describe=(msg)=>{if(!destroyed)status.textContent=msg;};
  const stopPlayback=()=>{
    if(clock!==null){clearInterval(clock);clock=null;}
    play.textContent="Play";play.setAttribute("aria-label","Play synchronized rotations");
  };
  const syncControls=()=>{
    const enabled=present().length>0;
    for(const control of [play,back,forward,slider,speedSelect])control.disabled=!enabled;
    slider.value=String(Math.round(position*1000));
    ordinalText.textContent=Math.round(position*100)+"%";
  };
  const unsubscribe=preloader.subscribe(info=>{
    if(destroyed)return;
    progress.max=Math.max(1,info.total);
    progress.value=info.completed;
    const bytes=present().reduce((sum,entry)=>sum+(entry.rotation.totalBytes||0),0);
    const size=bytes>0?" · about "+(bytes/1048576).toFixed(1)+" MiB total":"";
    progressText.textContent=info.total ?
      "Prefetched "+info.completed+" / "+info.total+" frames"+
      (info.failed?" · "+info.failed+" unavailable":"")+size :
      "Waiting for selected rotation manifests";
  });
  function showFallback(item,representative){
    const box=el("div","motion-empty");
    box.append(el("span","motion-unavailable",item.rotation?.reason ||
      "Original rotation unavailable"));
    if(representative?.url){
      const img=el("img","motion-static");
      img.src=representative.url;
      img.alt="Original representative still for "+item.report;
      img.loading="lazy";img.decoding="async";
      box.prepend(img);
    }
    item.slot.append(box);
  }
  // Only append loaded+decoded Image nodes. Crucially never change the src
  // attribute of a currently visible image while waiting for the next frame.
  function commitFrames(items,frames,images,target){
    // Reject partial/error batches; leave every previously displayed image
    // intact so the comparison never flashes a blank/mismatched state.
    if(images.some(image=>!image)){
      stopPlayback();
      describe("A source frame did not load. Previous frames retained; Retry frame or scrub again.");
      for(const item of items)item.error.hidden=false;
      return;
    }
    items.forEach((item,i)=>{
      const image=images[i],frame=frames[i];
      // A repeated underlying asset URL across stones cannot share the same
      // physical DOM image node; duplicate only in this rare case.
      const duplicate=images.indexOf(image)<i;
      const display=duplicate?image.cloneNode(false):image;
      display.className="motion-image";
      display.alt="Original frame "+(frame.ordinal+1)+" of "+
        item.rotation.frameCount+" for "+item.report+
        "; ordinal position, not a calibrated camera angle";
      item.stage.replaceChildren(display);
      item.caption.textContent="Frame "+(frame.ordinal+1)+" / "+
        item.rotation.frameCount+" · source index "+frame.sourceIndex;
      item.error.hidden=true;
      item.displayedURL=frame.url;
    });
    describe(clock===null?"Synchronized frames ready":"Playing synchronized original frames");
  }
  function seek(target,{forceRetry=false}={}){
    if(destroyed || !Number.isFinite(target))return;
    position=Math.max(0,Math.min(0.999999,target));
    syncControls();
    const items=present();
    if(!items.length)return;
    const frames=items.map(item=>item.rotation.frames[
      frameIndexAt(position,item.rotation.frameCount)]);
    const urls=frames.map(frame=>frame.url);
    const request=++sequence;
    pending=true;
    describe("Buffering synchronized frames · previous image remains visible");
    if(forceRetry){
      // Explicit Retry requeues failed media through the same bounded loader.
      void Promise.all(urls.map(url=>preloader.retry(url))).then(()=>{
        if(!destroyed && request===sequence)seek(position);
      });
      return;
    }
    const captured=position;
    void coordinator.seek(urls,images=>{
      if(destroyed || request!==sequence)return;
      commitFrames(items,frames,images,captured);
    }).then(success=>{
      if(destroyed || request!==sequence)return;
      pending=false;
      if(!success)describe("Newer seek superseded an older frame request");
    }).catch(()=>{
      if(destroyed || request!==sequence)return;
      pending=false;stopPlayback();
      describe("Frame loading failed; previous images retained");
    });
    preloader.observe(items.map(item=>item.rotation),captured);
  }
  function step(direction){seek(stepPosition(position,stepCount(),direction));}
  function tick(){
    if(destroyed || pending)return;
    if(!present().length){stopPlayback();return;}
    step(1);
  }
  function start(){
    if(clock!==null || !present().length)return;
    play.textContent="Pause";play.setAttribute("aria-label","Pause synchronized rotations");
    clock=setInterval(tick,Math.max(45,Math.round(120/speed)));
    describe("Playing as frames buffer; no skipped or flashing frames");
  }
  function toggle(){if(clock===null)start();else stopPlayback();}
  slider.addEventListener("input",()=>{
    stopPlayback();seek(Number(slider.value)/1001);
  });
  back.addEventListener("click",()=>{stopPlayback();step(-1);});
  forward.addEventListener("click",()=>{stopPlayback();step(1);});
  play.addEventListener("click",toggle);
  speedSelect.addEventListener("change",()=>{
    const next=Number(speedSelect.value);
    if(![0.5,1,2].includes(next))return;
    speed=next;
    if(clock!==null){stopPlayback();start();}
  });

  function setStone(id,rotation,representative,report=id){
    if(destroyed || !slots.has(id))return;
    const slot=slots.get(id);
    slot.replaceChildren();
    const item={id,report,rotation,slot,displayedURL:null};
    stones.set(id,item);
    if(rotation?.status!=="available"){
      showFallback(item,representative);
      syncControls();return;
    }
    const figure=el("figure","motion-figure");
    const stage=el("div","motion-frame-stage");
    stage.append(el("span","motion-loading","Preparing first original frame…"));
    const error=el("div","motion-frame-error");
    error.hidden=true;
    const retry=el("button","motion-retry","Retry frame");
    retry.type="button";
    retry.addEventListener("click",()=>{stopPlayback();seek(position,{forceRetry:true});});
    error.append(el("span","","Frame unavailable · "),retry);
    const caption=el("figcaption","motion-frame-caption");
    figure.append(stage,error,caption);
    slot.append(figure);
    item.stage=stage;item.error=error;item.caption=caption;
    syncControls();seek(position);
  }
  function failStone(id){
    if(!slots.has(id)||destroyed)return;
    stones.delete(id);coordinator.invalidate();sequence++;
    slots.get(id).replaceChildren(el("span","motion-unavailable",
      "Rotation manifest unavailable; retry this column"));
    if(!present().length)stopPlayback();
    syncControls();
    if(present().length)seek(position);
  }
  function destroy(){
    if(destroyed)return;
    stopPlayback();destroyed=true;sequence++;
    coordinator.close();unsubscribe();preloader.stop();stones.clear();
  }
  syncControls();
  return {setStone,failStone,destroy,seek};
}
