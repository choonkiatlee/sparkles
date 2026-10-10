// Token-free, owner-confirmed GitHub Issues handoff for sparse curation changes.
import {draftCount} from "./curation.mjs";
export const CURATION_REQUEST_SCHEMA="sparkles-diamond-curation-request/1";
export const CURATION_REQUEST_MARKER="<!-- sparkles-diamond-curation-request/v1 -->";
export const CURATION_REQUEST_TITLE="Save diamond curation";
export const MAX_REQUEST_CHANGES=20;

export function curationChanges(published,draft,validIds) {
  const changes=[];
  for(const id of Object.keys(draft.diamonds).sort()) {
    if(!validIds.has(id)) throw new Error("Unknown personal diamond");
    for(const field of ["archived","starred"]) {
      if(!Object.prototype.hasOwnProperty.call(draft.diamonds[id],field)) continue;
      const to=draft.diamonds[id][field];
      const from=published.diamonds[id]?.[field] || false;
      if(typeof to!=="boolean" || typeof from!=="boolean") throw new Error("Invalid curation state");
      if(from!==to) changes.push({id,field,from,to});
    }
  }
  if(!changes.length) throw new Error("No changes to save");
  if(changes.length>MAX_REQUEST_CHANGES) throw new Error("Save at most "+MAX_REQUEST_CHANGES+" changes per issue");
  return changes;
}
// A snapshot digest prevents an old browser tab from silently overwriting
// newer decisions, including an intervening true→false→true sequence.
export async function curationDigest(published) {
  const canonical=JSON.stringify(Object.keys(published.diamonds).sort().map(id=>[
    id,published.diamonds[id].starred===true,published.diamonds[id].archived===true
  ]));
  const raw=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(canonical));
  return [...new Uint8Array(raw)].map(n=>n.toString(16).padStart(2,"0")).join("");
}
export async function createCurationIssueUrl(published,draft,validIds) {
  if(draftCount(draft)===0) throw new Error("No unsaved changes");
  const changes=curationChanges(published,draft,validIds);
  const baseline_sha256=await curationDigest(published);
  const issue=new URL("https://github.com/choonkiatlee/sparkles/issues/new");
  issue.searchParams.set("title",CURATION_REQUEST_TITLE);
  issue.searchParams.set("body",CURATION_REQUEST_MARKER+"\n"+JSON.stringify({
    schema:CURATION_REQUEST_SCHEMA,baseline_sha256,changes
  })+"\n");
  return issue.href;
}

// Reserve a tab *synchronously* in the click handler before hashing the
// published snapshot asynchronously, avoiding popup blockers. Keep the
// catalogue (and unsaved browser draft) in the original tab.
export async function openCurationIssueInNewTab(published,draft,validIds,
  openTab=()=>window.open("about:blank","_blank")) {
  const tab=openTab();
  if(!tab) throw new Error("Your browser blocked the GitHub tab. Allow pop-ups for this site and retry.");
  try {
    tab.opener=null; // GitHub must not be able to reach the catalogue tab.
    const url=await createCurationIssueUrl(published,draft,validIds);
    tab.location.replace(url);
  } catch(error) {
    tab.close();
    throw error;
  }
}
