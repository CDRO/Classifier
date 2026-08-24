const STORAGE_KEY = "classifier.destinees";
const DEFAULT_DESTINEES = ["Destinee A", "Destinee B", "Destinee C"];
const SOURCE_PATH = window.CLASSIFIER_CONFIG?.sourcePath || "/data/source";
const DESTINATION_PATH = window.CLASSIFIER_CONFIG?.destinationPath || "/data/destination";
const API_BASE_URL = window.CLASSIFIER_CONFIG?.apiBaseUrl || "";
const list = document.querySelector("#destinee-list");
const folderList = document.querySelector("#folder-list");
const count = document.querySelector("#count");
const error = document.querySelector("#form-error");
const inboxList = document.querySelector("#inbox-list");
const inboxStatus = document.querySelector("#inbox-status");
const reviewPanel = document.querySelector("#review-panel");
const reviewStatus = document.querySelector("#review-status");
const documentPreview = document.querySelector("#document-preview");
const pageSummary = document.querySelector("#page-summary");
const reviewDestinee = document.querySelector("#review-destinee");
const pageText = document.querySelector("#page-text");
const finalizeButton = document.querySelector("#finalize-document");
const finalizeStatus = document.querySelector("#finalize-status");
let selectedDocument = null;

function loadDestinees() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return Array.isArray(saved) && saved.length ? saved : [...DEFAULT_DESTINEES];
  } catch {
    return [...DEFAULT_DESTINEES];
  }
}

function render(destinees) {
  list.replaceChildren();
  folderList.replaceChildren();
  count.textContent = `${destinees.length} configured`;

  destinees.forEach((destinee, index) => {
    const row = document.createElement("div");
    row.className = "destinee-row";
    row.innerHTML = `
      <span class="row-number">${String(index + 1).padStart(2, "0")}</span>
      <input class="destinee-input" type="text" maxlength="80" value="${escapeHtml(destinee)}" aria-label="Destinee ${index + 1}">
      <button class="remove-button" type="button" aria-label="Remove destinee ${escapeHtml(destinee)}">&times;</button>`;
    row.querySelector(".remove-button").addEventListener("click", () => {
      const next = readRows().filter((_, rowIndex) => rowIndex !== index);
      render(next);
    });
    list.append(row);

    const folder = document.createElement("div");
    folder.className = "folder-item";
    folder.innerHTML = `<strong>${escapeHtml(destinee)}</strong><small>${escapeHtml(DESTINATION_PATH)}/${escapeHtml(destinee)}/</small>`;
    folderList.append(folder);
  });
}

function readRows() {
  return [...document.querySelectorAll(".destinee-input")].map((input) => input.value.trim());
}

