import test from "node:test";
import assert from "node:assert/strict";
import {emptyCuration,emptyDraft,setDraftFlag,validateCuration} from "../catalogue/curation.mjs";
import {CURATION_REQUEST_MARKER,CURATION_REQUEST_SCHEMA,CURATION_REQUEST_TITLE,
  curationChanges,createCurationIssueUrl,openCurationIssueInNewTab,curationDigest,MAX_REQUEST_CHANGES} from "../catalogue/curation-request.mjs";
const ids=new Set(["igi-lg111","igi-lg222"]);
test("issue save handoff is owner-confirmed, sparse and includes per-field expected state",async()=>{
  const published=validateCuration({schema:"sparkles-diamond-curation/1",diamonds:{
    "igi-lg111":{archived:true,starred:true}
  }},ids);
  let draft=setDraftFlag(published,emptyDraft(),"igi-lg111","starred",false,ids);
  draft=setDraftFlag(published,draft,"igi-lg222","archived",true,ids);
  const changes=curationChanges(published,draft,ids);
  assert.deepEqual(changes,[
    {id:"igi-lg111",field:"starred",from:true,to:false},
    {id:"igi-lg222",field:"archived",from:false,to:true}
  ]);
  const url=new URL(await createCurationIssueUrl(published,draft,ids));
  assert.equal(url.origin,"https://github.com");
  assert.equal(url.pathname,"/choonkiatlee/sparkles/issues/new");
  assert.equal(url.searchParams.get("title"),CURATION_REQUEST_TITLE);
  const [marker,body]=url.searchParams.get("body").trim().split("\n");
  assert.equal(marker,CURATION_REQUEST_MARKER);
  assert.deepEqual(JSON.parse(body),{schema:CURATION_REQUEST_SCHEMA,
    baseline_sha256:await curationDigest(published),changes});
  assert.match(JSON.parse(body).baseline_sha256,/^[a-f0-9]{64}$/);
  assert.ok(!url.searchParams.has("token"));
});
test("empty, oversized, forged and malformed drafts cannot be submitted",async()=>{
  await assert.rejects(()=>createCurationIssueUrl(emptyCuration(),emptyDraft(),ids),/No unsaved/);
  assert.throws(()=>curationChanges(emptyCuration(),{diamonds:{"ref-r01":{starred:true}}},ids));
  const bigIds=new Set(Array.from({length:MAX_REQUEST_CHANGES+1},(_,i)=>"igi-lg"+i));
  let draft=emptyDraft();
  for(const id of bigIds)draft=setDraftFlag(emptyCuration(),draft,id,"starred",true,bigIds);
  await assert.rejects(()=>createCurationIssueUrl(emptyCuration(),draft,bigIds),/at most/);
});

test("Save on GitHub opens new tab in click gesture, before async digest",async()=>{
  const published=emptyCuration();
  const draft=setDraftFlag(published,emptyDraft(),"igi-lg111","starred",true,ids);
  const events=[];
  let navigated="";
  const tab={
    opener:{secret:"main catalogue"},
    location:{replace:(url)=>{events.push("navigate");navigated=url;}},
    close:()=>events.push("close"),
  };
  const save=openCurationIssueInNewTab(published,draft,ids,()=>{
    events.push("open");
    return tab;
  });
  // The new tab opens during the original user gesture, not after await.
  assert.deepEqual(events,["open"]);
  assert.equal(tab.opener,null);
  await save;
  assert.deepEqual(events,["open","navigate"]);
  const url=new URL(navigated);
  assert.equal(url.host,"github.com");
  assert.equal(url.pathname,"/choonkiatlee/sparkles/issues/new");
  assert.equal(url.searchParams.get("title"),CURATION_REQUEST_TITLE);
});
test("blocked popups and URL errors do not navigate or lose original tab",async()=>{
  const data=emptyCuration();
  const draft=setDraftFlag(data,emptyDraft(),"igi-lg111","archived",true,ids);
  await assert.rejects(
    ()=>openCurationIssueInNewTab(data,draft,ids,()=>null),/blocked/);
  let closed=false;
  await assert.rejects(()=>openCurationIssueInNewTab(data,emptyDraft(),ids,
    ()=>({opener:{},location:{replace:()=>assert.fail("must not navigate")},
      close:()=>{closed=true;}})),/No unsaved changes/);
  assert.equal(closed,true);
});
