import { createIngestionIssueUrl } from "./ingest-request.mjs";

const form = document.getElementById("add-diamond-form");
const urlInput = document.getElementById("diamond-request-url");
const error = document.getElementById("diamond-request-error");

if (form && urlInput && error) {
  urlInput.addEventListener("input", () => {
    error.hidden = true;
    error.textContent = "";
  });
  form.addEventListener("submit", event => {
    event.preventDefault();
    try {
      window.location.assign(createIngestionIssueUrl(urlInput.value));
    } catch (exception) {
      error.textContent = exception.message;
      error.hidden = false;
      urlInput.focus();
    }
  });
}
