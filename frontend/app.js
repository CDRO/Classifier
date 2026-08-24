const STORAGE_KEY = "classifier.destinees";
const DEFAULT_DESTINEES = [];
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
const analysisProvider = document.querySelector("#analysis-provider");
const documentPreview = document.querySelector("#document-preview");
const previewLoader = document.querySelector("#document-preview-loader");
const pageSummary = document.querySelector("#page-summary");
const analysisSummary = document.querySelector("#analysis-summary");
const reviewDestinee = document.querySelector("#review-destinee");
const reviewFilename = document.querySelector("#review-filename");
const pageText = document.querySelector("#page-text");
const historyList = document.querySelector("#history-list");
const historyStatus = document.querySelector("#history-status");
const finalizeButton = document.querySelector("#finalize-document");
const finalizeStatus = document.querySelector("#finalize-status");
const splitBoundaries = document.querySelector("#split-boundaries");
const splitStatus = document.querySelector("#split-status");
const applySplitButton = document.querySelector("#apply-split");
const splitOutputs = document.querySelector("#split-outputs");
const finalizeSplitButton = document.querySelector("#finalize-split");
const appVersion = document.querySelector("#app-version");
const appRevision = document.querySelector("#app-revision");
const globalAnalysisStatus = document.querySelector("#global-analysis-status");
const reviewSourcePath = document.querySelector("#review-source-path");
const reviewOriginalFilename = document.querySelector("#review-original-filename");
const reviewDuplicateWarning = document.querySelector("#review-duplicate-warning");
const inboxSearch = document.querySelector("#inbox-search");
const inboxFolderFilter = document.querySelector("#inbox-folder-filter");
const inboxStatusFilter = document.querySelector("#inbox-status-filter");
const inboxDuplicateFilter = document.querySelector("#inbox-duplicate-filter");
const inboxSort = document.querySelector("#inbox-sort");
const historySearch = document.querySelector("#history-search");
const historyFolderFilter = document.querySelector("#history-folder-filter");
const historyStatusFilter = document.querySelector("#history-status-filter");
const historySort = document.querySelector("#history-sort");
let selectedDocument = null;
let configuredDestinees = [];
let splitParts = [];
let inboxFiles = [];
let historyDocuments = [];

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

function resetReviewPanelState() {
  selectedDocument = null;
  reviewFilename.value = "";
  analysisSummary.textContent = "";
  pageSummary.textContent = "";
  reviewDestinee.value = "";
  reviewDestinee.disabled = true;
  finalizeButton.disabled = true;
  finalizeStatus.textContent = "";
  reviewSourcePath.textContent = "—";
  reviewOriginalFilename.textContent = "—";
  reviewDuplicateWarning.textContent = "";
  reviewDuplicateWarning.hidden = true;
  splitBoundaries.replaceChildren();
  splitOutputs.replaceChildren();
  splitOutputs.hidden = true;
  finalizeSplitButton.hidden = true;
  splitStatus.textContent = "";
  pageText.replaceChildren();
  documentPreview.src = "about:blank";
  previewLoader.classList.add("visible");
}

function getStatusLabel(status) {
  return String(status || "received").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getInboxFilterOptions() {
  const statusOptions = ["all", "received", "duplicate", "in_review", "classified", "dismissed"];
  const sourceFolders = ["all", ...new Set(inboxFiles.map((file) => formatSourcePath(file.name).directory).filter(Boolean))];
  const duplicateOptions = ["all", "duplicate", "unique"];

  const populateSelect = (select, values, selectedValue) => {
    const current = selectedValue || select.value;
    select.replaceChildren();
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "all" ? "All" : value === "unique" ? "Unique" : value === "duplicate" ? "Duplicate" : value === "received" ? "Received" : value === "in_review" ? "In review" : value === "classified" ? "Classified" : value === "dismissed" ? "Dismissed" : value;
      if (value === current || (current === "" && value === "all")) {
        option.selected = true;
      }
      select.append(option);
    });
  };

  populateSelect(inboxFolderFilter, sourceFolders, inboxFolderFilter.value);
  populateSelect(inboxStatusFilter, statusOptions, inboxStatusFilter.value);
  populateSelect(inboxDuplicateFilter, duplicateOptions, inboxDuplicateFilter.value);
}

