import test from "node:test";
import assert from "node:assert/strict";

import { createIngestionIssueUrl } from "../catalogue/ingest-request.mjs";

test("ingestion opens a safe new tab without leaving the catalogue", async () => {
  const originalDocument = globalThis.document;
  const originalWindow = globalThis.window;
  const listeners = new Map();
  const opened = [];
  let focused = false;

  const form = { addEventListener: (name, callback) => listeners.set("form:" + name, callback) };
  const input = {
    value: "133/CE7EED747",
    addEventListener: (name, callback) => listeners.set("input:" + name, callback),
    focus: () => { focused = true; },
  };
  const error = { hidden: true, textContent: "" };
  const preview = { hidden: true, textContent: "" };
  const elements = {
    "add-diamond-form": form,
    "diamond-request-url": input,
    "diamond-request-error": error,
    "diamond-request-preview": preview,
  };

  globalThis.document = { getElementById: id => elements[id] };
  globalThis.window = {
    open: (...args) => opened.push(args),
    location: { assign: () => { throw new Error("Must not leave the catalogue"); } },
  };

  try {
    await import("../catalogue/ingest-request-form.mjs");
    listeners.get("input:input")();
    assert.match(preview.textContent, /qualitydiamonds.co.uk/);

    let prevented = false;
    listeners.get("form:submit")({ preventDefault: () => { prevented = true; } });
    assert.equal(prevented, true);
    assert.deepEqual(opened, [[
      createIngestionIssueUrl(input.value), "_blank", "noopener,noreferrer",
    ]]);
    assert.equal(error.hidden, true);

    input.value = "https://example.com/diamond";
    listeners.get("form:submit")({ preventDefault: () => {} });
    assert.equal(opened.length, 1, "Invalid requests never open a tab");
    assert.equal(error.hidden, false);
    assert.match(error.textContent, /Only exact Quality Diamonds or Diyona/);
    assert.equal(focused, true);
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
  }
});
