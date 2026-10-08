import test from "node:test";
import assert from "node:assert/strict";
import {createPreviewCache,createCanvasSurface} from "../catalogue/rotation-canvas.mjs";

const source=(name,width=640,height=480)=>({name,naturalWidth:width,naturalHeight:height});
const makeCanvas=(frames)=>{
  const canvas={width:0,height:0,events:[],role:null,
    setAttribute(key,value){this[key]=value;},
    getContext(){return {
      drawImage:(...args)=>{this.events.push(["draw",...args]);frames?.push(args);},
      clearRect:(...args)=>this.events.push(["clear",...args]),
    };}};
  return canvas;
};

test("compact previews preserve aspect ratio, evict old frames and never read pixels",()=>{
  const canvases=[];
  const cache=createPreviewCache({maxSide:160,maxFrames:2,makeCanvas:()=>{
    const canvas=makeCanvas();canvases.push(canvas);return canvas;
  }});
  const a=source("a"),b=source("b",400,800),c=source("c",100,100);
  assert.equal(cache.add("a",a),true);
  assert.deepEqual([canvases[0].width,canvases[0].height],[160,120]);
  assert.equal(cache.add("a",a),true);
  assert.equal(canvases.length,1,"same source does not need a second preview");
  assert.equal(cache.add("b",b),true);
  assert.deepEqual([canvases[1].width,canvases[1].height],[80,160]);
  assert.ok(cache.get("a"));
  assert.equal(cache.add("c",c),true);
  assert.equal(cache.get("b"),null,"least-recently-used preview was evicted");
  assert.ok(cache.get("a"));
  assert.ok(cache.get("c"));
  assert.equal(cache.stats().count,2);
  assert.equal(cache.add("bad",{naturalWidth:0,naturalHeight:0}),false);
  cache.clear();
  assert.equal(cache.get("a"),null);
  assert.equal(cache.add("new",a),false);
});

test("Canvas2D surface paints full originals and small previews into one stable DOM element",()=>{
  const canvas=makeCanvas(), stage={clientWidth:255,clientHeight:195,children:[],
    replaceChildren(...nodes){this.children=[...nodes];}};
  const surface=createCanvasSurface(stage,"IGI TEST",()=>canvas);
  assert.ok(surface);
  const original=source("original");
  const preview={name:"small canvas",width:160,height:120};
  assert.equal(surface.draw(original),true);
  assert.equal(stage.children[0],canvas);
  assert.deepEqual([canvas.width,canvas.height],[255,195]);
  assert.equal(canvas.events.at(-1)[1],original);
  assert.equal(surface.draw(preview),true);
  assert.equal(stage.children.length,1,"same canvas survives frame changes");
  assert.equal(stage.children[0],canvas);
  assert.equal(canvas.events.at(-1)[1],preview);
  assert.equal(canvas.role,"img");
  assert.equal(createCanvasSurface(stage,"IGI TEST",()=>({getContext:()=>null})),null);
});

test("preview cache tolerates browsers without canvas or unusable decoded dimensions",()=>{
  const cache=createPreviewCache({makeCanvas:()=>({getContext:()=>null})});
  assert.equal(cache.add("a",source("a")),false);
  assert.equal(cache.stats().count,0);
  assert.throws(()=>createPreviewCache({maxSide:999}),RangeError);
  assert.throws(()=>createPreviewCache({maxFrames:0}),RangeError);
});
