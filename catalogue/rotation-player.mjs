// C3b synchronized original JPEG playback without blank-frame flicker.
// Fully fetched source frames are NOT equivalent to retained decoded bitmaps.
import { FRAME_PREFETCH, createFramePreloader, createFrameGate,
  frameIndexAt, stepPosition, PREFETCH_MODES } from "./rotation.mjs";

const el=(tag,className="",text=null)=>{
  const result=document.createElement(tag);
  if (className) result.className=className;
  if (text!==null) result.textContent=String(text);
  return result;
};
const textFor=mode=>({
  none:"Visible frames only",
  nearby:"Nearby frames",
  all:"All selected frames"
})[mode];

export function createRotationPlayer({host,slots,config=FRAME_PREFETCH}) {
  const stones=new Map();
  const preloader=createFramePreloader({
    mode:config.mode,nearbyRadius:config.nearbyRadius,
    maxConcurrent:config.maxConcurrent,maxDecoded:config.maxDecoded
  });
  let position=0,clock=null,destroyed=false;
  const toolbar=el("div","motion-toolbar-main");
  const lead=el("div","motion-toolbar-intro");
  lead.append(el("strong","","Synchronized original rotations"),
    el("p","subtle","Shared relative frame position only · original views are not calibrated or phase-aligned"));
  const controls=el("div","motion-controls");
  const backward=el("button","motion-step","← Step");
  const play=el("button","motion-play","Play");
  const forward=el("button","motion-step","Step →");
  for (const button of [backward,play,forward]) button.type="button";
  const sliderLabel=el("label","motion-range-label","Position");
  const slider=el("input","motion-slider");
  slider.type="range";slider.min="0";slider.max="1000";slider.step="1";slider.value="0";
  slider.setAttribute("aria-label","Shared relative rotation position");
  const positionLabel=el("span","motion-position","0%");
  sliderLabel.append(slider,positionLabel);
  controls.append(backward,play,forward,sliderLabel);
  toolbar.append(lead,controls);
  const footer=el("div","motion-loading");
  const prefetchLabel=el("label","motion-prefetch-label","Load frames");
  const modeSelect=el("select","motion-prefetch");
  modeSelect.setAttribute("aria-label","Frame prefetch mode");
  for (const mode of PREFETCH_MODES) {
    const opt=el("option","",textFor(mode));
    opt.value=mode;modeSelect.append(opt);
  }
  modeSelect.value=preloader.mode;prefetchLabel.append(modeSelect);
  const progress=el("span","motion-loading-status","Frames load on demand");
  progress.setAttribute("role","status");
  progress.setAttribute("aria-live","polite");
  footer.append(prefetchLabel,progress);
  host.append(toolbar,footer);

  const ready=()=>[...stones.values()].filter(item=>item.rotation?.status==="available");
  const currentStepCount=()=>Math.max(1,...ready().map(item=>item.rotation.frameCount));
  const allSequences=()=>ready().map(item=>item.rotation);
  const showProgress=()=>{
    const {mode,loaded,failed}=preloader.stats();
    const count=allSequences().reduce((sum,s)=>sum+s.frameCount,0);
    if (!count) {progress.textContent="No complete original rotation loaded";return;}
    if (mode==="all") {
      progress.textContent="Background prefetch: "+loaded+" / "+count+" original frames"+
        (failed?" · "+failed+" unavailable":"")+
        (loaded+failed>=count?" · complete":" · playback available while loading");
    } else if (mode==="nearby") {
      progress.textContent="Loading adjacent frames · "+loaded+" cached"+
        (failed?" · "+failed+" unavailable":"");
    } else progress.textContent="Visible frames only · no background prefetch";
  };
  const unsubscribe=preloader.subscribe(showProgress);
  function syncControls() {
    const enabled=ready().length>0;
    for (const control of [backward,play,forward,slider]) control.disabled=!enabled;
    positionLabel.textContent=Math.round(position*100)+"%";
    slider.value=String(Math.round(position*1000));
  }
  function updateCaption(item,frame,text) {
    item.caption.textContent="Frame "+(frame.ordinal+1)+" / "+item.rotation.frameCount+
      " · "+text;
  }
  function displayLoaded(item,frame) {
    if (destroyed || item.requestedURL!==frame.url) return;
    const current=item.layers[item.visibleIndex];
    // Avoid replacing a decoded, already-painted image.
    if (current.src===frame.url && !current.hidden && current.complete && current.naturalWidth) {
      updateCaption(item,frame,"source index "+frame.sourceIndex);return;
    }
    const nextIndex=1-item.visibleIndex;
    const next=item.layers[nextIndex];
    const expected=frame.url;
    next.onload=null;next.onerror=null;
    const flip=()=>{
      if (destroyed || item.requestedURL!==expected || !stones.has(item.id)) return;
      next.hidden=false;
      current.hidden=true;
      item.visibleIndex=nextIndex;
      item.error.hidden=true;
      updateCaption(item,frame,"source index "+frame.sourceIndex);
    };
    next.onload=()=>{
      if (typeof next.decode==="function") {
        // Decode off-screen, then reveal in one DOM update. If decoding
        // rejects after an image load, the browser can still paint it.
        Promise.resolve().then(()=>next.decode()).catch(()=>{}).then(flip);
      } else flip();
    };
    next.onerror=()=>{
      if (item.requestedURL!==expected) return;
      item.error.hidden=false;
      updateCaption(item,frame,"could not paint image · previous frame retained");
    };
    next.alt="Original rotation frame "+(frame.ordinal+1)+" of "+item.rotation.frameCount+
      " for "+item.report+"; ordinal, uncalibrated view";
    next.src=expected;
  }
  function warnLoad(item,frame) {
    if (destroyed || item.requestedURL!==frame.url) return;
    item.error.hidden=false;
    updateCaption(item,frame,"source unavailable · last visible image retained");
  }
  function renderStone(item) {
    const rotation=item.rotation;
    if (rotation?.status!=="available") return;
    const index=frameIndexAt(position,rotation.frameCount);
    const frame=rotation.frames[index];
    if (item.requestedURL===frame.url) return;
    item.requestedURL=frame.url;
    item.error.hidden=true;
    if (item.layers[item.visibleIndex]?.hidden) {
      updateCaption(item,frame,"preparing first image…");
    } else {
      updateCaption(item,frame,"loading new image · previous frame remains visible");
    }
    item.gate.show(frame);
  }
  function warmAhead() {
    if (preloader.mode==="none") return;
    for (const item of ready()) {
      const idx=frameIndexAt(position,item.rotation.frameCount);
      for (let k=1;k<=3;k++) {
        const url=item.rotation.frames[(idx+k)%item.rotation.frameCount].url;
        // A playing/soon-to-be-visible frame must outrank all-mode bulk queue.
        preloader.request(url,{priority:true});
      }
    }
  }
  function refresh({initial=false}={}) {
    if (destroyed) return;
    syncControls();
    for (const item of ready()) renderStone(item);
    if (initial || preloader.mode==="nearby") preloader.observe(allSequences(),position);
    if (clock!==null || initial) warmAhead();
    showProgress();
  }
  function seek(value) {
    if (!Number.isFinite(value)) return;
    position=Math.max(0,Math.min(0.999999,value));
    refresh();
  }
  function step(direction) {
    seek(stepPosition(position,currentStepCount(),direction));
  }
  function pause() {
    if (clock!==null) {clearInterval(clock);clock=null;}
    play.textContent="Play";play.setAttribute("aria-label","Play synchronized rotations");
  }
  function toggle() {
    if (clock!==null) {pause();return;}
    if (!ready().length) return;
    play.textContent="Pause";play.setAttribute("aria-label","Pause synchronized rotations");
    warmAhead();
    clock=setInterval(()=>step(1),120);
  }
  slider.addEventListener("input",()=>{pause();seek(Number(slider.value)/1001);});
  backward.addEventListener("click",()=>{pause();step(-1);});
  forward.addEventListener("click",()=>{pause();step(1);});
  play.addEventListener("click",toggle);
  modeSelect.addEventListener("change",()=>{
    preloader.setMode(modeSelect.value,allSequences(),position);
    warmAhead();
    showProgress();
  });

  function setStone(id,rotation,representative,report=id) {
    if (destroyed || !slots.has(id)) return;
    const previous=stones.get(id);
    previous?.gate?.stop();
    const slot=slots.get(id);
    slot.replaceChildren();
    const item={id,rotation,slot,report,requestedURL:null,visibleIndex:0};
    stones.set(id,item);
    if (rotation?.status!=="available") {
      const fallback=el("div","motion-empty");
      fallback.append(el("span","motion-unavailable",
        rotation?.reason || "Original ordered rotation unavailable"));
      if (representative?.url) {
        const img=el("img","motion-static");
        img.src=representative.url;img.alt="Original still for "+report;
        img.loading="lazy";img.decoding="async";
        fallback.prepend(img);
      }
      slot.append(fallback);refresh();return;
    }
    const figure=el("figure","motion-figure");
    const viewport=el("div","motion-viewport");
    const front=el("img","motion-image");
    const back=el("img","motion-image");
    front.decoding="async";back.decoding="async";
    back.hidden=true;front.hidden=!representative?.url;
    if (representative?.url) {
      front.src=representative.url;
      front.alt="Representative published original image for "+report;
    }
    viewport.append(front,back);
    const error=el("div","motion-frame-error");
    error.hidden=true;
    const retry=el("button","motion-retry","Retry frame");
    retry.type="button";
    retry.addEventListener("click",()=>{
      const frame=item.rotation.frames[frameIndexAt(position,item.rotation.frameCount)];
      item.gate.retry(frame);
      error.hidden=true;
      updateCaption(item,frame,"retrying original frame…");
    });
    error.append(el("span","","Image unavailable · showing last usable view"),retry);
    const caption=el("figcaption","motion-frame-caption","Preparing original frame…");
    figure.append(viewport,error,caption);slot.append(figure);
    item.layers=[front,back];item.caption=caption;item.error=error;
    item.gate=createFrameGate({
      load:url=>preloader.request(url,{priority:true}),
      present:frame=>displayLoaded(item,frame),
      onError:frame=>warnLoad(item,frame)
    });
    refresh({initial:true});
  }
  function failStone(id) {
    if (destroyed || !slots.has(id)) return;
    stones.get(id)?.gate?.stop();
    stones.delete(id);
    slots.get(id).replaceChildren(el("span","motion-unavailable",
      "Motion manifest unavailable; retry this column"));
    if (!ready().length) pause();
    refresh();
  }
  function destroy() {
    pause();destroyed=true;
    for (const item of stones.values()) item.gate?.stop();
    unsubscribe();preloader.stop();stones.clear();
  }
  syncControls();
  return {setStone,failStone,destroy,seek};
}
