// Manifest-backed C2 comparison and C3a selected-only ordinal 360 viewer.
import { comparisonRows, createManifestLoader, projectComparison,
  publicUrl, dateText } from "./compare.mjs";
import { displayValue, priceText } from "./core.mjs";
import { DEFAULT_PREFETCH_MODE, normalPosition, frameAt, extractRotation,
  motionUnavailable, prefetchURLs, createPrefetchQueue, preloadImage } from "./rotation.mjs";

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
  const head = column.head;
  head.replaceChildren();
  const picture = el("div","compare-picture");
  if (projected.representative) {
    const img = el("img");
    img.src = projected.representative.url;
    img.alt = projected.representative.label + " for " + projected.report + "; angle not calibrated";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("error",()=>picture.replaceChildren(
      el("span","photo-empty","Published image unavailable")));
    picture.append(img);
  } else picture.append(el("span","photo-empty","No published still or validated rotation"));
  head.append(picture, el("strong","compare-report",projected.lab + " " + projected.report));
  head.append(el("span","compare-source",displayValue(projected.currentListing.retailer)));
  head.append(el("small","compare-caption",
    projected.representative ? projected.representative.label+" · viewpoint uncalibrated" :
      "Evidence missing or video-only"));
  for (const [key] of comparisonRows)
    column.cells.get(key).textContent = projected.values[key];

  const certificateCell = column.cells.get("certificate");
  certificateCell.replaceChildren();
  if (projected.certificate) {
    appendLink(certificateCell,"Published original PDF ↗",projected.certificate.url);
  } else certificateCell.append(el("span","missing","Certificate PDF not recovered"));
  if (projected.verification) {
    if (projected.certificate) certificateCell.append(el("span","link-separator"," · "));
    appendLink(certificateCell,
      projected.certificate ? "Original certificate link ↗" : "Verification link only ↗",
      projected.verification);
  }
  const sourceCell = column.cells.get("source");
  sourceCell.replaceChildren();
  const latest = projected.currentListing;
  if (!appendLink(sourceCell,"Latest listing ↗", latest.url))
    sourceCell.append(el("span","missing","No usable listing link"));
  if (projected.listings.length > 1)
    sourceCell.append(el("span","subtle"," · "+projected.listings.length+" saved observations"));

  const provenanceCell = column.cells.get("provenance");
  provenanceCell.replaceChildren();
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
  column.head.replaceChildren(el("strong","compare-report",column.row.lab+" "+column.row.report_number));
  column.head.append(el("span","error-small","Could not load published manifest"));
  const button=el("button","retry-manifest","Retry");
  button.type="button";
  button.addEventListener("click",onRetry);
  column.head.append(button);
  for (const cell of column.cells.values()) cell.textContent="Unavailable";
  column.cells.get("provenance").textContent="Manifest unavailable: "+reason;
}

