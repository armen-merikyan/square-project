const GALLERY_MANIFEST_PATH = "art/manifest.json";

const artGrid = document.querySelector("#artGrid");
const artInspector = document.querySelector("#artInspector");
const galleryCount = document.querySelector("#galleryCount");
const gallerySearch = document.querySelector("#gallerySearch");
const galleryPagination = document.querySelector("#galleryPagination");
const colorFilterList = document.querySelector("#colorFilterList");
const clearColorFilters = document.querySelector("#clearColorFilters");
const galleryWorkspace = document.querySelector(".gallery-workspace");
const galleryFilters = document.querySelector("#galleryFilters");
const toggleColorFilters = document.querySelector("#toggleColorFilters");
const colorSimilarity = document.querySelector("#colorSimilarity");
const colorSimilarityValue = document.querySelector("#colorSimilarityValue");

const PAGE_SIZE_OPTIONS = [24, 48, 72, 96];
const FILTER_VISIBILITY_COOKIE = "square_color_filters";
const COLOR_SIMILARITY_COOKIE = "square_color_similarity";
let galleryRecords = [];
let filteredRecords = [];
let colorBuckets = [];
let colorToBucket = new Map();
let pageSize = PAGE_SIZE_OPTIONS[0];
let currentPage = 1;
let selectedId = "";
let previousFocus = null;
let colorFiltersVisible = true;
let colorSimilarityThreshold = Number(colorSimilarity.value);
const includedColorSeeds = new Set();
const excludedColorSeeds = new Set();

function readCookie(name) {
  return document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.split("=")[1];
}

function savePreference(name, value) {
  const encodedValue = encodeURIComponent(value);
  document.cookie = `${name}=${encodedValue}; max-age=31536000; path=/; SameSite=Lax`;

  try {
    window.localStorage.setItem(name, value);
  } catch {
    // Ignore unavailable storage in restrictive browser modes.
  }
}

function readPreference(name) {
  const cookieValue = readCookie(name);

  if (cookieValue) {
    return decodeURIComponent(cookieValue);
  }

  try {
    return window.localStorage.getItem(name);
  } catch {
    return null;
  }
}

function setColorFiltersVisible(visible, shouldSave = true) {
  colorFiltersVisible = visible;
  galleryWorkspace.classList.toggle("filters-hidden", !visible);
  galleryFilters.toggleAttribute("hidden", !visible);
  toggleColorFilters.textContent = visible ? "Hide filters" : "Show filters";
  toggleColorFilters.setAttribute("aria-expanded", String(visible));

  if (shouldSave) {
    savePreference(FILTER_VISIBILITY_COOKIE, visible ? "shown" : "hidden");
  }
}

function compactId(id) {
  return `${id.slice(0, 4)}...${id.slice(-4)}`;
}

function uniqueColors(pixels = []) {
  return [...new Set(pixels.map((pixel) => normalizeColor(pixel.color)).filter(Boolean))];
}

function normalizeColor(color = "") {
  return color.trim().toUpperCase();
}

