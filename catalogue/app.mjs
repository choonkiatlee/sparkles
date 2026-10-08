import { MAX_SELECTION, MIN_COMPARISON, validateIndex, visibleRows,
  priceText, dimensionsText, displayValue, selectionFromSearch,
  selectionSearch, toggleSelection } from "./core.mjs";

import { createComparisonView } from "./comparison-view.mjs";

const $ = id => document.getElementById(id);
const controls = { search:$("search"), status:$("status-filter"), sort:$("sort") };
const state = { rows:[], selected:[], comparing:false, ready:false };
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
  const tr = node("tr", "overview-row"+(selected ? " is-selected":""));
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
  tr.append(checkCell,identity,carat,colour,clarity,price,status,score);
  tr.addEventListener("click", event=>{
    if (event.target.closest("input,a,label,button")) return;
    if (!input.disabled) toggle();
  });
  return tr;
}
function syncURL() {
  const search = selectionSearch(location.search,state.selected,state.comparing);
  history.replaceState(null,"",location.pathname + (search ? "?"+search : "") + location.hash);
}
function render() {
  if (!state.ready) return;
  const rows = visibleRows(state.rows,{
    search:controls.search.value,status:controls.status.value,sort:controls.sort.value
  });
  $("count").textContent = rows.length+" of "+state.rows.length+" saved "+(state.rows.length===1?"stone":"stones");
  const cards = $("cards");
  cards.replaceChildren(...rows.map(makeRow));
  $("empty").hidden = rows.length > 0;
  const quantity = state.selected.length;
  $("selected-count").textContent = quantity === 0 ? "Select two to five diamonds." :
    quantity < MIN_COMPARISON ? "1 selected · choose at least one more." :
    quantity+" selected · ready to compare"+(quantity===MAX_SELECTION?" (maximum).":".");
  $("selected-chips").replaceChildren(...state.selected.map(id => node("span","chip",id)));
  $("clear-selection").disabled = quantity===0;
  const compare = $("compare-button");
  compare.disabled = quantity < MIN_COMPARISON;
  compare.textContent = state.comparing ? "Hide overview" : "Compare "+quantity+" selected";
  comparisonView.update(state.rows,state.selected,state.comparing);
}
function applyNavigationState() {
  const parsed = selectionFromSearch(location.search,new Set(state.rows.map(r=>r.id)));
  state.selected = parsed.selected; state.comparing = parsed.comparing;
  render();
}
async function boot() {
  for (const c of Object.values(controls)) {
    c.addEventListener(c===controls.search?"input":"change",render);
  }
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
    state.ready = true;
    for (const c of Object.values(controls)) c.disabled = false;
    applyNavigationState();
  } catch(error) {
    $("count").textContent = "Catalogue unavailable";
    $("error").textContent = "Could not load the published catalogue ("+error.message+"). Try refreshing the page.";
    $("error").hidden = false;
  }
}
boot();
