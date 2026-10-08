// Pure URL validation and GitHub issue handoff; no credentials on Pages.
export const REQUEST_MARKER = "<!-- sparkles-diamond-ingest/v1 -->";
export const REQUEST_TITLE = "Ingest diamond";

export function normalizeListingUrl(input) {
  if (typeof input !== "string" || !input.trim() || input.length > 2048) {
    throw new Error("Paste one supported diamond listing URL.");
  }
  const trimmed = input.trim();
  if (/[^\x20-\x7e]/.test(trimmed)) {
    throw new Error("The listing URL contains unsupported characters.");
  }
  let url;
  try { url = new URL(trimmed); }
  catch { throw new Error("Enter a valid HTTPS listing URL."); }
  if (url.protocol !== "https:" || url.username || url.password || url.port || url.hash) {
    throw new Error("Use the original HTTPS retailer listing link, without credentials or fragments.");
  }
  const keys = [...url.searchParams.keys()];
  const host = url.hostname.toLowerCase();
  if (["diyona.com", "www.diyona.com"].includes(host) &&
      url.pathname.replace(/\/$/, "") === "/pages/diamond-detail" &&
      keys.length === 1 && keys[0] === "sku" &&
      /^[a-z0-9_-]+$/i.test(url.searchParams.get("sku") || "")) {
    return url.href;
  }
  if (["qualitydiamonds.co.uk", "www.qualitydiamonds.co.uk"].includes(host) &&
      url.pathname.replace(/\/$/, "") === "/loose-diamonds/buy-loose-diamonds" &&
      keys.length === 1 && keys[0] === "d" &&
      /^[0-9]+\/[a-z0-9]+$/i.test(url.searchParams.get("d") || "")) {
    return url.href;
  }
  throw new Error("Only exact Quality Diamonds or Diyona diamond listing URLs are currently supported.");
}

export function createIngestionIssueUrl(listingUrl) {
  const exactUrl = normalizeListingUrl(listingUrl);
  const issue = new URL("https://github.com/choonkiatlee/sparkles/issues/new");
  issue.searchParams.set("title", REQUEST_TITLE);
  issue.searchParams.set("body", REQUEST_MARKER + "\nDiamond URL: " + exactUrl + "\n");
  return issue.href;
}
