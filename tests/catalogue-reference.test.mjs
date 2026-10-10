import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {selectionFromSearch,selectionSearch,toggleSelection,MAX_SELECTION} from "../catalogue/core.mjs";
import {validateReferenceIndex,referenceManifestURL,validateReferenceManifest,
  createReferenceManifestLoader,projectReferenceComparison} from "../catalogue/reference.mjs";

const readJSON=path=>JSON.parse(readFileSync(new URL("../"+path,import.meta.url),"utf8"));
const refs=validateReferenceIndex(readJSON("data/reference-index.json"));
const certified=readJSON("data/catalog.json").diamonds;
const ref=id=>refs.find(row=>row.reference_id===id);
const doc=row=>readJSON(row.manifest_path);

test("all curated examples validate independently of certificates or local media",()=>{
  assert.ok(refs.length>=23);
  for(const row of refs){
    assert.equal(row.id,"ref-"+row.reference_id);
    assert.equal(referenceManifestURL(row),"../"+row.manifest_path);
    assert.equal(validateReferenceManifest(row,doc(row)).id,row.reference_id);
    const projected=projectReferenceComparison(row,doc(row));
    assert.equal(projected.kind,"reference");
    assert.ok(["available","unavailable","video_only"].includes(projected.rotation.status));
    assert.ok(projected.commentary.length>20);
    assert.equal(projected.values.price,"Not recorded");
  }
  for(let i=1;i<=11;i++) assert.ok(ref("ps285166-r"+String(i).padStart(2,"0")));
  const r07=projectReferenceComparison(ref("ps285166-r07"),doc(ref("ps285166-r07")));
  assert.ok(r07.commentary.includes("under-table steps"));
  assert.equal(r07.mediaSources[0].kind,"viewer");
  assert.match(r07.mediaSources[0].url,/v360\.diamonds/);
  assert.equal(r07.identityStatus,"reported");
  assert.equal(doc(ref("ps285166-r07")).identity.lab,"IGI");
  assert.equal(doc(ref("ps285166-r07")).identity.report_number,"625406458");
  assert.equal(doc(ref("ps285166-r07")).linked_diamond_id,null);
  assert.ok(r07.sourceLinks.some(source=>
    source.kind==="certificate_link" &&
    source.url==="https://www.igi.org/verify-your-report/?r=625406458"));
});

test("all three educational threads have independent, source-backed reference entries",()=>{
  for(let i=12;i<=15;i++)assert.ok(ref("ps282648-r"+i));
  for(let i=16;i<=23;i++)assert.ok(ref("ps281114-r"+i));
  const r12=projectReferenceComparison(ref("ps282648-r12"),doc(ref("ps282648-r12")));
  assert.equal(r12.identityStatus,"unverified");
  assert.match(r12.commentary,/Karl_K/);
  assert.ok(["available","unavailable"].includes(r12.rotation.status));
  assert.equal(r12.mediaSources[0].kind,"viewer");
  const r14=doc(ref("ps282648-r14")),r15=doc(ref("ps282648-r15"));
  assert.notDeepEqual(r14.diamond_metadata.dimensions,r15.diamond_metadata.dimensions);
  assert.equal(r14.source_links[1].url,r15.source_links[1].url);
  const r18=projectReferenceComparison(ref("ps281114-r18"),doc(ref("ps281114-r18")));
  assert.ok(["available","unavailable"].includes(r18.rotation.status));
  assert.ok(r18.sourceLinks.some(s=>s.kind==="research_media_archive"));
  const r21=doc(ref("ps281114-r21")),r23=doc(ref("ps281114-r23"));
  assert.equal(r21.identity.report_number,"2135242286");
  assert.match(r21.commentary,/D VS2/);
  assert.match(r23.commentary,/EMERALD/);
});