function getStatusPriority(status) {
  const priority = {
    duplicate: 0,
    received: 1,
    in_review: 2,
    classified: 3,
    dismissed: 4,
    failed: 5
  };
  return priority[String(status || "received")] ?? 99;
}

function sortDocuments(files, mode = "path") {
  const sortedFiles = [...files];
  sortedFiles.sort((left, right) => {
    const leftStatus = getStatusPriority(left.status || "received");
    const rightStatus = getStatusPriority(right.status || "received");
    const leftName = String(left.name || "").toLowerCase();
    const rightName = String(right.name || "").toLowerCase();

    if (mode === "duplicate") {
      const duplicateDifference = Number(Boolean(right.duplicate_of)) - Number(Boolean(left.duplicate_of));
      if (duplicateDifference !== 0) return duplicateDifference;
    }

    if (mode === "status") {
      const statusDifference = leftStatus - rightStatus;
      if (statusDifference !== 0) return statusDifference;
    }

    return leftName.localeCompare(rightName);
  });
  return sortedFiles;
}

function getVisibleInboxFiles() {
  const searchValue = inboxSearch?.value.trim().toLowerCase() || "";
  const folderValue = inboxFolderFilter?.value || "all";
  const statusValue = inboxStatusFilter?.value || "all";
  const duplicateValue = inboxDuplicateFilter?.value || "all";

  const filtered = inboxFiles.filter((file) => {
    const source = formatSourcePath(file.name);
    const statusText = (file.status || "received").toLowerCase();
    const duplicateText = String(file.duplicate_of || "").toLowerCase();
    const matchesSearch = !searchValue || [
      file.name,
      source.directory,
      source.basename,
      statusText,
      duplicateText,
      file.status || "received"
    ].some((value) => String(value).toLowerCase().includes(searchValue));
    const matchesFolder = folderValue === "all" || source.directory === folderValue || (folderValue === "root" && source.directory === "root") || (folderValue === "/data/source" && source.directory === "root");
    const matchesStatus = statusValue === "all" || (file.status || "received") === statusValue;
    const isDuplicate = Boolean(file.duplicate_of);
    const matchesDuplicate = duplicateValue === "all" || (duplicateValue === "duplicate" && isDuplicate) || (duplicateValue === "unique" && !isDuplicate);
    return matchesSearch && matchesFolder && matchesStatus && matchesDuplicate;
  });

  return sortDocuments(filtered, inboxSort?.value || "path");
}

function renderInbox(files) {
  const visibleFiles = getVisibleInboxFiles();
  inboxList.replaceChildren();
  inboxStatus.textContent = visibleFiles.length
    ? `${visibleFiles.length} completed PDF${visibleFiles.length === 1 ? "" : "s"} matching the current filter.`
    : "No completed PDFs match the current filter.";

  const sourceGroups = new Map();
  visibleFiles.forEach((file) => {
    const source = formatSourcePath(file.name);
    const directory = source.directory === "root" ? "/data/source" : `/data/source/${source.directory}`;
    if (!sourceGroups.has(directory)) {
      sourceGroups.set(directory, []);
    }
    sourceGroups.get(directory).push(file);
  });

  [...sourceGroups.entries()].sort(([left], [right]) => left.localeCompare(right)).forEach(([directory, groupedFiles]) => {
    const group = document.createElement("div");
    group.className = "source-group";
    const label = document.createElement("div");
    label.className = "source-group-header";
    label.innerHTML = `<span>${escapeHtml(directory)}</span><span class="source-group-count">${groupedFiles.length}</span>`;
    group.append(label);

    groupedFiles.forEach((file) => {
      const item = document.createElement("div");
      item.className = `inbox-item${selectedDocument && selectedDocument.filename === file.name ? " is-active" : ""}`;
      item.setAttribute("aria-current", selectedDocument && selectedDocument.filename === file.name ? "true" : "false");
      const duplicateNote = file.duplicate_of ? ` · duplicate of ${escapeHtml(file.duplicate_of)}` : "";
      const statusClass = file.duplicate_of ? "warning" : "good";
      const source = formatSourcePath(file.name);
      item.innerHTML = `<button class="inbox-document" type="button"><strong>${escapeHtml(source.basename)}</strong><small>Source: ${escapeHtml(directory)} · ${formatBytes(file.size)} · ready in n8n input${duplicateNote}</small></button><button class="dismiss-button" type="button" aria-label="Dismiss ${escapeHtml(file.name)}">Dismiss</button><span class="file-state file-state-${statusClass}">${escapeHtml((file.status || "received").replace("_", " ").toUpperCase())}</span>`;
      item.querySelector(".inbox-document").addEventListener("click", () => inspectDocument(file.name));
      item.querySelector(".dismiss-button").addEventListener("click", () => dismissDocument(file.name));
      group.append(item);
    });

    inboxList.append(group);
  });
}

