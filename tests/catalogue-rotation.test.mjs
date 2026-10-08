import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {extractRotation,frameIndexAt,stepPosition,createFramePreloader,
  FRAME_PREFETCH,PREFETCH_MODES,createFrameGate} from "../catalogue/rotation.mjs";

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

test("full prefetch exists, is opt-in, loads selected frames, and respects concurrency",()=>{
  assert.deepEqual(PREFETCH_MODES,["none","nearby","all"]);
  assert.equal(FRAME_PREFETCH.mode,"all");
  const seq=extractRotation([{
    kind:"rotation",status:"success",metadata:{sequence_complete:true},
    frames:Array.from({length:8},(_,i)=>({source_index:i,
      asset:{storage:{url:"https://example.test/"+i+".jpg"},media_type:"image/jpeg"}}))
  }]);
  const requests=[], pending=[];
  const imageFactory=()=>{
    const image={onload:null,onerror:null};
    Object.defineProperty(image,"src",{set(url){requests.push(url);pending.push(image);}});
    return image;
  };
  const idle=createFramePreloader({mode:"none",imageFactory});
  idle.observe([seq],0);
  assert.equal(requests.length,0);
  idle.stop();
  const preload=createFramePreloader({mode:"all",maxConcurrent:2,imageFactory});
  preload.observe([seq],0);
  assert.equal(requests.length,2);
  assert.equal(preload.stats().queued,6);
  for(let i=0;i<8;i++) pending[i].onload();
  assert.equal(requests.length,8);
  assert.equal(new Set(requests).size,8);
  preload.observe([seq],0.5);
  assert.equal(requests.length,8);
  preload.stop();
  assert.equal(preload.stats().queued,0);
});

test("nearby prefetch wraps and remains bounded to neighboring image URLs",()=>{
  const frames=Array.from({length:6},(_,i)=>({source_index:i,
    asset:{storage:{backend:"github_release",url:"https://github.com/assets/"+i+".jpg"},media_type:"image/jpeg"}}));
  const seq=extractRotation([{kind:"rotation",status:"success",metadata:{sequence_complete:true},frames}]);
  const requested=[];
  const preloader=createFramePreloader({mode:"nearby",nearbyRadius:1,imageFactory:()=>{
    const image={onload:null,onerror:null};
    Object.defineProperty(image,"src",{set(url){requested.push(url);image.onload();}});
    return image;
  }});
  preloader.observe([seq],0);
  assert.deepEqual(requested.sort(),["https://github.com/assets/1.jpg","https://github.com/assets/5.jpg"]);
  preloader.stop();
});


test("urgent visible frame jumps ahead of hundreds of queued bulk requests",()=>{
  const seq=extractRotation([{
    kind:"rotation",status:"success",metadata:{sequence_complete:true},
    frames:Array.from({length:24},(_,i)=>({source_index:i,
      asset:{storage:{url:"https://media.test/"+i+".jpg"},media_type:"image/jpeg"}}))
  }]);
  const requested=[],pending=[];
  const preloader=createFramePreloader({mode:"all",maxConcurrent:1,maxDecoded:3,
    imageFactory:()=>{
      const img={onload:null,onerror:null};
      Object.defineProperty(img,"src",{set(url){requested.push(url);pending.push(img);}});
      return img;
    }
  });
  preloader.observe([seq],0);
  assert.equal(requested.length,1);
  assert.equal(preloader.stats().total,24);
  const urgent=preloader.request(seq.frames[20].url,{priority:true});
  pending[0].onload();
  assert.equal(requested[1],seq.frames[20].url);
  pending[1].onload();
  return urgent.then(img=>{
    assert.ok(img);
    assert.equal(preloader.stats().loaded,2);
    preloader.stop();
  });
});

test("decoded-frame retention is bounded even when every original is prefetched",()=>{
  const seq=extractRotation([{
    kind:"rotation",status:"success",metadata:{sequence_complete:true},
    frames:Array.from({length:12},(_,i)=>({source_index:i,
      asset:{storage:{url:"https://media.test/"+i+".jpg"},media_type:"image/jpeg"}}))
  }]);
  const requests=[],pending=[];
  const cache=createFramePreloader({mode:"all",maxConcurrent:2,maxDecoded:2,
    imageFactory:()=>{
      const img={onload:null,onerror:null};
      Object.defineProperty(img,"src",{set(url){requests.push(url);pending.push(img);}});
      return img;
    }
  });
  cache.observe([seq],0);
  for(let i=0;i<12;i++) pending[i].onload();
  assert.equal(cache.stats().loaded,12);
  assert.equal(cache.stats().decoded,2);
  assert.equal(cache.stats().active,0);
  assert.equal(cache.stats().queued,0);
  cache.stop();
});

test("changing all to visible-only cancels queued bulk tasks without cancelling displayed requests",async()=>{
  const seq=extractRotation([{
    kind:"rotation",status:"success",metadata:{sequence_complete:true},
    frames:Array.from({length:6},(_,i)=>({source_index:i,
      asset:{storage:{url:"https://media.test/"+i+".jpg"},media_type:"image/jpeg"}}))
  }]);
  const pending=[];
  const manager=createFramePreloader({mode:"all",maxConcurrent:1,imageFactory:()=>{
    const img={onload:null,onerror:null};
    Object.defineProperty(img,"src",{set(){pending.push(img);}});
    return img;
  }});
  manager.observe([seq],0);
  assert.equal(manager.stats().queued,5);
  manager.setMode("none",[seq],0);
  assert.equal(manager.stats().queued,0);
  assert.equal(manager.mode,"none");
  pending[0].onload();
  assert.equal(manager.stats().loaded,1);
  manager.stop();
});

test("stale fast scrubs never paint an older image and failure preserves prior displayed view",async()=>{
  const pending=new Map(),presented=[],errors=[];
  const gate=createFrameGate({
    load:url=>new Promise(resolve=>pending.set(url,resolve)),
    present:frame=>presented.push(frame.url),
    onError:frame=>errors.push(frame.url)
  });
  const frame=id=>({url:"https://media.test/"+id+".jpg",ordinal:id});
  gate.show(frame(1));
  await new Promise(resolve=>setImmediate(resolve));
  pending.get(frame(1).url)({ok:true});
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(presented,[frame(1).url]);
  gate.show(frame(2));gate.show(frame(3));
  await new Promise(resolve=>setImmediate(resolve));
  pending.get(frame(3).url)({ok:true});
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(presented,[frame(1).url,frame(3).url]);
  pending.get(frame(2).url)({ok:true});
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(presented,[frame(1).url,frame(3).url]);
  gate.show(frame(4));
  await new Promise(resolve=>setImmediate(resolve));
  pending.get(frame(4).url)(null);
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(errors,[frame(4).url]);
  assert.equal(gate.shownURL,frame(3).url);
  gate.retry(frame(4));
  await new Promise(resolve=>setImmediate(resolve));
  pending.get(frame(4).url)({ok:true});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(gate.shownURL,frame(4).url);
  gate.stop();
});
