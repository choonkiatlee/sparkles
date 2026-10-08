// Browser-side *rendering* previews of published originals; no extra media,
// transcoding, hosted thumbnails or calibrated camera angles required.
// These small canvases are reused while scrubbing. Network bytes are still the
// original images: the first spin depends on their download/decode speed.
export const PREVIEW_OPTIONS=Object.freeze({maxSide:160,maxFrames:768});

const sourceSize=source=>{
  const width=source?.naturalWidth || source?.width;
  const height=source?.naturalHeight || source?.height;
  return Number.isFinite(width) && Number.isFinite(height) &&
    width>0 && height>0 ? {width,height} : null;
};

const canvasFactory=()=>typeof OffscreenCanvas==="function" ?
  new OffscreenCanvas(1,1) : document.createElement("canvas");

export function createPreviewCache({
  maxSide=PREVIEW_OPTIONS.maxSide,
  maxFrames=PREVIEW_OPTIONS.maxFrames,
  makeCanvas=canvasFactory,
}={}) {
  if(!Number.isInteger(maxSide) || maxSide<32 || maxSide>256 ||
     !Number.isInteger(maxFrames) || maxFrames<2 || maxFrames>2048)
    throw new RangeError("Invalid preview cache bounds");
  const frames=new Map();
  let closed=false;
  function add(url,original) {
    if(closed || !url)return false;
    if(frames.has(url))return true;
    const size=sourceSize(original);
    if(!size)return false;
    try {
      const canvas=makeCanvas();
      const ratio=Math.min(1,maxSide/Math.max(size.width,size.height));
      canvas.width=Math.max(1,Math.round(size.width*ratio));
      canvas.height=Math.max(1,Math.round(size.height*ratio));
      const ctx=canvas.getContext?.("2d",{alpha:false});
      if(!ctx)return false;
      ctx.drawImage(original,0,0,canvas.width,canvas.height);
      // Store a bounded, downscaled canvas rather than retaining every
      // decoded full-resolution image. No pixel reads or exports: cross-origin
      // Release images can be drawn without needing CORS opt-in.
      frames.set(url,canvas);
      while(frames.size>maxFrames) frames.delete(frames.keys().next().value);
      return true;
    }catch{return false;} // Older browsers still use original-image fallback.
  }
  function get(url) {
    if(closed)return null;
    const value=frames.get(url);
    if(value){frames.delete(url);frames.set(url,value);}
    return value||null;
  }
  function clear() {closed=true;frames.clear();}
  return {add,get,clear,stats:()=>({count:frames.size,maxFrames,maxSide})};
}

// Return null if Canvas2D is unavailable, so the existing decoded-image
// renderer remains the graceful fallback. Never read pixels from the canvas.
export function createCanvasSurface(stage,report,makeCanvas=()=>document.createElement("canvas")) {
  let canvas,ctx;
  try {
    canvas=makeCanvas();
    // Transparent letterboxing lets the stage's neutral background show.
    ctx=canvas?.getContext?.("2d",{alpha:true});
    if(!ctx)return null;
  }catch{return null;}
  canvas.className="motion-image motion-canvas";
  canvas.setAttribute("role","img");
  canvas.setAttribute("aria-label","Original rotation of "+report+"; relative sequence position");
  let attached=false;
  function draw(source) {
    const sourceDimensions=sourceSize(source);
    if(!sourceDimensions)return false;
    try {
      const width=stage.clientWidth || 300;
      const height=stage.clientHeight || 195;
      const pixelRatio=Math.min(2,typeof devicePixelRatio==="number" ? devicePixelRatio : 1);
      const w=Math.max(1,Math.round(width*pixelRatio));
      const h=Math.max(1,Math.round(height*pixelRatio));
      if(canvas.width!==w)canvas.width=w;
      if(canvas.height!==h)canvas.height=h;
      // Changing canvas dimensions resets the context; reacquire it.
      ctx=canvas.getContext("2d",{alpha:true});
      const ratio=Math.min(w/sourceDimensions.width,h/sourceDimensions.height);
      const dw=sourceDimensions.width*ratio, dh=sourceDimensions.height*ratio;
      ctx.clearRect(0,0,w,h);
      ctx.drawImage(source,(w-dw)/2,(h-dh)/2,dw,dh);
      if(!attached){stage.replaceChildren(canvas);attached=true;}
      return true;
    }catch{return false;}
  }
  return {draw,canvas};
}
