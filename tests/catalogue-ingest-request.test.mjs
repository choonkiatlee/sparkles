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

test("one field expands Diyona SKU or full Quality Diamonds ID into exact listing URLs", () => {
  const examples = [
    ["268F4881D", "https://diyona.com/pages/diamond-detail?sku=268F4881D"],
    ["B934F4533", diyona],
    ["133/CE7EED747", quality],
    ["133/9155264EA", "https://www.qualitydiamonds.co.uk/loose-diamonds/buy-loose-diamonds?d=133/9155264EA"],
  ];
  for (const [id, expected] of examples) {
    assert.equal(normalizeListingUrl(id), expected, id);
    assert.equal(normalizeListingUrl("  " + id + "  "), expected, "trim " + id);
    const issue = new URL(createIngestionIssueUrl(id));
    assert.equal(issue.searchParams.get("body"), REQUEST_MARKER + "\nDiamond URL: " + expected + "\n", id);
  }
});

test("a bare unqualified ID is Diyona, never a guessed Quality Diamonds numeric prefix", () => {
  // Both retailers have similarly shaped 9-character hex IDs.
  // A Quality Diamonds request MUST include its 133/… (or other) prefix.
  assert.equal(normalizeListingUrl("CE7EED747"),
    "https://diyona.com/pages/diamond-detail?sku=CE7EED747");
});

test("bare ID injection, fragment and incomplete Quality Diamonds IDs are rejected", () => {
  for (const value of [
    "133/", "/CE7EED747", "133/CE7EED747/extra",
    "133/CE7EED747?x=1", "133/CE7EED747#fragment",
    "268F4881D\nDiamond URL: https://example.com",
    "268F4881D&extra=1", "sku=268F4881D",
    "CE7EED747.example.com", "133\\CE7EED747",
  ]) {
    assert.throws(() => createIngestionIssueUrl(value), Error, value);
  }
});
