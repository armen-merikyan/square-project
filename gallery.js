const GALLERY_MANIFEST_PATH = "art/manifest.json";

const artGrid = document.querySelector("#artGrid");
const artInspector = document.querySelector("#artInspector");
const galleryCount = document.querySelector("#galleryCount");
const gallerySearch = document.querySelector("#gallerySearch");
const galleryPagination = document.querySelector("#galleryPagination");

const PAGE_SIZE = 24;
let galleryRecords = [];
let filteredRecords = [];
let currentPage = 1;
let selectedId = "";
let previousFocus = null;

function compactId(id) {
  return `${id.slice(0, 10)}...${id.slice(-8)}`;
}

function uniqueColors(pixels = []) {
  return [...new Set(pixels.map((pixel) => pixel.color).filter(Boolean))];
}

function recordSearchText(record) {
  return [
    record.id,
    record.title,
    record.seed,
    record.reasoning,
    ...uniqueColors(record.pixels)
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

  const id = document.createElement("span");
  id.textContent = compactId(record.id);

  meta.append(title, id);
  card.append(image, meta);
  card.addEventListener("click", () => renderInspector(record));

  return card;
}

function renderPagination(totalPages) {
  galleryPagination.replaceChildren();

  if (totalPages <= 1) {
    return;
  }

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

  const next = document.createElement("button");
  next.type = "button";
  next.textContent = "Next";
  next.disabled = currentPage === totalPages;
  next.addEventListener("click", () => {
    currentPage += 1;
    renderCurrentPage();
  });

  galleryPagination.append(previous, status, next);
}

function renderCurrentPage() {
  const totalPages = Math.max(1, Math.ceil(filteredRecords.length / PAGE_SIZE));
  currentPage = Math.min(Math.max(currentPage, 1), totalPages);

  const start = (currentPage - 1) * PAGE_SIZE;
  const pageRecords = filteredRecords.slice(start, start + PAGE_SIZE);
  const query = gallerySearch.value.trim();

  galleryCount.textContent = query
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

function applySearch() {
  const terms = gallerySearch.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  filteredRecords = terms.length
    ? galleryRecords.filter((record) => terms.every((term) => record.searchText.includes(term)))
    : galleryRecords;
  currentPage = 1;
  renderCurrentPage();
}

async function renderGallery() {
  galleryCount.textContent = "Loading";

  const artworkIds = await fetchArtworkIds();
  galleryRecords = (await Promise.all(artworkIds.map(fetchArtwork))).map((record) => ({
    ...record,
    searchText: recordSearchText(record)
  }));
  filteredRecords = galleryRecords;
  renderCurrentPage();
}

gallerySearch.addEventListener("input", applySearch);

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