async function dismissDocument(filename) {
  const reason = window.prompt("Optional reason for dismissing this document:", "");
  if (reason === null) return;
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(filename)}/dismiss`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Dismissal failed");
    reviewPanel.hidden = true;
    document.querySelector(".workflow-layout").classList.remove("review-active");
    inboxStatus.textContent = `${result.filename} was dismissed and archived.`;
    await refreshInbox();
    await refreshHistory();
  } catch (dismissError) {
    inboxStatus.textContent = dismissError.message;
  }
}

async function inspectDocument(filename) {
  resetReviewPanelState();
  reviewPanel.hidden = false;
  document.querySelector(".workflow-layout").classList.add("review-active");
  reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  reviewStatus.textContent = `Loading ${filename}...`;
  inboxStatus.textContent = `Loading ${filename}...`;
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(filename)}/prepare`, { method: "POST" });
    if (!response.ok) throw new Error("Document lookup failed");
    const preparedDocument = await response.json();
    const queuedDocument = inboxFiles.find((file) => file.name === filename) || null;
    selectedDocument = {
      filename,
      processingId: preparedDocument.processing_id,
      duplicateOf: queuedDocument?.duplicate_of || null,
      sourcePath: preparedDocument.source_path || filename,
      originalName: preparedDocument.original_name || preparedDocument.source_path?.split(/[\\/]/).pop() || filename
    };
    const source = formatSourcePath(selectedDocument.sourcePath || filename);
    reviewStatus.textContent = `${source.basename} · source: ${source.fullPath} · ${getQueueSummary(filename)}`;
    reviewFilename.value = preparedDocument.original_name;
    reviewSourcePath.textContent = selectedDocument.sourcePath.startsWith("/") ? `/data/source/${selectedDocument.sourcePath.replace(/^\//, "")}` : `/data/source/${selectedDocument.sourcePath}`;
    reviewOriginalFilename.textContent = preparedDocument.original_name;
    if (selectedDocument.duplicateOf) {
      reviewDuplicateWarning.hidden = false;
      reviewDuplicateWarning.textContent = `Duplicate warning: this file matches ${selectedDocument.duplicateOf}. Check the output target before finalizing.`;
    }
    documentPreview.src = `${API_BASE_URL}/api/processing/${encodeURIComponent(preparedDocument.processing_id)}/file`;
    pageSummary.textContent = `${preparedDocument.page_count} page${preparedDocument.page_count === 1 ? "" : "s"} prepared for review.`;
    const configResponse = await fetch(`${API_BASE_URL}/api/classification/config`);
    if (!configResponse.ok) throw new Error("Configuration lookup failed");
    const config = await configResponse.json();
    configuredDestinees = config.destinees;
    reviewDestinee.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Choose a destinee";
    placeholder.disabled = true;
    placeholder.selected = true;
    reviewDestinee.append(placeholder);
    config.destinees.forEach((destinee) => {
      const option = document.createElement("option");
      option.value = destinee;
      option.textContent = destinee;
      reviewDestinee.append(option);
    });
    reviewDestinee.disabled = false;
    analysisProvider.textContent = "Analysis provider: Gemini analyzing...";
    analysisProvider.className = "analysis-provider provider-gemini";
    analysisSummary.textContent = "Reading document content...";
    reviewFilename.value = "Analyzing filename suggestion...";
    const analysisResponse = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(filename)}/analyze?processing_id=${encodeURIComponent(preparedDocument.processing_id)}`, { method: "POST" });
    if (!analysisResponse.ok) throw new Error("Content analysis failed");
    const analysis = await analysisResponse.json();
    const party = analysis.party ? ` · ${analysis.party}` : "";
    const language = analysis.language && analysis.language !== "unknown" ? ` · ${analysis.language}` : "";
    const signals = analysis.signals?.length ? ` Signals: ${analysis.signals.join("; ")}.` : "";
    const entities = [
      analysis.amounts?.length ? `Amounts: ${analysis.amounts.join(", ")}` : "",
      analysis.reference_numbers?.length ? `References: ${analysis.reference_numbers.join(", ")}` : ""
    ].filter(Boolean).join(" · ");
    analysisSummary.textContent = `${analysis.category} · ${analysis.date}${language}${party} (${Math.round(analysis.confidence * 100)}% confidence): ${analysis.summary}${entities ? ` ${entities}.` : ""}${signals}`;
    analysisProvider.textContent = analysis.analysis_source === "gemini" ? "Analysis provider: Gemini" : "Analysis provider: Local fallback";
    analysisProvider.className = `analysis-provider ${analysis.analysis_source === "gemini" ? "provider-gemini" : "provider-local"}`;
    await loadAnalysisProvider();
    reviewFilename.value = analysis.suggested_filename;
    pageText.replaceChildren();
    splitBoundaries.replaceChildren();
    for (let page = 2; page <= preparedDocument.page_count; page += 1) {
      const label = document.createElement("label");
      label.className = "split-boundary";
      label.innerHTML = `<input type="checkbox" value="${page}"> page ${page}`;
      splitBoundaries.append(label);
    }
    preparedDocument.pages.forEach((page) => {
      const block = document.createElement("article");
      block.className = "page-text-block";
      const ocrLabel = page.ocr_used ? " · OCR" : "";
      block.innerHTML = `<img class="page-thumbnail" src="${API_BASE_URL}/api/processing/${encodeURIComponent(preparedDocument.processing_id)}/pages/${page.page}/thumbnail" alt="Page ${page.page} preview"><div class="page-text-heading"><strong>Page ${page.page}${ocrLabel}</strong><div class="rotation-controls"><button type="button" data-rotation="270" aria-label="Rotate page ${page.page} left">&#8634;</button><button type="button" data-rotation="90" aria-label="Rotate page ${page.page} right">&#8635;</button></div></div><p>${escapeHtml(page.text || "No text extracted.")}</p>`;
      block.querySelectorAll("[data-rotation]").forEach((button) => {
        button.addEventListener("click", () => rotatePage(page.page, Number(button.dataset.rotation)));
      });
      pageText.append(block);
    });
    finalizeButton.disabled = true;
    finalizeStatus.textContent = "";
    inboxStatus.textContent = `${preparedDocument.original_name} is ready for destinee review.`;
  } catch {
    await loadAnalysisProvider();
    inboxStatus.textContent = "The document could not be loaded from the n8n input directory.";
  }
}

