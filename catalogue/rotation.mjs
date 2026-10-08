// C3a pure, storage-neutral ordered-motion model and configurable prefetch policy.
// A playback position is *ordinal* and never a calibrated physical viewing angle.
import { assetUrl } from "./compare.mjs";

export const PREFETCH_MODES = Object.freeze(["none","nearby","all"]);
export const FRAME_PREFETCH = Object.freeze({
  // Change only this mode to "all" to opt into downloading all frames for
  // the *selected* stones when their comparison is opened.
  mode: "none",
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

export function createFramePreloader({mode=FRAME_PREFETCH.mode,
  nearbyRadius=FRAME_PREFETCH.nearbyRadius,
  maxConcurrent=FRAME_PREFETCH.maxConcurrent,
  imageFactory=()=>new Image()}={}) {
  if (!PREFETCH_MODES.includes(mode)) throw new RangeError("Invalid frame prefetch mode");
  if (!Number.isInteger(nearbyRadius) || nearbyRadius<0 || nearbyRadius>16 ||
      !Number.isInteger(maxConcurrent) || maxConcurrent<1 || maxConcurrent>12)
    throw new RangeError("Invalid prefetch limits");
  let stopped=false,active=0;
  const seen=new Set(),queue=[];
  function pump() {
    while (!stopped && active<maxConcurrent && queue.length) {
      const url=queue.shift();
      active++;
      let image;
      try {
        image=imageFactory();
        const done=()=>{image.onload=null;image.onerror=null;active--;pump();};
        image.onload=done;
        image.onerror=()=>{seen.delete(url);done();};
        image.src=url;
      } catch {
        seen.delete(url);active--;
      }
    }
  }
  function add(url) {
    if (!url || seen.has(url)) return;
    seen.add(url);queue.push(url);
  }
  function observe(sequences,position) {
    if (stopped || mode==="none") return;
    for (const seq of sequences) {
      if (seq?.status!=="available") continue;
      if (mode==="all") {
        for (const frame of seq.frames) add(frame.url);
      } else {
        const current=frameIndexAt(position,seq.frameCount);
        // Current frame is loaded by the visible <img>, only prefetch neighbors.
        for (let k=1;k<=nearbyRadius;k++) {
          add(seq.frames[(current+k)%seq.frameCount].url);
          add(seq.frames[(current-k+seq.frameCount)%seq.frameCount].url);
        }
      }
    }
    pump();
  }
  function stop() {stopped=true;queue.length=0;seen.clear();}
  return {mode,observe,stop,stats:()=>({active,queued:queue.length,seen:seen.size})};
}
