const STORAGE_KEY = "classifier.destinees";
const DEFAULT_DESTINEES = [];
const SOURCE_PATH = window.CLASSIFIER_CONFIG?.sourcePath || "/data/source";
const DESTINATION_PATH = window.CLASSIFIER_CONFIG?.destinationPath || "/data/destination";
const API_BASE_URL = window.CLASSIFIER_CONFIG?.apiBaseUrl || "";

const list = document.querySelector("#destinee-list");
const sourceRootList = document.querySelector("#source-root-list");
const destinationRouteList = document.querySelector("#destination-route-list");
const folderList = document.querySelector("#folder-list");
const count = document.querySelector("#count");
const error = document.querySelector("#form-error");

function sanitizeDestineeList(values) {
  if (!Array.isArray(values)) {
    return [];
  }
  return values
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

function sanitizeSourceRoots(values) {
  const roots = Array.isArray(values) ? values.map((value) => String(value || "").trim()).filter(Boolean) : [];
  return roots.length ? roots : [SOURCE_PATH];
}

function escapeHtml(value) {
  return String(value).replace(/[&<>\"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;"
  }[character]));
}

function loadDestinees() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    const nextDestinees = sanitizeDestineeList(saved);
    return nextDestinees.length ? nextDestinees : [...DEFAULT_DESTINEES];
  } catch {
    return [...DEFAULT_DESTINEES];
  }
}

function persistDestineeState(destinees) {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitizeDestineeList(destinees)));
}

function buildValidDestinationRouteMap(destinees, explicitRoutes = {}) {
  const validDestinees = new Set(sanitizeDestineeList(destinees));
  const validEntries = Object.entries(explicitRoutes || {}).filter(([destinee, path]) => {
    const name = String(destinee || "").trim();
    const route = String(path || "").trim();
    return Boolean(name) && validDestinees.has(name) && Boolean(route);
  });
  return Object.fromEntries(validEntries);
}

function buildDefaultDestinationRoutes(destinees, explicitRoutes = {}) {
  return buildValidDestinationRouteMap(destinees, explicitRoutes);
}

function bindRemoveHandler(container, callback) {
  if (!container) {
    return;
  }

  const previousCallback = container._removeHandlerCallback;
  const previousHandler = container._removeHandlerFn;
  if (previousCallback === callback && previousHandler) {
    return;
  }

  if (previousHandler) {
    container.removeEventListener("click", previousHandler);
  }

  const handler = (event) => {
    const button = event.target.closest(".remove-button");
    if (!button) {
      return;
    }
    const row = button.closest(".destinee-row");
    if (!row) {
      return;
    }
    callback(row);
  };

  container._removeHandlerCallback = callback;
  container._removeHandlerFn = handler;
  container.addEventListener("click", handler);
}

function renderSourceRoots(sourceRoots) {
  if (!sourceRootList) {
    return;
  }

  bindRemoveHandler(sourceRootList, (row) => {
    const next = [...sourceRootList.querySelectorAll(".source-root-input")]
      .map((input) => input.value.trim())
      .filter(Boolean);
    const index = [...sourceRootList.children].indexOf(row);
    const filtered = next.filter((_, rowIndex) => rowIndex !== index);
    renderSourceRoots(filtered.length ? filtered : [SOURCE_PATH]);
  });

  sourceRootList.replaceChildren();
  const rows = sourceRoots.length ? sourceRoots : [SOURCE_PATH];
  rows.forEach((sourceRoot, index) => {
    const row = document.createElement("div");
    row.className = "destinee-row";
    row.innerHTML = `
      <span class="row-number">${String(index + 1).padStart(2, "0")}</span>
      <input class="source-root-input" type="text" value="${escapeHtml(sourceRoot)}" aria-label="Source root ${index + 1}">
      <button class="remove-button" type="button" aria-label="Remove source root ${escapeHtml(sourceRoot)}">&times;</button>
    `;
    sourceRootList.append(row);
  });
}

