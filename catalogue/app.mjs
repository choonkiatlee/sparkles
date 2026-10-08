import { MAX_SELECTION, MIN_COMPARISON, validateIndex, visibleRows,
  priceText, dimensionsText, displayValue, selectionFromSearch,
  selectionSearch, toggleSelection } from "./core.mjs";

const $ = id => document.getElementById(id);
const controls = { search:$("search"), status:$("status-filter"), sort:$("sort") };
const state = { rows:[], selected:[], comparing:false, ready:false };
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
function labeledFact(label, value) {
  const d = node("div");
  d.append(node("dt", "", label), node("dd", "", displayValue(value)));
  return d;
}
function makeCard(row) {
  const card = node("article","diamond" + (state.selected.includes(row.id) ? " is-selected" : ""));
  const imageArea = node("div","photograph");
  const src = httpUrl(row.thumbnail_url);
  if (src) {
    const img = node("img");
    img.src = src;
    img.alt = "Published evidence for " + displayValue(row.report_number) + "; viewing angle uncalibrated";
    img.loading = "lazy"; img.decoding = "async";
    img.addEventListener("error", () => imageArea.replaceChildren(node("span","photo-empty","Published image unavailable")));
    imageArea.append(img);
  } else imageArea.append(node("span","photo-empty","No published image"));
  const content = node("div","card-content");
  const heading = node("div","idline");
  const id = node("div");
  id.append(node("h3","",displayValue(row.lab)+" "+displayValue(row.report_number)),
    node("p","subtitle",displayValue(row.retailer)));
  const status = node("span","status " + (/^(complete|partial)$/.test(row.retrieval_status) ? row.retrieval_status : ""),
    displayValue(row.retrieval_status));
  heading.append(id,status);
  const facts = node("dl","facts");
  facts.append(labeledFact("Carat",row.carat == null ? null : row.carat+" ct"),
    labeledFact("Colour",row.colour),labeledFact("Clarity",row.clarity));
  const more = node("div","more");
  more.append(node("p","subtitle",displayValue(row.shape)+" · "+dimensionsText(row)),
    node("p","price",priceText(row)));
  if (row.tax_basis) more.append(node("p","tax",row.tax_basis));
  else more.append(node("p","tax","Tax basis unknown"));
  const links = node("div","links");
  const source = link("Original listing ↗",row.source_url);
  if (source) links.append(source);
  if (links.children.length) more.append(links);
  const select = node("label","select-control");
  const input = node("input");
  input.type = "checkbox"; input.checked = state.selected.includes(row.id);
  input.disabled = !input.checked && state.selected.length >= MAX_SELECTION;
  input.setAttribute("aria-label","Select "+displayValue(row.report_number)+" for comparison");
  input.addEventListener("change", () => {
    state.selected = toggleSelection(state.selected,row.id);
    state.comparing = state.comparing && state.selected.length >= MIN_COMPARISON;
    syncURL(); render();
    const moved = [...$("cards").querySelectorAll("input[type=checkbox]")].find(x => x.getAttribute("aria-label")===input.getAttribute("aria-label"));
    moved?.focus();
  });
  select.append(input,node("span","","Select to compare"));
  content.append(heading,facts,more,select);
  card.append(imageArea,content);
  return card;
}
function syncURL() {
  const search = selectionSearch(location.search,state.selected,state.comparing);
  history.replaceState(null,"",location.pathname + (search ? "?"+search : "") + location.hash);
}
function renderPreview() {
  const section = $("comparison"), grid = $("comparison-grid");
  const rows = state.selected.map(id => state.rows.find(row=>row.id===id)).filter(Boolean);
  const show = state.comparing && rows.length >= MIN_COMPARISON;
  section.hidden = !show;
  grid.replaceChildren();
  if (!show) return;
  rows.forEach(row => {
    const item = node("div","comparison-item");
    item.append(node("h4","",displayValue(row.report_number)),
      node("p","",displayValue(row.carat)+" ct · "+displayValue(row.colour)+" · "+displayValue(row.clarity)),
      node("p","",dimensionsText(row)),node("p","",priceText(row)),
      node("p","", "Retrieval: "+displayValue(row.retrieval_status)));
    grid.append(item);
  });
}
function render() {
  if (!state.ready) return;
  const rows = visibleRows(state.rows,{
    search:controls.search.value,status:controls.status.value,sort:controls.sort.value
  });
  $("count").textContent = rows.length+" of "+state.rows.length+" saved "+(state.rows.length===1?"stone":"stones");
  const cards = $("cards");
  cards.replaceChildren(...rows.map(makeCard));
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
  renderPreview();
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