export function createComparisonView({container, grid, fetcher}) {
  // Playback never touches original C2 still images, provenance or index images.
  const prefetch=createPrefetchQueue(preloadImage);
  let position=0;
  let playing=false;
  let timer=null;
  let mode=DEFAULT_PREFETCH_MODE;
  let playerColumns=[];
  let controls=null;
  const counts=()=>playerColumns.map(c=>c.rotation?.count || 0).filter(Boolean);
  const hasPlayable=()=>counts().length>0;
  function stopPlayback() {
    if (timer !== null) clearInterval(timer);
    timer=null;
    playing=false;
    if (controls) {
      controls.play.textContent="Play";
      controls.play.setAttribute("aria-pressed","false");
    }
  }
  function updateFrames() {
    for (const col of playerColumns) {
      if (!col.rotation || !col.player) continue;
      const frame=frameAt(col.rotation,position);
      if (!frame) continue;
      if (col.player.img.dataset.url !== frame.url) {
        col.player.img.dataset.url=frame.url;
        col.player.img.src=frame.url;
        col.player.img.hidden=false;
      }
      col.player.status.textContent="Frame "+(frame.index+1)+" / "+frame.count+
        " · source "+frame.sourceIndex+" · relative position";
      prefetch.enqueue(prefetchURLs(col.rotation,position,mode));
    }
    if (controls) {
      controls.scrub.value=String(Math.floor(position*1000));
      controls.position.textContent=Math.round(position*100)+"% of rotation";
      controls.play.disabled=!hasPlayable();
      controls.previous.disabled=!hasPlayable();
      controls.next.disabled=!hasPlayable();
    }
  }
  function seek(value) {
    position=normalPosition(value);
    updateFrames();
  }
  function createToolbar() {
    const toolbar=el("div","rotation-toolbar");
    toolbar.setAttribute("role","group");
    toolbar.setAttribute("aria-label","Shared synchronized ordinal 360 rotation controls");
    const main=el("div","rotation-main-controls");
    const previous=el("button","rotation-step","← Frame");
    previous.type="button";
    const play=el("button","rotation-play","Play");
    play.type="button"; play.setAttribute("aria-pressed","false");
    const next=el("button","rotation-step","Frame →");
    next.type="button";
    const scrub=el("input","rotation-scrub");
    scrub.type="range";scrub.min="0";scrub.max="999";scrub.step="1";scrub.value="0";
    scrub.setAttribute("aria-label","Synchronized ordinal rotation position");
    const progress=el("output","rotation-position","0% of rotation");
    progress.setAttribute("aria-live","off");
    previous.addEventListener("click",()=>seek(position-1/Math.max(...counts(),1)));
    next.addEventListener("click",()=>seek(position+1/Math.max(...counts(),1)));
    scrub.addEventListener("input",()=>seek(Number(scrub.value)/1000));
    play.addEventListener("click",()=>{
      if (playing) {stopPlayback();return;}
      if (!hasPlayable()) return;
      playing=true;
      play.textContent="Pause";play.setAttribute("aria-pressed","true");
      // The rate is deliberately time-based/ordinal, not supplier viewing degrees.
      timer=setInterval(()=>seek(position+1/120),125);
    });
    previous.disabled=true;play.disabled=true;next.disabled=true;
    main.append(previous,play,next,scrub,progress);
    const extras=el("div","rotation-extras");
    const label=el("label","rotation-preload");
    const checkbox=el("input");
    checkbox.type="checkbox";
    checkbox.checked=mode==="all";
    checkbox.addEventListener("change",()=>{
      mode=checkbox.checked?"all":"nearby";
      prefetch.stop();
      updateFrames();
    });
    label.append(checkbox,el("span","","Prefetch every frame (more data)"));
    extras.append(label,el("span","rotation-caveat",
      "OFF by default · frames synchronized by relative sequence position, not calibrated angle."));
    toolbar.append(main,extras);
    controls={previous,play,next,scrub,position:progress};
    return toolbar;
  }
  function renderMotion(col,projected) {
    const cell=col.cells.get("rotation");
    cell.replaceChildren();
    const rotation=extractRotation(projected.evidence);
    col.rotation=rotation;
    if (!rotation) {
      const fallback=el("div","rotation-unavailable",motionUnavailable(projected.evidence));
      cell.append(fallback);
      const video=projected.evidence.find(e=>e?.kind==="video" && e.status==="success");
      if (video) appendLink(cell,"Original video ↗",video.payload_asset?.storage?.url);
      return;
    }
    const picture=el("div","rotation-picture");
    const image=el("img");
    image.alt="Original ordered rotation of "+projected.report+"; frame positions are not angle calibrated";
    image.decoding="async";
    image.loading="eager";
    const status=el("small","rotation-frame-label","");
    const retry=el("button","rotation-retry","Retry frame");
    retry.type="button";retry.hidden=true;
    retry.addEventListener("click",()=>{
      retry.hidden=true;
      const url=image.dataset.url;
      image.removeAttribute("src");
      // An explicit click retries the image even if the shared playhead didn't move.
      image.src=url;
    });
    image.addEventListener("load",()=>{ retry.hidden=true; });
    image.addEventListener("error",()=>{
      retry.hidden=false;
      status.textContent="Frame unavailable · seek another position or retry";
    });
    picture.append(image);
    cell.append(picture,status,retry);
    col.player={img:image,status,retry};
    updateFrames();
  }
  const load = createManifestLoader(fetcher);
  let signature = "";
  let generation=0;
  function update(rows,selected,comparing) {
    const show = comparing && selected.length >= 2;
    container.hidden=!show;
    const nextSignature = show ? selected.join(",") : "";
    if (signature===nextSignature) return;
    stopPlayback();
    prefetch.stop();
    position=0;
    mode=DEFAULT_PREFETCH_MODE;
    playerColumns=[];
    controls=null;
    signature=nextSignature;
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
      th.append(el("strong","compare-report",row.lab+" "+row.report_number));
      th.append(el("span","subtle","Loading saved evidence…"));
      first.append(th);
      return {row,head:th,cells:new Map()};
    });
    thead.append(first); table.append(thead);
    const tbody=el("tbody");
    const fieldRows=[
      ["rotation","360 rotation"],...comparisonRows,["certificate","Certificate"],["source","Source listings"],
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
    playerColumns=columns;
    grid.append(createToolbar(),outer);
    async function loadColumn(column) {
      column.head.append(el("span","sr-only","Loading manifest"));
      try {
        const data = projectComparison(column.row,await load(column.row));
        if (generation !== currentGeneration) return;
        fillColumn(column,data);
        renderMotion(column,data);
      } catch(error) {
        if (generation !== currentGeneration) return;
        column.rotation=null;
        column.player=null;
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