function parseHexColor(color) {
  const match = normalizeColor(color).match(/^#([0-9A-F]{6})$/);

  if (!match) {
    return null;
  }

  const value = match[1];

  return {
    r: Number.parseInt(value.slice(0, 2), 16),
    g: Number.parseInt(value.slice(2, 4), 16),
    b: Number.parseInt(value.slice(4, 6), 16)
  };
}

function colorDistance(colorA, colorB) {
  const rgbA = parseHexColor(colorA);
  const rgbB = parseHexColor(colorB);

  if (!rgbA || !rgbB) {
    return colorA === colorB ? 0 : Number.POSITIVE_INFINITY;
  }

  return Math.hypot(rgbA.r - rgbB.r, rgbA.g - rgbB.g, rgbA.b - rgbB.b);
}

function bucketKey(colors) {
  return colors.join("|");
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

function makeMetric(label, value, options = {}) {
  const item = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");

  term.textContent = label;

  if (options.copyValue) {
    const copyButton = document.createElement("button");
    copyButton.className = "metric-copy";
    copyButton.type = "button";
    copyButton.textContent = value;
    copyButton.title = `Copy ${options.copyValue}`;
    copyButton.setAttribute("aria-label", `Copy ${label} ${options.copyValue}`);
    copyButton.addEventListener("click", async () => {
      try {
        await copyTextToClipboard(options.copyValue);
        copyButton.dataset.copied = "true";
        copyButton.setAttribute("aria-label", `Copied ${label}`);
        window.setTimeout(() => {
          copyButton.dataset.copied = "false";
          copyButton.setAttribute("aria-label", `Copy ${label} ${options.copyValue}`);
        }, 1400);
      } catch {
        copyButton.setAttribute("aria-label", `Unable to copy ${label}`);
      }
    });
    description.appendChild(copyButton);
  } else {
    description.textContent = value;
  }

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

function renderPixelArtwork(record) {
  const width = record.size?.width || 8;
  const height = record.size?.height || 8;
  const pixelMap = new Map(
    (record.pixels || []).map((pixel) => [
      `${pixel.x}:${pixel.y}`,
      normalizeColor(pixel.color)
    ])
  );
  const artwork = document.createElement("div");
  artwork.className = "gallery-pixel-art";
  artwork.style.setProperty("--pixel-columns", width);
  artwork.style.setProperty("--pixel-rows", height);
  artwork.setAttribute("aria-label", `${record.title || "Square artwork"} color pixels`);

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const color = pixelMap.get(`${x}:${y}`) || "#FFFFFF";
      const bucket = colorBucketForColor(color);
      const state = colorFilterState(bucket.colors);
      const pixel = document.createElement("button");
      pixel.className = "gallery-pixel";
      pixel.type = "button";
      pixel.dataset.filterState = state;
      pixel.style.background = color;
      pixel.title = `${color} filter ${state}`;
      pixel.setAttribute("aria-label", `${color} pixel at ${x + 1}, ${y + 1}, ${state} filter`);
      pixel.addEventListener("click", (event) => {
        event.stopPropagation();
        cycleColorFilter(bucket.colors, color);
        applyFilters();
      });
      artwork.appendChild(pixel);
    }
  }

  return artwork;
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

function buildColorBuckets(records, threshold) {
  const buckets = [];
  const colorRecordIndexes = new Map();

  records.forEach((record, index) => {
    record.colors.forEach((color) => {
      if (!colorRecordIndexes.has(color)) {
        colorRecordIndexes.set(color, new Set());
      }

      colorRecordIndexes.get(color).add(index);
    });
  });

  colorUsage(records).forEach(([color, count]) => {
    let closestBucket = null;
    let closestDistance = Number.POSITIVE_INFINITY;

    buckets.forEach((bucket) => {
      const distance = colorDistance(color, bucket.representative);

      if (distance <= threshold && distance < closestDistance) {
        closestBucket = bucket;
        closestDistance = distance;
      }
    });

    if (closestBucket) {
      closestBucket.colors.push(color);
      closestBucket.count += count;
      return;
    }

    buckets.push({
      representative: color,
      colors: [color],
      count
    });
  });

  buckets.forEach((bucket) => {
    bucket.colors.sort((a, b) => a.localeCompare(b));
    bucket.key = bucketKey(bucket.colors);
    const recordIndexes = new Set();
    bucket.colors.forEach((color) => {
      colorRecordIndexes.get(color)?.forEach((index) => recordIndexes.add(index));
    });
    bucket.count = recordIndexes.size;
  });

  buckets.sort((a, b) =>
    b.count - a.count ||
    b.colors.length - a.colors.length ||
    a.representative.localeCompare(b.representative)
  );

  colorToBucket = new Map();
  buckets.forEach((bucket) => {
    bucket.colors.forEach((color) => {
      colorToBucket.set(color, bucket);
    });
  });

  colorBuckets = buckets;
}

function colorFilterState(colors) {
  if (colors.some((color) => includedColorSeeds.has(color))) {
    return "on";
  }

  if (colors.some((color) => excludedColorSeeds.has(color))) {
    return "off";
  }

  return "neutral";
}

function cycleColorFilter(colors, seed = colors[0]) {
  const state = colorFilterState(colors);

  if (state === "neutral") {
    includedColorSeeds.add(seed);
    colors.forEach((color) => excludedColorSeeds.delete(color));
    return;
  }

  if (state === "on") {
    colors.forEach((color) => includedColorSeeds.delete(color));
    excludedColorSeeds.add(seed);
    return;
  }

  colors.forEach((color) => excludedColorSeeds.delete(color));
}

function colorBucketForColor(color) {
  return colorToBucket.get(color) || {
    key: color,
    representative: color,
    colors: [color],
    count: 1
  };
}

function selectedColorGroups(seeds) {
  const groups = new Map();

  seeds.forEach((seed) => {
    const bucket = colorBucketForColor(seed);
    groups.set(bucket.key, bucket.colors);
  });

  return [...groups.values()];
}

function colorGroupMatches(record, colors) {
  return colors.some((color) => record.colorSet.has(color));
}

function updateSimilarityLabel() {
  const threshold = Number(colorSimilarity.value);
  colorSimilarityValue.textContent = threshold === 0 ? "Exact" : `+${threshold}`;
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const helper = document.createElement("textarea");
  helper.value = text;
  helper.setAttribute("readonly", "");
  helper.style.position = "fixed";
  helper.style.left = "-9999px";
  document.body.appendChild(helper);
  helper.select();
  document.execCommand("copy");
  helper.remove();
}

function renderColorFilters() {
  colorFilterList.replaceChildren();

  colorBuckets.forEach((bucket) => {
    const state = colorFilterState(bucket.colors);
    const color = bucket.representative;
    const colorLabel = bucket.colors.length === 1
      ? color
      : `${color} and ${bucket.colors.length - 1} similar colors`;
    const item = document.createElement("div");
    item.className = "color-filter-item";
    item.dataset.state = state;
    item.tabIndex = 0;
    item.setAttribute("role", "button");
    item.setAttribute("aria-label", `${colorLabel}, ${bucket.count} artworks, ${state} filter`);
    const toggleFilter = () => {
      cycleColorFilter(bucket.colors, bucket.representative);
      applyFilters();
    };
    item.addEventListener("click", toggleFilter);
    item.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }

      event.preventDefault();
      toggleFilter();
    });

    const swatch = document.createElement("span");
    swatch.className = "color-filter-swatch";
    swatch.style.background = bucket.colors.length === 1
      ? color
      : `linear-gradient(135deg, ${bucket.colors.slice(0, 6).join(", ")})`;
    swatch.setAttribute("aria-label", colorLabel);

    const copyButton = document.createElement("button");
    copyButton.className = "color-filter-copy";
    copyButton.type = "button";
    copyButton.title = `Copy ${color}`;
    copyButton.setAttribute("aria-label", `Copy ${color}`);
    copyButton.textContent = "Copy";
    copyButton.addEventListener("click", async (event) => {
      event.stopPropagation();

      try {
        await copyTextToClipboard(color);
        copyButton.dataset.copied = "true";
        copyButton.setAttribute("aria-label", `Copied ${color}`);
        window.setTimeout(() => {
          copyButton.dataset.copied = "false";
          copyButton.setAttribute("aria-label", `Copy ${color}`);
        }, 1100);
      } catch {
        copyButton.setAttribute("aria-label", `Unable to copy ${color}`);
      }
    });
    swatch.appendChild(copyButton);

    const total = document.createElement("span");
    total.className = "color-filter-count";
    total.textContent = String(bucket.count);
    total.setAttribute("aria-hidden", "true");
    swatch.appendChild(total);

    if (bucket.colors.length > 1) {
      const variations = document.createElement("span");
      variations.className = "color-filter-variations";
      variations.textContent = `+${bucket.colors.length - 1}`;
      variations.setAttribute("aria-hidden", "true");
      swatch.appendChild(variations);
    }

    item.appendChild(swatch);
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
  closeButton.textContent = "X";
  closeButton.addEventListener("click", closeInspector);

  const image = document.createElement("img");
  image.src = `art/${record.id}.svg`;
  image.alt = `${record.title || "Square artwork"} artwork`;
  image.decoding = "async";

  const content = document.createElement("div");
  content.className = "inspector-content";

  const title = document.createElement("h2");
  title.textContent = record.title || "Untitled square";

  const seed = document.createElement("p");
  seed.className = "inspector-seed";
  seed.textContent = record.seed || "No seed recorded";

  const heading = document.createElement("div");
  heading.className = "inspector-heading";
  heading.append(title, seed);

  const metrics = document.createElement("dl");
  metrics.className = "inspector-metrics";
  metrics.append(
    makeMetric("Grid", `${width} x ${height}`),
    makeMetric("Cells", String(record.pixels?.length || width * height)),
    makeMetric("Colors", String(colors.length)),
    makeMetric("Record", compactId(record.id), { copyValue: record.id })
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
    heading,
    metrics,
    reasoningLabel,
    reasoning,
    paletteLabel,
    renderSwatches(colors)
  );

  frame.append(jsonLink, closeButton, image, content);
  artInspector.appendChild(frame);

  openInspector();

  document.querySelectorAll(".gallery-card").forEach((card) => {
    const isSelected = card.dataset.id === selectedId;
    card.classList.toggle("is-selected", isSelected);
    card.toggleAttribute("aria-current", isSelected);
  });
}

function renderCard(record, index) {
  const card = document.createElement("article");
  card.className = "gallery-card";
  card.dataset.id = record.id;

  const meta = document.createElement("span");
  meta.className = "gallery-card-meta";

  const title = document.createElement("button");
  title.className = "gallery-card-title";
  title.type = "button";
  title.textContent = record.title || `Square ${index + 1}`;
  title.setAttribute("aria-label", `View details for ${record.title || `artwork ${index + 1}`}`);
  title.addEventListener("click", () => renderInspector(record));

  meta.append(title);
  card.append(renderPixelArtwork(record), meta);

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
  const hasColorFilters = includedColorSeeds.size > 0 || excludedColorSeeds.size > 0;

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
    card.toggleAttribute("aria-current", isSelected);
  });
}

