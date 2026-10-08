// C3a pure, storage-neutral ordered-motion model and configurable prefetch policy.
// A playback position is *ordinal* and never a calibrated physical viewing angle.
// Resolve the already-published storage URL directly, without depending on C2
// metadata projection or requiring a specific provider/backend.
const assetUrl = asset => {
  const value=asset?.storage?.url;
  if (typeof value !== "string") return null;
  try {
    const parsed=new URL(value);
    return ["https:","http:"].includes(parsed.protocol) &&
      !parsed.username && !parsed.password ? parsed.href : null;
  } catch { return null; }
};

export const PREFETCH_MODES = Object.freeze(["none","nearby","all"]);
export const FRAME_PREFETCH = Object.freeze({
  // C3b: full prefetch defaults ON for selected comparisons only.
  // Change to "nearby" or "none" to reduce the initial download.
  mode: "all",
  nearbyRadius: 6,
  maxConcurrent: 6,
  // Retain only a few decoded full-resolution frames in JS, not 256 x 5.
  maxDecoded: 24,
});


const isImage = asset => !asset?.media_type ||
  /^image\/(jpeg|png|webp|gif)$/.test(asset.media_type);

export function extractRotation(evidence) {
  const candidates = Array.isArray(evidence) ? evidence.filter(e=>e?.kind==="rotation") : [];
  for (const rotation of candidates) {
    if (rotation.status !== "success" || rotation.metadata?.sequence_complete !== true ||
        !Array.isArray(rotation.frames) || rotation.frames.length < 2 || rotation.frames.length > 4096)
      continue;
    const count = rotation.frames.length;
    if (rotation.metadata.frame_count !== undefined &&
        rotation.metadata.frame_count !== count) continue;
    // frames[] is the decoded temporal order. stored_position is scrambled
    // supplier storage position and MUST NOT be used to reorder this list.
    const frames = rotation.frames.map((frame,i)=>{
      const url = assetUrl(frame?.asset);
      if (!url || !isImage(frame.asset) ||
          !Number.isInteger(frame.source_index) || frame.source_index < 0)
        return null;
      return {url, sourceIndex:frame.source_index, ordinal:i};
    });
    if (frames.some(x=>x===null) ||
        new Set(frames.map(x=>x.sourceIndex)).size !== count) continue;
    const totalBytes=rotation.frames.reduce((sum,frame)=>
      sum+(Number.isFinite(frame.asset?.byte_count) ? frame.asset.byte_count : 0),0);
    return {status:"available",frameCount:count,frames,totalBytes};
  }
  const hasVideo=Array.isArray(evidence) && evidence.some(e=>
    e?.kind==="video" && e.status==="success" && assetUrl(e.payload_asset));
  if (hasVideo) return {status:"video_only",reason:"Original video available, but no complete ordered frame sequence"};
  if (candidates.length) return {status:"unavailable",reason:"Saved rotation is incomplete, invalid or unavailable"};
  return {status:"unavailable",reason:"No complete ordered 360 sequence saved"};
}

export function frameIndexAt(position, frameCount) {
  if (!Number.isInteger(frameCount) || frameCount < 1) throw new RangeError("Invalid frame count");
  if (!Number.isFinite(position)) throw new TypeError("Nonfinite normalized position");
  const wrapped = ((position % 1) + 1) % 1;
  return Math.min(frameCount-1,Math.floor(wrapped*frameCount));
}

export function stepPosition(position, frameCount, direction=1) {
  const current=frameIndexAt(position,frameCount);
  const next=((current+Math.sign(direction))%frameCount+frameCount)%frameCount;
  return next/frameCount;
}

