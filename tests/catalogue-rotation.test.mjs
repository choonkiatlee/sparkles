import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {extractRotation,frameIndexAt,stepPosition,createFramePreloader,
  FRAME_PREFETCH,PREFETCH_MODES} from "../catalogue/rotation.mjs";

const manifest = id => JSON.parse(readFileSync(new URL("../data/diamonds/"+id+".json",import.meta.url)));
const first=manifest("igi-lg756520111"),second=manifest("igi-lg816611062");

test("published rotations preserve actual array order despite scrambled stored positions",()=>{
  for (const doc of [first,second]) {
    const original=doc.evidence.find(e=>e.kind==="rotation");
    const result=extractRotation(doc.evidence);
    assert.equal(result.status,"available");
    assert.equal(result.frameCount,256);
    assert.equal(result.frames[0].sourceIndex,original.frames[0].source_index);
    assert.equal(result.frames[1].sourceIndex,original.frames[1].source_index);
    assert.equal(result.frames.at(-1).sourceIndex,original.frames.at(-1).source_index);
    assert.equal(result.frames[0].url,original.frames[0].asset.storage.url);
    assert.notEqual(original.frames[0].stored_position,0);
  }
});

test("ordinal normalization, mixed frame counts, wrap and step are deterministic",()=>{
  assert.equal(frameIndexAt(0,256),0);
  assert.equal(frameIndexAt(0.5,256),128);
  assert.equal(frameIndexAt(0.5,120),60);
  assert.equal(frameIndexAt(0.999,256),255);
  assert.equal(frameIndexAt(1,256),0);
  assert.equal(frameIndexAt(-0.01,256),253);
  assert.equal(stepPosition(0,256,-1),255/256);
  assert.equal(stepPosition(255/256,256,1),0);
  assert.equal(frameIndexAt(stepPosition(0.5,120,1),120),61);
  assert.throws(()=>frameIndexAt(NaN,256));
  assert.throws(()=>frameIndexAt(0,0));
});

test("incomplete, missing and video-only evidence never masquerades as rotation",()=>{
  const asset=url=>({media_type:"image/jpeg",storage:{backend:"r2",url}});
  const f=i=>({source_index:i,stored_position:200-i,asset:asset("https://r2.example.test/f"+i+".jpg")});
  const rotation=frames=>({kind:"rotation",status:"success",
    metadata:{sequence_complete:true,frame_count:frames.length},frames});
  const ok=extractRotation([rotation([f(0),f(1),f(2)])]);
  assert.equal(ok.status,"available");
  assert.equal(ok.frames[1].url,"https://r2.example.test/f1.jpg");
  assert.equal(extractRotation([rotation([f(0),f(0)])]).status,"unavailable");
  assert.equal(extractRotation([{...rotation([f(0),f(1)]),metadata:{sequence_complete:false}}]).status,"unavailable");
  assert.equal(extractRotation([rotation([{...f(0),asset:asset("javascript:evil")},f(1)])]).status,"unavailable");
  assert.equal(extractRotation([rotation([{...f(0),asset:asset("https://x/u")},f(1)])]).status,"available");
  const video={kind:"video",status:"success",payload_asset:{storage:{url:"https://cdn.example.test/video.mp4"}}};
  assert.equal(extractRotation([video]).status,"video_only");
  assert.equal(extractRotation([]).status,"unavailable");
  assert.equal(extractRotation([{...rotation([f(0),f(1)]),status:"failed"},video]).status,"video_only");
  assert.equal(extractRotation([{...rotation([f(0),f(1)]),metadata:{sequence_complete:true,frame_count:255}}]).status,"unavailable");
});


const sequence = (size,prefix="https://example.test/")=>extractRotation([{
  kind:"rotation",status:"success",metadata:{sequence_complete:true},
  frames:Array.from({length:size},(_,i)=>({source_index:i,
    asset:{media_type:"image/jpeg",storage:{url:prefix+i+".jpg"}}}))
}]);

test("full prefetch is default ONLY on selected observed sequences, with concurrency caps",async()=>{
  assert.deepEqual(PREFETCH_MODES,["none","nearby","all"]);
  assert.equal(FRAME_PREFETCH.mode,"all");
  const requests=[],pending=[];
  const factory=()=>{
    const image={onload:null,onerror:null};
    Object.defineProperty(image,"src",{set(url){requests.push(url);pending.push(image);}});
    return image;
  };
  const p=createFramePreloader({mode:"all",maxConcurrent:2,maxDecodedImages:3,imageFactory:factory});
  assert.equal(p.stats().total,0);
  const a=sequence(8),b=sequence(4,"https://r2.example.test/");
  p.observe([a,b],0);
  assert.equal(requests.length,2);
  assert.equal(p.stats().queued,10);
  for(let i=0;i<12;i++)pending[i].onload();
  assert.equal(requests.length,12);
  assert.equal(p.stats().loaded,12);
  assert.equal(p.stats().total,12);
  assert.ok(p.stats().retained<=3);
  p.observe([a,b],0.5);
  assert.equal(requests.length,12,"full mode must not requeue evicted frames on seek");
  p.stop();
  assert.equal(p.stats().total,0);
});

test("demand priority, retry, dedup and safe cleanup",async()=>{
  const pending=[],requests=[];
  const factory=()=>{
    const image={onload:null,onerror:null};
    Object.defineProperty(image,"src",{set(url){requests.push(url);pending.push(image);}});
    return image;
  };
  const p=createFramePreloader({mode:"all",maxConcurrent:1,maxDecodedImages:2,imageFactory:factory});
  const seq=sequence(5);
  p.observe([seq],0);
  const fourth=seq.frames[4].url;
  const promise=p.ensure(fourth);
  pending[0].onload();
  assert.equal(requests[1],fourth,"demand should jump ahead of background queue");
  pending[1].onerror();
  assert.equal(await promise,null);
  assert.equal(p.stats().failed,1);
  const promise2=p.ensure(fourth,{retry:true});
  // A previously failed frame is retried after active background network work.
  let ix=2;
  while(requests.at(-1)!==fourth && ix<10){pending[ix].onload();ix++;}
  assert.equal(requests.at(-1),fourth);
  pending.at(-1).onload();
  assert.equal((await promise2)!==null,true);
  p.stop();
  const p2=createFramePreloader({mode:"none",imageFactory:factory});
  p2.observe([seq],0);
  assert.equal(p2.stats().total,0);
  p2.stop();
});

test("nearby mode limits requests to just requested neighbors with wrap",async()=>{
  const requests=[];
  const p=createFramePreloader({mode:"nearby",nearbyRadius:1,imageFactory:()=>{
    const image={onload:null,onerror:null};
    Object.defineProperty(image,"src",{set(url){requests.push(url);image.onload();}});
    return image;
  }});
  const seq=sequence(6,"https://github.com/assets/");
  p.observe([seq],0);
  assert.deepEqual(requests.sort(),["https://github.com/assets/1.jpg","https://github.com/assets/5.jpg"]);
  assert.equal(p.stats().total,2);
  p.stop();
});
