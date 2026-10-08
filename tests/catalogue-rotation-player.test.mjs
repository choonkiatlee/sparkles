import test from "node:test";
import assert from "node:assert/strict";
import {createRotationPlayer} from "../catalogue/rotation-player.mjs";

class FakeElement {
  constructor(tag,queue) {
    this.tag=tag;this.queue=queue;this.children=[];this.hidden=false;
    this.className="";this.listeners=new Map();this.textContent="";
    this.attributes=new Map();this.disabled=false;this.onload=null;this.onerror=null;
  }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(k,v){this.attributes.set(k,v);}
  addEventListener(k,fn){this.listeners.set(k,fn);}
  removeEventListener(k){this.listeners.delete(k);}
  set src(url){
    this._src=url;
    if(this.tag==="img" && url) this.queue.push({node:this,url});
  }
  get src(){return this._src;}
  decode(){return Promise.resolve();}
  dispatch(k){this.listeners.get(k)?.();}
}
const find=(el,cls)=>{
  if(el.className?.split(" ").includes(cls)) return el;
  for(const c of el.children||[]){
    const found=find(c,cls);
    if(found)return found;
  }
  return null;
};
const sequence=(name,n=3)=>({
  status:"available",frameCount:n,
  frames:Array.from({length:n},(_,ordinal)=>({
    sourceIndex:ordinal,ordinal,url:"https://media.test/"+name+"/"+ordinal+".jpg",
  })),
});
const flush=async()=>{await Promise.resolve();await Promise.resolve();};

test("buffered comparison holds the previous original until next image finishes decoding",async()=>{
  const stageRequests=[],prefetchRequests=[];
  const docListeners=new Map();
  const originalDoc=globalThis.document;
  const originalImage=globalThis.Image;
  globalThis.document={
    hidden:false,
    createElement:tag=>new FakeElement(tag,stageRequests),
    addEventListener:(key,fn)=>docListeners.set(key,fn),
    removeEventListener:key=>docListeners.delete(key),
  };
  globalThis.Image=class {
    constructor(){this.onload=null;this.onerror=null;}
    set src(url){if(url)prefetchRequests.push({node:this,url});}
  };
  try {
    const host=new FakeElement("div",stageRequests);
    const slots=new Map([
      ["A",new FakeElement("td",stageRequests)],
      ["B",new FakeElement("td",stageRequests)],
    ]);
    const player=createRotationPlayer({host,slots,config:{
      mode:"all",nearbyRadius:1,maxConcurrent:2,
    }});
    const play=find(host,"motion-play");
    player.setStone("A",sequence("A"),null);
    player.setStone("B",sequence("B"),null);
    assert.equal(play.disabled,true,"must finish full prefetch before autoplay");
    const startRequests=stageRequests.slice();
    assert.equal(startRequests.length,2);
    // Complete the initial displayed original frame on each side.
    for(const request of startRequests) request.node.onload();
    await flush();
    const stage=find(slots.get("A"),"motion-stage");
    const originals=stage.children.filter(e=>e.className==="motion-image");
    assert.equal(originals.filter(e=>!e.hidden).length,1);
    const old=originals.find(e=>!e.hidden);
    player.seek(0.5);
    const next=stageRequests.at(-2).node;
    assert.equal(old.hidden,false,"old original remains visible until new image decodes");
    assert.equal(next.hidden,true);
    next.onload();
    await flush();
    assert.equal(old.hidden,true);
    assert.equal(next.hidden,false,"decoded new original replaces previous atomically");

    // All mode must fetch all selected originals but only after comparison.
    let i=0;
    while(i<prefetchRequests.length){
      const pending=prefetchRequests[i++];
      pending.node.onload();
    }
    assert.equal(prefetchRequests.length,6);
    assert.equal(play.disabled,false,"play enabled when both complete ordered sequences loaded");
    assert.match(find(host,"motion-progress-label").textContent,/Ready: 6\/6/);

    // Rapid seeks must not let obsolete callbacks overwrite newer frames.
    player.seek(0.999);
    const stale=stageRequests.at(-2).node;
    const oldCallback=stale.onload;
    player.seek(0);
    oldCallback();
    await flush();
    assert.equal(next.hidden,false,"stale callback cannot blank the current image");
    assert.ok(docListeners.has("visibilitychange"));
    player.destroy();
    assert.equal(docListeners.has("visibilitychange"),false);
  } finally {
    globalThis.document=originalDoc;
    globalThis.Image=originalImage;
  }
});