function escapeHtml(value) {
  return value.replace(/[&<>"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[character]));
}

function renderInbox(files) {
  inboxList.replaceChildren();
  inboxStatus.textContent = files.length
    ? `${files.length} completed PDF${files.length === 1 ? "" : "s"} waiting for classification.`
    : "No completed PDFs are waiting for classification.";
  files.forEach((file) => {
    const item = document.createElement("div");
    item.className = "inbox-item";
    item.innerHTML = `<button class="inbox-document" type="button"><strong>${escapeHtml(file.name)}</strong><small>${formatBytes(file.size)} · ready in n8n input</small></button><span class="file-state">READY</span>`;
    item.querySelector(".inbox-document").addEventListener("click", () => inspectDocument(file.name));
    inboxList.append(item);
  });
}

async function inspectDocument(filename) {
  inboxStatus.textContent = `Loading ${filename}...`;
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(filename)}/prepare`, { method: "POST" });
    if (!response.ok) throw new Error("Document lookup failed");
    const preparedDocument = await response.json();
    selectedDocument = { filename, processingId: preparedDocument.processing_id };
    reviewPanel.hidden = false;
    reviewStatus.textContent = preparedDocument.original_name;
    documentPreview.src = `${API_BASE_URL}/api/documents/${encodeURIComponent(filename)}/file`;
    pageSummary.textContent = `${preparedDocument.page_count} page${preparedDocument.page_count === 1 ? "" : "s"} prepared for review.`;
    pageText.replaceChildren();
    preparedDocument.pages.forEach((page) => {
      const block = document.createElement("article");
      block.className = "page-text-block";
      block.innerHTML = `<strong>Page ${page.page}</strong><p>${escapeHtml(page.text || "No text extracted.")}</p>`;
      pageText.append(block);
    });
    const configResponse = await fetch(`${API_BASE_URL}/api/classification/config`);
    const config = await configResponse.json();
    reviewDestinee.replaceChildren();
    config.destinees.forEach((destinee) => {
      const option = document.createElement("option");
      option.value = destinee;
      option.textContent = destinee;
      reviewDestinee.append(option);
    });
    finalizeButton.disabled = false;
    finalizeStatus.textContent = "";
    inboxStatus.textContent = `${preparedDocument.original_name} is ready for destinee review.`;
    reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch {
    inboxStatus.textContent = "The document could not be loaded from the n8n input directory.";
  }
}

finalizeButton.addEventListener("click", async () => {
  if (!selectedDocument || !reviewDestinee.value) return;
  finalizeButton.disabled = true;
  finalizeStatus.textContent = "Finalizing...";
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(selectedDocument.filename)}/finalize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ processing_id: selectedDocument.processingId, destinee: reviewDestinee.value })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Finalization failed");
    finalizeStatus.textContent = `Classified for ${result.destinee}.`;
    finalizeButton.textContent = "Finalized";
  } catch (finalizeError) {
    finalizeStatus.textContent = finalizeError.message;
    finalizeButton.disabled = false;
  }
});

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function refreshInbox() {
  inboxStatus.textContent = "Checking for completed PDFs...";
  try {
    const response = await fetch(`${API_BASE_URL}/api/classification/scan`, { method: "POST" });
    if (!response.ok) throw new Error("Scan failed");
    const result = await response.json();
    renderInbox(result.files);
  } catch {
    inboxList.replaceChildren();
    inboxStatus.textContent = "The n8n input directory is not reachable yet.";
  }
}

document.querySelector("#add-destinee").addEventListener("click", () => {
  const next = readRows();
  next.push("");
  render(next);
  list.lastElementChild.querySelector("input").focus();
});

document.querySelector("#refresh-inbox").addEventListener("click", refreshInbox);

document.querySelector("#destinee-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const destinees = readRows();
  const normalized = destinees.map((value) => value.toLocaleLowerCase());
  if (destinees.some((value) => !value)) {
    error.textContent = "Every destinee needs a name.";
    return;
  }
  if (new Set(normalized).size !== normalized.length) {
    error.textContent = "Destinee names must be unique.";
    return;
  }
  try {
    const response = await fetch(`${API_BASE_URL}/api/classification/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ destinees })
    });
    if (!response.ok) throw new Error("API request failed");
    localStorage.setItem(STORAGE_KEY, JSON.stringify(destinees));
    error.textContent = "Configuration saved.";
  } catch {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(destinees));
    error.textContent = "Saved locally. The API is not reachable yet.";
  }
  render(destinees);
});

async function initialize() {
  let destinees = loadDestinees();
  try {
    const response = await fetch(`${API_BASE_URL}/api/classification/config`);
    if (response.ok) {
      const config = await response.json();
      destinees = config.destinees;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(destinees));
    }
  } catch {
    // Static-only mode uses the local fallback until the API is running.
  }
  render(destinees);
}

initialize();
refreshInbox();

document.querySelector("[data-source-path]").textContent = SOURCE_PATH;
document.querySelector("[data-destination-path]").textContent = `${DESTINATION_PATH}/`;
document.querySelector("[data-preview-root]").textContent = `${DESTINATION_PATH}/`;