test("mixed selection URLs round trip, respect five entries, and do not merge identities",()=>{
  const ids=new Set([...certified.map(row=>row.id),...refs.map(row=>row.id)]);
  const one=certified[0].id, two=certified[1].id;
  const r05=ref("ps285166-r05").id,r10=ref("ps285166-r10").id;
  const selected=[one,r05,two,r10,ref("ps285166-r07").id];
  assert.equal(new Set(selected).size,5);
  const query=selectionSearch("?campaign=study",selected,true);
  assert.deepEqual(selectionFromSearch("?"+query,ids),{selected,comparing:true});
  assert.equal(toggleSelection(selected,ref("ps285166-r09").id).length,MAX_SELECTION);
  assert.notEqual(r05,r10);
  assert.notEqual(doc(ref("ps285166-r05")).identity.report_number,
    doc(ref("ps285166-r10")).identity.report_number);
  const referenceOnly=selectionFromSearch("?selected="+r05+","+r10+"&compare=1",ids);
  assert.deepEqual(referenceOnly.selected,[r05,r10]);
  assert.equal(referenceOnly.comparing,true);
});

test("canonical paths and schema resist tampering; reference does not pass certified schema",()=>{
  const row=ref("ps285166-r07"), manifest=doc(row);
  assert.throws(()=>referenceManifestURL({...row,manifest_path:"../../other.json"}));
  assert.throws(()=>validateReferenceIndex({schema:"fake",references:[]}));
  assert.throws(()=>validateReferenceIndex({schema:"sparkles-reference-index/1",
    references:[{...row,selection_id:"other"}]}));
  assert.throws(()=>validateReferenceManifest(row,{...manifest,schema:"sparkles-diamond-catalogue/1"}));
  assert.throws(()=>validateReferenceManifest(row,{...manifest,id:"different"}));
});

test("complete ordered reference rotation reuses existing original-frame model",()=>{
  const row=ref("ps285166-r07"),manifest=doc(row);
  const frame=i=>({source_index:i,asset:{media_type:"image/jpeg",
    storage:{url:"https://example.test/rotation/"+i+".jpg"}}});
  const evidence={kind:"rotation",status:"success",
    metadata:{sequence_complete:true,frame_count:2},frames:[frame(0),frame(1)]};
  const result=projectReferenceComparison(row,{...manifest,evidence:[evidence]});
  assert.equal(result.rotation.status,"available");
  assert.equal(result.rotation.frameCount,2);
  assert.equal(result.rotation.frames[1].ordinal,1);
  assert.match(result.values.motion,/2 frames/);
  assert.match(result.values.motion,/not angle-calibrated/);
});

test("reference manifest loader caches success and retries transient failures",async()=>{
  const row=ref("ps285166-r07");let calls=0;
  const load=createReferenceManifestLoader(async url=>{
    assert.equal(url,referenceManifestURL(row));calls++;
    return {ok:true,json:async()=>doc(row)};
  });
  await Promise.all([load(row),load(row)]);
  assert.equal(calls,1);
  const retry=createReferenceManifestLoader(async()=>{throw Error("offline");});
  await assert.rejects(retry(row),/offline/);
  await assert.rejects(retry(row),/offline/);
});

test("archived Kashi originals remain playable independent MP4s, not 360 frames",()=>{
  const row=ref("ps281114-r20");
  const example=structuredClone(doc(row));
  const original="https://github.com/choonkiatlee/sparkles/releases/download/sparkles-reference-ps281114-r20/original.mp4";
  example.evidence=[{
    kind:"video",status:"success",media_type:"video/mp4",
    payload_asset:{media_type:"video/mp4",storage:{url:original}},
  }];
  const result=projectReferenceComparison(row,example);
  assert.equal(result.rotation.status,"video_only");
  assert.equal(result.video.url,original);
  assert.equal(result.video.type,"video/mp4");
  assert.match(result.values.motion,/Video available/);
  example.evidence[0].status="missing";
  assert.equal(projectReferenceComparison(row,example).video,null);
});