applySplitButton.addEventListener("click", async () => {
  if (!selectedDocument) return;
  const splitPages = [...splitBoundaries.querySelectorAll("input:checked")].map((input) => Number(input.value));
  splitStatus.textContent = "Creating PDF parts...";
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(selectedDocument.filename)}/split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ processing_id: selectedDocument.processingId, split_pages: splitPages })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Split failed");
    splitParts = result.parts;
    splitOutputs.replaceChildren();
    splitOutputs.hidden = false;
    finalizeSplitButton.hidden = false;
    result.parts.forEach((part) => {
      const row = document.createElement("div");
      row.className = "split-output-row";
      row.dataset.part = part.part;
      const filename = part.path.split(/[\\/]/).pop();
      row.innerHTML = `<strong>Part ${part.part} · pages ${part.start_page}-${part.end_page}</strong><input class="split-filename" type="text" value="${escapeHtml(filename)}" maxlength="180"><select class="split-destinee" required><option value="" selected disabled>Choose a destinee</option>${configuredDestinees.map((destinee) => `<option value="${escapeHtml(destinee)}">${escapeHtml(destinee)}</option>`).join("")}</select>`;
      splitOutputs.append(row);
    });
    splitStatus.textContent = `${result.part_count} PDF part${result.part_count === 1 ? "" : "s"} prepared. The original remains unchanged.`;
  } catch (splitError) {
    splitStatus.textContent = splitError.message;
  }
});

