// Browser-only C3a synchronized 360 viewer: independent original image URLs,
// one normalized position, no physical-angle/face-up phase alignment.
import { FRAME_PREFETCH, createFramePreloader, frameIndexAt, stepPosition } from "./rotation.mjs";

const el = (tag,className="",text=null)=>{
  const result=document.createElement(tag);
  if (className) result.className=className;
  if (text!==null) result.textContent=String(text);
  return result;
};

export function createRotationPlayer({host,slots,config=FRAME_PREFETCH}) {
  const stones=new Map();
  const preloader=createFramePreloader({mode:config.mode,nearbyRadius:config.nearbyRadius,
    maxConcurrent:config.maxConcurrent});
  let position=0,clock=null,destroyed=false;
  const top=el("div","motion-toolbar-main");
  const lead=el("div","motion-toolbar-intro");
  lead.append(el("strong","", "Synchronized original rotations"),
    el("p","subtle","Shared relative frame position only · no calibrated physical angle or face-up phase alignment"));
  top.append(lead);
  const controls=el("div","motion-controls");
  const back=el("button","motion-step","← Step");
  const play=el("button","motion-play","Play");
  const forward=el("button","motion-step","Step →");
  for (const button of [back,play,forward]) button.type="button";
  const sliderLabel=el("label","motion-range-label","Position");
  const slider=el("input","motion-slider");
  slider.type="range";slider.min="0";slider.max="1000";slider.step="1";slider.value="0";
  slider.setAttribute("aria-label","Shared relative rotation position");
  const valueLabel=el("span","motion-position","0%");
  valueLabel.setAttribute("aria-live","off");
  sliderLabel.append(slider,valueLabel);
  controls.append(back,play,forward,sliderLabel);
  top.append(controls);host.append(top);

  const ready=()=>[...stones.values()].filter(item=>item.rotation?.status==="available");
  const currentStepCount=()=>Math.max(1,...ready().map(item=>item.rotation.frameCount));
  function syncControls() {
    const enabled=ready().length>0;
    for (const control of [play,back,forward,slider]) control.disabled=!enabled;
    valueLabel.textContent=Math.round(position*100)+"%";
    slider.value=String(Math.round(position*1000));
  }
  function renderStone(item) {
    const {rotation,slot,report}=item;
    if (rotation?.status!=="available") return;
    const index=frameIndexAt(position,rotation.frameCount);
    const frame=rotation.frames[index];
    if (item.currentURL===frame.url && item.currentIndex===index) return;
    item.currentURL=frame.url;item.currentIndex=index;
    item.image.hidden=false;
    item.fallback.hidden=true;
    item.caption.textContent="Frame "+(index+1)+" / "+rotation.frameCount+" · original ordered media";
    const expected=frame.url;
    item.image.onload=()=>{
      if (destroyed || item.currentURL!==expected) return;
      item.caption.textContent="Frame "+(index+1)+" / "+rotation.frameCount+
        " · source index "+frame.sourceIndex;
    };
    item.image.onerror=()=>{
      if (destroyed || item.currentURL!==expected) return;
      item.image.hidden=true;
      item.fallback.hidden=false;
      item.caption.textContent="Frame "+(index+1)+" unavailable · original media could not load";
    };
    item.image.alt="Original diamond rotation frame "+(index+1)+" of "+rotation.frameCount+
      " for "+report+"; angle not calibrated";
    item.image.src=expected;
  }
  function refresh() {
    if (destroyed) return;
    syncControls();
    for (const item of ready()) renderStone(item);
    preloader.observe(ready().map(item=>item.rotation),position);
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
    clock=setInterval(()=>step(1),120);
  }
  slider.addEventListener("input",()=>{
    pause();seek(Number(slider.value)/1001);
  });
  back.addEventListener("click",()=>{pause();step(-1);});
  forward.addEventListener("click",()=>{pause();step(1);});
  play.addEventListener("click",toggle);
  function setStone(id,rotation,representative,report=id) {
    if (destroyed || !slots.has(id)) return;
    const slot=slots.get(id);
    slot.replaceChildren();
    const item={rotation,slot,report,currentURL:null,currentIndex:-1};
    stones.set(id,item);
    if (rotation?.status!=="available") {
      const fallback=el("div","motion-empty");
      fallback.append(el("span","motion-unavailable",
        rotation?.reason || "Original rotation unavailable"));
      if (representative?.url) {
        const img=el("img","motion-static");
        img.src=representative.url;img.alt="Original representative still for "+report;
        img.loading="lazy";img.decoding="async";
        fallback.prepend(img);
      }
      slot.append(fallback);
      refresh();return;
    }
    const figure=el("figure","motion-figure");
    const image=el("img","motion-image");
    image.decoding="async";
    const fallback=el("div","motion-frame-error");
    fallback.hidden=true;
    const errorText=el("span","", "Frame unavailable · ");
    const retry=el("button","motion-retry","Retry frame");
    retry.type="button";
    retry.addEventListener("click",()=>{
      item.currentURL=null;item.currentIndex=-1;renderStone(item);
    });
    fallback.append(errorText,retry);
    const caption=el("figcaption","motion-frame-caption");
    figure.append(image,fallback,caption);
    slot.append(figure);
    item.image=image;item.fallback=fallback;item.caption=caption;
    refresh();
  }
  function failStone(id) {
    if (!slots.has(id) || destroyed) return;
    stones.delete(id);
    slots.get(id).replaceChildren(el("span","motion-unavailable","Motion manifest unavailable; retry this column"));
    if (!ready().length) pause();
    refresh();
  }
  function destroy() {
    pause();destroyed=true;preloader.stop();stones.clear();
  }
  syncControls();
  return {setStone,failStone,destroy,seek};
}
