const GALLERY_MANIFEST_PATH = "art/manifest.json";

const artGrid = document.querySelector("#artGrid");
const artInspector = document.querySelector("#artInspector");
const galleryCount = document.querySelector("#galleryCount");
const gallerySearch = document.querySelector("#gallerySearch");
const galleryPagination = document.querySelector("#galleryPagination");
const colorFilterList = document.querySelector("#colorFilterList");
const clearColorFilters = document.querySelector("#clearColorFilters");

const PAGE_SIZE_OPTIONS = [24, 48, 72, 96];
let galleryRecords = [];
let filteredRecords = [];
let pageSize = PAGE_SIZE_OPTIONS[0];
let currentPage = 1;
let selectedId = "";
let previousFocus = null;
const includedColors = new Set();
const excludedColors = new Set();

function compactId(id) {
  return `${id.slice(0, 10)}...${id.slice(-8)}`;
}

function uniqueColors(pixels = []) {
  return [...new Set(pixels.map((pixel) => normalizeColor(pixel.color)).filter(Boolean))];
}

function normalizeColor(color = "") {
  return color.trim().toUpperCase();
}

function recordSearchText(record) {
  return [
    record.id,
    record.title,
    record.seed,
    record.reasoning,
    ...record.colors
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

async function fetchArtworkIds() {
  const response = await fetch(GALLERY_MANIFEST_PATH);

  if (!response.ok) {
    throw new Error("Unable to load art manifest.");
  }

  const manifest = await response.json();
  const ids = Array.isArray(manifest) ? manifest : manifest.artworkIds;

  if (!Array.isArray(ids) || ids.length === 0) {
    throw new Error("Art manifest does not include any artwork ids.");
  }

  return ids;
}

async function fetchArtwork(id) {
  const response = await fetch(`art/${id}.json`);

  if (!response.ok) {
    throw new Error(`Unable to load ${id}.json`);
  }

  return response.json();
}

function makeMetric(label, value) {
  const item = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");

  term.textContent = label;
  description.textContent = value;
  item.append(term, description);
  return item;
}

function renderSwatches(colors) {
  const swatches = document.createElement("div");
  swatches.className = "color-swatches";

  colors.forEach((color) => {
    const swatch = document.createElement("span");
    swatch.style.background = color;
    swatch.title = color;
    swatch.setAttribute("aria-label", color);
    swatches.appendChild(swatch);
  });

  return swatches;
}

function colorUsage(records) {
  const usage = new Map();

  records.forEach((record) => {
    record.colors.forEach((color) => {
      usage.set(color, (usage.get(color) || 0) + 1);
    });
  });

  return [...usage.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function renderColorFilters() {
  colorFilterList.replaceChildren();

  colorUsage(galleryRecords).forEach(([color, count]) => {
    const item = document.createElement("div");
    item.className = "color-filter-item";

    const swatch = document.createElement("span");
    swatch.className = "color-filter-swatch";
    swatch.style.background = color;
    swatch.setAttribute("aria-hidden", "true");

    const label = document.createElement("span");
    label.className = "color-filter-label";
    label.textContent = color;

    const total = document.createElement("span");
    total.className = "color-filter-count";
    total.textContent = String(count);

    const include = document.createElement("button");
    include.type = "button";
    include.className = "color-filter-action";
    include.textContent = "+";
    include.setAttribute("aria-label", `Include ${color}`);
    include.classList.toggle("is-active", includedColors.has(color));
    include.addEventListener("click", () => {
      if (includedColors.has(color)) {
        includedColors.delete(color);
      } else {
        includedColors.add(color);
        excludedColors.delete(color);
      }
      applyFilters();
    });

    const exclude = document.createElement("button");
    exclude.type = "button";
    exclude.className = "color-filter-action";
    exclude.textContent = "-";
    exclude.setAttribute("aria-label", `Exclude ${color}`);
    exclude.classList.toggle("is-active", excludedColors.has(color));
    exclude.addEventListener("click", () => {
      if (excludedColors.has(color)) {
        excludedColors.delete(color);
      } else {
        excludedColors.add(color);
        includedColors.delete(color);
      }
      applyFilters();
    });

    item.append(swatch, label, total, include, exclude);
    colorFilterList.appendChild(item);
  });
}

function closeInspector() {
  if (artInspector.open && typeof artInspector.close === "function") {
    artInspector.close();
  } else {
    artInspector.removeAttribute("open");
    artInspector.classList.remove("is-fallback-open");
    document.body.classList.remove("has-open-inspector");
  }
}

function openInspector() {
  document.body.classList.add("has-open-inspector");

  if (typeof artInspector.showModal === "function") {
    if (!artInspector.open) {
      try {
        artInspector.showModal();
      } catch {
        artInspector.setAttribute("open", "");
        artInspector.classList.add("is-fallback-open");
      }
    }
    return;
  }

  artInspector.setAttribute("open", "");
  artInspector.classList.add("is-fallback-open");
}

function renderInspector(record) {
  selectedId = record.id;
  previousFocus = document.activeElement;
  const colors = uniqueColors(record.pixels);
  const width = record.size?.width || 8;
  const height = record.size?.height || 8;

  artInspector.replaceChildren();

  const frame = document.createElement("div");
  frame.className = "inspector-frame";

  const closeButton = document.createElement("button");
  closeButton.className = "inspector-close";
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", "Close artwork details");
  closeButton.textContent = "Close";
  closeButton.addEventListener("click", closeInspector);

  const image = document.createElement("img");
  image.src = `art/${record.id}.svg`;
  image.alt = `${record.title || "Square artwork"} artwork`;
  image.decoding = "async";

  const content = document.createElement("div");
  content.className = "inspector-content";

  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Selected square";

  const title = document.createElement("h2");
  title.textContent = record.title || "Untitled square";

  const seed = document.createElement("p");
  seed.className = "inspector-seed";
  seed.textContent = record.seed || "No seed recorded";

  const metrics = document.createElement("dl");
  metrics.className = "inspector-metrics";
  metrics.append(
    makeMetric("Grid", `${width} x ${height}`),
    makeMetric("Cells", String(record.pixels?.length || width * height)),
    makeMetric("Colors", String(colors.length)),
    makeMetric("Record", compactId(record.id))
  );

  const reasoningLabel = document.createElement("h3");
  reasoningLabel.textContent = "Artist statement";

  const reasoning = document.createElement("p");
  reasoning.className = "inspector-reasoning";
  reasoning.textContent = record.reasoning || "No reasoning recorded.";

  const paletteLabel = document.createElement("h3");
  paletteLabel.textContent = "Palette";

  const jsonLink = document.createElement("a");
  jsonLink.className = "button secondary inspector-download";
  jsonLink.href = `art/${record.id}.json`;
  jsonLink.download = `${record.id}.json`;
  jsonLink.textContent = "Download JSON";

  content.append(
    eyebrow,
    title,
    seed,
    metrics,
    reasoningLabel,
    reasoning,
    paletteLabel,
    renderSwatches(colors),
    jsonLink
  );

  frame.append(closeButton, image, content);
  artInspector.appendChild(frame);

  openInspector();

  document.querySelectorAll(".gallery-card").forEach((card) => {
    const isSelected = card.dataset.id === selectedId;
    card.classList.toggle("is-selected", isSelected);
    card.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });
}

function renderCard(record, index) {
  const card = document.createElement("button");
  card.className = "gallery-card";
  card.type = "button";
  card.dataset.id = record.id;
  card.setAttribute("aria-label", `View details for ${record.title || `artwork ${index + 1}`}`);

  const image = document.createElement("img");
  image.src = `art/${record.id}.svg`;
  image.alt = "";
  image.decoding = "async";

  const meta = document.createElement("span");
  meta.className = "gallery-card-meta";

  const title = document.createElement("strong");
  title.textContent = record.title || `Square ${index + 1}`;

  meta.append(title);
  card.append(image, meta);
  card.addEventListener("click", () => renderInspector(record));

  return card;
}

function renderPagination(totalPages) {
  galleryPagination.replaceChildren();

  const previous = document.createElement("button");
  previous.type = "button";
  previous.textContent = "Previous";
  previous.disabled = currentPage === 1;
  previous.addEventListener("click", () => {
    currentPage -= 1;
    renderCurrentPage();
  });

  const status = document.createElement("span");
  status.textContent = `Page ${currentPage} of ${totalPages}`;

  const pageSizeLabel = document.createElement("label");
  pageSizeLabel.className = "page-size-control";
  pageSizeLabel.textContent = "Per page";

  const pageSizeSelect = document.createElement("select");
  pageSizeSelect.setAttribute("aria-label", "Artworks per page");
  PAGE_SIZE_OPTIONS.forEach((option) => {
    const optionElement = document.createElement("option");
    optionElement.value = String(option);
    optionElement.textContent = String(option);
    optionElement.selected = option === pageSize;
    pageSizeSelect.appendChild(optionElement);
  });
  pageSizeSelect.addEventListener("change", (event) => {
    pageSize = Number(event.target.value);
    currentPage = 1;
    renderCurrentPage();
  });
  pageSizeLabel.appendChild(pageSizeSelect);

  const next = document.createElement("button");
  next.type = "button";
  next.textContent = "Next";
  next.disabled = currentPage === totalPages;
  next.addEventListener("click", () => {
    currentPage += 1;
    renderCurrentPage();
  });

  if (totalPages > 1) {
    galleryPagination.append(previous, status, next, pageSizeLabel);
  } else {
    galleryPagination.append(status, pageSizeLabel);
  }
}

function renderCurrentPage() {
  const totalPages = Math.max(1, Math.ceil(filteredRecords.length / pageSize));
  currentPage = Math.min(Math.max(currentPage, 1), totalPages);

  const start = (currentPage - 1) * pageSize;
  const pageRecords = filteredRecords.slice(start, start + pageSize);
  const query = gallerySearch.value.trim();
  const hasColorFilters = includedColors.size > 0 || excludedColors.size > 0;

  galleryCount.textContent = query || hasColorFilters
    ? `${filteredRecords.length} of ${galleryRecords.length} artworks`
    : `${galleryRecords.length} artworks`;

  if (pageRecords.length === 0) {
    artGrid.innerHTML = `<p class="carousel-error">No artworks match your search.</p>`;
    galleryPagination.replaceChildren();
    closeInspector();
    selectedId = "";
    return;
  }

  artGrid.replaceChildren(...pageRecords.map((record, index) => renderCard(record, start + index)));
  renderPagination(totalPages);

  document.querySelectorAll(".gallery-card").forEach((card) => {
    const isSelected = card.dataset.id === selectedId;
    card.classList.toggle("is-selected", isSelected);
    card.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });
}

function applyFilters() {
  const terms = gallerySearch.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  filteredRecords = galleryRecords.filter((record) => {
    const matchesText = terms.every((term) => record.searchText.includes(term));
    const matchesIncluded = [...includedColors].every((color) => record.colors.includes(color));
    const matchesExcluded = [...excludedColors].every((color) => !record.colors.includes(color));

    return matchesText && matchesIncluded && matchesExcluded;
  });
  currentPage = 1;
  renderColorFilters();
  renderCurrentPage();
}

async function renderGallery() {
  galleryCount.textContent = "Loading";

  const artworkIds = await fetchArtworkIds();
  galleryRecords = (await Promise.all(artworkIds.map(fetchArtwork))).map((record) => {
    const colors = uniqueColors(record.pixels);
    return {
      ...record,
      colors,
      searchText: recordSearchText({ ...record, colors })
    };
  });
  filteredRecords = galleryRecords;
  renderColorFilters();
  renderCurrentPage();
}

gallerySearch.addEventListener("input", applyFilters);
clearColorFilters.addEventListener("click", () => {
  includedColors.clear();
  excludedColors.clear();
  applyFilters();
});

artInspector.addEventListener("click", (event) => {
  if (event.target === artInspector) {
    closeInspector();
  }
});

artInspector.addEventListener("close", () => {
  document.body.classList.remove("has-open-inspector");
  artInspector.classList.remove("is-fallback-open");

  if (previousFocus) {
    previousFocus.focus();
    previousFocus = null;
  }
});

renderGallery().catch((error) => {
  galleryCount.textContent = "Error";
  artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
});