finalizeSplitButton.addEventListener("click", async () => {
  if (!selectedDocument || !splitParts.length) return;
  const outputs = [...splitOutputs.querySelectorAll(".split-output-row")].map((row) => ({
    part: Number(row.dataset.part),
    output_filename: row.querySelector(".split-filename").value.trim(),
    destinee: row.querySelector(".split-destinee").value
  }));
  if (outputs.some((output) => !output.output_filename || !output.destinee)) {
    splitStatus.textContent = "Choose a destinee and filename for every split part.";
    return;
  }
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(selectedDocument.filename)}/finalize-split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ processing_id: selectedDocument.processingId, outputs })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Split finalization failed");
    splitStatus.textContent = `${result.outputs.length} split outputs finalized.`;
    finalizeSplitButton.hidden = true;
    await refreshInbox();
    await refreshHistory();
  } catch (splitFinalizeError) {
    splitStatus.textContent = splitFinalizeError.message;
  }
});

async function rotatePage(page, rotation) {
  if (!selectedDocument) return;
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(selectedDocument.filename)}/rotate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ processing_id: selectedDocument.processingId, page, rotation })
    });
    if (!response.ok) throw new Error("Rotation failed");
    documentPreview.src = `${API_BASE_URL}/api/processing/${encodeURIComponent(selectedDocument.processingId)}/file?refresh=${Date.now()}`;
    pageText.querySelectorAll(".page-thumbnail").forEach((thumbnail) => {
      thumbnail.src = `${thumbnail.src.split("?")[0]}?refresh=${Date.now()}`;
    });
    finalizeStatus.textContent = `Page ${page} rotated ${rotation} degrees.`;
  } catch {
    finalizeStatus.textContent = "The page could not be rotated.";
  }
}

function getQueueSummary(filename) {
  const visibleFiles = getVisibleInboxFiles();
  if (!visibleFiles.length) return "Queue: no documents";
  const currentIndex = visibleFiles.findIndex((file) => file.name === filename);
  if (currentIndex === -1) return `Queue: ${visibleFiles.length} documents`;
  return `Queue: ${currentIndex + 1} / ${visibleFiles.length}`;
}

function getNextInboxFile(currentFilename, fileList = inboxFiles) {
  if (!fileList.length) return null;
  const currentIndex = fileList.findIndex((file) => file.name === currentFilename);
  if (currentIndex === -1) return fileList[0] ?? null;
  return fileList[currentIndex + 1] ?? fileList[0] ?? null;
}

function getExistingOutputConflict(destinee, outputFilename) {
  if (!destinee || !outputFilename) return null;
  const normalized = outputFilename.trim();
  return historyDocuments.find((entry) => {
    const entryDestinee = String(entry.destinee || "").trim();
    if (!entryDestinee || entryDestinee.toLowerCase() !== destinee.toLowerCase()) return false;
    const destinationPath = String(entry.destination_path || "").trim();
    return destinationPath && destinationPath.toLowerCase().endsWith(`/${normalized.toLowerCase()}`);
  }) || null;
}

