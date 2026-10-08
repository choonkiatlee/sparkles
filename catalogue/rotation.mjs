// Shared ordinal frame viewer contract; no calibrated camera-angle assumptions.
// The compact catalogue never imports this: source frames load only for compared stones.
import { assetUrl, publicUrl } from "./compare.mjs";

export const PREFETCH_ALL_DEFAULT = false;
export const DEFAULT_PREFETCH_MODE = PREFETCH_ALL_DEFAULT ? "all" : "nearby";
export const PREFETCH_CONCURRENCY = 3;

export function normalPosition(position) {
  return Number.isFinite(position) ? ((position % 1) + 1) % 1 : 0;
}
export function frameIndex(position, count) {
  if (!Number.isSafeInteger(count) || count < 1) return null;
  return Math.min(count - 1, Math.floor(normalPosition(position) * count));
}
export function frameAt(rotation, position) {
  if (!rotation?.frames?.length) return null;
  const index = frameIndex(position, rotation.frames.length);
  return index === null ? null : { ...rotation.frames[index], index, count:rotation.frames.length };
}
export function extractRotation(evidence) {
  if (!Array.isArray(evidence)) return null;
  for (const entry of evidence) {
    if (entry?.kind !== "rotation" || entry.status !== "success" ||
        entry.metadata?.sequence_complete !== true || !Array.isArray(entry.frames) ||
        entry.frames.length < 2) continue;
    const frames = [];
    for (const frame of entry.frames) {
      const url = assetUrl(frame?.asset);
      if (!url || !Number.isSafeInteger(frame?.source_index) || frame.source_index < 0 ||
          !Number.isSafeInteger(frame?.stored_position) || frame.stored_position < 0 ||
          (frame.asset?.media_type && !frame.asset.media_type.startsWith("image/"))) {
        frames.length = 0;
        break;
      }
      frames.push({ url, sourceIndex:frame.source_index, storedPosition:frame.stored_position });
    }
    if (frames.length === entry.frames.length) return { frames, count:frames.length };
  }
  return null;
}
export function motionUnavailable(evidence) {
  if (!Array.isArray(evidence)) return "No recovered motion evidence";
  if (evidence.some(e=>e?.kind==="video" && e.status==="success" &&
      publicUrl(e.payload_asset?.storage?.url)))
    return "Original video only · no validated ordered frames";
  if (evidence.some(e=>e?.kind==="rotation"))
    return "Rotation incomplete or unavailable · original still above";
  return "No ordered rotation · original still above";
}
export function nearbyFrameIndices(position, count, radius=2) {
  const center = frameIndex(position,count);
  if (center === null) return [];
  const unique = new Set();
  for (let delta=1; delta<=radius; delta++) {
    unique.add((center + delta) % count);
    unique.add((center - delta + count) % count);
  }
  unique.delete(center);
  return [...unique];
}
export function prefetchURLs(rotation, position, mode=DEFAULT_PREFETCH_MODE) {
  if (!rotation) return [];
  const count=rotation.frames.length;
  const active=frameIndex(position,count);
  const indexes=mode==="all" ? Array.from({length:count},(_,i)=>i).filter(i=>i!==active) :
    nearbyFrameIndices(position,count);
  return indexes.map(i=>rotation.frames[i].url);
}
// Small async queue, reusable in browser and unit tests. The *all* policy queues
// many urls but never creates unbounded parallel image requests or holds bitmaps.
// stop() drops queued URLs and invalidates in-flight completion for old selections.
export function createPrefetchQueue(load, {concurrency=PREFETCH_CONCURRENCY}={}) {
  if (typeof load!=="function" || !Number.isSafeInteger(concurrency) || concurrency < 1)
    throw new TypeError("Invalid prefetch loader or concurrency");
  let active=0, queue=[], seen=new Set(), revision=0;
  const pump=()=>{
    while (active<concurrency && queue.length) {
      const {url, epoch}=queue.shift();
      if (epoch!==revision) continue;
      active++;
      Promise.resolve().then(()=>load(url)).catch(()=>{}).finally(()=>{
        active--;
        pump();
      });
    }
  };
  return {
    enqueue(urls) {
      for (const url of urls) {
        if (!publicUrl(url) || seen.has(url)) continue;
        seen.add(url);
        queue.push({url,epoch:revision});
      }
      pump();
    },
    stop() { revision++; queue=[]; seen=new Set(); },
    stats() { return {active,queued:queue.length,seen:seen.size}; }
  };
}
export function preloadImage(url) {
  return new Promise(resolve=>{
    const image=new Image();
    image.onload=()=>resolve(true);
    image.onerror=()=>resolve(false);
    image.src=url;
  });
}
