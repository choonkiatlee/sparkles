import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {extractRotation,frameIndexAt,stepPosition,createFramePreloader,
  FRAME_PREFETCH,PREFETCH_MODES,createBufferedFrameCoordinator} from "../catalogue/rotation.mjs";

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

// C3b network priority, retry, decoded-LRU and full-default contracts are
// exercised below with the public focus/retry/stats API.

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


test("full prefetch prioritizes newly scrubbed frame over queued backgrounds",async()=>{
  const seq=extractRotation([{kind:"rotation",status:"success",
    metadata:{sequence_complete:true},
    frames:Array.from({length:10},(_,i)=>({source_index:i,
      asset:{media_type:"image/jpeg",storage:{url:"https://assets.test/"+i+".jpg"}}}))}]);
  const requests=[],images=[];
  const preload=createFramePreloader({mode:"all",maxConcurrent:1,maxDecoded:2,
    imageFactory:()=>{
      const img={onload:null,onerror:null};
      Object.defineProperty(img,"src",{set(value){requests.push(value);images.push(img);}});
      return img;
    }});
  preload.observe([seq],0);
  assert.equal(requests.length,1);
  const focused=preload.focus([seq.frames[9].url]);
  images[0].onload();
  assert.equal(requests[1],seq.frames[9].url);
  images[1].onload();
  const [ready]=await focused;
  assert.ok(ready);
  for(let i=2;i<10;i++) images[i].onload();
  assert.equal(preload.stats().completed,10);
  assert.equal(preload.stats().decoded,2);
  assert.equal(requests.length,10);
  preload.stop();
});

test("prefetch progress, error and on-demand retry preserve independent original URLs",async()=>{
  const requested=[];
  const factory=()=>{
    const img={onload:null,onerror:null};
    Object.defineProperty(img,"src",{set(value){requested.push({value,img});}});
    return img;
  };
  const preloader=createFramePreloader({mode:"nearby",maxConcurrent:2,imageFactory:factory});
  let latest;
  const unsubscribe=preloader.subscribe(state=>{latest=state;});
  const urls=["https://example.test/one.jpg","https://example.test/two.jpg"];
  const pending=preloader.focus(urls);
  assert.equal(latest.active,2);
  requested[0].img.onload();
  requested[1].img.onerror();
  const result=await pending;
  assert.ok(result[0]);assert.equal(result[1],null);
  assert.equal(latest.completed,1);assert.equal(latest.failed,1);
  const retry=preloader.retry(urls[1]);
  assert.equal(requested.length,3);
  requested[2].img.onload();
  assert.ok(await retry);
  assert.equal(preloader.stats().failed,0);
  assert.equal(preloader.stats().completed,2);
  unsubscribe();preloader.stop();
});

test("stale scrub completion never commits after a newer one or player teardown",async()=>{
  const resolvers=[];
  const committed=[];
  const coordinator=createBufferedFrameCoordinator(()=>new Promise(resolve=>resolvers.push(resolve)));
  const old=coordinator.seek(["frame-10"],x=>committed.push(["old",x]));
  const latest=coordinator.seek(["frame-200"],x=>committed.push(["latest",x]));
  resolvers[1](["ready-200"]);
  assert.equal(await latest,true);
  resolvers[0](["late-10"]);
  assert.equal(await old,false);
  assert.deepEqual(committed,[["latest",["ready-200"]]]);
  const teardown=coordinator.seek(["frame-20"],x=>committed.push(["after close",x]));
  coordinator.close();
  resolvers[2](["ready-20"]);
  assert.equal(await teardown,false);
  assert.equal(committed.length,1);
});

test("all prefetch works across mixed count selected stones and progress is bounded",()=>{
  const make=(base,n)=>extractRotation([{kind:"rotation",status:"success",
    metadata:{sequence_complete:true,frame_count:n},
    frames:Array.from({length:n},(_,i)=>({source_index:i,
      asset:{storage:{url:"https://"+base+".test/"+i+".jpg"}}}))}]);
  const sets=[make("release",8),make("r2",12)];
  const requested=[],pending=[];
  const preload=createFramePreloader({mode:"all",maxConcurrent:3,maxDecoded:4,
    imageFactory:()=>{
      const img={onload:null,onerror:null};
      Object.defineProperty(img,"src",{set(value){requested.push(value);pending.push(img);}});
      return img;
    }});
  preload.observe(sets,0);
  preload.observe(sets,0.5);
  assert.equal(preload.stats().total,20);
  assert.equal(preload.stats().queued,17);
  for(let i=0;i<20;i++)pending[i].onload();
  assert.equal(new Set(requested).size,20);
  assert.equal(preload.stats().completed,20);
  assert.ok(preload.stats().decoded<=4);
  preload.stop();
});

test("actual saved motion source-byte estimates are positive and remain separate",()=>{
  const firstSeq=extractRotation(first.evidence);
  const secondSeq=extractRotation(second.evidence);
  assert.ok(firstSeq.totalBytes>1_000_000);
  assert.ok(secondSeq.totalBytes>1_000_000);
  assert.notEqual(firstSeq.frames[0].url,secondSeq.frames[0].url);
});
