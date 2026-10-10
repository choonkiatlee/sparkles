// Manifest-backed, per-column comparison. Browser DOM only; C3 adds motion.
import { comparisonRows, createManifestLoader, projectComparison,
  publicUrl, dateText } from "./compare.mjs";
import { displayValue, priceText } from "./core.mjs";
import { createRotationPlayer } from "./rotation-player.mjs";
import {createReferenceManifestLoader,projectReferenceComparison} from "./reference.mjs";

const el = (tag, className="", text=null) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== null) element.textContent = String(text);
  return element;
};
const link = (caption, url) => {
  const href = publicUrl(url);
  if (!href) return null;
  const anchor = el("a","",caption);
  anchor.href = href;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
};
const appendLink = (parent, caption, url) => {
  const anchor = link(caption,url);
  if (anchor) parent.append(anchor);
  return Boolean(anchor);
};
const bullet = (parent, content) => {
  const li = el("li");
  if (typeof content === "string") li.textContent=content;
  else li.append(content);
  parent.append(li);
  return li;
};

function fillColumn(column, projected) {
  const reference = projected.kind === "reference";
  const head = column.head;
  head.replaceChildren();
  const picture = el("div","compare-picture");
  if (projected.rotation?.status === "video_only" && projected.video?.url) {
    const video = el("video");
    video.src = projected.video.url;
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    video.setAttribute("aria-label","Published original vendor video; independent playback");
    picture.append(video);
  } else if (projected.representative) {
    const img = el("img");
    img.src = projected.representative.url;
    img.alt = projected.representative.label + " for " + projected.report + "; angle not calibrated";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("error",()=>picture.replaceChildren(
      el("span","photo-empty","Published image unavailable")));
    picture.append(img);
  } else picture.append(el("span","photo-empty","No published still or validated rotation"));
  head.append(el("strong","compare-report", reference ? projected.label : projected.lab + " " + projected.report));
  head.append(el("span","compare-source", reference ? "Expert learning reference · " + projected.identityStatus + " identity" : displayValue(projected.currentListing.retailer)));
  if (reference) {
    const note=el("div","compare-expert-note");
    note.append(el("strong","compare-note-label",
      column.note ? "Why this example matters · "+column.note.label : "Expert observation"));
    note.append(el("p","",column.note?.comment || projected.commentary));
    head.append(note);
  }
  head.append(picture);
  head.append(el("small","compare-caption",
    projected.rotation?.status === "video_only" && projected.video?.url ?
      "Published original MP4 · independent playback (not synchronized 360 frames)" :
      projected.representative ? projected.representative.label+" · viewpoint uncalibrated" :
      "Evidence missing"));
  for (const [key] of comparisonRows)
    column.cells.get(key).textContent = projected.values[key];

  const certificateCell = column.cells.get("certificate");
  certificateCell.replaceChildren();
  if (reference) {
    certificateCell.append(el("span","missing",projected.report === "Unknown" ? "Certificate not established" : projected.lab + " " + projected.report + " (source reported; not independently verified here)"));
  } else if (projected.certificate) {
    appendLink(certificateCell,"Published original PDF ↗",projected.certificate.url);
  } else certificateCell.append(el("span","missing","Certificate PDF not recovered"));
  if (!reference && projected.verification) {
    if (projected.certificate) certificateCell.append(el("span","link-separator"," · "));
    appendLink(certificateCell,
      projected.certificate ? "Original certificate link ↗" : "Verification link only ↗",
      projected.verification);
  }
  const sourceCell = column.cells.get("source");
  sourceCell.replaceChildren();
  if (reference) {
    const sourceList = [...projected.sourceLinks, ...projected.mediaSources];
    if (!sourceList.length) sourceCell.append(el("span","missing","No source links"));
    sourceList.forEach((source,i) => {
      if (i) sourceCell.append(el("span","link-separator"," · "));
      appendLink(sourceCell,source.kind === "viewer" ? "Open original viewer ↗" :
        source.kind === "discussion" ? "Expert discussion ↗" : "Original source ↗",source.url);
    });
  } else {
    const latest = projected.currentListing;
    if (!appendLink(sourceCell,"Latest listing ↗", latest.url))
      sourceCell.append(el("span","missing","No usable listing link"));
    if (projected.listings.length > 1)
      sourceCell.append(el("span","subtle"," · "+projected.listings.length+" saved observations"));
  }

  const provenanceCell = column.cells.get("provenance");
  provenanceCell.replaceChildren();
  if (reference) {
    // Expert notes are visible up front. Evidence details remain supplemental.
    const detail = el("details","provenance");
    detail.append(el("summary","","Evidence details"));
    const body = el("div","provenance-body");
    if (projected.topics.length)
      body.append(el("p","subtle","Topics: " + projected.topics.join(" · ")));
    body.append(el("p","subtle",projected.evidence.length ?
      "Saved evidence: " + projected.values.motion : "Original media is linked, not locally ingested."));
    detail.append(body);
    provenanceCell.append(detail);
    return;
  }
  const detail = el("details","provenance");
  detail.append(el("summary","", "View sources & evidence"));
  const contents = el("div","provenance-body");
  contents.append(el("h4","", "Latest retrieval"));
  contents.append(el("p","",projected.latestAt+" · "+projected.values.retrieval));
  if (projected.reasons.length) {
    const list = el("ul");
    projected.reasons.forEach(r=>bullet(list,displayValue(r)));
    contents.append(list);
  }
  contents.append(el("h4","", "Listing observations"));
  const listingList=el("ul");
  if (!projected.listings.length) bullet(listingList,"No listing observations");
  projected.listings.forEach(obs=>{
    const li = bullet(listingList,
      dateText(obs.observed_at)+" · "+displayValue(obs.retailer)+" · "+priceText(obs)+
      " · "+displayValue(obs.tax_basis));
    li.append(el("span","subtle"," · "+displayValue(obs.retailer_sku)));
    const l=link(" · Source ↗",obs.url);
    if (l) li.append(l);
  });
  contents.append(listingList);
  contents.append(el("h4","", "Saved evidence"));
  const evList=el("ul");
  if (!projected.evidence.length) bullet(evList,"No recovered evidence recorded");
  projected.evidence.forEach(e=>{
    const count = e.kind==="rotation" && Array.isArray(e.frames)
      ? " · "+e.frames.length+" ordered frames" : "";
    const li=bullet(evList, displayValue(e.kind)+" · "+displayValue(e.status)+count);
    const file=e.kind==="video" ? e.payload_asset?.storage?.url : null;
    if (file) appendLink(li," · Original video ↗",file);
    const chain = Array.isArray(e.provenance) ? e.provenance : [];
    const unique = new Set();
    chain.forEach(p=>{
      if (!p?.locator || unique.has(p.locator)) return;
      unique.add(p.locator);
      if (unique.size<=2) appendLink(li," · "+displayValue(p.source)+" ↗",p.locator);
    });
  });
  contents.append(evList);
  const failures = (projected.currentRetrieval.attempts || []).filter(a=>
    a?.status && !["success","resolved","not_requested"].includes(a.status));
  if (failures.length) {
    contents.append(el("h4","", "Incomplete evidence attempts"));
    const list=el("ul");
    failures.forEach(a=>bullet(list,
      displayValue(a.kind)+" · "+displayValue(a.status)+
      (a.message ? " · "+a.message : "")));
    contents.append(list);
  }
  detail.append(contents);
  provenanceCell.append(detail);
}

