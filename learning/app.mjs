// Separate educational browse surface, sharing selection helpers and the one existing viewer.
import {MAX_SELECTION,MIN_COMPARISON,validateIndex,
  selectionFromSearch,selectionSearch,toggleSelection} from "../catalogue/core.mjs";
import {createComparisonView} from "../catalogue/comparison-view.mjs";
import {validateReferenceIndex,createReferenceManifestLoader} from "../catalogue/reference.mjs";

const $ = id => document.getElementById(id);
const state = {references:[], certified:[], allRows:[], docs:new Map(),
  failures:new Set(),selected:[],comparing:false,ready:false};
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
  const params=selectionSearch(location.search,state.selected,state.comparing);
  history.replaceState(null,"",location.pathname+(params?"?"+params:"")+location.hash);
}
function select(id) {
  state.selected=toggleSelection(state.selected,id);
  state.comparing=state.comparing && state.selected.length>=MIN_COMPARISON;
  updateURL();
  render();
  document.getElementById("pick-"+id)?.focus();
}
function makeCard(row) {
  const doc=state.docs.get(row.id);
  const chosen=state.selected.includes(row.id);
  const card=node("article","reference-card"+(chosen?" is-selected":""));
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
  const visible=state.references.filter(row=>{
    const doc=state.docs.get(row.id);
    if(topic!=="all" && !(doc?.topics||row.topics||[]).includes(topic))return false;
    const haystack=[row.id,row.label,row.carat,row.lab,row.report_number,
      doc?.commentary||row.commentary_excerpt,...(row.topics||[])].join(" ").toLowerCase();
    return haystack.includes(search);
  });
  $("cards").replaceChildren(...visible.map(makeCard));
  $("count").textContent=visible.length+" of "+state.references.length+" expert references";
  $("empty").hidden=visible.length>0;
  const n=state.selected.length;
  $("selected-count").textContent=n===0?"Choose two to five stones to compare." :
    n<MIN_COMPARISON?"1 selected · choose at least one more." :
    n+" selected · ready to compare"+(n===MAX_SELECTION?" (maximum).":".");
  $("selected-chips").replaceChildren(...state.selected.map(id=>
    node("span","chip",nameFor(id))));
  $("clear-selection").disabled=!n;
  $("compare-button").disabled=n<MIN_COMPARISON;
  $("compare-button").textContent=state.comparing?"Hide comparison":"Compare "+n+" selected";
  updateLinks();
  comparisonView.update(state.allRows,state.selected,state.comparing);
}
function navigationState() {
  if(!state.ready)return;
  const ids=new Set(state.allRows.map(row=>row.id));
  const next=selectionFromSearch(location.search,ids);
  state.selected=next.selected;state.comparing=next.comparing;
  render();
}
async function getJSON(url) {
  const response=await fetch(url,{cache:"no-cache"});
  if(!response.ok)throw new Error("HTTP "+response.status);
  return response.json();
}
async function boot() {
  $("search").addEventListener("input",render);
  $("topic").addEventListener("change",render);
  $("clear-selection").addEventListener("click",()=>{
    state.selected=[];state.comparing=false;updateURL();render();
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
    state.ready=true;
    $("search").disabled=false;$("topic").disabled=false;
    navigationState();
  }catch(error){
    $("count").textContent="References unavailable";
    $("error").textContent="Could not load the published learning references ("+error.message+").";
    $("error").hidden=false;
  }
}
boot();
