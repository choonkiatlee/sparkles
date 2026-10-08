// Real Chromium smoke of the saved catalogue, original GitHub Release motion
// assets and synchronized C3b player. Not a photometric quality judgement.
// Intentionally dispatched sparingly because a full 2 x 256-image warmup costs
// approximately 17 MiB per fresh browser context.
import assert from "node:assert/strict";
import {mkdir,writeFile} from "node:fs/promises";
import path from "node:path";
import {chromium,devices} from "playwright";

const origin=process.env.CATALOGUE_SMOKE_ORIGIN || "http://127.0.0.1:8765";
const route="/catalogue/?selected=igi-lg756520111%2Cigi-lg816611062&compare=1";
const resultDir=path.resolve("browser-smoke-results");
await mkdir(resultDir,{recursive:true});
const summaries=[];
const browser=await chromium.launch({headless:true});

async function runProfile(label,device) {
  const context=await browser.newContext(device);
  const page=await context.newPage();
  const errors=[];
  page.on("pageerror",error=>errors.push(String(error)));
  const started=Date.now();
  let summary={profile:label,result:"failed"};
  try {
    await page.goto(origin+route,{waitUntil:"domcontentloaded",timeout:30000});
    await page.locator("#comparison").waitFor({state:"visible",timeout:30000});
    await page.locator(".motion-image-stage").first().waitFor({timeout:30000});
    assert.equal(await page.locator(".motion-image-stage").count(),2,
      "Both original rotation columns must render");

    const toggle=page.getByRole("checkbox",{name:"Preload every original rotation frame for selected stones"});
    assert.equal(await toggle.isChecked(),true,"selected-stone full prefetch must be ON by default");
    await page.waitForFunction(()=>{
      const imgs=[...document.querySelectorAll(".motion-image-stage img")];
      return imgs.length===2 && imgs.every(img=>img.complete && img.naturalWidth>0);
    },null,{timeout:120000});
    const firstPaintSeconds=(Date.now()-started)/1000;

    // Validate the complete *real* media prefetch, not merely JS mocks. A
    // failed asset is a test failure, with progress/screenshots still archived.
    await page.waitForFunction(()=>{
      const status=document.querySelector(".motion-prefetch-progress")?.textContent||"";
      const m=/Preloaded (\d+) \/ (\d+) frames(?: · (\d+) failed)?/.exec(status);
      if(!m)return false;
      const done=Number(m[1]),total=Number(m[2]),failed=Number(m[3]||0);
      return total>=512 && done+failed>=total;
    },null,{timeout:240000});
    const warmupSeconds=(Date.now()-started)/1000;
    const progress=await page.locator(".motion-prefetch-progress").innerText();
    const failed=/ · (\d+) failed/.exec(progress);
    assert.equal(Number(failed?.[1]||0),0,"Every published original frame must load");
    assert.match(progress,/Preloaded 512 \/ 512 frames/);

    const blankCheck=page.evaluate(()=>new Promise(resolve=>{
      const start=performance.now(), seen=new Set();
      let blankPaints=0,mismatchedPaints=0,samples=0;
      function sample(){
        const imgs=[...document.querySelectorAll(".motion-image-stage img")];
        if(imgs.length!==2 || imgs.some(img=>!img.complete || img.naturalWidth===0))blankPaints++;
        const labels=[...document.querySelectorAll(".motion-frame-caption")]
          .map(el=>/^Frame (\d+) \//.exec(el.textContent||"")?.[1]);
        if(labels.length===2 && labels[0] && labels[1] && labels[0]!==labels[1])
          mismatchedPaints++;
        if(labels[0]&&labels[1])seen.add(labels.join("/"));
        samples++;
        if(performance.now()-start<4500)requestAnimationFrame(sample);
        else resolve({blankPaints,mismatchedPaints,samples,
          distinctSynchronizedPositions:seen.size});
      }
      requestAnimationFrame(sample);
    }));
    await page.locator("button.motion-play").click();
    const measurements=await blankCheck;
    await page.locator("button.motion-play").click();
    assert.equal(measurements.blankPaints,0,
      "Visible original images must not blank during playback");
    assert.equal(measurements.mismatchedPaints,0,
      "Selected panes must commit the same ordinal step on one paint");
    assert.ok(measurements.distinctSynchronizedPositions>=3,
      "Playback must advance by several original frames after prefetch");

    // Seek away and verify that both columns agree on frame 129 / 256.
    await page.locator(".motion-slider").evaluate(slider=>{
      slider.value="500";
      slider.dispatchEvent(new Event("input",{bubbles:true}));
    });
    await page.waitForFunction(()=>{
      const labels=[...document.querySelectorAll(".motion-frame-caption")]
        .map(el=>el.textContent||"");
      return labels.length===2 && labels.every(x=>x.startsWith("Frame 129 / 256"));
    },null,{timeout:45000});
    await page.screenshot({path:path.join(resultDir,label+"-360.png"),fullPage:true});

    // On an emulated touch device, check usable slider bounds and a genuine
    // touchscreen event. Otherwise test native keyboard range interaction.
    const bounds=await page.locator(".motion-slider").boundingBox();
    assert.ok(bounds && bounds.width>=75 && bounds.height>0,
      "Shared scrubber must be visible and usable at this viewport");
    if(label==="mobile"){
      await page.touchscreen.tap(bounds.x+bounds.width*0.75,bounds.y+bounds.height/2);
      assert.notEqual(await page.locator(".motion-slider").inputValue(),"500",
        "Touch interaction must move the shared scrubber");
    } else {
      await page.locator(".motion-slider").focus();
      await page.keyboard.press("ArrowRight");
      assert.notEqual(await page.locator(".motion-slider").inputValue(),"500",
        "Keyboard interaction must move the shared scrubber");
    }
    assert.deepEqual(errors,[],"No JavaScript page errors allowed");
    summary={profile:label,result:"passed",firstPaintSeconds,warmupSeconds,
      prefetch:progress,paintSamples:measurements.samples,
      ...measurements,viewport:page.viewportSize()};
    console.log("PASS C3 live-browser smoke "+JSON.stringify(summary));
  }catch(error){
    summary={...summary,error:String(error),pageErrors:errors,
      progress:await page.locator(".motion-prefetch-progress").allTextContents().catch(()=>[])};
    console.error("FAIL C3 live-browser smoke "+JSON.stringify(summary));
    await page.screenshot({path:path.join(resultDir,label+"-failure.png"),fullPage:true,
      timeout:10000}).catch(()=>{});
    throw error;
  }finally{
    summaries.push(summary);
    await context.close();
  }
}
try{
  await runProfile("desktop",{viewport:{width:1280,height:900}});
  await runProfile("mobile",{...devices["Pixel 7"],viewport:{width:390,height:844}});
}finally{
  await writeFile(path.join(resultDir,"results.json"),JSON.stringify(summaries,null,2));
  await browser.close();
}
