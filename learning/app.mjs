// Separate educational browse surface, sharing selection helpers and the one existing viewer.
import {MAX_SELECTION,MIN_COMPARISON,validateIndex,
  selectionFromSearch,selectionSearch,toggleSelection} from "../catalogue/core.mjs";
import {createComparisonView} from "../catalogue/comparison-view.mjs";
import {validateReferenceIndex,createReferenceManifestLoader} from "../catalogue/reference.mjs";
import {validateExpertGuide,comparisonExamples} from "./guide.mjs";

const $ = id => document.getElementById(id);
const state = {references:[], certified:[], allRows:[], docs:new Map(),
  failures:new Set(),selected:[],comparing:false,ready:false,focusLesson:null,compareLessonId:null,guide:[]};
const loadReference = createReferenceManifestLoader((...args)=>fetch(...args));
const comparisonView = createComparisonView({
  container:$("comparison"),grid:$("comparison-grid"),fetcher:(...args)=>fetch(...args)
});
const node=(tag,className="",text=null)=>{
  const n=document.createElement(tag);
  if(className)n.className=className;
  if(text!==null)n.textContent=String(text);
  return n;
};
function externalLink(label,value) {
  if(typeof value!=="string")return null;
  try {
    const url=new URL(value);
    if(!["https:","http:"].includes(url.protocol)||url.username||url.password)return null;
    const a=node("a","",label);
    a.href=url.href;a.target="_blank";a.rel="noopener noreferrer";
    return a;
  } catch {return null;}
}
const friendly=tag=>tag.replace(/-/g," ").replace(/\b\w/g,c=>c.toUpperCase());
const nameFor=id=>state.allRows.find(row=>row.id===id)?.label || id;
function updateLinks() {
  const params=selectionSearch("",state.selected,state.comparing);
  const suffix=params?"?"+params:"";
  $("catalogue-link").href="../catalogue/"+suffix;
  $("browse-catalogue").href="../catalogue/"+suffix;
}
function updateURL() {
  const params=new URLSearchParams(selectionSearch(location.search,state.selected,state.comparing));
  if(state.comparing && state.compareLessonId)params.set("lesson",state.compareLessonId);
  else params.delete("lesson");
  const query=params.toString();
  history.replaceState(null,"",location.pathname+(query?"?"+query:"")+location.hash);
}
function select(id) {
  state.compareLessonId=null;
  state.selected=toggleSelection(state.selected,id);
  state.comparing=state.comparing && state.selected.length>=MIN_COMPARISON;
  updateURL();
  render();
  document.getElementById("pick-"+id)?.focus();
}
// Guide example controls work against the same basket and comparison player as the gallery.
function guideSelection(lesson) {
  return comparisonExamples(lesson,new Set(state.references.map(row=>row.id)),MAX_SELECTION);
}
function studyLesson(lesson) {
  state.focusLesson=lesson;
  $("search").value="";
  $("topic").value="all";
  render();
  $("references").scrollIntoView({behavior:"smooth",block:"start"});
}
function compareLesson(lesson) {
  const ids=guideSelection(lesson);
  if(ids.length<MIN_COMPARISON)return;
  // Replace the existing shared basket with every example from this segment.
  state.selected=ids;
  state.compareLessonId=lesson.id;
  state.comparing=true;
  updateURL();
  render();
  $("comparison").scrollIntoView({behavior:"smooth",block:"start"});
}
function guideExample(example) {
  const row=state.references.find(row=>row.reference_id===example.id);
  const wrapper=node("div","guide-example");
  const media=node("div","guide-example-preview");
  const imageURL=externalLink("Published still",row?.thumbnail_url);
  if(imageURL){
    const img=node("img");
    img.src=imageURL.href;img.loading="lazy";img.alt="Published still for "+example.id;
    img.addEventListener("error",()=>{
      media.replaceChildren(node("span","",example.id.split("-").at(-1).toUpperCase()));
    });
    media.append(img);
  } else {
    media.append(node("span","",example.id.split("-").at(-1).toUpperCase()));
  }
  const copy=node("div","guide-example-copy");
  copy.append(node("strong","",example.label));
  copy.append(node("p","",example.comment));
  if(row)copy.append(node("span","guide-example-id",row.label));
  wrapper.append(copy,media);
  return wrapper;
}
function makeGuideCard(lesson,position) {
  const card=node("article","guide-card");
  card.id="guide-"+lesson.id;
  const eyebrow=node("p","guide-card-eyebrow",String(position+1).padStart(2,"0")+" / "+lesson.category);
  const title=node("h3","",lesson.title);
  card.append(eyebrow,title,node("p","guide-summary",lesson.summary));
  card.append(node("p","guide-look-for","Look for: "+lesson.prompt));
  const examples=node("div","guide-examples");
  lesson.examples.forEach(example=>examples.append(guideExample(example)));
  card.append(examples);
  const sources=node("div","guide-source-links");
  const original=externalLink("Read the original expert discussion ↗",lesson.source_url);
  if(original)sources.append(original);
  if(lesson.annotated_source){
    const annotated=externalLink(lesson.annotated_source.label+" ↗",lesson.annotated_source.url);
    if(annotated)sources.append(annotated);
  }
  card.append(sources);
  const actions=node("div","guide-actions");
  const inspect=node("button","outline","Study these examples");
  inspect.type="button";
  inspect.disabled=!lesson.examples.length;
  inspect.addEventListener("click",()=>studyLesson(lesson));
  const ids=guideSelection(lesson);
  const compare=node("button","","Compare all "+lesson.examples.length+" examples");
  compare.type="button";
  compare.disabled=ids.length<MIN_COMPARISON;
  compare.addEventListener("click",()=>compareLesson(lesson));
  actions.append(inspect,compare);
  card.append(actions);
  card.append(node("p","guide-basket-note",
    ids.length>=MIN_COMPARISON ?
      "Compares every example in this segment, replacing your current basket. Expert notes appear above the images." :
      lesson.examples.length<MIN_COMPARISON ?
        "Add a second curated example to enable comparison." :
        "This category exceeds the "+MAX_SELECTION+"-diamond shared comparison limit."));

  return card;
}
function renderGuide() {
  $("guide-cards").replaceChildren(...state.guide.map(makeGuideCard));
}

