import { MAX_SELECTION, MIN_COMPARISON, validateIndex, visibleRows,
  priceText, dimensionsText, displayValue, selectionFromSearch,
  selectionSearch, toggleSelection } from "./core.mjs";

import { createComparisonView } from "./comparison-view.mjs";
import { validateReferenceIndex } from "./reference.mjs";
import { DRAFT_STORAGE_KEY, emptyDraft, validateCuration, validateDraft,
  flagsFor, setDraftFlag, reconcileDraft, draftCount, archivedCount,
  curationRows } from "./curation.mjs";
import { openCurationIssueInNewTab } from "./curation-request.mjs";

const $ = id => document.getElementById(id);
const controls = { search:$("search"), status:$("status-filter"), sort:$("sort") };
const curationControls = { archived:$("show-archived"), shortlist:$("shortlist-only") };
const state = { rows:[], referenceRows:[], allRows:[], selected:[], comparing:false, ready:false,
  published:null, draft:emptyDraft(), localError:"", refreshError:"" };
const comparisonView = createComparisonView({container:$("comparison"),grid:$("comparison-grid"),fetcher:(...args)=>fetch(...args)});
const node = (tag, className="", text=null) => {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== null) n.textContent = String(text);
  return n;
};
function httpUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const u = new URL(value, document.baseURI);
    return ["https:","http:"].includes(u.protocol) ? u.href : null;
  } catch { return null; }
}
function link(text, href) {
  const safe = httpUrl(href);
  if (!safe) return null;
  const a = node("a", "", text);
  a.href = safe; a.target = "_blank"; a.rel = "noopener noreferrer";
  return a;
}
// Overview renders from the compact index only. Detailed manifests load on compare.
function makeRow(row) {
  const selected = state.selected.includes(row.id);
  const flags = flagsFor(state.published,state.draft,row.id);
  const tr = node("tr", "overview-row"+(selected ? " is-selected":"")+(flags.archived ? " is-archived":""));
  const checkCell = node("td", "cell-select");
  const label = node("label", "row-selection");
  const input = node("input");
  input.type = "checkbox";
  input.checked = selected;
  input.disabled = !selected && state.selected.length >= MAX_SELECTION;
  input.setAttribute("aria-label","Select "+displayValue(row.report_number)+" for comparison");
  function toggle() {
    state.selected = toggleSelection(state.selected,row.id);
    state.comparing = state.comparing && state.selected.length >= MIN_COMPARISON;
    syncURL();
    render();
    const replacement = [...$("cards").querySelectorAll("input[type=checkbox]")]
      .find(x => x.getAttribute("aria-label") === input.getAttribute("aria-label"));
    replacement?.focus();
  }
  input.addEventListener("change", toggle);
  label.append(input);
  checkCell.append(label);
  const identity = node("th","cell-identity");
  identity.scope="row";
  const detail = node("div","diamond-identity");
  const thumb = node("span","mini-photo");
  const generatedIcon = Boolean(row.overview_thumbnail_url);
  const imageURL = httpUrl(row.overview_thumbnail_url || row.thumbnail_url);
  if (imageURL) {
    const img=node("img");
    img.src=imageURL;
    img.alt=generatedIcon ? "Automatically cropped diamond overview thumbnail" : "Representative saved diamond image";
    img.loading="lazy"; img.decoding="async";
    img.title=generatedIcon ? "Automatic source-hash-traced crop; orientation uncalibrated" : "Original representative image";
    img.addEventListener("error",()=>{
      // A temporary derived-asset issue should never hide the original saved image.
      const original = httpUrl(row.thumbnail_url);
      if (generatedIcon && original && img.src !== original) {
        img.src = original;
        img.alt = "Original representative diamond image (generated icon unavailable)";
        return;
      }
      thumb.replaceChildren(node("span","photo-empty","◇"));
    });
    thumb.append(img);
  } else {
    thumb.append(node("span","photo-empty","◇"));
  }
  const captions = node("span","diamond-caption");
  const source=link(displayValue(row.lab)+" "+displayValue(row.report_number),row.source_url);
  if (source) {source.className="report-link";captions.append(source);}
  else captions.append(node("strong","report-link",displayValue(row.lab)+" "+displayValue(row.report_number)));
  captions.append(node("small","retailer-name",displayValue(row.retailer)));
  captions.append(node("small","size-note",dimensionsText(row)));
  if (flags.archived) captions.append(node("small","archive-label","Archived · hidden by default"));
  detail.append(thumb,captions);
  identity.append(detail);
  const carat = node("td","cell-number",row.carat == null ? "Unknown" : row.carat+" ct");
  const colour = node("td","cell-grade",displayValue(row.colour));
  const clarity = node("td","cell-grade",displayValue(row.clarity));
  const price = node("td","cell-price");
  price.append(node("strong","",priceText(row)));
  const tax = node("small","tax-brief",row.tax_basis || "Tax basis unknown");
  tax.title = row.tax_basis || "Tax basis unknown";
  price.append(tax);
  const status = node("td","cell-status");
  status.append(node("span","status "+(/^(complete|partial)$/.test(row.retrieval_status)?row.retrieval_status:""),displayValue(row.retrieval_status)));
  const score = node("td","cell-score");
  score.append(node("span","not-scored","Not scored"));
  const curation = node("td","cell-curation");
  const actions = node("span","curation-actions");
  const star = node("button","curation-star"+(flags.starred?" is-starred":""),flags.starred?"★":"☆");
  star.type="button"; star.disabled=!!state.localError;
  star.setAttribute("aria-label",(flags.starred?"Remove ":"Add ")+displayValue(row.report_number)+
    (flags.starred?" from shortlist":" to shortlist"));
  star.setAttribute("aria-pressed",String(flags.starred));
  star.title=flags.starred?"Remove from shortlist":"Add to shortlist";
  star.addEventListener("click",()=>changeCuration(row.id,"starred",!flags.starred));
  const archive = node("button","curation-archive",flags.archived?"Restore":"Archive");
  archive.type="button"; archive.disabled=!!state.localError;
  archive.setAttribute("aria-label",(flags.archived?"Restore ":"Archive ")+displayValue(row.report_number));
  archive.setAttribute("aria-pressed",String(flags.archived));
  archive.addEventListener("click",()=>changeCuration(row.id,"archived",!flags.archived));
  actions.append(star,archive); curation.append(actions);
  tr.append(checkCell,identity,carat,colour,clarity,price,status,score,curation);
  tr.addEventListener("click", event=>{
    if (event.target.closest("input,a,label,button")) return;
    if (!input.disabled) toggle();
  });
  return tr;
}
function changeCuration(id,field,value) {
  if (state.localError) return;
  const ids=new Set(state.rows.map(row=>row.id));
  try {
    const next=setDraftFlag(state.published,state.draft,id,field,value,ids);
    if (draftCount(next)) localStorage.setItem(DRAFT_STORAGE_KEY,JSON.stringify(next));
    else localStorage.removeItem(DRAFT_STORAGE_KEY);
    state.draft=next; render();
  } catch (error) {
    state.localError="Cannot save browser draft ("+error.message+"). Reset local changes to retry.";
    render();
  }
}
async function saveOnGitHub() {
  if(state.localError) return;
  try {
    const ids=new Set(state.rows.map(row=>row.id));
    // Leave the catalogue and browser draft intact while the owner confirms
    // the prefilled GitHub issue in a separate tab.
    $("save-curation").disabled=true;
    await openCurationIssueInNewTab(state.published,state.draft,ids);
    $("save-curation").disabled=false;
  } catch(error) {
    state.refreshError="Could not prepare GitHub save ("+error.message+").";
    render();
  }
}
async function refreshCuration() {
  $("refresh-curation").disabled=true;
  try {
    const response=await fetch("../data/diamond-curation.json",{cache:"no-store"});
    if(!response.ok) throw new Error("HTTP "+response.status);
    const ids=new Set(state.rows.map(row=>row.id));
    const published=validateCuration(await response.json(),ids);
    const reconciled=reconcileDraft(published,state.draft,ids);
    if(draftCount(reconciled)) localStorage.setItem(DRAFT_STORAGE_KEY,JSON.stringify(reconciled));
    else localStorage.removeItem(DRAFT_STORAGE_KEY);
    state.published=published;
    state.draft=reconciled;
    state.refreshError="";
  } catch(error) {
    state.refreshError="Could not verify GitHub curation state ("+error.message+
      "). Your browser draft is unchanged.";
  } finally {
    $("refresh-curation").disabled=false;
    render();
  }
}
function resetDraft() {
  try {
    localStorage.removeItem(DRAFT_STORAGE_KEY);
    state.draft=emptyDraft();state.localError="";render();
  } catch (error) {
    state.localError="Cannot clear browser draft ("+error.message+").";
    render();
  }
}
function syncURL() {
  const search = selectionSearch(location.search,state.selected,state.comparing);
  history.replaceState(null,"",location.pathname + (search ? "?"+search : "") + location.hash);
}
function render() {
  if (!state.ready) return;
  const rows = curationRows(visibleRows(state.rows,{
    search:controls.search.value,status:controls.status.value,sort:controls.sort.value
  }),{showArchived:curationControls.archived.checked,shortlistOnly:curationControls.shortlist.checked},
    state.published,state.draft);
  const archived = archivedCount(state.rows,state.published,state.draft);
  $("count").textContent = rows.length+" shown · "+state.rows.length+" saved · "+archived+" archived";
  $("archived-count").textContent = String(archived);
  const pending=draftCount(state.draft);
  $("curation-pending").textContent = pending ?
    pending+" pending change"+(pending===1?"":"s")+" in this browser. Confirm Save on GitHub, then Refresh saved state to verify publication." :
    "No unsaved changes. Stars and archives shown here are backed by published Git state.";
  $("save-curation").disabled=!pending || !!state.localError;
  $("refresh-curation-error").textContent=state.refreshError;
  $("refresh-curation-error").hidden=!state.refreshError;
  $("curation-local-error").textContent=state.localError;
  $("curation-local-error").hidden=!state.localError;
  $("reset-curation").disabled=!pending && !state.localError;
  const cards = $("cards");
  cards.replaceChildren(...rows.map(makeRow));
  $("empty").hidden = rows.length > 0;
  const quantity = state.selected.length;
  $("selected-count").textContent = quantity === 0 ? "Select two to "+MAX_SELECTION+" diamonds." :
    quantity < MIN_COMPARISON ? "1 selected · choose at least one more." :
    quantity+" selected · ready to compare"+(quantity===MAX_SELECTION?" (maximum).":".");
  $("selected-chips").replaceChildren(...state.selected.map(id => {
    const row=state.allRows.find(row=>row.id===id);
    return node("span","chip",row?.kind==="reference" ? row.label : id);
  }));
  $("clear-selection").disabled = quantity===0;
  const compare = $("compare-button");
  compare.disabled = quantity < MIN_COMPARISON;
  compare.textContent = state.comparing ? "Hide overview" : "Compare "+quantity+" selected";
  const query=selectionSearch("",state.selected,state.comparing);
  const learningLink=$("learning-link");
  if (learningLink) learningLink.href="../learning/" + (query ? "?"+query : "");
  comparisonView.update(state.allRows,state.selected,state.comparing);
}
function applyNavigationState() {
  const parsed = selectionFromSearch(location.search,new Set(state.allRows.map(r=>r.id)));
  state.selected = parsed.selected; state.comparing = parsed.comparing;
  render();
}
async function boot() {
  for (const c of Object.values(controls)) {
    c.addEventListener(c===controls.search?"input":"change",render);
  }
  for (const c of Object.values(curationControls)) c.addEventListener("change",render);
  $("reset-curation").addEventListener("click",resetDraft);
  $("save-curation").addEventListener("click",saveOnGitHub);
  $("refresh-curation").addEventListener("click",refreshCuration);
  $("compare-button").addEventListener("click",()=>{
    if (state.selected.length < MIN_COMPARISON) return;
    state.comparing = !state.comparing; syncURL(); render();
    if (state.comparing) $("comparison").scrollIntoView({behavior:"smooth",block:"nearest"});
  });
  $("clear-selection").addEventListener("click",()=>{
    state.selected=[];state.comparing=false;syncURL();render();
  });
  addEventListener("popstate",applyNavigationState);
  try {
    const response = await fetch("../data/catalog.json",{cache:"no-cache"});
    if (!response.ok) throw new Error("HTTP "+response.status);
    state.rows = validateIndex(await response.json());
    // Never silently show archived records if the authoritative curation fails.
    const curated=await fetch("../data/diamond-curation.json",{cache:"no-cache"});
    if (!curated.ok) throw new Error("Curation HTTP "+curated.status);
    const ids=new Set(state.rows.map(row=>row.id));
    state.published=validateCuration(await curated.json(),ids);
    try {
      const saved=localStorage.getItem(DRAFT_STORAGE_KEY);
      state.draft=saved ? reconcileDraft(state.published,
        validateDraft(JSON.parse(saved),ids),ids) : emptyDraft();
      // A confirmed Git write in PR B will drop matching local overrides.
      if (saved && !draftCount(state.draft)) localStorage.removeItem(DRAFT_STORAGE_KEY);
      else if (saved) localStorage.setItem(DRAFT_STORAGE_KEY,JSON.stringify(state.draft));
    } catch (error) {
      state.localError="Browser draft unavailable or invalid ("+error.message+
        "). Use Reset local changes to discard it.";
      state.draft=emptyDraft();
    }
    // The personal catalogue remains usable if the optional learning index fails.
    try {
      const refs = await fetch("../data/reference-index.json",{cache:"no-cache"});
      if (!refs.ok) throw new Error("HTTP "+refs.status);
      state.referenceRows = validateReferenceIndex(await refs.json());
    } catch(error) {
      console.warn("Learning references unavailable", error);
      state.referenceRows = [];
    }
    state.allRows = [...state.rows,...state.referenceRows];
    state.ready = true;
    for (const c of Object.values(controls)) c.disabled = false;
    for (const c of Object.values(curationControls)) c.disabled = false;
    applyNavigationState();
  } catch(error) {
    $("count").textContent = "Catalogue unavailable";
    $("error").textContent = "Could not load the published catalogue ("+error.message+"). Try refreshing the page.";
    $("error").hidden = false;
  }
}
boot();
