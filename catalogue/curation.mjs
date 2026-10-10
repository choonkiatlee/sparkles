// Owner curation is separate from certified evidence and its generated index.
// The published Git JSON is authoritative; sparse browser drafts are unsynced.
export const CURATION_SCHEMA = "sparkles-diamond-curation/1";
export const DRAFT_SCHEMA = "sparkles-diamond-curation-draft/1";
export const DRAFT_STORAGE_KEY = "sparkles-diamond-curation-draft-v1";
const FIELDS = ["starred", "archived"];
const identifier = id => typeof id === "string" && /^[a-z0-9][a-z0-9-]*$/.test(id);
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

function checkMap(data, schema, validIds) {
  if (!data || typeof data !== "object" || Array.isArray(data) ||
      data.schema !== schema || !data.diamonds ||
      typeof data.diamonds !== "object" || Array.isArray(data.diamonds) ||
      Object.keys(data).some(k => k !== "schema" && k !== "diamonds")) {
    throw new Error("Invalid diamond curation document");
  }
  const diamonds = Object.create(null);
  for (const [id, flags] of Object.entries(data.diamonds)) {
    if (!identifier(id) || (validIds && !validIds.has(id)) ||
        !flags || typeof flags !== "object" || Array.isArray(flags)) {
      throw new Error("Unknown or invalid personal diamond curation ID");
    }
    const fields = Object.keys(flags);
    if (!fields.length || fields.some(field => !FIELDS.includes(field))) {
      throw new Error("Invalid curation flags");
    }
    diamonds[id] = {};
    for (const field of fields) {
      if (typeof flags[field] !== "boolean") throw new Error("Curation flags must be booleans");
      diamonds[id][field] = flags[field];
    }
  }
  return {schema, diamonds};
}
export const emptyCuration = () => ({schema:CURATION_SCHEMA,diamonds:Object.create(null)});
export const emptyDraft = () => ({schema:DRAFT_SCHEMA,diamonds:Object.create(null)});
export const validateCuration = (value, validIds) => checkMap(value, CURATION_SCHEMA, validIds);
export const validateDraft = (value, validIds) => checkMap(value, DRAFT_SCHEMA, validIds);

export function flagsFor(published, draft, id) {
  const base = published.diamonds[id] || {};
  const pending = draft.diamonds[id] || {};
  return {starred:own(pending,"starred") ? pending.starred : (base.starred || false),
          archived:own(pending,"archived") ? pending.archived : (base.archived || false)};
}

export function setDraftFlag(published, draft, id, field, value, validIds) {
  if (!FIELDS.includes(field) || typeof value !== "boolean" ||
      !identifier(id) || !validIds.has(id)) throw new Error("Invalid curation change");
  const diamonds = Object.assign(Object.create(null),draft.diamonds);
  const next = {...(diamonds[id] || {})};
  const baseline = published.diamonds[id]?.[field] || false;
  if (value === baseline) delete next[field];
  else next[field] = value;
  if (Object.keys(next).length) diamonds[id] = next;
  else delete diamonds[id];
  return {schema:DRAFT_SCHEMA,diamonds};
}

export function reconcileDraft(published, draft, validIds) {
  let out = emptyDraft();
  for (const [id, fields] of Object.entries(draft.diamonds)) {
    if (!validIds.has(id)) continue;
    for (const [field, value] of Object.entries(fields)) {
      out = setDraftFlag(published,out,id,field,value,validIds);
    }
  }
  return out;
}
export const draftCount = draft => Object.values(draft.diamonds)
  .reduce((n,flags)=>n+Object.keys(flags).length,0);
export const archivedCount = (rows,published,draft) => rows
  .filter(row=>flagsFor(published,draft,row.id).archived).length;

// Filtering is presentation only. Never remove archived IDs from the shared basket.
export function curationRows(sortedRows,{showArchived=false,shortlistOnly=false}={},published,draft) {
  return sortedRows.filter(row=>{
    const flags=flagsFor(published,draft,row.id);
    return (showArchived || !flags.archived) && (!shortlistOnly || flags.starred);
  });
}