function updateFinalizeWarnings() {
  if (!selectedDocument || !reviewDestinee.value) {
    finalizeButton.disabled = true;
    finalizeStatus.textContent = "";
    return;
  }

  const filename = reviewFilename.value.trim();
  const conflict = getExistingOutputConflict(reviewDestinee.value, filename);

  if (!filename) {
    finalizeStatus.textContent = "Choose a valid output filename before finalizing.";
    finalizeButton.disabled = true;
    return;
  }

  if (conflict) {
    finalizeStatus.textContent = `Conflict: ${conflict.destination_path || filename} already exists for ${reviewDestinee.value}. Pick a different filename.`;
    finalizeButton.disabled = true;
    return;
  }

  finalizeStatus.textContent = "Ready to finalize.";
  finalizeButton.disabled = false;
}

finalizeButton.addEventListener("click", async () => {
  if (!selectedDocument || !reviewDestinee.value) {
    finalizeStatus.textContent = "Choose a destinee before finalizing.";
    return;
  }
  const conflict = getExistingOutputConflict(reviewDestinee.value, reviewFilename.value.trim());
  if (conflict) {
    finalizeStatus.textContent = `Warning: ${conflict.destination_path || reviewFilename.value.trim()} already exists for this destinee.`;
    return;
  }
  finalizeButton.disabled = true;
  finalizeStatus.textContent = "Finalizing...";
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(selectedDocument.filename)}/finalize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        processing_id: selectedDocument.processingId,
        destinee: reviewDestinee.value,
        output_filename: reviewFilename.value.trim()
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Finalization failed");
    finalizeStatus.textContent = `Classified for ${result.destinee}.`;
    const nextFiles = await refreshInbox();
    const nextDocument = getNextInboxFile(selectedDocument.filename, nextFiles);
    if (nextDocument) {
      await inspectDocument(nextDocument.name);
      return;
    }
    reviewPanel.hidden = true;
    document.querySelector(".workflow-layout").classList.remove("review-active");
    finalizeButton.textContent = "Finalized";
    await refreshHistory();
  } catch (finalizeError) {
    finalizeStatus.textContent = finalizeError.message;
    finalizeButton.disabled = false;
  }
});

function formatSourcePath(filename) {
  const normalized = String(filename || "").replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  const basename = parts.pop() || normalized;
  const directory = parts.length ? parts.join("/") : "root";
  return {
    basename,
    directory,
    fullPath: directory === "root" ? "/data/source" : `/data/source/${directory}`
  };
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function goToNextVisibleDocument() {
  if (!selectedDocument) return;
  const nextFiles = getVisibleInboxFiles();
  const nextDocument = getNextInboxFile(selectedDocument.filename, nextFiles);
  if (!nextDocument) {
    reviewPanel.hidden = true;
    document.querySelector(".workflow-layout").classList.remove("review-active");
    return;
  }
  await inspectDocument(nextDocument.name);
}

async function refreshInbox() {
  inboxStatus.textContent = "Checking for completed PDFs...";
  try {
    const response = await fetch(`${API_BASE_URL}/api/classification/scan`, { method: "POST" });
    if (!response.ok) throw new Error("Scan failed");
    const result = await response.json();
    inboxFiles = result.files || [];
    getInboxFilterOptions();
    renderInbox(inboxFiles);
    refreshHistory();
    return inboxFiles;
  } catch {
    inboxFiles = [];
    inboxList.replaceChildren();
    inboxStatus.textContent = "The n8n input directory is not reachable yet.";
    return [];
  }
}

async function loadAnalysisProvider() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/analysis/status`);
    if (!response.ok) throw new Error("Provider status failed");
    const status = await response.json();
    const cooldown = status.retry_after ? ` Retry in ${status.retry_after}.` : "";
    if (status.gemini_configured && status.available) {
      analysisProvider.textContent = "Analysis provider: Gemini available";
      globalAnalysisStatus.textContent = "Gemini is available for document analysis.";
      globalAnalysisStatus.className = "global-analysis-status provider-gemini";
      analysisProvider.className = "analysis-provider provider-gemini";
    } else if (status.gemini_configured && status.message) {
      analysisProvider.textContent = `Analysis provider: Gemini temporarily unavailable; local fallback active.${cooldown}`;
      globalAnalysisStatus.textContent = `Gemini quota or availability warning. Local fallback is active.${cooldown}`;
      globalAnalysisStatus.className = "global-analysis-status provider-warning";
      analysisProvider.className = "analysis-provider provider-warning";
    } else {
      analysisProvider.textContent = "Analysis provider: Local fallback";
      globalAnalysisStatus.textContent = "Gemini is not configured. Local analysis is active.";
      globalAnalysisStatus.className = "global-analysis-status provider-local";
      analysisProvider.className = "analysis-provider provider-local";
    }
    if (status.message) {
      analysisProvider.title = status.message;
      globalAnalysisStatus.title = status.message;
    }
  } catch {
    analysisProvider.textContent = "Analysis provider status unavailable";
    analysisProvider.className = "analysis-provider";
  }
}

async function loadVersion() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/version`);
    if (!response.ok) throw new Error("Version request failed");
    const result = await response.json();
    appVersion.textContent = `v${result.version}`;
    appRevision.textContent = `revision ${result.revision}`;
  } catch {
    appVersion.textContent = "version unavailable";
    appRevision.textContent = "revision unavailable";
  }
}

