const STORAGE_KEY = "classifier.destinees";
const DEFAULT_DESTINEES = ["Destinee A", "Destinee B", "Destinee C"];
const SOURCE_PATH = window.CLASSIFIER_CONFIG?.sourcePath || "/data/source";
const DESTINATION_PATH = window.CLASSIFIER_CONFIG?.destinationPath || "/data/destination";
const API_BASE_URL = window.CLASSIFIER_CONFIG?.apiBaseUrl || "";
const list = document.querySelector("#destinee-list");
const folderList = document.querySelector("#folder-list");
const count = document.querySelector("#count");
const error = document.querySelector("#form-error");

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

document.querySelector("#add-destinee").addEventListener("click", () => {
  const next = readRows();
  next.push("");
  render(next);
  list.lastElementChild.querySelector("input").focus();
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

document.querySelector("[data-source-path]").textContent = SOURCE_PATH;
document.querySelector("[data-destination-path]").textContent = `${DESTINATION_PATH}/`;
document.querySelector("[data-preview-root]").textContent = `${DESTINATION_PATH}/`;
