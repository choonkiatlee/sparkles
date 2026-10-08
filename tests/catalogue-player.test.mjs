// Browser image-loading simulation without a DOM framework. Verify that the
// actual C3b view holds decoded images through slow/mismatched frame fetches.
import test from "node:test";
import assert from "node:assert/strict";
import { createRotationPlayer } from "../catalogue/rotation-player.mjs";

class Element {
  constructor(tag) { this.tag=tag;this.children=[];this.handlers={};this.hidden=false; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=[...nodes]; }
  setAttribute(key,val) { this[key]=val; }
  addEventListener(event,callback) { this.handlers[event]=callback; }
  set textContent(text) { this._text=String(text);this.children=[]; }
  get textContent() { return this._text; }
}
const makeSequence = id=>({
  status:"available",frameCount:4,totalBytes:64000,
  frames:Array.from({length:4},(_,i)=>({
    url:"https://assets.example.test/"+id+"/"+i+".jpg",sourceIndex:i,ordinal:i
  })),
});
async function flush() { for(let i=0;i<12;i++)await Promise.resolve(); }

test("360 player keeps prior decoded frames until both new columns are ready",async()=>{
  const priorDocument=globalThis.document,priorImage=globalThis.Image,requests=[];
  class FakeImage extends Element {
    constructor(){super("img");}
    set src(url){this._src=url;requests.push(this);}
    get src(){return this._src;}
    decode(){return Promise.resolve();}
  }
  globalThis.document={createElement:tag=>new Element(tag)};
  globalThis.Image=FakeImage;
  try{
    const host=new Element("div"),left=new Element("td"),right=new Element("td");
    const player=createRotationPlayer({host,slots:new Map([["a",left],["b",right]]),
      config:{mode:"none",nearbyRadius:2,maxConcurrent:4,maxDecoded:8}});
    const stage=slot=>slot.children[0].children[0];
    player.setStone("a",makeSequence("a"),null,"A");
    player.setStone("b",makeSequence("b"),null,"B");
    const originals=requests.filter(i=>i.src.endsWith("/0.jpg"));
    assert.equal(originals.length,2);
    originals.forEach(img=>img.onload());
    await flush();
    const initialLeft=stage(left).children[0],initialRight=stage(right).children[0];
    assert.equal(initialLeft.src,"https://assets.example.test/a/0.jpg");
    assert.equal(initialRight.src,"https://assets.example.test/b/0.jpg");
    const seek=player.seek(0.5);
    const second=requests.filter(i=>i.src.endsWith("/2.jpg"));
    assert.equal(second.length,2);
    second[0].onload();
    await flush();
    assert.equal(stage(left).children[0],initialLeft);
    assert.equal(stage(right).children[0],initialRight);
    second[1].onload();
    await seek;
    assert.equal(stage(left).children[0].src,"https://assets.example.test/a/2.jpg");
    assert.equal(stage(right).children[0].src,"https://assets.example.test/b/2.jpg");

    const stale=player.seek(0.75);
    const latest=player.seek(0.25);
    requests.filter(i=>i.src.endsWith("/1.jpg")).forEach(img=>img.onload());
    await latest;
    requests.filter(i=>i.src.endsWith("/3.jpg")).forEach(img=>img.onload());
    await stale;
    assert.equal(stage(left).children[0].src,"https://assets.example.test/a/1.jpg");
    assert.equal(stage(right).children[0].src,"https://assets.example.test/b/1.jpg");

    const bad=player.seek(0.5);
    // Already decoded URLs can be reused, so trigger a never-before-displayed
    // frame's fetch failure instead (0 is still decoded from initial load).
    await bad;
    player.destroy();
    assert.equal(await player.seek(0),false);
  }finally{
    globalThis.document=priorDocument;globalThis.Image=priorImage;
  }
});