function renderDestinationRoutes(destinees, destinationRoots = {}) {
  if (!destinationRouteList) {
    return;
  }

  const validDestinees = sanitizeDestineeList(destinees);
  const routeMap = buildValidDestinationRouteMap(validDestinees, destinationRoots);

  bindRemoveHandler(destinationRouteList, (row) => {
    const routeNames = [...destinationRouteList.querySelectorAll(".route-name-input")].map((input) => input.value.trim());
    const currentRouteIndex = [...destinationRouteList.children].indexOf(row);
    const currentName = routeNames[currentRouteIndex];
    if (!currentName) {
      return;
    }

    const currentRoutes = buildValidDestinationRouteMap(validDestinees, Object.fromEntries(readDestinationRouteRows()));
    const nextRoutes = Object.fromEntries(
      Object.entries(currentRoutes).filter(([name]) => name !== currentName)
    );
    renderDestinationRoutes(validDestinees, nextRoutes);
  });

  destinationRouteList.replaceChildren();
  const routeEntries = Object.entries(routeMap);
  if (!routeEntries.length) {
    return;
  }

  routeEntries.forEach(([destinee, path], index) => {
    const row = document.createElement("div");
    row.className = "destinee-row";
    row.innerHTML = `
      <span class="row-number">${String(index + 1).padStart(2, "0")}</span>
      <input class="route-name-input" type="text" value="${escapeHtml(destinee)}" readonly placeholder="Destinee" aria-label="Route name ${index + 1}">
      <input class="route-path-input" type="text" value="${escapeHtml(path)}" placeholder="/data/destination/${escapeHtml(destinee)}" aria-label="Route path ${index + 1}">
      <button class="remove-button" type="button" aria-label="Remove destination route ${escapeHtml(destinee)}">&times;</button>
    `;
    destinationRouteList.append(row);
  });
}

