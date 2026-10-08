import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  PREFETCH_ALL_DEFAULT, DEFAULT_PREFETCH_MODE, PREFETCH_CONCURRENCY,
  normalPosition, frameIndex, frameAt, extractRotation, motionUnavailable,
  nearbyFrameIndices, prefetchURLs, createPrefetchQueue
} from "../catalogue/rotation.mjs";
import { projectComparison } from "../catalogue/compare.mjs";

function saved(id) {
  const catalog=JSON.parse(readFileSync(new URL("../data/catalog.json",import.meta.url)));
  const row=catalog.diamonds.find(r=>r.id===id);
  const manifest=JSON.parse(readFileSync(new URL("../"+row.manifest_path,import.meta.url)));
  return {row,manifest};
}
function synthetic(count,base="https://cdn.example.test",backend="r2") {
  return [{
    kind:"rotation",status:"success",metadata:{sequence_complete:true},
    frames:Array.from({length:count},(_,i)=>({
      source_index:(i*7)%Math.max(1,count),stored_position:i,
      asset:{media_type:"image/jpeg",storage:{backend,url:base+"/frame-"+i+".jpg"}}
    }))
  }];
}

test("real 256-frame published motion projects without fetching any images",()=>{
  for (const id of ["igi-lg756520111","igi-lg816611062"]) {
    const {row,manifest}=saved(id);
    const projected=projectComparison(row,manifest);
    const rotation=extractRotation(projected.evidence);
    assert.equal(rotation.count,256);
    assert.equal(rotation.frames[0].storedPosition,
      manifest.evidence.find(e=>e.kind==="rotation").frames[0].stored_position);
    assert.match(rotation.frames[0].url,/github.com\/.*\.jpg$/);
    assert.equal(frameAt(rotation,0).index,0);
    assert.equal(frameAt(rotation,0.5).index,128);
    assert.equal(frameAt(rotation,0.99999).index,255);
  }
});

test("shared normalized ordinal position maps mixed 64/120/256 sequence counts",()=>{
  const progress=[0,0.25,0.5,0.99,1,-0.001];
  assert.deepEqual(progress.map(p=>frameIndex(p,64)),[0,16,32,63,0,63]);
  assert.deepEqual(progress.map(p=>frameIndex(p,120)),[0,30,60,118,0,119]);
  assert.deepEqual(progress.map(p=>frameIndex(p,256)),[0,64,128,253,0,255]);
  assert.equal(frameIndex(NaN,256),0);
  assert.equal(frameIndex(Infinity,256),0);
  assert.equal(frameIndex(0,0),null);
  assert.equal(normalPosition(-0.25),0.75);
});

test("per-column resolved original URLs work with R2 and publisher Release backend",()=>{
  for (const backend of ["r2","github_release"]) {
    const evidence=synthetic(7,"https://media.test",backend);
    const spin=extractRotation(evidence);
    assert.equal(spin.count,7);
    assert.equal(frameAt(spin,0.5).url,"https://media.test/frame-3.jpg");
    assert.equal(frameAt(spin,0.5).sourceIndex,(3*7)%7);
  }
});

test("incomplete and malicious rotation data cannot be presented as a validated sequence",()=>{
  assert.equal(extractRotation([{kind:"rotation",status:"success",metadata:{sequence_complete:false},
    frames:synthetic(2)[0].frames}]),null);
  assert.equal(extractRotation([{kind:"rotation",status:"failed",metadata:{sequence_complete:true},
    frames:synthetic(2)[0].frames}]),null);
  assert.equal(extractRotation([{...synthetic(3)[0],frames:[
    ...synthetic(3)[0].frames.slice(0,2),
    {source_index:3,stored_position:3,asset:{storage:{url:"javascript:alert(1)"}}}
  ]}]),null);
  assert.equal(extractRotation([{...synthetic(2)[0],frames:[
    ...synthetic(2)[0].frames.slice(0,1),
    {source_index:1,asset:{storage:{url:"https://cdn.example.test/a.jpg"}}}
  ]}]),null);
  assert.match(motionUnavailable([{kind:"rotation",status:"failed"}]),/Rotation incomplete/);
  assert.match(motionUnavailable([{kind:"video",status:"success",
    payload_asset:{storage:{url:"https://example.test/movie.mp4"}}}]),/video only/i);
  assert.match(motionUnavailable([]),/No ordered rotation/);
  assert.match(motionUnavailable(null),/No recovered motion evidence/);
});

test("bounded nearby mode is the default; all-mode queues exactly other frames only",()=>{
  assert.equal(PREFETCH_ALL_DEFAULT,false);
  assert.equal(DEFAULT_PREFETCH_MODE,"nearby");
  assert.equal(PREFETCH_CONCURRENCY,3);
  const spin=extractRotation(synthetic(256));
  assert.deepEqual(nearbyFrameIndices(0,256),[1,255,2,254]);
  const nearby=prefetchURLs(spin,0);
  assert.equal(nearby.length,4);
  assert.ok(nearby.every(url=>url.includes("frame-")));
  const all=prefetchURLs(spin,0,"all");
  assert.equal(all.length,255);
  assert.ok(!all.includes(spin.frames[0].url));
  assert.ok(all.includes(spin.frames[255].url));
  const selected=[extractRotation(synthetic(64)),extractRotation(synthetic(256))];
  assert.equal(selected.flatMap(r=>prefetchURLs(r,0)).length,8);
  assert.equal(selected.flatMap(r=>prefetchURLs(r,0,"all")).length,318);
  assert.equal(prefetchURLs(null,0,"all").length,0);
});

test("full-prefetch queue respects concurrency and stop drops old queued URLs",async()=>{
  let peak=0, active=0;
  const pending=[];
  const requested=[];
  const q=createPrefetchQueue(url=>new Promise(resolve=>{
    requested.push(url);
    active++; peak=Math.max(peak,active);
    pending.push(()=>{active--;resolve(true);});
  }),{concurrency:2});
  const urls=Array.from({length:12},(_,i)=>"https://assets.test/"+i+".jpg");
  q.enqueue(urls);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requested.length,2);
  assert.equal(peak,2);
  assert.equal(q.stats().queued,10);
  pending.shift()();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requested.length,3);
  q.stop();
  assert.equal(q.stats().queued,0);
  while (pending.length) pending.shift()();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requested.length,3,"stale queued requests must not resume");
  const newURL="https://assets.test/new.jpg";
  q.enqueue([newURL,newURL,"javascript:alert(1)"]);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requested.at(-1),newURL);
  assert.equal(q.stats().seen,1);
  pending.shift()();
  await new Promise(resolve=>setImmediate(resolve));
});