function makeCard(row) {
  const doc=state.docs.get(row.id);
  const chosen=state.selected.includes(row.id);
  const card=node("article","reference-card"+(chosen?" is-selected":""));
  card.id="reference-"+row.reference_id;
  card.append(node("span","case-label","Learning reference · "+row.reference_id));
  card.append(node("h3","",row.label));
  const grades=[row.carat==null?null:row.carat+" ct",row.colour,row.clarity]
    .filter(Boolean).join(" · ");
  card.append(node("p","identity-note",grades+(grades?" · ":"")+
    (row.report_number?row.lab+" "+row.report_number+" (reported)":"Certificate not established")));
  const media=node("div","reference-illustration");
  if(row.thumbnail_url){
    const picture=node("img");
    const url=externalLink("source",row.thumbnail_url);
    if(url){picture.src=url.href;picture.alt="Published reference still";picture.loading="lazy";
      picture.addEventListener("error",()=>media.replaceChildren(
        node("span","placeholder-gem","◇"),node("small","","No saved preview")));
      media.append(picture);}
  }
  if(!media.childElementCount)media.append(node("span","placeholder-gem","◇"),
    node("small","","No locally published image yet"));
  card.append(media);
  card.append(node("p","reference-commentary",
    doc?.commentary || row.commentary_excerpt || "No commentary available."));
  if(state.failures.has(row.id))
    card.append(node("p","load-error","Full source details could not load; the index summary is shown."));
  const topics=node("div","topics");
  (doc?.topics || row.topics || []).forEach(topic=>
    topics.append(node("span","topic-tag",friendly(topic))));
  card.append(topics);
  const sources=node("div","source-links");
  const links=doc?.source_links || (row.source_url?[{kind:"discussion",url:row.source_url}]:[]);
  links.forEach(item=>{
    const a=externalLink(item.kind==="discussion"?"Expert discussion ↗":"Original source ↗",item.url);
    if(a)sources.append(a);
  });
  (doc?.media_sources || []).forEach(item=>{
    const a=externalLink(item.kind==="viewer"?"Open original viewer ↗":"Original media ↗",item.url);
    if(a)sources.append(a);
  });
  if(sources.childElementCount)card.append(sources);
  card.append(node("p","media-state",row.has_motion ?
    "Stored rotation available · ordinal frame alignment only" :
    "No stored rotation · external links are not ingested motion"));
  const actions=node("div","card-actions");
  const button=node("button",chosen?"is-active":"",
    chosen?"Remove from comparison":"Add to comparison");
  button.type="button";button.id="pick-"+row.id;
  button.disabled=!chosen && state.selected.length>=MAX_SELECTION;
  button.setAttribute("aria-pressed",String(chosen));
  button.addEventListener("click",()=>select(row.id));
  actions.append(button);card.append(actions);
  return card;
}
function render() {
  if(!state.ready)return;
  const search=$("search").value.toLowerCase().trim();
  const topic=$("topic").value;
  const focusedIds=state.focusLesson ?
    new Set(state.focusLesson.examples.map(example=>example.id)) : null;
  const visible=state.references.filter(row=>{
    if(focusedIds && !focusedIds.has(row.reference_id))return false;
    const doc=state.docs.get(row.id);
    if(topic!=="all" && !(doc?.topics||row.topics||[]).includes(topic))return false;
    const haystack=[row.id,row.label,row.carat,row.lab,row.report_number,
      doc?.commentary||row.commentary_excerpt,...(row.topics||[])].join(" ").toLowerCase();
    return haystack.includes(search);
  });
  $("cards").replaceChildren(...visible.map(makeCard));
  $("count").textContent=visible.length+" of "+state.references.length+" expert references";
  $("focused-lesson").hidden=!state.focusLesson;
  if(state.focusLesson)
    $("focused-lesson-label").textContent="Studying: "+state.focusLesson.title+" · "+visible.length+" relevant examples";
  $("empty").hidden=visible.length>0;
  const n=state.selected.length;
  $("selected-count").textContent=n===0?"Choose two to "+MAX_SELECTION+" stones to compare." :
    n<MIN_COMPARISON?"1 selected · choose at least one more." :
    n+" selected · ready to compare"+(n===MAX_SELECTION?" (maximum).":".");
  $("selected-chips").replaceChildren(...state.selected.map(id=>
    node("span","chip",nameFor(id))));
  $("clear-selection").disabled=!n;
  $("compare-button").disabled=n<MIN_COMPARISON;
  $("compare-button").textContent=state.comparing?"Hide comparison":"Compare "+n+" selected";
  updateLinks();
  const lesson=state.guide.find(item=>item.id===state.compareLessonId);
  const notesById=new Map((lesson?.examples||[]).map(example=>
    ["ref-"+example.id,{label:example.label,comment:example.comment}]));
  comparisonView.update(state.allRows,state.selected,state.comparing,
    {notesById,contextKey:lesson?.id||""});
}
function navigationState() {
  if(!state.ready)return;
  const ids=new Set(state.allRows.map(row=>row.id));
  const next=selectionFromSearch(location.search,ids);
  state.selected=next.selected;state.comparing=next.comparing;
  const lessonId=new URLSearchParams(location.search).get("lesson");
  const candidate=state.guide.find(lesson=>lesson.id===lessonId);
  const examples=candidate?guideSelection(candidate):[];
  state.compareLessonId=next.comparing && examples.length===next.selected.length &&
    examples.every((id,i)=>id===next.selected[i]) ? candidate.id : null;
  render();
}
async function getJSON(url) {
  const response=await fetch(url,{cache:"no-cache"});
  if(!response.ok)throw new Error("HTTP "+response.status);
  return response.json();
}
async function boot() {
  $("search").addEventListener("input",()=>{state.focusLesson=null;render();});
  $("topic").addEventListener("change",()=>{state.focusLesson=null;render();});
  $("show-all").addEventListener("click",()=>{
    state.focusLesson=null;$("search").value="";$("topic").value="all";render();
  });
  $("clear-selection").addEventListener("click",()=>{
    state.selected=[];state.comparing=false;state.compareLessonId=null;updateURL();render();
  });
  $("compare-button").addEventListener("click",()=>{
    if(state.selected.length<MIN_COMPARISON)return;
    state.comparing=!state.comparing;updateURL();render();
    if(state.comparing)$("comparison").scrollIntoView({behavior:"smooth",block:"nearest"});
  });
  addEventListener("popstate",navigationState);
  try{
    state.references=validateReferenceIndex(await getJSON("../data/reference-index.json"));
    const topics=new Set(state.references.flatMap(row=>row.topics||[]));
    for(const tag of [...topics].sort()){
      const option=node("option","",friendly(tag));option.value=tag;$("topic").append(option);
    }
    // Certified selection is optional while browsing; only reference data is essential.
    try{
      state.certified=validateIndex(await getJSON("../data/catalog.json"));
    }catch(error){console.warn("Personal catalogue index unavailable",error);}
    state.allRows=[...state.certified,...state.references];
    await Promise.all(state.references.map(async row=>{
      try{state.docs.set(row.id,await loadReference(row));}
      catch(error){state.failures.add(row.id);console.warn("Reference detail unavailable",row.id,error);}
    }));
    try {
      state.guide=validateExpertGuide(
        await getJSON("../data/learning-guide.json"),
        new Set(state.references.map(row=>row.id)));
    } catch(error) {
      console.warn("Learning guide unavailable",error);
      $("guide-cards").append(node("p","error","The expert guide could not load; the reference gallery below remains available."));
    }
    state.ready=true;
    if(state.guide.length)renderGuide();
    $("search").disabled=false;$("topic").disabled=false;
    navigationState();
  }catch(error){
    $("count").textContent="References unavailable";
    $("error").textContent="Could not load the published learning references ("+error.message+").";
    $("error").hidden=false;
  }
}
boot();