function failColumn(column,reason,onRetry) {
  column.head.replaceChildren(el("strong","compare-report",column.row.kind === "reference" ? column.row.label : column.row.lab+" "+column.row.report_number));
  column.head.append(el("span","error-small","Could not load published manifest"));
  const button=el("button","retry-manifest","Retry");
  button.type="button";
  button.addEventListener("click",onRetry);
  column.head.append(button);
  for (const cell of column.cells.values()) cell.textContent="Unavailable";
  column.cells.get("provenance").textContent="Manifest unavailable: "+reason;
}

export function createComparisonView({container, grid, fetcher}) {
  const load = createManifestLoader(fetcher);
  const loadReference = createReferenceManifestLoader(fetcher);
  let signature = "";
  let generation=0;
  let player=null;
  function update(rows,selected,comparing,{notesById=new Map(),contextKey=""}={}) {
    const show = comparing && selected.length >= 2;
    container.hidden=!show;
    const nextSignature = show ? selected.join(",")+"|"+contextKey : "";
    if (signature===nextSignature) return;
    signature=nextSignature;
    player?.destroy();
    player=null;
    generation++;
    const currentGeneration=generation;
    grid.replaceChildren();
    if (!show) return;
    const matching = selected.map(id=>rows.find(row=>row.id===id)).filter(Boolean);
    const outer=el("div","compare-scroll");
    outer.setAttribute("tabindex","0");
    outer.setAttribute("role","region");
    outer.setAttribute("aria-label","Selected diamond comparison; scroll horizontally for more columns");
    const table=el("table","compare-table");
    table.style.minWidth = (170 + matching.length * 255) + "px";
    const thead=el("thead");
    const first=el("tr");
    const title=el("th","compare-row-label","Stone");
    title.scope="col";
    first.append(title);
    const columns=matching.map(row=>{
      const th=el("th","compare-head");
      th.scope="col";
      th.append(el("strong","compare-report",row.kind === "reference" ? row.label : row.lab+" "+row.report_number));
      th.append(el("span","subtle","Loading saved evidence…"));
      first.append(th);
      return {row,head:th,cells:new Map(),note:notesById.get(row.id)};
    });
    thead.append(first); table.append(thead);
    const tbody=el("tbody");
    const fieldRows=[
      ["rotation","Original rotation"],...comparisonRows,["certificate","Certificate"],["source","Source listings"],
      ["provenance","Provenance"]
    ];
    fieldRows.forEach(([key,label])=>{
      const tr=el("tr");
      const th=el("th","compare-row-label",label);
      th.scope="row"; tr.append(th);
      columns.forEach(col=>{
        const td=el("td","compare-value","Loading…");
        col.cells.set(key,td); tr.append(td);
      });
      tbody.append(tr);
    });
    table.append(tbody);
    outer.append(table);
    const toolbar=el("div","motion-toolbar");
    grid.append(toolbar,outer);
    player=createRotationPlayer({
      host:toolbar,
      slots:new Map(columns.map(col=>[col.row.id,col.cells.get("rotation")]))
    });
    async function loadColumn(column) {
      column.head.append(el("span","sr-only","Loading manifest"));
      try {
        const data = column.row.kind === "reference" ?
          projectReferenceComparison(column.row,await loadReference(column.row)) :
          projectComparison(column.row,await load(column.row));
        if (generation !== currentGeneration) return;
        fillColumn(column,data);
        player?.setStone(column.row.id,data.rotation,data.representative,data.label || data.report);
      } catch(error) {
        if (generation !== currentGeneration) return;
        player?.failStone(column.row.id);
        failColumn(column,error.message,()=>{
          column.head.replaceChildren(el("span","subtle","Retrying…"));
          loadColumn(column);
        });
      }
    }
    columns.forEach(loadColumn);
  }
  return {update};
}