// A bounded-concurrency HTTP-cache warmer and decoded-frame cache.
// Full mode requests each selected source URL, but retains at most
// maxDecodedImages decoded Image objects. Browser HTTP cache may evict images.
// All-frame prefetch uses the browser's HTTP cache for *downloads*, not a
// permanent in-memory decoded frame atlas. Keeping 1,280 decoded ~800px photos
// strongly could exceed gigabytes; only a small LRU is kept here.
//
// Visible-frame loads always outrank background prefetch; the player swaps
// images only after successful load/decode.
export function createFramePreloader({
  mode=FRAME_PREFETCH.mode,
  nearbyRadius=FRAME_PREFETCH.nearbyRadius,
  maxConcurrent=FRAME_PREFETCH.maxConcurrent,
  maxDecoded=FRAME_PREFETCH.maxDecoded,
  imageFactory=()=>new Image(),
}={}) {
  if (!PREFETCH_MODES.includes(mode)) throw new RangeError("Invalid frame prefetch mode");
  if (!Number.isInteger(nearbyRadius) || nearbyRadius<0 || nearbyRadius>32 ||
      !Number.isInteger(maxConcurrent) || maxConcurrent<1 || maxConcurrent>12 ||
      !Number.isInteger(maxDecoded) || maxDecoded<2 || maxDecoded>128)
    throw new RangeError("Invalid prefetch limits");

  let stopped=false, active=0;
  const entries=new Map(), decoded=new Map(), completed=new Set(), failures=new Set();
  const background=[], backgroundSet=new Set(), listeners=new Set();
  let urgent=[];
  let previousFullSignature="";

  const stats=()=>({mode,active,queued:background.length+urgent.length,
    total:entries.size,completed:completed.size,failed:failures.size,
    decoded:decoded.size});
  const notify=()=>{const state=stats();for(const fn of listeners) fn(state);};
  const subscribe=fn=>{listeners.add(fn);fn(stats());return ()=>listeners.delete(fn);};

  function hold(url,image) {
    decoded.delete(url);
    decoded.set(url,image);
    while(decoded.size>maxDecoded) {
      const oldest=decoded.keys().next().value;
      decoded.delete(oldest);
      const record=entries.get(oldest);
      if(record && record.state==="fetched") record.image=null;
    }
  }
  function queuedRecord(url) {
    let record=entries.get(url);
    if (record?.state==="fetched" && record.image) {
      hold(url,record.image);
      return record;
    }
    if(record && (record.state==="queued" || record.state==="loading")) return record;
    let resolve;
    const promise=new Promise(done=>{resolve=done;});
    record={url,state:"queued",image:null,resolve,promise};
    entries.set(url,record);
    return record;
  }
  function pump() {
    while(!stopped && (urgent.length || background.length)) {
      const fromUrgent=urgent.length>0;
      // A full prefetch may occupy every background slot for seconds.
      // Let user-requested frames temporarily use a couple of extra bounded
      // connections instead of waiting for background downloads to finish.
      const capacity=maxConcurrent+(fromUrgent ? Math.min(2,maxConcurrent) : 0);
      if(active>=capacity)break;
      const url=fromUrgent?urgent.shift():background.shift();
      if(!fromUrgent)backgroundSet.delete(url);
      const record=entries.get(url);
      if(!record || record.state!=="queued") continue;
      record.state="loading";active++;
      let image;
      let done=false;
      const settle=(successful)=>{
        if(done)return;done=true;
        if(image){image.onload=null;image.onerror=null;}
        active=Math.max(0,active-1);
        if(!stopped){
          if(successful){
            record.state="fetched";record.image=image;
            completed.add(url);failures.delete(url);
            hold(url,image);record.resolve(image);
          } else {
            record.state="failed";record.image=null;failures.add(url);
            record.resolve(null);
          }
          notify();pump();
        } else record.resolve(null);
      };
      try {
        image=imageFactory();
        image.onload=()=>{
          // decode() resolves only once the pixels can be painted. Browser
          // support varies, so onload itself is a valid fallback.
          if(typeof image.decode==="function"){
            Promise.resolve().then(()=>image.decode()).then(()=>settle(true),()=>settle(true));
          }else settle(true);
        };
        image.onerror=()=>settle(false);
        image.src=url;
      }catch{settle(false);}
    }
  }
  function focus(urls) {
    if(stopped)return Promise.resolve(urls.map(()=>null));
    const wanted=new Set(urls.filter(Boolean));
    // Drop obsolete queued urgent requests in on-demand mode. Ongoing image
    // downloads cannot be reliably canceled across third-party hosts.
    if(mode==="none"){
      for(const old of urgent){
        if(wanted.has(old))continue;
        const entry=entries.get(old);
        if(entry?.state==="queued"){
          entry.resolve(null);entries.delete(old);
        }
      }
    }
    urgent=[];
    const records=urls.map(url=>{
      if(!url)return null;
      const record=queuedRecord(url);
      if(record.state==="queued")urgent.push(url);
      return record;
    });
    pump();notify();
    return Promise.all(records.map(record=>
      !record ? Promise.resolve(null) :
      record.state==="fetched" && record.image ? Promise.resolve(record.image) :
      record.state==="failed" ? Promise.resolve(null) :
      record.promise));
  }
  function observe(sequences,position) {
    if(stopped || mode==="none")return;
    const available=sequences.filter(seq=>seq?.status==="available");
    if(mode==="all"){
      const signature=available.map(seq=>seq.frameCount+":"+seq.frames[0].url).join("|");
      if(signature===previousFullSignature)return;
      previousFullSignature=signature;
      // Rebuild the not-yet-started queue so newly loaded stones are not
      // starved behind the first stone's remaining 256 frames.
      background.length=0;backgroundSet.clear();
      // Interleave stones: two 256-frame stones must both make progress,
      // rather than fully fetching the first before starting the second.
      const largest=Math.max(0,...available.map(seq=>seq.frameCount));
      for(let i=0;i<largest;i++){
        for(const seq of available){
          const frame=seq.frames[i];
          if(!frame)continue;
          const record=queuedRecord(frame.url);
          if(record.state==="queued" && !backgroundSet.has(frame.url)){
            background.push(frame.url);backgroundSet.add(frame.url);
          }
        }
      }
    }else{
      background.length=0;backgroundSet.clear();
      for(const seq of available){
        const current=frameIndexAt(position,seq.frameCount);
        for(let i=1;i<=nearbyRadius;i++){
          for(const index of [(current+i)%seq.frameCount,
                 (current-i+seq.frameCount)%seq.frameCount]){
            const url=seq.frames[index].url;
            const record=queuedRecord(url);
            if(record.state==="queued" && !backgroundSet.has(url)){
              background.push(url);backgroundSet.add(url);
            }
          }
        }
      }
    }
    pump();notify();
  }
  function retry(url) {
    if(!url)return Promise.resolve(null);
    const record=entries.get(url);
    if(record?.state==="failed"){
      entries.delete(url);failures.delete(url);
    }
    return focus([url]).then(images=>images[0]);
  }
  function stop() {
    if(stopped)return;
    stopped=true;urgent=[];background.length=0;backgroundSet.clear();
    for(const record of entries.values()){
      if(record.state==="queued")record.resolve(null);
      // Any active request will settle itself when its browser event fires;
      // detach every callback from the player by clearing subscribers.
    }
    listeners.clear();decoded.clear();
  }
  return {mode,observe,focus,retry,stop,stats,subscribe};
}

// Serial number invalidates slower earlier seek operations. A completed
// batch of frames is delivered to the DOM together, avoiding unsynchronized
// partial swaps and preventing a stale frame from flashing after a fast scrub.
export function createBufferedFrameCoordinator(load) {
  let serial=0,closed=false;
  async function seek(frames,commit) {
    if(closed)return false;
    const request=++serial;
    const results=await load(frames);
    if(closed || request!==serial)return false;
    commit(results);
    return true;
  }
  function invalidate() {serial++;}
  function close() {closed=true;serial++;}
  return {seek,invalidate,close};
}
