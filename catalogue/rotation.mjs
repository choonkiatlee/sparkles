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
  // Full fetch is chosen deliberately after C3a exposed very visible flicker.
  // Runs ONLY on selected manifest rotations in the open comparison.
  // Use "nearby" or "none" here if bandwidth/storage becomes an issue.
  mode: "all",
  nearbyRadius: 3,
  maxConcurrent: 6,
  maxDecodedImages: 24, // bound retained decoded images, NOT network downloads
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
    return {status:"available",frameCount:count,frames};
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
export function createFramePreloader({mode=FRAME_PREFETCH.mode,
  nearbyRadius=FRAME_PREFETCH.nearbyRadius,
  maxConcurrent=FRAME_PREFETCH.maxConcurrent,
  maxDecodedImages=FRAME_PREFETCH.maxDecodedImages,
  imageFactory=()=>new Image()}={}) {
  if (!PREFETCH_MODES.includes(mode)) throw new RangeError("Invalid frame prefetch mode");
  if (!Number.isInteger(nearbyRadius) || nearbyRadius<0 || nearbyRadius>16 ||
      !Number.isInteger(maxConcurrent) || maxConcurrent<1 || maxConcurrent>12 ||
      !Number.isInteger(maxDecodedImages) || maxDecodedImages<2 || maxDecodedImages>128)
    throw new RangeError("Invalid prefetch limits");
  let stopped=false, active=0;
  const records=new Map(), queue=[], decoded=new Map(), listeners=new Set();
  const notify=()=>{for(const callback of listeners)callback(stats());};
  const stats=()=>{
    let loaded=0,failed=0;
    for(const value of records.values()) {
      if(value.everLoaded) loaded++;
      if(value.state==="failed") failed++;
    }
    return {mode,total:records.size,loaded,failed,active,queued:queue.length,retained:decoded.size};
  };
  const touch=(url,image)=>{
    decoded.delete(url);decoded.set(url,image);
    while(decoded.size>maxDecodedImages)decoded.delete(decoded.keys().next().value);
  };
  function pump() {
    while(!stopped && active<maxConcurrent && queue.length) {
      const entry=queue.shift();
      if(entry.state!=="queued")continue;
      entry.state="loading";active++;
      try {
        const image=imageFactory();
        image.decoding="async";
        const finish=(success)=>{
          image.onload=null;image.onerror=null;active--;
          if(stopped)return;
          if(success) {
            entry.state="loaded";entry.everLoaded=true;
            touch(entry.url,image);
          } else entry.state="failed";
          const callbacks=entry.waiters.splice(0);
          callbacks.forEach(resolve=>resolve(success ? image : null));
          notify();pump();
        };
        image.onload=()=>finish(true);
        image.onerror=()=>finish(false);
        image.src=entry.url;
      } catch {
        entry.state="failed";active--;
        entry.waiters.splice(0).forEach(resolve=>resolve(null));
        notify();
      }
    }
  }
  function enqueue(url,{priority=false,retry=false}={}) {
    if(stopped || !url)return null;
    let entry=records.get(url);
    if(!entry) {
      entry={url,state:"queued",everLoaded:false,waiters:[]};
      records.set(url,entry); queue.push(entry);
    } else if(entry.state==="failed" && retry) {
      entry.state="queued";queue.push(entry);
    } else if(entry.state==="loaded" && !decoded.has(url)) {
      // Decoded image evicted. Loading again usually hits the browser HTTP cache.
      entry.state="queued";queue.push(entry);
    }
    if(priority && entry.state==="queued"){
      const i=queue.indexOf(entry);
      if(i>0) {queue.splice(i,1);queue.unshift(entry);}
    }
    return entry;
  }
  function peek(url) {
    if(stopped)return null;
    const image=decoded.get(url);
    if(image)touch(url,image);
    return image || null;
  }
  function ensure(url,{priority=true,retry=false}={}) {
    const loaded=peek(url);
    if(loaded)return Promise.resolve(loaded);
    const entry=enqueue(url,{priority,retry});
    if(!entry || entry.state==="failed")return Promise.resolve(null);
    const result=new Promise(resolve=>entry.waiters.push(resolve));
    pump();notify();
    return result;
  }
  function observe(sequences,position) {
    if(stopped || mode==="none")return;
    const valid=sequences.filter(seq=>seq?.status==="available");
    // In all-mode collect frames in a round-robin layout so one stone doesn't
    // monopolize the network while others are still unbuffered.
    if(mode==="all"){
      const highest=Math.max(0,...valid.map(seq=>seq.frameCount));
      for(let offset=0;offset<highest;offset++){
        for(const seq of valid){
          if(offset<seq.frameCount){
            const ix=(frameIndexAt(position,seq.frameCount)+offset)%seq.frameCount;
            // Only queue if not already visited. Never redownload all evicted frames.
            const url=seq.frames[ix].url;
            if(!records.has(url))enqueue(url);
          }
        }
      }
    } else {
      for(const seq of valid){
        const center=frameIndexAt(position,seq.frameCount);
        for(let k=1;k<=nearbyRadius;k++){
          for(const sign of [1,-1]){
            const url=seq.frames[(center+sign*k+seq.frameCount)%seq.frameCount].url;
            if(!records.has(url))enqueue(url);
          }
        }
      }
    }
    pump();notify();
  }
  function subscribe(callback){
    listeners.add(callback);callback(stats());
    return ()=>listeners.delete(callback);
  }
  function stop(){
    stopped=true;
    // Complete pending waiters, and disable events from retired player state.
    for(const item of records.values())item.waiters.splice(0).forEach(resolve=>resolve(null));
    queue.length=0;decoded.clear();listeners.clear();records.clear();
  }
  return {mode,observe,ensure,peek,subscribe,stop,stats};
}
