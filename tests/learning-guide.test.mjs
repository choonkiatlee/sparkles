import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {validateExpertGuide,comparisonPair} from "../learning/guide.mjs";
import {validateReferenceIndex} from "../catalogue/reference.mjs";
import {selectionFromSearch,selectionSearch,MAX_SELECTION} from "../catalogue/core.mjs";

const readJSON=path=>JSON.parse(readFileSync(new URL("../"+path,import.meta.url),"utf8"));
const published=readJSON("data/learning-guide.json");
const refs=validateReferenceIndex(readJSON("data/reference-index.json"));
const ids=new Set(refs.map(row=>row.id));
const lessons=validateExpertGuide(published,ids);
const doc=id=>readJSON("data/references/"+id+".json");

test("editable guide references real curated diamonds and trustworthy sources",()=>{
  assert.equal(published.schema,"sparkles-learning-guide/1");
  assert.ok(lessons.length>=4);
  for(const name of ["movement","centre","tilt","contrast"])
    assert.ok(lessons.some(lesson=>lesson.id===name),name);
  for(const lesson of lessons){
    assert.ok(lesson.summary.length>25);
    assert.ok(lesson.prompt.length>10);
    assert.ok(lesson.source_url.startsWith("https://"));
    assert.ok(lesson.examples.length>=1);
    for(const example of lesson.examples){
      assert.ok(doc(example.id).commentary.length>20);
      assert.ok(example.label.length>0);
      assert.ok(example.comment.length>10);
    }
    if(lesson.featured_pair)assert.equal(comparisonPair(lesson,ids).length,2);
  }
  const annotated=lessons.find(lesson=>lesson.id==="tilt")?.annotated_source;
  assert.match(annotated.label,/screenshot.*reply/i);
  assert.match(annotated.url,/page-2/);
});

test("all new references are taught in the expanded guide",()=>{
  assert.ok(lessons.length>=8);
  const idsInGuide=new Set(lessons.flatMap(x=>x.examples.map(y=>y.id)));
  for(let i=12;i<=15;i++)assert.ok(idsInGuide.has("ps282648-r"+i));
  for(let i=16;i<=23;i++)assert.ok(idsInGuide.has("ps281114-r"+i));
  for(const slug of ["evidence-reassessment","p3-specific-leakage","same-spec-comparison","performance-vs-preference"]){
    const lesson=lessons.find(x=>x.id===slug);
    assert.ok(lesson);
    assert.equal(comparisonPair(lesson,ids).length,2);
  }
});

test("featured comparison remains stable when later agents append examples",()=>{
  for(const lesson of lessons.filter(x=>x.featured_pair)){
    const selected=comparisonPair(lesson,ids);
    const query=selectionSearch("?source=learning",selected,true);
    assert.deepEqual(selectionFromSearch("?"+query,ids),{selected,comparing:true});
    assert.ok(selected.length<=MAX_SELECTION);
    assert.match(query,/source=learning/);
  }
  const base=lessons[0];
  const extra=refs.find(row=>!base.examples.some(x=>x.id===row.reference_id));
  assert.ok(extra);
  const extended={...base,examples:[...base.examples,
    {id:extra.reference_id,label:"Another example",comment:"Source-backed expert observation"}]};
  assert.equal(validateExpertGuide({schema:published.schema,lessons:[extended]},ids).length,1);
  assert.deepEqual(comparisonPair(extended,ids),comparisonPair(base,ids));
});

test("new categories can start with one example and gain a featured pair later",()=>{
  const [first,second]=refs;
  const newLesson={
    id:"new-teaching-concept",category:"Another useful phenomenon",
    title:"What happens during tilt?",summary:"A nuanced observation with a clear source.",
    prompt:"Watch how reflections move on rotation.",
    source_url:"https://www.pricescope.com/community/threads/example.12345/",
    examples:[{id:first.reference_id,label:"First source",comment:"Reviewer describes a specific observation."}]
  };
  assert.equal(validateExpertGuide({schema:published.schema,lessons:[...lessons,newLesson]},ids).length,lessons.length+1);
  assert.deepEqual(comparisonPair(newLesson,ids),[]);
  const expanded={...newLesson,examples:[...newLesson.examples,
    {id:second.reference_id,label:"Counterexample",comment:"Another source-backed judgement."}],
    featured_pair:[first.reference_id,second.reference_id]};
  assert.deepEqual(comparisonPair(expanded,ids),[first.id,second.id]);
  assert.equal(validateExpertGuide({schema:published.schema,lessons:[expanded]},ids).length,1);
});

test("guide validation rejects orphan references, duplicate slugs and broken comparison pairs",()=>{
  assert.throws(()=>validateExpertGuide({...published,schema:"unknown"},ids),/format/);
  assert.throws(()=>validateExpertGuide({schema:published.schema,lessons:[lessons[0],lessons[0]]},ids),/category/);
  assert.throws(()=>validateExpertGuide({schema:published.schema,lessons:[
    {...lessons[0],examples:[{id:"nonexistent-reference",label:"Bad",comment:"Never ingested"}]}
  ]},ids),/missing reference/);
  assert.throws(()=>validateExpertGuide({schema:published.schema,lessons:[
    {...lessons[0],featured_pair:[lessons[0].examples[0].id,lessons[0].examples[0].id]}
  ]},ids),/featured/);
  assert.throws(()=>validateExpertGuide({schema:published.schema,lessons:[
    {...lessons[0],source_url:"javascript:alert(1)"}
  ]},ids),/category/);
  assert.deepEqual(comparisonPair(lessons[0],new Set()),[]);
});

test("site uses authored schema, source-linked diagram and existing player",()=>{
  const img=readFileSync(new URL("../learning/where-to-look.svg",import.meta.url),"utf8");
  const html=readFileSync(new URL("../learning/index.html",import.meta.url),"utf8");
  const app=readFileSync(new URL("../learning/app.mjs",import.meta.url),"utf8");
  assert.match(img,/<svg.*viewBox=/);
  assert.match(img,/not a real diamond photograph|Not a real diamond photograph/i);
  assert.match(html,/not an expert's annotated photograph/i);
  assert.match(html,/\.\/where-to-look\.svg/);
  assert.match(html,/id="guide-cards"/);
  assert.match(app,/getJSON\("\.\.\/data\/learning-guide\.json"\)/);
  assert.match(app,/renderGuide/);
  assert.match(app,/compareLesson/);
  assert.match(app,/studyLesson/);
  assert.match(app,/comparisonView\.update/);
  assert.match(app,/state\.selected=pair/);
});
