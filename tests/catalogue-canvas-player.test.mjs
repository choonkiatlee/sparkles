import test from "node:test";
import assert from "node:assert/strict";
import {createRotationPlayer} from "../catalogue/rotation-player.mjs";

class Element {
  constructor(tag){this.tag=tag;this.children=[];this.handlers={};this.hidden=false;
    this.clientWidth=260;this.clientHeight=195;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(key,value){this[key]=value;}
  addEventListener(type,fn){this.handlers[type]=fn;}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text;}
}
class Canvas extends Element {
  constructor(){super("canvas");this.width=300;this.height=150;this.paints=[];}
  getContext(){return {
    clearRect(){},
    drawImage:(src,...args)=>this.paints.push({src,args}),
  };}
}
const sequence=id=>({
  status:"available",frameCount:4,totalBytes:64000,
  frames:Array.from({length:4},(_,i)=>({
    sourceIndex:i,ordinal:i,url:"https://example.test/"+id+"/"+i+".jpg",
  })),
});
const flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};

test("dual Canvas player spins with compact cached previews then refines both original frames",async()=>{
  const oldDoc=globalThis.document,oldImg=globalThis.Image;
  const requests=[];
  class Image extends Element {
    constructor(){super("img");this.naturalWidth=640;this.naturalHeight=480;}
    set src(value){this._src=value;requests.push(this);}
    get src(){return this._src;}
    decode(){return Promise.resolve();}
  }
  globalThis.document={createElement:tag=>tag==="canvas"?new Canvas():new Element(tag)};
  globalThis.Image=Image;
  try {
    const host=new Element("div"),left=new Element("td"),right=new Element("td");
    const player=createRotationPlayer({host,slots:new Map([["a",left],["b",right]]),
      config:{mode:"all",nearbyRadius:2,maxConcurrent:8,maxDecoded:8}});
    player.setStone("a",sequence("a"),null,"A");
    player.setStone("b",sequence("b"),null,"B");

    const completed=new Set();
    for(let round=0;round<12;round++){
      const pending=requests.filter(img=>!completed.has(img));
      pending.forEach(img=>{completed.add(img);img.onload();});
      await flush();
      if(requests.length>=8 && !requests.some(img=>!completed.has(img)))break;
    }
    assert.equal(new Set(requests.map(img=>img.src)).size,8,
      "existing original image URLs are downloaded, never replaced by new network endpoints");
    assert.equal(requests.length,8,"no repeated original downloads needed to build previews");

    const stage=slot=>slot.children[0].children[0];
    const leftCanvas=stage(left).children[0],rightCanvas=stage(right).children[0];
    assert.equal(leftCanvas.tag,"canvas");
    assert.equal(rightCanvas.tag,"canvas");
    assert.ok(leftCanvas.paints.at(-1).src instanceof Image);
    assert.ok(rightCanvas.paints.at(-1).src instanceof Image);
    const beforeCount=requests.length;

    await player.seek(0.5,{interactive:true});
    assert.equal(stage(left).children[0],leftCanvas);
    assert.equal(stage(right).children[0],rightCanvas);
    assert.equal(leftCanvas.paints.at(-1).src.tag,"canvas",
      "scrub displays the downscaled 160px preview");
    assert.equal(rightCanvas.paints.at(-1).src.tag,"canvas",
      "both selected diamonds advance together");
    assert.equal(leftCanvas.paints.at(-1).src.width,160);
    assert.equal(rightCanvas.paints.at(-1).src.width,160);
    assert.equal(requests.length,beforeCount,
      "preview scrubbing reuses already fetched frames with no extra HTTP requests");

    await player.seek(0.5);
    assert.ok(leftCanvas.paints.at(-1).src instanceof Image,
      "idle view refines from the retained full-resolution original");
    assert.ok(rightCanvas.paints.at(-1).src instanceof Image);
    assert.equal(stage(left).children[0],leftCanvas,
      "Canvas DOM element stays mounted across preview and refinement");
    player.destroy();
  }finally{
    globalThis.document=oldDoc;globalThis.Image=oldImg;
  }
});
