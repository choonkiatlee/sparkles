import test from "node:test";
import assert from "node:assert/strict";
import {emptyCuration,emptyDraft,setDraftFlag,validateCuration} from "../catalogue/curation.mjs";
import {CURATION_REQUEST_MARKER,CURATION_REQUEST_SCHEMA,CURATION_REQUEST_TITLE,
  curationChanges,createCurationIssueUrl,MAX_REQUEST_CHANGES} from "../catalogue/curation-request.mjs";
const ids=new Set(["igi-lg111","igi-lg222"]);
test("issue save handoff is owner-confirmed, sparse and includes per-field expected state",()=>{
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
  const url=new URL(createCurationIssueUrl(published,draft,ids));
  assert.equal(url.origin,"https://github.com");
  assert.equal(url.pathname,"/choonkiatlee/sparkles/issues/new");
  assert.equal(url.searchParams.get("title"),CURATION_REQUEST_TITLE);
  const [marker,body]=url.searchParams.get("body").trim().split("\n");
  assert.equal(marker,CURATION_REQUEST_MARKER);
  assert.deepEqual(JSON.parse(body),{schema:CURATION_REQUEST_SCHEMA,changes});
  assert.ok(!url.searchParams.has("token"));
});
test("empty, oversized, forged and malformed drafts cannot be submitted",()=>{
  assert.throws(()=>createCurationIssueUrl(emptyCuration(),emptyDraft(),ids),/No unsaved/);
  assert.throws(()=>curationChanges(emptyCuration(),{diamonds:{"ref-r01":{starred:true}}},ids));
  const bigIds=new Set(Array.from({length:MAX_REQUEST_CHANGES+1},(_,i)=>"igi-lg"+i));
  let draft=emptyDraft();
  for(const id of bigIds)draft=setDraftFlag(emptyCuration(),draft,id,"starred",true,bigIds);
  assert.throws(()=>createCurationIssueUrl(emptyCuration(),draft,bigIds),/at most/);
});
