// Pure manifest-to-comparison projection. No DOM, network, or source API calls.
import { dimensionsText, priceText, displayValue } from "./core.mjs";
import { extractRotation } from "./rotation.mjs";

const ID = /^[a-z0-9][a-z0-9-]*$/;
const SCHEMA = "sparkles-diamond-catalogue/1";
const sortedByDate = (items, field) => [...items].sort((a,b) =>
  String(a?.[field] ?? "").localeCompare(String(b?.[field] ?? "")));
const field = v => displayValue(v);
export const publicUrl = value => {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch { return null; }
};
export const assetUrl = asset => publicUrl(asset?.storage?.url);

export function manifestURL(row) {
  if (!row || typeof row.id !== "string" || !ID.test(row.id) ||
      row.manifest_path !== "data/diamonds/" + row.id + ".json")
    throw new Error("Noncanonical diamond manifest path");
  return "../data/diamonds/" + row.id + ".json";
}
export function validateManifest(row, manifest) {
  manifestURL(row);
  if (!manifest || manifest.schema !== SCHEMA || manifest.id !== row.id ||
      manifest.identity?.lab !== row.lab ||
      manifest.identity?.report_number !== row.report_number ||
      !manifest.diamond_metadata || !Array.isArray(manifest.listings) ||
      !Array.isArray(manifest.retrievals) || !Array.isArray(manifest.evidence)) {
    throw new Error("Published manifest schema or certified identity mismatch");
  }
  return manifest;
}
// Memoize successful reads only. After a failure, a retry can fetch a fresh copy.
export function createManifestLoader(fetcher) {
  const cache = new Map();
  return function load(row) {
    const url = manifestURL(row);
    if (!cache.has(url)) {
      const read = Promise.resolve().then(async () => {
        const response = await fetcher(url, {cache:"no-cache"});
        if (!response.ok) throw new Error("Manifest request failed (HTTP " + response.status + ")");
        return validateManifest(row, await response.json());
      }).catch(error => { cache.delete(url); throw error; });
      cache.set(url, read);
    }
    return cache.get(url);
  };
}
export const dateText = raw => {
  if (!raw || !Number.isFinite(Date.parse(raw))) return "Unknown";
  return new Date(raw).toISOString().replace("T", " ").slice(0,16) + " UTC";
};
export const proportionText = (value, suffix="") =>
  value === null || value === undefined || value === "" ? "Unknown" : field(value) + suffix;

export function describeMotion(evidence) {
  const rotations = evidence.filter(e => e?.kind === "rotation");
  const valid = rotations.filter(e => e.status === "success" && Array.isArray(e.frames) &&
    e.frames.length > 0 && e.metadata?.sequence_complete === true &&
    e.frames.every(f => assetUrl(f?.asset)));
  if (valid.length) {
    const total = valid.map(e=>e.frames.length).join(", ");
    return valid.length + " validated sequence" + (valid.length===1?"":"s") +
      " (" + total + " frames); ordinal, not angle-calibrated";
  }
  if (evidence.some(e=>e?.kind==="video" && e.status==="success" && assetUrl(e.payload_asset)))
    return "Video available; no validated frame sequence";
  if (rotations.length) return "Rotation missing, failed or incomplete";
  return "No recovered rotation";
}
export function representativeAsset(evidence) {
  for (const kind of ["still","rotation"]) {
    for (const item of evidence) {
      if (item?.kind !== kind || item.status !== "success") continue;
      const asset = kind === "still" ? item.payload_asset :
        item.metadata?.sequence_complete === true ? item.frames?.[0]?.asset : null;
      const url = assetUrl(asset);
      if (url && asset?.media_type?.startsWith("image/")) {
        return { url, kind, label: kind === "still" ? "Published still" : "First ordered rotation frame" };
      }
    }
  }
  return null;
}
export function projectComparison(row, candidate) {
  const doc = validateManifest(row,candidate);
  const metadata = doc.diamond_metadata;
  const listings = sortedByDate(doc.listings,"observed_at");
  const retrievals = sortedByDate(doc.retrievals,"retrieved_at");
  const currentListing = listings.at(-1) || {};
  const currentRetrieval = retrievals.at(-1) || {};
  const evidence = doc.evidence;
  const pdf = evidence.find(e=>e?.kind==="certificate" && e.status==="success" &&
    e.payload_asset?.media_type==="application/pdf" && assetUrl(e.payload_asset));
  const certificate = pdf ? {label:"Published certificate PDF",url:assetUrl(pdf.payload_asset)} : null;
  const verification = publicUrl(currentRetrieval.certificate_link);
  const proportions = metadata.reported_proportions || {};
  const values = {
    carat: metadata.carat == null ? "Unknown" : field(metadata.carat) + " ct",
    colour:field(metadata.colour), clarity:field(metadata.clarity),
    shape:field(metadata.shape), origin:field(metadata.origin),
    dimensions:dimensionsText(metadata),
    depth:proportionText(proportions.depth_percent,"%"),
    table:proportionText(proportions.table_percent,"%"),
    lengthWidth:proportionText(proportions.length_width_ratio),
    polish:field(proportions.polish), symmetry:field(proportions.symmetry),
    fluorescence:field(proportions.fluorescence),
    price:priceText(currentListing), tax:field(currentListing.tax_basis),
    retrieval:field(currentRetrieval.status), motion:describeMotion(evidence),
  };
  return {
    id:doc.id, report:field(doc.identity.report_number), lab:field(doc.identity.lab),
    values, representative:representativeAsset(evidence), rotation:extractRotation(evidence),
    certificate, verification, certificateRecovered:Boolean(pdf),
    listings, retrievals, evidence, currentListing, currentRetrieval,
    latestAt:dateText(currentRetrieval.retrieved_at),
    reasons:Array.isArray(currentRetrieval.completion_reasons) ? currentRetrieval.completion_reasons : [],
  };
}
export const comparisonRows = [
  ["carat","Carat"],["colour","Colour"],["clarity","Clarity"],
  ["shape","Shape"],["origin","Origin"],["dimensions","Dimensions (mm)"],
  ["depth","Reported depth"],["table","Reported table"],["lengthWidth","L/W ratio"],
  ["polish","Polish"],["symmetry","Symmetry"],["fluorescence","Fluorescence"],
  ["price","Observed price"],["tax","Tax basis"],["retrieval","Retrieval status"],
  ["motion","Motion evidence"]
];