function getHistoryVisibleEntries() {
  const searchValue = historySearch?.value.trim().toLowerCase() || "";
  const folderValue = historyFolderFilter?.value || "all";
  const statusValue = historyStatusFilter?.value || "all";

  const filtered = historyDocuments.filter((entry) => {
    const source = formatSourcePath(entry.name);
    const statusText = String(entry.status || "received").toLowerCase();
    const duplicateText = String(entry.duplicate_of || "").toLowerCase();
    const matchesSearch = !searchValue || [
      entry.name,
      source.directory,
      entry.destinee || "",
      statusText,
      duplicateText
    ].some((value) => String(value).toLowerCase().includes(searchValue));
    const folderMatch = folderValue === "all" || source.directory === folderValue || (folderValue === "root" && source.directory === "root");
    const statusMatch = statusValue === "all" || (entry.status || "received") === statusValue;
    return matchesSearch && folderMatch && statusMatch;
  });

  if (!(historySort && historySort.value)) return filtered;

  const sortedEntries = [...filtered];
  sortedEntries.sort((left, right) => {
    const leftName = String(left.name || "").toLowerCase();
    const rightName = String(right.name || "").toLowerCase();
    if (historySort.value === "status") {
      const statusDifference = getStatusPriority(left.status || "received") - getStatusPriority(right.status || "received");
      if (statusDifference !== 0) return statusDifference;
    }
    return leftName.localeCompare(rightName);
  });

  return sortedEntries;
}

function renderHistory(entries) {
  historyList.replaceChildren();
  const visibleEntries = getHistoryVisibleEntries();
  historyStatus.textContent = visibleEntries.length
    ? `${visibleEntries.length} document${visibleEntries.length === 1 ? "" : "s"} tracked.`
    : "No documents match the current history filters.";

  visibleEntries.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "history-item";
    const source = formatSourcePath(entry.name);
    const sourceLine = source.directory === "root" ? "/data/source" : `/data/source/${source.directory}`;
    const status = String(entry.status || "received");
    const duplicateBadge = entry.duplicate_of ? " · duplicate" : "";
    const archiveStatus = entry.dismissed_path ? "dismissed" : entry.archive_path ? "classified" : status;
    const displayStatus = archiveStatus === "classified" ? "classified" : archiveStatus === "dismissed" ? "dismissed" : getStatusLabel(status);
    const fileStateClass = archiveStatus === "dismissed" ? "warning" : archiveStatus === "classified" ? "good" : "neutral";
    item.innerHTML = `<div><strong>${escapeHtml(source.basename)}</strong><small>${escapeHtml(displayStatus.toUpperCase())}${entry.destinee ? ` · ${escapeHtml(entry.destinee)}` : ""}${duplicateBadge ? ` · ${escapeHtml(duplicateBadge.trim())}` : ""} · ${escapeHtml(sourceLine)}</small></div><span class="file-state file-state-${fileStateClass}">${escapeHtml(displayStatus.toUpperCase())}</span>`;
    historyList.append(item);
  });
}

