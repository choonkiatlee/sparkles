import test from "node:test";
import assert from "node:assert/strict";
import {
  CURATION_SCHEMA,DRAFT_SCHEMA,emptyCuration,emptyDraft,validateCuration,
  validateDraft,setDraftFlag,reconcileDraft,draftCount,flagsFor,curationRows,
  archivedCount
} from "../catalogue/curation.mjs";

const ids = new Set(["igi-lg111","igi-lg222","igi-lg333"]);
const rows = [...ids].map(id=>({id}));
test("empty published curation defaults to active and unstarred",()=>{
  const data=validateCuration({schema:CURATION_SCHEMA,diamonds:{}},ids);
  assert.deepEqual(flagsFor(data,emptyDraft(),"igi-lg111"),{starred:false,archived:false});
  assert.equal(archivedCount(rows,data,emptyDraft()),0);
  assert.equal(curationRows(rows,{},data,emptyDraft()).length,3);
});
test("archive and star are independent; archive hides only default browse",()=>{
  const base=emptyCuration();
  let draft=emptyDraft();
  draft=setDraftFlag(base,draft,"igi-lg111","starred",true,ids);
  draft=setDraftFlag(base,draft,"igi-lg111","archived",true,ids);
  assert.equal(draftCount(draft),2);
  assert.deepEqual(flagsFor(base,draft,"igi-lg111"),{starred:true,archived:true});
  assert.deepEqual(curationRows(rows,{},base,draft).map(r=>r.id),["igi-lg222","igi-lg333"]);
  assert.deepEqual(curationRows(rows,{showArchived:true,shortlistOnly:true},base,draft).map(r=>r.id),["igi-lg111"]);
  assert.deepEqual(curationRows(rows,{shortlistOnly:true},base,draft),[]);
  assert.equal(archivedCount(rows,base,draft),1);
});
test("toggles back to Git baseline remove pending overrides",()=>{
  const base=validateCuration({schema:CURATION_SCHEMA,diamonds:{"igi-lg222":{starred:true,archived:true}}},ids);
  let draft=setDraftFlag(base,emptyDraft(),"igi-lg222","starred",false,ids);
  draft=setDraftFlag(base,draft,"igi-lg222","archived",false,ids);
  assert.deepEqual(flagsFor(base,draft,"igi-lg222"),{starred:false,archived:false});
  draft=setDraftFlag(base,draft,"igi-lg222","starred",true,ids);
  draft=setDraftFlag(base,draft,"igi-lg222","archived",true,ids);
  assert.equal(draftCount(draft),0);
  assert.equal(archivedCount(rows,base,draft),1);
});
test("draft round-trips in browser storage and reconciles committed updates",()=>{
  const base=emptyCuration();
  let draft=setDraftFlag(base,emptyDraft(),"igi-lg333","starred",true,ids);
  draft=setDraftFlag(base,draft,"igi-lg222","archived",true,ids);
  const reread=validateDraft(JSON.parse(JSON.stringify(draft)),ids);
  assert.equal(draftCount(reread),2);
  const updated=validateCuration({schema:CURATION_SCHEMA,diamonds:{"igi-lg333":{starred:true}}},ids);
  const pending=reconcileDraft(updated,reread,ids);
  assert.equal(draftCount(pending),1);
  assert.equal(flagsFor(updated,pending,"igi-lg333").starred,true);
  assert.equal(flagsFor(updated,pending,"igi-lg222").archived,true);
});
test("strict curation schemas reject forged IDs, references, unknown fields and nonbooleans",()=>{
  for (const invalid of [
    {schema:"wrong",diamonds:{}},
    {schema:CURATION_SCHEMA,diamonds:{"ref-ps":{starred:true}}},
    {schema:CURATION_SCHEMA,diamonds:{"igi-unknown":{starred:true}}},
    {schema:CURATION_SCHEMA,diamonds:{"igi-lg111":{starred:"yes"}}},
    {schema:CURATION_SCHEMA,diamonds:{"igi-lg111":{favourite:true}}},
    {schema:CURATION_SCHEMA,diamonds:{"igi-lg111":{}}},
    {schema:CURATION_SCHEMA,diamonds:[]},
    {schema:CURATION_SCHEMA,diamonds:{},secret:42}
  ]) assert.throws(()=>validateCuration(invalid,ids));
  assert.throws(()=>setDraftFlag(emptyCuration(),emptyDraft(),"ref-example","starred",true,ids));
  assert.throws(()=>setDraftFlag(emptyCuration(),emptyDraft(),"igi-lg111","archived","true",ids));
  assert.throws(()=>validateDraft({schema:DRAFT_SCHEMA,diamonds:{"igi-lg222":{archived:null}}},ids));
});

test("archiving does not remove IDs from selection or shared deep links", async()=>{
  const {selectionFromSearch} = await import("../catalogue/core.mjs");
  const baseline=emptyCuration();
  const draft=setDraftFlag(baseline,emptyDraft(),"igi-lg111","archived",true,ids);
  const visible=curationRows(rows,{},baseline,draft);
  assert.equal(visible.some(row=>row.id==="igi-lg111"),false);
  assert.equal(rows.length,3); // The shared allRows reference is not mutated.
  const selected=selectionFromSearch("?selected=igi-lg111,igi-lg222&compare=1",ids);
  assert.deepEqual(selected.selected,["igi-lg111","igi-lg222"]);
  assert.equal(selected.comparing,true);
});
