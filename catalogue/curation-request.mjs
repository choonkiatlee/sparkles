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
export function createCurationIssueUrl(published,draft,validIds) {
  if(draftCount(draft)===0) throw new Error("No unsaved changes");
  const changes=curationChanges(published,draft,validIds);
  const issue=new URL("https://github.com/choonkiatlee/sparkles/issues/new");
  issue.searchParams.set("title",CURATION_REQUEST_TITLE);
  issue.searchParams.set("body",CURATION_REQUEST_MARKER+"\n"+JSON.stringify({
    schema:CURATION_REQUEST_SCHEMA,changes
  })+"\n");
  return issue.href;
}
