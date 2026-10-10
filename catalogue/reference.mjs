// Read-only reference adapter. Curated opinions never masquerade as certified manifests.
import { dimensionsText, displayValue } from "./core.mjs";
import { describeMotion, representativeAsset, publicUrl, proportionText } from "./compare.mjs";
import { extractRotation } from "./rotation.mjs";

const ID = /^[a-z0-9][a-z0-9-]*$/;
const INDEX_SCHEMA = "sparkles-reference-index/1";
const SCHEMA = "sparkles-reference/1";

export function validateReferenceIndex(index) {
  if (!index || index.schema !== INDEX_SCHEMA || !Array.isArray(index.references))
    throw new Error("Unsupported reference index");
  const ids = new Set();
  return index.references.map(row => {
    if (!row || !ID.test(row.id) || row.id.startsWith("ref-") ||
        row.selection_id !== "ref-" + row.id ||
        row.manifest_path !== "data/references/" + row.id + ".json" ||
        ids.has(row.selection_id)) throw new Error("Invalid reference selection or manifest path");
    ids.add(row.selection_id);
    // Normalize just the in-memory selection key. The published index is unchanged.
    return {...row, kind:"reference", reference_id:row.id, id:row.selection_id};
  });
}

export function referenceManifestURL(row) {
  if (!row || row.kind !== "reference" || !ID.test(row.reference_id) ||
      row.id !== "ref-" + row.reference_id ||
      row.manifest_path !== "data/references/" + row.reference_id + ".json")
    throw new Error("Noncanonical reference manifest path");
  return "../data/references/" + row.reference_id + ".json";
}

export function validateReferenceManifest(row, doc) {
  referenceManifestURL(row);
  if (!doc || doc.schema !== SCHEMA || doc.id !== row.reference_id ||
      typeof doc.commentary !== "string" || !doc.commentary.trim() ||
      !doc.identity || !doc.diamond_metadata ||
      !Array.isArray(doc.source_links) || !doc.source_links.length ||
      !Array.isArray(doc.media_sources) || !Array.isArray(doc.evidence))
    throw new Error("Invalid reference manifest");
  return doc;
}

export function createReferenceManifestLoader(fetcher) {
  const cache = new Map();
  return async function load(row) {
    const url = referenceManifestURL(row);
    if (!cache.has(url)) {
      const pending = Promise.resolve().then(async () => {
        const response = await fetcher(url, {cache:"no-cache"});
        if (!response.ok) throw new Error("Reference request failed (HTTP " + response.status + ")");
        return validateReferenceManifest(row, await response.json());
      }).catch(error => {cache.delete(url); throw error;});
      cache.set(url, pending);
    }
    return cache.get(url);
  };
}

export function projectReferenceComparison(row, candidate) {
  const doc = validateReferenceManifest(row, candidate);
  const meta = doc.diamond_metadata;
  const p = meta.reported_proportions || {};
  const evidence = doc.evidence;
  const sources = doc.source_links.filter(s => publicUrl(s?.url));
  const externalViewers = doc.media_sources.filter(s => publicUrl(s?.url));
  return {
    id:row.id, kind:"reference", label:doc.label || row.label,
    lab:displayValue(doc.identity.lab), report:displayValue(doc.identity.report_number),
    identityStatus:doc.identity.status, commentary:doc.commentary,
    topics:doc.topics || [], sourceLinks:sources, mediaSources:externalViewers,
    representative:representativeAsset(evidence), rotation:extractRotation(evidence),
    evidence,
    values:{
      carat:meta.carat == null ? "Unknown" : meta.carat + " ct",
      colour:displayValue(meta.colour), clarity:displayValue(meta.clarity),
      shape:displayValue(meta.shape), origin:displayValue(meta.origin),
      dimensions:dimensionsText(meta),
      depth:proportionText(p.depth_percent, "%"),
      table:proportionText(p.table_percent, "%"),
      lengthWidth:proportionText(p.length_width_ratio),
      polish:displayValue(p.polish), symmetry:displayValue(p.symmetry),
      fluorescence:displayValue(p.fluorescence),
      price:"Not recorded", tax:"Not applicable",
      retrieval:"Reference · " + (evidence.length ? "saved evidence" : "external sources only"),
      motion:describeMotion(evidence),
    }
  };
}
