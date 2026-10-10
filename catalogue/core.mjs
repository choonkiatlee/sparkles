// Pure, dependency-free catalogue view logic. No GitHub API or network calls.
// Allow every example in the largest curated learning segments to share one basket.
export const MAX_SELECTION = 10;
export const MIN_COMPARISON = 2;
const string = value => value == null ? "" : String(value).trim();
const numeric = value => value == null || string(value) === "" ? null : Number(value);
export const priceText = row => {
  const amount = numeric(row.price);
  if (amount === null || !Number.isFinite(amount)) return "Price unavailable";
  const currency = string(row.currency).toUpperCase();
  if (!/^[A-Z]{3}$/.test(currency)) return amount.toFixed(2) + (currency ? " " + currency : " (currency unknown)");
  try { return new Intl.NumberFormat("en-GB", { style:"currency", currency }).format(amount); }
  catch { return amount.toFixed(2) + " " + currency; }
};
export const dimensionsText = row => Array.isArray(row.dimensions) && row.dimensions.length >= 2
  ? row.dimensions.map(x => x == null ? "?" : String(x)).join(" × ") + " mm" : "Unknown";
export const displayValue = value => value == null || String(value).trim() === "" ? "Unknown" : String(value);
export function validateIndex(index) {
  if (!index || index.schema !== "sparkles-diamond-index/1" || !Array.isArray(index.diamonds)) {
    throw new Error("Unsupported catalogue index format");
  }
  const ids = new Set();
  for (const row of index.diamonds) {
    if (!row || !/^[a-z0-9][a-z0-9-]*$/.test(row.id) || ids.has(row.id)) throw new Error("Invalid or duplicate diamond ID");
    ids.add(row.id);
  }
  return index.diamonds;
}
// Common colour/clarity grade order; non-standard or missing grades sort last.
const COLOUR_GRADES = "D E F G H I J K L M N O P Q R S T U V W X Y Z".split(" ");
const CLARITY_GRADES = ["FL","IF","VVS1","VVS2","VS1","VS2","SI1","SI2","I1","I2","I3"];
export const gradeOrder = (value, grades) => {
  const pos = grades.indexOf(String(value ?? "").trim().toUpperCase());
  return pos < 0 ? grades.length : pos;
};
export function visibleRows(rows, { search="", status="all", sort="report" }={}) {
  const needle = string(search).toLowerCase();
  const filtered = rows.filter(row => {
    if (status !== "all" && row.retrieval_status !== status) return false;
    return [row.id, row.report_number, row.lab, row.retailer, row.shape, row.carat,
      row.colour, row.clarity, row.source_url].some(v => string(v).toLowerCase().includes(needle));
  });
  return [...filtered].sort((a,b) => {
    let comparison = 0;
    if (sort === "carat") {
      const x = numeric(a.carat), y = numeric(b.carat);
      comparison = x === null ? (y === null ? 0 : 1) : y === null ? -1 : x-y;
    } else if (sort === "colour" || sort === "clarity") {
      const grades = sort === "colour" ? COLOUR_GRADES : CLARITY_GRADES;
      comparison = gradeOrder(a[sort], grades) - gradeOrder(b[sort], grades);
    } else if (sort === "price") {
      // Price comparisons are valid only within a currency. Group by currency first.
      comparison = string(a.currency).localeCompare(string(b.currency));
      if (!comparison) {
        const x = numeric(a.price), y = numeric(b.price);
        comparison = x === null ? (y === null ? 0 : 1) : y === null ? -1 : x-y;
      }
    } else {
      comparison = string(a.report_number).localeCompare(string(b.report_number));
    }
    return comparison || a.id.localeCompare(b.id);
  });
}
export function selectionFromSearch(search, validIds) {
  const params = new URLSearchParams(search);
  const raw = (params.get("selected") || "").split(",");
  const output = [];
  for (const id of raw) if (validIds.has(id) && !output.includes(id) && output.length < MAX_SELECTION) output.push(id);
  return { selected: output, comparing: params.get("compare") === "1" && output.length >= MIN_COMPARISON };
}
export function toggleSelection(selected, id) {
  if (selected.includes(id)) return selected.filter(x => x !== id);
  return selected.length < MAX_SELECTION ? [...selected, id] : [...selected];
}
export function selectionSearch(search, selected, comparing=false) {
  const params = new URLSearchParams(search);
  params.delete("selected"); params.delete("compare");
  if (selected.length) params.set("selected", selected.join(","));
  if (comparing && selected.length >= MIN_COMPARISON) params.set("compare", "1");
  return params.toString();
}
