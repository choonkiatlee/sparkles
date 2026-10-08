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
  // Full prefetch is now intentional for selected comparisons (C3b).
  // Set to "nearby" or "none" to reduce bandwidth if needed.
  mode: "all",
  nearbyRadius: 2,
  maxConcurrent: 4,
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

// C3b: deduplicated, concurrency-limited, cancellable-at-boundary downloader.
// Completion indicates an original frame has arrived in the browser cache;
// it is NOT a guarantee the browser will keep all frames decoded in RAM.
// Keep only a bounded number of Image objects alive to avoid huge memory usage.
export function createFramePreloader({mode=FRAME_PREFETCH.mode,
  nearbyRadius=FRAME_PREFETCH.nearbyRadius,
  maxConcurrent=FRAME_PREFETCH.maxConcurrent,
  maxRetained=24,
  imageFactory=()=>new Image(),
  onProgress=()=>{}}={}) {
  if (!PREFETCH_MODES.includes(mode)) throw new RangeError("Invalid frame prefetch mode");
  if (!Number.isInteger(nearbyRadius) || nearbyRadius<0 || nearbyRadius>16 ||
      !Number.isInteger(maxConcurrent) || maxConcurrent<1 || maxConcurrent>12 ||
      !Number.isInteger(maxRetained) || maxRetained<0 || maxRetained>128)
    throw new RangeError("Invalid prefetch limits");
  let stopped=false;
  const entries=new Map(),queue=[],activeImages=new Map(),hot=new Map();
  const counts=()=>({
    total:entries.size,
    loaded:[...entries.values()].filter(s=>s==="ready").length,
    failed:[...entries.values()].filter(s=>s==="failed").length,
    active:activeImages.size,
    queued:queue.length,
    // Earlier "seen" is preserved as a diagnostic/compatibility metric.
    seen:entries.size,
  });
  function stats() {
    const c=counts();
    return {...c,complete:c.total>0 && c.loaded+c.failed===c.total &&
      c.active===0 && c.queued===0,mode};
  }
  const notify=()=>{if(!stopped) onProgress(stats());};
  function retain(url,img) {
    if (!maxRetained) return;
    hot.delete(url);hot.set(url,img);
    while (hot.size>maxRetained) hot.delete(hot.keys().next().value);
  }
  function pump() {
    while (!stopped && activeImages.size<maxConcurrent && queue.length) {
      const url=queue.shift();
      if (entries.get(url)!=="queued") continue;
      let img;
      try { img=imageFactory(); } catch {
        entries.set(url,"failed");
        continue;
      }
      entries.set(url,"loading");
      activeImages.set(url,img);
      let doneCalled=false;
      const done=ok=>{
        if(doneCalled) return;
        doneCalled=true;
        img.onload=null;img.onerror=null;
        activeImages.delete(url);
        if (stopped) return;
        entries.set(url,ok?"ready":"failed");
        if (ok) retain(url,img);
        notify();
        pump();
      };
      img.onload=()=>done(true);
      img.onerror=()=>done(false);
      try {img.src=url;} catch {done(false);}
    }
    notify();
  }
  function add(url,{retry=false}={}) {
    if (!url || stopped) return;
    if (entries.has(url) && !(retry && entries.get(url)==="failed")) return;
    entries.set(url,"queued");
    queue.push(url);
  }
  function observe(sequences,position) {
    if (stopped || mode==="none") return;
    const available=sequences.filter(seq=>seq?.status==="available");
    if (mode==="all") {
      // Prioritize immediate surrounding frames across *all* known selected
      // stones before requesting the remainder in a round-robin sequence.
      for (let d=0;d<=nearbyRadius;d++) {
        for (const seq of available) {
          const n=frameIndexAt(position,seq.frameCount);
          add(seq.frames[(n+d)%seq.frameCount].url);
          if (d) add(seq.frames[(n-d+seq.frameCount)%seq.frameCount].url);
        }
      }
      const longest=Math.max(0,...available.map(seq=>seq.frameCount));
      for (let index=0;index<longest;index++) {
        for (const seq of available) {
          if(index<seq.frameCount) add(seq.frames[index].url);
        }
      }
    } else {
      for (const seq of available) {
        const current=frameIndexAt(position,seq.frameCount);
        for (let k=1;k<=nearbyRadius;k++) {
          add(seq.frames[(current+k)%seq.frameCount].url);
          add(seq.frames[(current-k+seq.frameCount)%seq.frameCount].url);
        }
      }
    }
    pump();
  }
  function retry(url) {
    if (stopped || mode==="none") return;
    add(url,{retry:true});pump();
  }
  function stop() {
    stopped=true;queue.length=0;hot.clear();entries.clear();
    // Never allow a stale callback to change the re-opened comparison.
    for (const img of activeImages.values()) {
      img.onload=null;img.onerror=null;
      try {img.src="";} catch {/* browser may already have finished */}
    }
    activeImages.clear();
  }
  return {mode,observe,stop,retry,stats,isReady:url=>entries.get(url)==="ready"};
}