async function refreshHistory() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/history`);
    if (!response.ok) throw new Error("History request failed");
    const result = await response.json();
    historyDocuments = result.documents || [];
    const folders = ["all", ...new Set(historyDocuments.map((entry) => formatSourcePath(entry.name).directory).filter(Boolean))];
    const currentFolderValue = historyFolderFilter.value;
    historyFolderFilter.replaceChildren();
    folders.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "all" ? "All folders" : value;
      if (value === currentFolderValue || (currentFolderValue === "" && value === "all")) option.selected = true;
      historyFolderFilter.append(option);
    });
    const statusValues = ["all", "received", "in_review", "classified", "dismissed", "duplicate", "failed"];
    const currentStatus = historyStatusFilter.value;
    historyStatusFilter.replaceChildren();
    statusValues.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "all" ? "All statuses" : getStatusLabel(value);
      if (value === currentStatus || (currentStatus === "" && value === "all")) option.selected = true;
      historyStatusFilter.append(option);
    });
    renderHistory(historyDocuments);
  } catch {
    historyDocuments = [];
    historyList.replaceChildren();
    historyStatus.textContent = "Processing history is not reachable yet.";
  }
}

document.querySelector("#add-destinee").addEventListener("click", () => {
  const next = readRows();
  next.push("");
  render(next);
  list.lastElementChild.querySelector("input").focus();
});

document.querySelector("#refresh-inbox").addEventListener("click", refreshInbox);
document.querySelector("#refresh-history").addEventListener("click", refreshHistory);
document.querySelector("#clear-inbox-filters").addEventListener("click", () => {
  inboxSearch.value = "";
  inboxFolderFilter.value = "all";
  inboxStatusFilter.value = "all";
  inboxDuplicateFilter.value = "all";
  inboxSort.value = "path";
  renderInbox(inboxFiles);
});
document.querySelector("#clear-history-filters").addEventListener("click", () => {
  historySearch.value = "";
  historyFolderFilter.value = "all";
  historyStatusFilter.value = "all";
  historySort.value = "path";
  renderHistory(historyDocuments);
});
[inboxSearch, inboxFolderFilter, inboxStatusFilter, inboxDuplicateFilter, inboxSort].forEach((element) => {
  if (!element) return;
  element.addEventListener("input", () => renderInbox(inboxFiles));
  element.addEventListener("change", () => renderInbox(inboxFiles));
});
[historySearch, historyFolderFilter, historyStatusFilter, historySort].forEach((element) => {
  if (!element) return;
  element.addEventListener("input", () => renderHistory(historyDocuments));
  element.addEventListener("change", () => renderHistory(historyDocuments));
});
reviewDestinee.addEventListener("change", () => {
  if (!reviewDestinee.value) {
    finalizeButton.disabled = true;
    finalizeStatus.textContent = "";
    return;
  }

  updateFinalizeWarnings();
});

reviewFilename.addEventListener("input", () => {
  if (!selectedDocument) return;
  updateFinalizeWarnings();
});

window.addEventListener("keydown", async (event) => {
  const targetTag = event.target?.tagName;
  const isTypingField = targetTag === "INPUT" || targetTag === "TEXTAREA" || targetTag === "SELECT";
  if (isTypingField) return;

  if (!selectedDocument) return;

  if (event.key === "n" || event.key === "N") {
    event.preventDefault();
    await goToNextVisibleDocument();
    return;
  }

  if (event.key === "d" || event.key === "D") {
    event.preventDefault();
    await dismissDocument(selectedDocument.filename);
    return;
  }

  if ((event.key === "Enter" || event.key === " ") && reviewDestinee.value && !finalizeButton.disabled) {
    event.preventDefault();
    finalizeButton.click();
  }
});

documentPreview.addEventListener("load", () => {
  previewLoader.classList.remove("visible");
});

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
refreshHistory();
loadAnalysisProvider();
loadVersion();

document.querySelector("[data-source-path]").textContent = SOURCE_PATH;
document.querySelector("[data-destination-path]").textContent = `${DESTINATION_PATH}/`;
document.querySelector("[data-preview-root]").textContent = `${DESTINATION_PATH}/`;
