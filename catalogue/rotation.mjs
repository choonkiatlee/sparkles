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
  // Full prefetch is currently enabled for the selected comparison diamonds.
  // Switch this to "nearby" or "none" without changing playback logic.
  mode: "all",
  nearbyRadius: 4,
  maxConcurrent: 6,
  // Keep a small decoded-image LRU; prefetching original JPEGs must NOT
  // retain 256 full-resolution decoded bitmaps per stone in memory.
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

// Shared image fetch coordinator. A high-priority visible frame jumps ahead of
// the all-frame background queue, and decoded images have a bounded LRU.
// "all" means all original JPEG requests, NOT all decoded bitmaps held in RAM.
export function createFramePreloader({
  mode=FRAME_PREFETCH.mode,
  nearbyRadius=FRAME_PREFETCH.nearbyRadius,
  maxConcurrent=FRAME_PREFETCH.maxConcurrent,
  maxDecoded=FRAME_PREFETCH.maxDecoded,
  imageFactory=()=>new Image()
}={}) {
  if (!PREFETCH_MODES.includes(mode)) throw new RangeError("Invalid frame prefetch mode");
  if (!Number.isInteger(nearbyRadius) || nearbyRadius<0 || nearbyRadius>16 ||
      !Number.isInteger(maxConcurrent) || maxConcurrent<1 || maxConcurrent>12 ||
      !Number.isInteger(maxDecoded) || maxDecoded<1 || maxDecoded>128)
    throw new RangeError("Invalid frame prefetch limits");
  let currentMode=mode,stopped=false,active=0;
  const jobs=new Map(),immediate=[],background=[],decoded=new Map();
  const discovered=new Set(),completed=new Set(),failed=new Set();
  const subscribers=new Set(),activeImages=new Set();

  function stats() {
    return {mode:currentMode,active,queued:immediate.length+background.length,
      total:discovered.size,loaded:completed.size,failed:failed.size,
      decoded:decoded.size};
  }
  function notify() {
    if (stopped) return;
    for (const cb of subscribers) cb(stats());
  }
  function warm(url,image) {
    decoded.delete(url);
    decoded.set(url,image);
    while (decoded.size>maxDecoded) decoded.delete(decoded.keys().next().value);
  }
  function take(url) {
    if (!decoded.has(url)) return null;
    const image=decoded.get(url);
    warm(url,image);
    return image;
  }
  function settle(job,image) {
    if (!jobs.has(job.url)) return;
    jobs.delete(job.url);
    if (job.started) {
      active=Math.max(0,active-1);
      activeImages.delete(job.image);
    }
    if (!stopped) {
      if (image) {warm(job.url,image);completed.add(job.url);failed.delete(job.url);}
      else {failed.add(job.url);completed.delete(job.url);}
    }
    job.resolve(stopped?null:image);
    notify();
    pump();
  }
  function pump() {
    if (stopped) return;
    while (active<maxConcurrent && (immediate.length || background.length)) {
      const job=(immediate.length?immediate:background).shift();
      if (!jobs.has(job.url) || job.started) continue;
      job.started=true;active++;
      try {
        const image=imageFactory();
        job.image=image;
        activeImages.add(image);
        image.onload=()=>{image.onload=null;image.onerror=null;settle(job,image);};
        image.onerror=()=>{image.onload=null;image.onerror=null;settle(job,null);};
        image.src=job.url;
      } catch {settle(job,null);}
    }
    notify();
  }
  // A failed asset is retried only on explicit demand, not by the full-scan
  // observer on every scrub tick.
  function request(url,{priority=true}={}) {
    if (stopped || typeof url!=="string" || !url) return Promise.resolve(null);
    discovered.add(url);
    const warmImage=take(url);
    if (warmImage) return Promise.resolve(warmImage);
    const existing=jobs.get(url);
    if (existing) {
      if (priority && !existing.priority && !existing.started) {
        existing.priority=true;
        const at=background.indexOf(existing);
        if (at!==-1) background.splice(at,1);
        immediate.unshift(existing);
        pump();
      }
      return existing.promise;
    }
    if (!priority && (completed.has(url) || failed.has(url))) return Promise.resolve(null);
    let resolve;
    const promise=new Promise(done=>{resolve=done;});
    const job={url,priority,started:false,image:null,promise,resolve};
    jobs.set(url,job);
    (priority?immediate:background).push(job);
    pump();
    return promise;
  }
  function observe(sequences,position) {
    if (stopped || currentMode==="none") return;
    for (const seq of sequences) {
      if (seq?.status!=="available") continue;
      if (currentMode==="all") {
        for (const frame of seq.frames) request(frame.url,{priority:false});
      } else {
        const index=frameIndexAt(position,seq.frameCount);
        for (let k=1;k<=nearbyRadius;k++) {
          request(seq.frames[(index+k)%seq.frameCount].url,{priority:false});
          request(seq.frames[(index-k+seq.frameCount)%seq.frameCount].url,{priority:false});
        }
      }
    }
  }
  function setMode(nextMode,sequences=[],position=0) {
    if (!PREFETCH_MODES.includes(nextMode)) throw new RangeError("Invalid frame prefetch mode");
    if (stopped || nextMode===currentMode) return;
    currentMode=nextMode;
    // Cancel *queued* background tasks, allowing active transfers and any
    // currently requested visible frame to finish.
    for (const job of background.splice(0)) {
      jobs.delete(job.url);
      job.resolve(null);
    }
    notify();
    observe(sequences,position);
  }
  function subscribe(fn) {
    subscribers.add(fn);
    fn(stats());
    return ()=>subscribers.delete(fn);
  }
  function stop() {
    if (stopped) return;
    stopped=true;
    for (const job of jobs.values()) job.resolve(null);
    jobs.clear();immediate.length=0;background.length=0;
    for (const image of activeImages) {
      image.onload=null;image.onerror=null;
    }
    activeImages.clear();active=0;decoded.clear();subscribers.clear();
  }
  return {get mode(){return currentMode;},observe,request,subscribe,setMode,stop,stats};
}

// Keep the last visible image until the newly *loaded* image is available;
// obsolete scrub requests must never flash a late frame over the current one.
export function createFrameGate({load,present,onError=()=>{}}) {
  let generation=0,destroyed=false,requestedURL=null,shownURL=null;
  function show(frame) {
    if (destroyed || requestedURL===frame.url) return;
    const version=++generation;
    requestedURL=frame.url;
    Promise.resolve().then(()=>load(frame.url)).then(image=>{
      if (destroyed || version!==generation) return;
      if (!image) {
        onError(frame);
        return;
      }
      present(frame,image);
      shownURL=frame.url;
    },()=>{
      if (!destroyed && version===generation) onError(frame);
    });
  }
  function retry(frame) {
    if (destroyed) return;
    requestedURL=null;
    show(frame);
  }
  function stop() {destroyed=true;generation++;}
  return {show,retry,stop,get shownURL(){return shownURL;}};
}