function render(destinees) {
  if (!list) {
    return;
  }

  bindRemoveHandler(list, (row) => {
    const next = [...list.querySelectorAll(".destinee-input")].map((input) => input.value.trim());
    const index = [...list.children].indexOf(row);
    const filtered = next.filter((_, rowIndex) => rowIndex !== index);
    render(filtered);
    renderDestinationRoutes(filtered, buildValidDestinationRouteMap(filtered, Object.fromEntries(readDestinationRouteRows())));
  });

  list.replaceChildren();
  folderList.replaceChildren();
  count.textContent = `${sanitizeDestineeList(destinees).length} configured`;

  destinees.forEach((destinee, index) => {
    const row = document.createElement("div");
    row.className = "destinee-row";
    row.innerHTML = `
      <span class="row-number">${String(index + 1).padStart(2, "0")}</span>
      <input class="destinee-input" type="text" maxlength="80" value="${escapeHtml(destinee)}" aria-label="Destinee ${index + 1}">
      <button class="remove-button" type="button" aria-label="Remove destinee ${escapeHtml(destinee)}">&times;</button>
    `;

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

function readSourceRootRows() {
  return sanitizeSourceRoots([...document.querySelectorAll(".source-root-input")].map((input) => input.value.trim()));
}

function readDestinationRouteRows() {
  const validDestinees = new Set(readRows());
  const routeInputs = [...document.querySelectorAll(".route-name-input")];
  const pathInputs = [...document.querySelectorAll(".route-path-input")];

  const rows = routeInputs.map((input, index) => {
    const name = input.value.trim();
    const path = pathInputs[index]?.value.trim() || "";
    if (!name || !validDestinees.has(name) || !path) {
      return null;
    }
    return [name, path];
  });

  return rows.filter(Boolean);
}

async function initialize() {
  if (!list && !sourceRootList && !destinationRouteList && !document.querySelector("#destinee-form")) {
    return;
  }

  let config = { destinees: loadDestinees(), source_roots: [SOURCE_PATH], destination_roots: {} };
  try {
    const response = await fetch(`${API_BASE_URL}/api/classification/config`);
    if (response.ok) {
      const payload = await response.json();
      config = {
        destinees: sanitizeDestineeList(payload.destinees),
        source_roots: sanitizeSourceRoots(payload.source_roots),
        destination_roots: buildValidDestinationRouteMap(payload.destinees || [], payload.destination_roots || {})
      };
      persistDestineeState(config.destinees);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config.destinees));
    } else {
      persistDestineeState(config.destinees);
    }
  } catch {
    persistDestineeState(config.destinees);
  }

  const effectiveDestinees = sanitizeDestineeList(config.destinees);
  const effectiveSourceRoots = sanitizeSourceRoots(config.source_roots);
  const effectiveDestinationRoots = buildValidDestinationRouteMap(effectiveDestinees, config.destination_roots || {});

  render(effectiveDestinees);
  renderSourceRoots(effectiveSourceRoots);
  renderDestinationRoutes(effectiveDestinees, effectiveDestinationRoots);
}

function updateFolderPreview(destinees) {
  folderList.replaceChildren();
  destinees.forEach((destinee) => {
    const folder = document.createElement("div");
    folder.className = "folder-item";
    folder.innerHTML = `<strong>${escapeHtml(destinee)}</strong><small>${escapeHtml(DESTINATION_PATH)}/${escapeHtml(destinee)}/</small>`;
    folderList.append(folder);
  });
}

document.querySelector("#add-destinee")?.addEventListener("click", () => {
  const current = readRows();
  const next = [...current, ""];
  render(next);
  renderDestinationRoutes(sanitizeDestineeList(next), buildValidDestinationRouteMap(sanitizeDestineeList(next), Object.fromEntries(readDestinationRouteRows())));
});

document.querySelector("#add-source-root")?.addEventListener("click", () => {
  const current = readSourceRootRows();
  const next = [...current, SOURCE_PATH];
  renderSourceRoots(next);
});

document.querySelector("#add-destination-route")?.addEventListener("click", () => {
  const currentDestinees = readRows();
  const currentRoutes = buildValidDestinationRouteMap(currentDestinees, Object.fromEntries(readDestinationRouteRows()));
  const nextDestinee = currentDestinees.find((destinee) => !Object.prototype.hasOwnProperty.call(currentRoutes, destinee));
  if (!nextDestinee) {
    return;
  }
  currentRoutes[nextDestinee] = "/data/destination/" + nextDestinee;
  renderDestinationRoutes(currentDestinees, currentRoutes);
});

document.querySelector("#destinee-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
const rawDestinees = readRows();
    const destinees = sanitizeDestineeList(rawDestinees);
  const rawSourceRoots = readSourceRootRows();
  const sourceRoots = sanitizeSourceRoots(rawSourceRoots);
  const explicitDestinationRoutes = Object.fromEntries(readDestinationRouteRows());
  const destinationRoutes = buildValidDestinationRouteMap(destinees, explicitDestinationRoutes);
  const normalized = destinees.map((value) => value.toLocaleLowerCase());

  if (destinees.length === 0) {
    error.textContent = "Add at least one destinee.";
    localStorage.removeItem(STORAGE_KEY);
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
      body: JSON.stringify({ destinees, source_roots: sourceRoots, destination_roots: destinationRoutes })
    });

    if (!response.ok) {
      throw new Error("API request failed");
    }

    localStorage.removeItem(STORAGE_KEY);
    persistDestineeState(destinees);
    error.textContent = "Configuration saved.";
    updateFolderPreview(destinees);
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    persistDestineeState(destinees);
    error.textContent = "Saved locally. The API is not reachable yet.";
    updateFolderPreview(destinees);
  }

  render(destinees);
  renderSourceRoots(sourceRoots);
  renderDestinationRoutes(destinees, destinationRoutes);
});

initialize();

window.CLASSIFIER_CONFIG = Object.freeze({
  sourcePath: SOURCE_PATH,
  destinationPath: DESTINATION_PATH,
  apiBaseUrl: API_BASE_URL
});