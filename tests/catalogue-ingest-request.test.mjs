import test from "node:test";
import assert from "node:assert/strict";

import { REQUEST_MARKER, REQUEST_TITLE, normalizeListingUrl,
  createIngestionIssueUrl } from "../catalogue/ingest-request.mjs";

const quality = "https://www.qualitydiamonds.co.uk/loose-diamonds/buy-loose-diamonds?d=133/CE7EED747";
const diyona = "https://diyona.com/pages/diamond-detail?sku=B934F4533";

test("exact supported retailer URLs create a prefilled owner-confirmed issue", () => {
  for (const url of [quality, diyona, quality.replace("133/","133%2F")]) {
    const link = new URL(createIngestionIssueUrl(url));
    assert.equal(link.origin, "https://github.com");
    assert.equal(link.pathname, "/choonkiatlee/sparkles/issues/new");
    assert.equal(link.searchParams.get("title"), REQUEST_TITLE);
    assert.equal(link.searchParams.get("body"),
      REQUEST_MARKER + "\nDiamond URL: " + normalizeListingUrl(url) + "\n");
  }
});

test("valid listing IDs must be exact, without arbitrary query parameters", () => {
  const rejected = [
    "http://diyona.com/pages/diamond-detail?sku=B934F4533",
    "https://diyona.com/pages/diamond-detail",
    "https://diyona.com/pages/diamond-detail?sku=../other",
    "https://www.qualitydiamonds.co.uk/loose-diamonds/buy-loose-diamonds?d=133",
    quality + "&not_an_exact_listing=1",
    quality + "#abc",
    quality.replace("qualitydiamonds.co.uk", "qualitydiamonds.co.uk.attacker.test"),
    quality.replace("https://", "https://bob:password@"),
    quality.replace("https://www.", "https://www.") + "\nInjected: true",
    "javascript:alert(1)",
  ];
  for (const input of rejected) {
    assert.throws(() => createIngestionIssueUrl(input), Error, input);
  }
});

test("whitespace around an exact pasted listing can be trimmed", () => {
  assert.equal(normalizeListingUrl("  " + diyona + "  "), diyona);
});
