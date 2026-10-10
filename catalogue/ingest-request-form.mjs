import { createIngestionIssueUrl, normalizeListingUrl } from "./ingest-request.mjs";

const form = document.getElementById("add-diamond-form");
const urlInput = document.getElementById("diamond-request-url");
const error = document.getElementById("diamond-request-error");
const preview = document.getElementById("diamond-request-preview");

if (form && urlInput && error) {
  urlInput.addEventListener("input", () => {
    error.hidden = true;
    error.textContent = "";
    if (!preview) return;
    try {
      const url = normalizeListingUrl(urlInput.value);
      preview.textContent = "Will request: " + url;
      preview.hidden = false;
    } catch {
      preview.textContent = "";
      preview.hidden = true;
    }
  });
  form.addEventListener("submit", event => {
    event.preventDefault();
    try {
      window.open(createIngestionIssueUrl(urlInput.value), "_blank", "noopener,noreferrer");
    } catch (exception) {
      error.textContent = exception.message;
      error.hidden = false;
      urlInput.focus();
    }
  });
}