function applyFilters() {
  const terms = gallerySearch.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const includedGroups = selectedColorGroups(includedColorSeeds);
  const excludedGroups = selectedColorGroups(excludedColorSeeds);
  filteredRecords = galleryRecords.filter((record) => {
    const matchesText = terms.every((term) => record.searchText.includes(term));
    const matchesIncluded = includedGroups.every((colors) => colorGroupMatches(record, colors));
    const matchesExcluded = excludedGroups.every((colors) => !colorGroupMatches(record, colors));

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
      colorSet: new Set(colors),
      searchText: recordSearchText({ ...record, colors })
    };
  });
  filteredRecords = galleryRecords;
  buildColorBuckets(galleryRecords, colorSimilarityThreshold);
  renderColorFilters();
  renderCurrentPage();
}

gallerySearch.addEventListener("input", applyFilters);
colorSimilarity.addEventListener("input", () => {
  colorSimilarityThreshold = Number(colorSimilarity.value);
  updateSimilarityLabel();
  buildColorBuckets(galleryRecords, colorSimilarityThreshold);
  savePreference(COLOR_SIMILARITY_COOKIE, String(colorSimilarityThreshold));
  applyFilters();
});
toggleColorFilters.addEventListener("click", () => {
  setColorFiltersVisible(!colorFiltersVisible);
});
clearColorFilters.addEventListener("click", () => {
  includedColorSeeds.clear();
  excludedColorSeeds.clear();
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

setColorFiltersVisible(readPreference(FILTER_VISIBILITY_COOKIE) !== "hidden", false);
const savedSimilarity = Number(readPreference(COLOR_SIMILARITY_COOKIE));

if (Number.isFinite(savedSimilarity)) {
  colorSimilarity.value = String(savedSimilarity);
  colorSimilarityThreshold = savedSimilarity;
}

updateSimilarityLabel();

renderGallery().catch((error) => {
  galleryCount.textContent = "Error";
  artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
});
