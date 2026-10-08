import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {assetUrl, publicUrl, manifestURL, validateManifest, createManifestLoader,
  dateText, projectComparison, describeMotion, representativeAsset, comparisonRows} from "../catalogue/compare.mjs";

const get = id => {
  const row = JSON.parse(readFileSync(new URL("../data/catalog.json", import.meta.url))).diamonds.find(r=>r.id===id);
  const doc = JSON.parse(readFileSync(new URL("../"+row.manifest_path,import.meta.url)));
  return [row,doc];
};
const [qdRow,qdDoc] = get("igi-lg756520111");
const [diRow,diDoc] = get("igi-lg816611062");

test("published real manifests validate; certificate/partial provenance remains truthful",()=>{
  assert.equal(validateManifest(qdRow,qdDoc).id,qdRow.id);
  const partial=projectComparison(qdRow,qdDoc);
  const complete=projectComparison(diRow,diDoc);
  assert.equal(partial.values.retrieval,"partial");
  assert.equal(partial.certificateRecovered,false);
  assert.equal(partial.certificate,null);
  assert.match(partial.verification,/igi.org\/verify-your-report/);
  assert.ok(partial.reasons.some(s=>s.includes("certificate")));
  assert.equal(complete.values.retrieval,"complete");
  assert.equal(complete.certificateRecovered,true);
  assert.match(complete.certificate.url,/github.com\/.*\.pdf/);
  assert.match(complete.values.depth,/67.1%/);
  assert.match(partial.values.table,/64%/);
  assert.match(partial.values.price,/£685/);
  assert.match(complete.values.price,/\$749/);
  assert.equal(partial.listings[0].retailer_sku,"133/9155264EA");
  assert.ok(partial.representative.url.startsWith("https:"));
  assert.ok(complete.representative.url.startsWith("https:"));
  assert.match(complete.values.motion,/256 frames/);
  assert.match(complete.values.motion,/not angle-calibrated/);
  assert.equal(comparisonRows.length,16);
  assert.equal(partial.rotation.status,"available");
  assert.equal(partial.rotation.frameCount,256);
  assert.equal(complete.rotation.status,"available");
  assert.equal(complete.rotation.frameCount,256);
});
test("URLs reject traversal, wrong identity, cross-site protocol and malformed assets",()=>{
  assert.equal(manifestURL(qdRow),"../data/diamonds/igi-lg756520111.json");
  assert.throws(()=>manifestURL({...qdRow,manifest_path:"https://api.github.com/thing"}));
  assert.throws(()=>manifestURL({...qdRow,manifest_path:"../../secrets.json"}));
  assert.throws(()=>manifestURL({...qdRow,id:"../wrong"}));
  assert.throws(()=>validateManifest(qdRow,{...qdDoc,id:diRow.id}));
  assert.throws(()=>validateManifest(qdRow,{...qdDoc,identity:{lab:"IGI",report_number:diRow.report_number}}));
  assert.equal(publicUrl("javascript:alert(1)"),null);
  assert.equal(publicUrl("https://user:secret@example.com"),null);
  assert.equal(assetUrl({storage:{backend:"r2",url:"https://assets.example.test/diamond.jpg"}}),
    "https://assets.example.test/diamond.jpg");
});
test("manifest loading is deferred, deduplicates successful reads, and permits retry after error",async()=>{
  let calls=0;
  const load=createManifestLoader(async url=>{
    assert.equal(url,manifestURL(qdRow));
    calls++;
    return {ok:true,json:async()=>qdDoc};
  });
  assert.equal(calls,0);
  const [a,b]=await Promise.all([load(qdRow),load(qdRow)]);
  assert.equal(a,b);
  await load(qdRow);
  assert.equal(calls,1);
  let errors=0;
  const fail=createManifestLoader(async()=>{errors++;throw Error("offline");});
  await assert.rejects(fail(qdRow),/offline/);
  await assert.rejects(fail(qdRow),/offline/);
  assert.equal(errors,2);
});
test("video-only, missing motion and still/rotation fallbacks remain distinct",()=>{
  const video={kind:"video",status:"success",payload_asset:{storage:{backend:"r2",url:"https://example.test/video.mp4"}}};
  assert.match(describeMotion([video]),/Video available/);
  assert.equal(representativeAsset([video]),null);
  const still={kind:"still",status:"success",payload_asset:{media_type:"image/jpeg",storage:{backend:"r2",url:"https://example.test/a.jpg"}}};
  assert.equal(representativeAsset([still]).url,"https://example.test/a.jpg");
  assert.match(describeMotion([{kind:"rotation",status:"failed"}]),/missing, failed/);
  assert.match(describeMotion([]),/No recovered/);
  const unvalidated={kind:"rotation",status:"success",metadata:{sequence_complete:false},
    frames:[{asset:{media_type:"image/jpeg",storage:{url:"https://example.test/frame.jpg"}}}]};
  assert.equal(representativeAsset([unvalidated]),null);
});
test("nulls, multiple retailer observations and missing evidence are explicit",()=>{
  const revised={...qdDoc,
    diamond_metadata:{...qdDoc.diamond_metadata,reported_proportions:null,dimensions:null,colour:null},
    retrievals:[...qdDoc.retrievals,{retrieved_at:"2026-10-09T00:00:00Z",status:"partial",
      certificate_link:null,completion_reasons:["upstream unavailable"]}],
    listings:[...qdDoc.listings,{observed_at:"2026-10-09T00:00:00Z",retailer:"other",
      price:null,currency:null,tax_basis:null,url:"https://other.test/listing"}],
    evidence:[]};
  const p=projectComparison(qdRow,revised);
  assert.equal(p.values.colour,"Unknown");
  assert.equal(p.values.depth,"Unknown");
  assert.equal(p.values.dimensions,"Unknown");
  assert.equal(p.values.price,"Price unavailable");
  assert.equal(p.values.tax,"Unknown");
  assert.equal(p.listings.length,2);
  assert.equal(p.currentListing.retailer,"other");
  assert.deepEqual(p.reasons,["upstream unavailable"]);
  assert.equal(p.representative,null);
  assert.equal(p.rotation.status,"unavailable");
  assert.equal(dateText(null),"Unknown");
});
