const GALLERY_MANIFEST_PATH = "art/manifest.json";
const MANIFEST_CACHE_BUSTER = Date.now().toString(36);
const SHOP_VARIANTS = {
  print: {
    label: "Art print",
    description: "8x8 art print",
    price: "$24",
    button: "Order print",
    paymentLinkKey: "print"
  },
  framed: {
    label: "12x12 framed print",
    description: "8x8 image area with mat",
    price: "$39",
    button: "Order framed print",
    paymentLinkKey: "framed"
  }
};
const FRAME_TYPES = {
  black: {
    label: "Black",
    image: "frames/black.jpg",
    swatch: "linear-gradient(135deg, #050505 0%, #242424 50%, #050505 100%)"
  },
  white: {
    label: "White",
    image: "frames/white.jpg",
    swatch: "linear-gradient(135deg, #f7f7f4 0%, #ffffff 48%, #d9d9d5 100%)"
  },
  natural: {
    label: "Natural",
    image: "frames/natural.jpg",
    swatch: "linear-gradient(135deg, #d8b889 0%, #f1d9aa 45%, #b98c55 100%)"
  },
  brown: {
    label: "Brown",
    image: "frames/brown.jpg",
    swatch: "linear-gradient(135deg, #4a2816 0%, #7a4a28 50%, #2d170d 100%)"
  },
  gold: {
    label: "Gold",
    image: "frames/gold.jpg",
    swatch: "linear-gradient(135deg, #b88924 0%, #f2d36b 48%, #8d6518 100%)"
  }
};
const PAYMENT_LINKS = window.SQUARE_PROJECT_PAYMENT_LINKS || {};

const artGrid = document.querySelector("#artGrid");
const artInspector = document.querySelector("#artInspector");
const galleryCount = document.querySelector("#galleryCount");
const gallerySearch = document.querySelector("#gallerySearch");
const galleryCategory = document.querySelector("#galleryCategory");
const galleryImageSize = document.querySelector("#galleryImageSize");
const galleryPagination = document.querySelector("#galleryPagination");
const galleryLoading = document.querySelector("#galleryLoading");
const galleryLoadingTitle = document.querySelector("#galleryLoadingTitle");
const galleryLoadingPercent = document.querySelector("#galleryLoadingPercent");
const galleryLoadingProgress = document.querySelector("#galleryLoadingProgress");
const galleryLoadingStep = document.querySelector("#galleryLoadingStep");
const galleryLoadingTime = document.querySelector("#galleryLoadingTime");
const galleryStats = document.querySelector("#galleryStats");
const colorFilterList = document.querySelector("#colorFilterList");
const clearColorFilters = document.querySelector("#clearColorFilters");
const toggleFilterOutlines = document.querySelector("#toggleFilterOutlines");
const galleryWorkspace = document.querySelector(".gallery-workspace");
const galleryFilters = document.querySelector("#galleryFilters");
const toggleColorFilters = document.querySelector("#toggleColorFilters");
const galleryAutoplayToggle = document.querySelector("#galleryAutoplayToggle");
const galleryAutoplaySpeed = document.querySelector("#galleryAutoplaySpeed");
const colorSimilarity = document.querySelector("#colorSimilarity");
const colorSimilarityValue = document.querySelector("#colorSimilarityValue");

const PAGE_SIZE_OPTIONS = [24, 48, 72, 96];
const COLOR_FILTER_RENDER_LIMIT = 600;
const CHUNK_RENDER_INTERVAL = 10;
const ALL_ARTWORK_PARALLEL_BATCH_SIZE = 6;
const AUTOPLAY_PAGE_TRANSITION = 180;
const PAGE_FLIP_TOTAL_MS = 1420;
const PAGE_FLIP_SWAP_MS = 420;
const PAGE_FLIP_EXIT_STAGGER_MS = 120;
const PAGE_FLIP_ENTER_STAGGER_MS = 440;
const AUTOPLAY_SPEED_OPTIONS = {
  "1x": 9000,
  "2x": 6500,
  "3x": 3500
};
const AUTOPLAY_SPEED_VALUES = Object.keys(AUTOPLAY_SPEED_OPTIONS);
const FILTER_VISIBILITY_COOKIE = "square_color_filters";
const FILTER_OUTLINES_COOKIE = "square_filter_outlines";
const COLOR_SIMILARITY_COOKIE = "square_color_similarity";
const GALLERY_IMAGE_SIZE_COOKIE = "square_gallery_image_size";
const GALLERY_PAGE_SIZE_COOKIE = "square_gallery_page_size";
const GALLERY_AUTOPLAY_SPEED_COOKIE = "square_gallery_autoplay_speed";
const ALL_ARTWORK_CATEGORY_ID = "all-artwork";
let galleryRecords = [];
let filteredRecords = [];
let colorBuckets = [];
let colorToBucket = new Map();
let precomputedColorBucketsByThreshold = {};
let precomputedColorBucketTotalsByThreshold = {};
let galleryTotalCount = 0;
let galleryCategories = [];
let activeCategory = null;
let pageSize = PAGE_SIZE_OPTIONS[0];
let currentPage = 1;
let selectedId = "";
let previousFocus = null;
let colorFiltersVisible = true;
let filterOutlinesVisible = true;
let colorSimilarityThreshold = Number(colorSimilarity.value);
let galleryImageSizeValue = Number(galleryImageSize.value);
let selectedShopVariant = "print";
let selectedFrameType = "black";
let galleryLoadComplete = false;
let galleryLoadToken = 0;
let pageRenderToken = 0;
let allArtworkMode = false;
let allArtworkNextCategoryIndex = 0;
let allArtworkLoading = false;
let allArtworkObserver = null;
let allArtworkSentinel = null;
let galleryAutoplayActive = false;
let galleryAutoplayTimer = null;
let galleryAutoplaySpeedValue = "1x";
const fullArtworkCache = new Map();
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
  toggleColorFilters.classList.toggle("filter-toggle-visible", visible);
  toggleColorFilters.classList.toggle("filter-toggle-hidden", !visible);
  toggleColorFilters.setAttribute("aria-expanded", String(visible));
  toggleColorFilters.setAttribute("aria-label", visible ? "Hide color filters" : "Show color filters");
  toggleColorFilters.title = visible ? "Hide color filters" : "Show color filters";

  if (shouldSave) {
    savePreference(FILTER_VISIBILITY_COOKIE, visible ? "shown" : "hidden");
  }
}

function setFilterOutlinesVisible(visible, shouldSave = true) {
  filterOutlinesVisible = visible;
  galleryWorkspace.classList.toggle("filter-outlines-hidden", !visible);
  galleryWorkspace.classList.toggle("filter-outlines-visible", visible);
  toggleFilterOutlines.setAttribute("aria-pressed", String(visible));
  toggleFilterOutlines.setAttribute(
    "aria-label",
    visible ? "Hide filtered pixel outlines" : "Show filtered pixel outlines"
  );
  toggleFilterOutlines.title = visible ? "Hide filtered pixel outlines" : "Show filtered pixel outlines";

  if (shouldSave) {
    savePreference(FILTER_OUTLINES_COOKIE, visible ? "shown" : "hidden");
  }
}

function setAnalysisControlsEnabled(enabled, { searchEnabled = enabled } = {}) {
  gallerySearch.disabled = !searchEnabled;
  colorSimilarity.disabled = !enabled;
  clearColorFilters.disabled = !enabled;
  toggleFilterOutlines.disabled = !enabled;
  toggleColorFilters.disabled = !enabled;
  galleryWorkspace.classList.toggle("is-lightweight-browse", !enabled);

  if (!searchEnabled) {
    gallerySearch.value = "";
  }

  if (!enabled) {
    colorFilterList.replaceChildren();
    setColorFiltersVisible(false, false);
  } else {
    setColorFiltersVisible(readPreference(FILTER_VISIBILITY_COOKIE) !== "hidden", false);
    setFilterOutlinesVisible(readPreference(FILTER_OUTLINES_COOKIE) !== "hidden", false);
  }
}

function clampGalleryImageSize(value) {
  const min = Number(galleryImageSize.min);
  const max = Number(galleryImageSize.max);
  const normalized = Number(value);

  if (!Number.isFinite(normalized)) {
    return Number(galleryImageSize.defaultValue);
  }

  return Math.min(Math.max(normalized, min), max);
}

function setGalleryImageSize(value, shouldSave = true) {
  galleryImageSizeValue = clampGalleryImageSize(value);
  galleryImageSize.value = String(galleryImageSizeValue);
  artGrid.style.setProperty("--gallery-card-min", `${galleryImageSizeValue}px`);

  if (shouldSave) {
    savePreference(GALLERY_IMAGE_SIZE_COOKIE, String(galleryImageSizeValue));
  }
}

function normalizePageSize(value) {
  const normalized = Number(value);
  return PAGE_SIZE_OPTIONS.includes(normalized) ? normalized : PAGE_SIZE_OPTIONS[0];
}

function setPageSize(value, shouldSave = true) {
  pageSize = normalizePageSize(value);

  if (shouldSave) {
    savePreference(GALLERY_PAGE_SIZE_COOKIE, String(pageSize));
  }
}

function normalizeAutoplaySpeed(value) {
  return Object.hasOwn(AUTOPLAY_SPEED_OPTIONS, value) ? value : "1x";
}

function setGalleryAutoplaySpeed(value, shouldSave = true) {
  galleryAutoplaySpeedValue = normalizeAutoplaySpeed(value);
  galleryAutoplaySpeed.textContent = galleryAutoplaySpeedValue;
  galleryAutoplaySpeed.setAttribute("aria-label", `Automatic browsing speed: ${galleryAutoplaySpeedValue}`);
  galleryAutoplaySpeed.title = `Automatic browsing speed: ${galleryAutoplaySpeedValue}`;

  if (shouldSave) {
    savePreference(GALLERY_AUTOPLAY_SPEED_COOKIE, galleryAutoplaySpeedValue);
  }

  if (galleryAutoplayActive) {
    scheduleGalleryAutoplay();
  }
}

function galleryAutoplayInterval() {
  return AUTOPLAY_SPEED_OPTIONS[galleryAutoplaySpeedValue];
}

function nextGalleryAutoplaySpeed() {
  const currentIndex = AUTOPLAY_SPEED_VALUES.indexOf(galleryAutoplaySpeedValue);
  return AUTOPLAY_SPEED_VALUES[(currentIndex + 1) % AUTOPLAY_SPEED_VALUES.length];
}

function getTotalPages() {
  return Math.max(1, Math.ceil(filteredRecords.length / pageSize));
}

function updateGalleryAutoplayControls(totalPages = getTotalPages()) {
  const isDisabled = totalPages <= 1;
  galleryAutoplayToggle.disabled = isDisabled;
  galleryAutoplayToggle.classList.toggle("is-playing", galleryAutoplayActive);
  galleryAutoplayToggle.setAttribute("aria-pressed", String(galleryAutoplayActive));
  galleryAutoplayToggle.setAttribute(
    "aria-label",
    galleryAutoplayActive ? "Stop automatic page browsing" : "Play automatic page browsing"
  );
  galleryAutoplayToggle.title = galleryAutoplayActive
    ? "Stop automatic page browsing"
    : "Play automatic page browsing";

  galleryAutoplaySpeed.disabled = isDisabled;
}

function clearGalleryAutoplayTimer() {
  if (galleryAutoplayTimer) {
    window.clearTimeout(galleryAutoplayTimer);
    galleryAutoplayTimer = null;
  }
}

function stopGalleryAutoplay() {
  galleryAutoplayActive = false;
  clearGalleryAutoplayTimer();
  artGrid.classList.remove("is-autoplay-advance");
  updateGalleryAutoplayControls();
}

function scheduleGalleryAutoplay(totalPages = getTotalPages()) {
  clearGalleryAutoplayTimer();

  if (!galleryAutoplayActive || totalPages <= 1) {
    return;
  }

  galleryAutoplayTimer = window.setTimeout(() => {
    const latestTotalPages = getTotalPages();

    if (!galleryAutoplayActive || latestTotalPages <= 1) {
      stopGalleryAutoplay();
      renderCurrentPage();
      return;
    }

    artGrid.classList.add("is-autoplay-advance");
    window.setTimeout(() => {
      if (!galleryAutoplayActive) {
        return;
      }

      currentPage = currentPage >= latestTotalPages ? 1 : currentPage + 1;
      renderCurrentPage();
    }, AUTOPLAY_PAGE_TRANSITION);
  }, galleryAutoplayInterval());
}

function startGalleryAutoplay(totalPages = getTotalPages()) {
  if (totalPages <= 1) {
    stopGalleryAutoplay();
    return;
  }

  galleryAutoplayActive = true;
  updateGalleryAutoplayControls(totalPages);
  scheduleGalleryAutoplay(totalPages);
}

function reducedMotionPreferred() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function clearPageTransitionClasses(cards) {
  cards.forEach((card) => {
    card.classList.remove("is-page-exiting", "is-page-entering");
    card.style.removeProperty("--page-flip-delay");
  });
}

function applyPageTransitionOrder(cards, staggerMs) {
  const lastIndex = Math.max(cards.length - 1, 1);

  cards.forEach((card, index) => {
    const delay = Math.round((staggerMs * index) / lastIndex);
    card.style.setProperty("--page-flip-delay", `${delay}ms`);
  });
}

function updateSelectedCards() {
  document.querySelectorAll(".gallery-card").forEach((card) => {
    const isSelected = card.dataset.id === selectedId;
    card.classList.toggle("is-selected", isSelected);
    card.toggleAttribute("aria-current", isSelected);
  });
}

function renderPageCards(pageRecords, start, token) {
  const hasExistingCards = artGrid.querySelector(".gallery-card");
  const shouldAnimate = hasExistingCards && !reducedMotionPreferred();

  const finishRender = () => {
    if (token !== pageRenderToken) {
      return;
    }

    artGrid.replaceChildren(...pageRecords.map((record, index) => renderCard(record, start + index)));
    const newCards = [...artGrid.querySelectorAll(".gallery-card")];

    if (shouldAnimate) {
      applyPageTransitionOrder(newCards, PAGE_FLIP_ENTER_STAGGER_MS);
      newCards.forEach((card) => card.classList.add("is-page-entering"));
      artGrid.classList.add("is-page-transitioning");
      window.setTimeout(() => {
        clearPageTransitionClasses(newCards);
        artGrid.classList.remove("is-page-transitioning");
      }, PAGE_FLIP_TOTAL_MS - PAGE_FLIP_SWAP_MS);
    }

    hydrateVisiblePixelArtwork(pageRecords, token);
    updateSelectedCards();
  };

  if (!shouldAnimate) {
    finishRender();
    return;
  }

  const oldCards = [...artGrid.querySelectorAll(".gallery-card")];
  artGrid.classList.add("is-page-transitioning");
  applyPageTransitionOrder(oldCards, PAGE_FLIP_EXIT_STAGGER_MS);
  oldCards.forEach((card) => card.classList.add("is-page-exiting"));
  window.setTimeout(finishRender, PAGE_FLIP_SWAP_MS);
}

function stopAllArtworkObserver() {
  if (allArtworkObserver) {
    allArtworkObserver.disconnect();
    allArtworkObserver = null;
  }

  if (allArtworkSentinel) {
    allArtworkSentinel.remove();
    allArtworkSentinel = null;
  }
}

function resetAllArtworkModeState() {
  stopAllArtworkObserver();
  allArtworkNextCategoryIndex = 0;
  allArtworkLoading = false;
}

function allArtworkCategory() {
  return {
    id: ALL_ARTWORK_CATEGORY_ID,
    label: "All artwork",
    description: "Loads every category and builds full search and color filters",
    count: galleryTotalCount
  };
}

function isAllArtworkCategory(category) {
  return category?.id === ALL_ARTWORK_CATEGORY_ID;
}

function compactId(id) {
  return `${id.slice(0, 4)}...${id.slice(-4)}`;
}

function formatStatNumber(value) {
  return Number.isFinite(value)
    ? new Intl.NumberFormat("en-US").format(value)
    : "...";
}

function collectionColorFamilyTotal(manifest) {
  const totals = manifest?.indexes?.colorBucketTotals;

  if (!totals || typeof totals !== "object") {
    return NaN;
  }

  const broadestThreshold = Object.keys(totals)
    .map(Number)
    .filter(Number.isFinite)
    .sort((a, b) => b - a)[0];

  return Number.isFinite(broadestThreshold) ? totals[String(broadestThreshold)] : NaN;
}

function renderCollectionStats(manifest, artworkIds) {
  if (!galleryStats) {
    return;
  }

  const artworkCount = Number.isFinite(manifest?.count) ? manifest.count : artworkIds.length;
  const exactColors = manifest?.indexes?.colorBucketTotals?.["0"];
  const colorFamilies = collectionColorFamilyTotal(manifest);
  const pixelCells = artworkCount * 64;
  const stats = {
    artworks: artworkCount,
    colors: exactColors,
    families: colorFamilies,
    pixels: pixelCells
  };

  Object.entries(stats).forEach(([key, value]) => {
    const stat = galleryStats.querySelector(`[data-stat="${key}"]`);

    if (stat) {
      stat.textContent = formatStatNumber(value);
    }
  });
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

async function fetchGalleryManifest() {
  const manifestUrl = `${GALLERY_MANIFEST_PATH}?v=${MANIFEST_CACHE_BUSTER}`;
  const response = await fetch(manifestUrl, { cache: "no-store" });

  if (!response.ok) {
    throw new Error("Unable to load art manifest.");
  }

  return response.json();
}

async function fetchArtworkIds() {
  const manifest = await fetchGalleryManifest();
  const ids = Array.isArray(manifest) ? manifest : manifest.artworkIds;

  if (!Array.isArray(ids) || ids.length === 0) {
    throw new Error("Art manifest does not include any artwork ids.");
  }

  return ids;
}

async function fetchArtwork(id) {
  if (fullArtworkCache.has(id)) {
    return fullArtworkCache.get(id);
  }

  const response = await fetch(`art/${id}.json`);

  if (!response.ok) {
    throw new Error(`Unable to load ${id}.json`);
  }

  const record = await response.json();
  fullArtworkCache.set(id, record);
  return record;
}

async function fetchArtworkChunk(chunk) {
  const separator = chunk.path.includes("?") ? "&" : "?";
  const response = await fetch(`${chunk.path}${separator}v=${MANIFEST_CACHE_BUSTER}`);

  if (!response.ok) {
    throw new Error(`Unable to load ${chunk.path}`);
  }

  const data = await response.json();
  return Array.isArray(data) ? data : data.records;
}

async function fetchCategoryRecords(category) {
  if (!category?.path) {
    return [];
  }

  const separator = category.path.includes("?") ? "&" : "?";
  const response = await fetch(`${category.path}${separator}v=${MANIFEST_CACHE_BUSTER}`);

  if (!response.ok) {
    throw new Error(`Unable to load ${category.label || "gallery category"}.`);
  }

  const data = await response.json();
  return Array.isArray(data) ? data : data.records;
}

async function mapInParallelBatches(items, batchSize, mapper) {
  const results = new Array(items.length);

  for (let start = 0; start < items.length; start += batchSize) {
    const batch = items.slice(start, start + batchSize);
    const batchResults = await Promise.all(batch.map((item, batchIndex) => mapper(item, start + batchIndex)));
    batchResults.forEach((result, batchIndex) => {
      results[start + batchIndex] = result;
    });
  }

  return results;
}

function yieldToBrowser() {
  return new Promise((resolve) => {
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(resolve, { timeout: 120 });
      return;
    }

    window.setTimeout(resolve, 0);
  });
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

function renderArtworkImage(record) {
  const image = document.createElement("img");
  image.src = `art/${record.id}.svg`;
  image.alt = `${record.title || "Square artwork"} artwork`;
  image.decoding = "async";
  return image;
}

function pixelColorAt(record, x, y) {
  const match = (record.pixels || []).find((pixel) => pixel.x === x && pixel.y === y);
  return match ? normalizeColor(match.color) : "";
}

async function filterByImagePixel(record, event) {
  const target = event.currentTarget;
  const width = record.size?.width || 8;
  const height = record.size?.height || 8;
  const rect = target.getBoundingClientRect();
  const x = Math.min(width - 1, Math.max(0, Math.floor(((event.clientX - rect.left) / rect.width) * width)));
  const y = Math.min(height - 1, Math.max(0, Math.floor(((event.clientY - rect.top) / rect.height) * height)));
  const fullRecord = await getFullArtworkRecord(record);
  const color = pixelColorAt(fullRecord, x, y);

  if (!color) {
    return;
  }

  const bucket = colorBucketForColor(color);
  cycleColorFilter(bucket.colors, color);
  applyFilters();
}

function renderFramePreview(record) {
  const preview = document.createElement("div");
  preview.className = "frame-preview";
  preview.dataset.variant = selectedShopVariant;
  preview.dataset.frameType = selectedFrameType;

  const printStage = document.createElement("div");
  printStage.className = "print-preview-stage";
  printStage.appendChild(renderArtworkImage(record));

  const framedStage = document.createElement("div");
  framedStage.className = "framed-preview-stage";

  const framedArt = renderArtworkImage(record);
  framedArt.className = "framed-artwork";

  const frameImage = document.createElement("img");
  frameImage.className = "frame-shell";
  frameImage.src = FRAME_TYPES[selectedFrameType].image;
  frameImage.alt = "";
  frameImage.decoding = "async";
  frameImage.setAttribute("aria-hidden", "true");

  framedStage.append(framedArt, frameImage);
  preview.append(printStage, framedStage);

  preview.frameImage = frameImage;
  return preview;
}

function checkoutReference(record, variant, frameType = "") {
  const frameColor = variant === "framed" ? frameType : "none";
  const reference = `art_${record.id}_variant_${variant}_frame_${frameColor}`
    .replace(/[^a-zA-Z0-9_-]/g, "_");
  return reference.slice(0, 200);
}

function paymentLinkForVariant(variant, record = null, frameType = selectedFrameType) {
  const variantConfig = SHOP_VARIANTS[variant];
  const artworkLinks = record && PAYMENT_LINKS.artworks && PAYMENT_LINKS.artworks[record.id];
  const artworkLink = artworkLinks && artworkLinks[variant];

  if (variant === "framed" && artworkLink && typeof artworkLink === "object") {
    return (artworkLink[frameType] || artworkLink[selectedFrameType] || "").trim();
  }

  if (typeof artworkLink === "string") {
    return artworkLink.trim();
  }

  return (variantConfig && PAYMENT_LINKS[variantConfig.paymentLinkKey] || "").trim();
}

function paymentLinkUrl(record, variant, frameType = selectedFrameType) {
  const url = new URL(paymentLinkForVariant(variant, record, frameType));
  url.searchParams.set("client_reference_id", checkoutReference(record, variant, frameType));
  url.searchParams.set("utm_source", "square_project");
  url.searchParams.set("utm_medium", "gallery");
  url.searchParams.set("utm_content", variant);
  url.searchParams.set("utm_term", variant === "framed" ? frameType : "none");
  return url.toString();
}

function checkoutStatusForVariant(variant, record = null, frameType = selectedFrameType) {
  return paymentLinkForVariant(variant, record, frameType)
    ? "Ready for Stripe payment link."
    : "Payment link is not configured.";
}

function checkoutToneForVariant(variant, record = null, frameType = selectedFrameType) {
  return paymentLinkForVariant(variant, record, frameType) ? "neutral" : "error";
}

function startCheckout(record, variant, frameType, status) {
  const variantConfig = SHOP_VARIANTS[variant];

  if (!variantConfig) {
    status.textContent = "Choose a valid order option.";
    status.dataset.tone = "error";
    return;
  }

  try {
    if (!paymentLinkForVariant(variant, record, frameType)) {
      throw new Error("Payment link is not configured.");
    }

    status.textContent = "Opening Stripe payment link.";
    status.dataset.tone = "neutral";
    window.location.href = paymentLinkUrl(record, variant, frameType);
  } catch (error) {
    status.textContent = error.message;
    status.dataset.tone = "error";
  }
}

function updateFramePreview(preview, frameType) {
  preview.dataset.frameType = frameType;

  if (preview.frameImage) {
    preview.frameImage.src = FRAME_TYPES[frameType].image;
  }
}

function renderOrderPanel(record, preview) {
  const panel = document.createElement("section");
  panel.className = "order-panel";
  panel.setAttribute("aria-label", "Order artwork");

  const heading = document.createElement("h3");
  heading.textContent = "Order";

  const options = document.createElement("div");
  options.className = "order-options";

  const frameChooser = document.createElement("div");
  frameChooser.className = "frame-type-options";
  frameChooser.hidden = selectedShopVariant !== "framed";

  const frameChooserLabel = document.createElement("h4");
  frameChooserLabel.textContent = "Frame type";

  const frameButtons = document.createElement("div");
  frameButtons.className = "frame-type-list";

  Object.entries(FRAME_TYPES).forEach(([frameType, config]) => {
    const frameButton = document.createElement("button");
    frameButton.className = "frame-type-option";
    frameButton.type = "button";
    frameButton.dataset.frameType = frameType;
    frameButton.setAttribute("aria-pressed", String(frameType === selectedFrameType));
    frameButton.setAttribute("aria-label", `${config.label} frame`);

    const swatch = document.createElement("span");
    swatch.style.background = config.swatch;
    swatch.setAttribute("aria-hidden", "true");

    const label = document.createElement("strong");
    label.textContent = config.label;

    frameButton.append(swatch, label);
    frameButton.addEventListener("click", () => {
      selectedFrameType = frameType;
      updateFramePreview(preview, frameType);
      frameButtons.querySelectorAll(".frame-type-option").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.frameType === frameType));
      });
      status.textContent = checkoutStatusForVariant(selectedShopVariant, record, frameType);
      status.dataset.tone = checkoutToneForVariant(selectedShopVariant, record, frameType);
      checkoutButton.disabled = !paymentLinkForVariant(selectedShopVariant, record, frameType);
    });
    frameButtons.appendChild(frameButton);
  });

  frameChooser.append(frameChooserLabel, frameButtons);

  Object.entries(SHOP_VARIANTS).forEach(([variant, config]) => {
    const option = document.createElement("button");
    option.className = "order-option";
    option.type = "button";
    option.dataset.variant = variant;
    option.setAttribute("aria-pressed", String(variant === selectedShopVariant));

    const label = document.createElement("span");
    label.textContent = config.label;

    const detail = document.createElement("small");
    detail.textContent = config.description;

    const price = document.createElement("strong");
    price.textContent = config.price;

    option.append(label, detail, price);
    option.addEventListener("click", () => {
      selectedShopVariant = variant;
      preview.dataset.variant = variant;
      updateFramePreview(preview, selectedFrameType);
      frameChooser.hidden = variant !== "framed";
      options.querySelectorAll(".order-option").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.variant === variant));
      });
      checkoutButton.textContent = SHOP_VARIANTS[variant].button;
      status.textContent = checkoutStatusForVariant(variant, record, selectedFrameType);
      status.dataset.tone = checkoutToneForVariant(variant, record, selectedFrameType);
      checkoutButton.disabled = !paymentLinkForVariant(variant, record, selectedFrameType);
    });
    options.appendChild(option);
  });

  const checkoutButton = document.createElement("button");
  checkoutButton.className = "button primary checkout-button";
  checkoutButton.type = "button";
  checkoutButton.textContent = SHOP_VARIANTS[selectedShopVariant].button;
  checkoutButton.disabled = !paymentLinkForVariant(selectedShopVariant, record, selectedFrameType);

  const status = document.createElement("p");
  status.className = "checkout-status";
  status.dataset.tone = checkoutToneForVariant(selectedShopVariant, record, selectedFrameType);
  status.textContent = checkoutStatusForVariant(selectedShopVariant, record, selectedFrameType);

  checkoutButton.addEventListener(
    "click",
    () => startCheckout(record, selectedShopVariant, selectedFrameType, status),
  );

  panel.append(heading, options, frameChooser, checkoutButton, status);
  return panel;
}

function colorUsage(records) {
  const usage = new Map();

  records.forEach((record) => {
    (record.colors || []).forEach((color) => {
      usage.set(color, (usage.get(color) || 0) + 1);
    });
  });

  return [...usage.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function buildColorBuckets(records, threshold) {
  if (records.length === galleryTotalCount && usePrecomputedColorBuckets(threshold)) {
    return;
  }

  const buckets = [];

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
    bucket.count = 0;
  });

  const colorToBucketKey = new Map();
  buckets.forEach((bucket) => {
    bucket.colors.forEach((color) => colorToBucketKey.set(color, bucket.key));
  });

  const bucketByKey = new Map(buckets.map((bucket) => [bucket.key, bucket]));
  records.forEach((record) => {
    const matchedBucketKeys = new Set();
    (record.colors || []).forEach((color) => {
      const key = colorToBucketKey.get(color);

      if (key) {
        matchedBucketKeys.add(key);
      }
    });
    matchedBucketKeys.forEach((key) => {
      bucketByKey.get(key).count += 1;
    });
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

function setColorBucketLookup(buckets) {
  colorToBucket = new Map();
  buckets.forEach((bucket) => {
    bucket.colors.forEach((color) => {
      colorToBucket.set(color, bucket);
    });
  });

  colorBuckets = buckets;
}

function usePrecomputedColorBuckets(threshold) {
  const cachedBuckets = precomputedColorBucketsByThreshold[String(threshold)];

  if (!Array.isArray(cachedBuckets)) {
    return false;
  }

  setColorBucketLookup(cachedBuckets.map((bucket) => ({
    ...bucket,
    colors: Array.isArray(bucket.colors) ? bucket.colors : []
  })));
  return true;
}

function hasPrecomputedColorBuckets() {
  return Object.keys(precomputedColorBucketsByThreshold).length > 0;
}

function colorBucketTotalCount() {
  const cachedTotal = precomputedColorBucketTotalsByThreshold[String(colorSimilarityThreshold)];
  return Number.isFinite(cachedTotal) ? cachedTotal : colorBuckets.length;
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

function formatRemainingTime(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 1) {
    return "Less than a second remaining.";
  }

  const roundedSeconds = Math.ceil(seconds);

  if (roundedSeconds < 60) {
    return `About ${roundedSeconds} seconds remaining.`;
  }

  const minutes = Math.ceil(roundedSeconds / 60);
  return `About ${minutes} minute${minutes === 1 ? "" : "s"} remaining.`;
}

function updateGalleryLoading({
  title = "Preparing the collection",
  step = "Starting gallery load.",
  loaded = 0,
  total = 0,
  startedAt = performance.now()
} = {}) {
  const percent = total > 0 ? Math.round((loaded / total) * 100) : 0;
  const elapsedSeconds = Math.max((performance.now() - startedAt) / 1000, 0);
  const averageSeconds = loaded > 0 ? elapsedSeconds / loaded : null;
  const remainingSeconds = averageSeconds === null ? null : averageSeconds * Math.max(total - loaded, 0);

  galleryLoading.hidden = false;
  galleryLoadingTitle.textContent = title;
  galleryLoadingPercent.textContent = `${percent}%`;
  galleryLoadingProgress.value = percent;
  galleryLoadingProgress.textContent = `${percent}%`;
  galleryLoadingStep.textContent = step;
  galleryLoadingTime.textContent = total > 0 && loaded > 0
    ? `${loaded} of ${total} records loaded. ${formatRemainingTime(remainingSeconds)}`
    : "Estimating time remaining.";
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
  const totalBucketCount = colorBucketTotalCount();

  colorBuckets.slice(0, COLOR_FILTER_RENDER_LIMIT).forEach((bucket) => {
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

  if (totalBucketCount > COLOR_FILTER_RENDER_LIMIT) {
    const overflow = document.createElement("p");
    overflow.className = "filter-overflow";
    overflow.textContent = `${totalBucketCount - COLOR_FILTER_RENDER_LIMIT} lower-frequency colors hidden. Search still covers every loaded artwork.`;
    colorFilterList.appendChild(overflow);
  }
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

  const preview = renderFramePreview(record);

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
    renderOrderPanel(record, preview),
    reasoningLabel,
    reasoning,
    paletteLabel,
    renderSwatches(colors)
  );

  frame.append(jsonLink, closeButton, preview, content);
  artInspector.appendChild(frame);

  openInspector();

  document.querySelectorAll(".gallery-card").forEach((card) => {
    const isSelected = card.dataset.id === selectedId;
    card.classList.toggle("is-selected", isSelected);
    card.toggleAttribute("aria-current", isSelected);
  });
}

function setArtworkUrl(record) {
  const url = new URL(window.location.href);
  url.searchParams.set("art", record.id);
  window.history.replaceState({}, "", url);
}

async function getFullArtworkRecord(record) {
  if (record.pixels) {
    return record;
  }

  const fullRecord = await fetchArtwork(record.id);
  const colors = (fullRecord.colors || uniqueColors(fullRecord.pixels))
    .map(normalizeColor)
    .filter(Boolean);
  return {
    ...record,
    ...fullRecord,
    colors,
    colorSet: new Set(colors),
    searchText: recordSearchText({ ...fullRecord, colors })
  };
}

async function openGalleryRecord(record, { updateUrl = false } = {}) {
  const recordIndex = filteredRecords.findIndex((item) => item.id === record.id);

  if (!allArtworkMode && recordIndex >= 0) {
    currentPage = Math.floor(recordIndex / pageSize) + 1;
    renderCurrentPage();
  }

  if (updateUrl) {
    setArtworkUrl(record);
  }

  const fullRecord = await getFullArtworkRecord(record);
  renderInspector(fullRecord);

  const selectedCard = [...document.querySelectorAll(".gallery-card")]
    .find((card) => card.dataset.id === record.id);
  document.querySelectorAll(".gallery-card").forEach((card) => {
    const isSelected = card.dataset.id === record.id;
    card.classList.toggle("is-selected", isSelected);
    card.toggleAttribute("aria-current", isSelected);
  });
  selectedCard?.scrollIntoView({ block: "center", behavior: "smooth" });
}

function renderCardImage(record) {
  const image = document.createElement("img");
  image.className = "gallery-card-image";
  image.src = `art/${record.id}.svg`;
  image.alt = `${record.title || "Square artwork"} artwork`;
  image.title = "Click a pixel to filter by its color";
  image.decoding = "async";
  image.loading = "lazy";
  image.addEventListener("click", (event) => {
    event.stopPropagation();
    filterByImagePixel(record, event).catch((error) => {
      artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
    });
  });
  return image;
}

function cachedFullArtworkRecord(record) {
  if (record.pixels) {
    return record;
  }

  const cachedRecord = fullArtworkCache.get(record.id);

  if (!cachedRecord?.pixels) {
    return null;
  }

  return {
    ...record,
    ...cachedRecord
  };
}

function renderCardArtwork(record) {
  const fullRecord = cachedFullArtworkRecord(record);
  return fullRecord ? renderPixelArtwork(fullRecord) : renderCardImage(record);
}

function renderCard(record, index) {
  const card = document.createElement("article");
  card.className = "gallery-card";
  card.dataset.id = record.id;

  const meta = document.createElement("span");
  meta.className = "gallery-card-meta";

  const title = document.createElement("a");
  title.className = "gallery-card-title";
  title.href = record.pagePath || `artwork/${record.id}/`;
  title.textContent = record.title || `Square ${index + 1}`;
  title.setAttribute("aria-label", `Open page for ${record.title || `artwork ${index + 1}`}`);

  const quickView = document.createElement("button");
  quickView.className = "gallery-card-quick-view";
  quickView.type = "button";
  quickView.textContent = "Quick view";
  quickView.setAttribute("aria-label", `Quick view ${record.title || `artwork ${index + 1}`}`);
  quickView.addEventListener("click", () => {
    openGalleryRecord(record, { updateUrl: true }).catch((error) => {
      artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
    });
  });

  meta.append(title, quickView);
  card.append(renderCardArtwork(record), meta);

  return card;
}

function renderLightweightCard(record, index) {
  const card = document.createElement("article");
  card.className = "gallery-card gallery-card-lightweight";
  card.dataset.id = record.id;

  const imageLink = document.createElement("a");
  imageLink.className = "gallery-card-image-button";
  imageLink.href = record.pagePath || `artwork/${record.id}/`;
  imageLink.setAttribute("aria-label", `Open page for ${record.title || `artwork ${index + 1}`}`);
  imageLink.appendChild(renderArtworkImage(record));

  const meta = document.createElement("span");
  meta.className = "gallery-card-meta";

  const title = document.createElement("a");
  title.className = "gallery-card-title";
  title.href = record.pagePath || `artwork/${record.id}/`;
  title.textContent = record.title || `Square ${index + 1}`;
  title.setAttribute("aria-label", `Open page for ${record.title || `artwork ${index + 1}`}`);

  const quickView = document.createElement("button");
  quickView.className = "gallery-card-quick-view";
  quickView.type = "button";
  quickView.textContent = "Quick view";
  quickView.setAttribute("aria-label", `Quick view ${record.title || `artwork ${index + 1}`}`);
  quickView.addEventListener("click", () => {
    openGalleryRecord(record, { updateUrl: true }).catch((error) => {
      artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
    });
  });

  meta.append(title, quickView);
  card.append(imageLink, meta);

  return card;
}

async function hydrateVisiblePixelArtwork(records, token) {
  await Promise.all(records.map(async (record) => {
    if (record.pixels || fullArtworkCache.has(record.id)) {
      return;
    }

    try {
      await fetchArtwork(record.id);
    } catch {
      // The image fallback remains clickable if the JSON cannot be fetched.
    }
  }));

  if (token !== pageRenderToken) {
    return;
  }

  records.forEach((record) => {
    const card = artGrid.querySelector(`.gallery-card[data-id="${record.id}"]`);
    const fallbackImage = card?.querySelector(".gallery-card-image");
    const fullRecord = cachedFullArtworkRecord(record);

    if (!card || !fallbackImage || !fullRecord) {
      return;
    }

    fallbackImage.replaceWith(renderPixelArtwork(fullRecord));
  });
}

function renderPagination(totalPages) {
  galleryPagination.replaceChildren();

  const pageStart = (currentPage - 1) * pageSize + 1;
  const pageEnd = Math.min(currentPage * pageSize, filteredRecords.length);

  const summary = document.createElement("p");
  summary.className = "pagination-summary";
  summary.textContent = `Showing ${pageStart}-${pageEnd} of ${filteredRecords.length}`;

  const controls = document.createElement("div");
  controls.className = "pagination-controls";

  const previous = document.createElement("button");
  previous.type = "button";
  previous.className = "pagination-arrow";
  previous.textContent = "Prev";
  previous.setAttribute("aria-label", "Previous page");
  previous.disabled = currentPage === 1;
  previous.addEventListener("click", () => {
    currentPage -= 1;
    renderCurrentPage();
  });

  const pageNumbers = document.createElement("div");
  pageNumbers.className = "pagination-pages";
  pageNumbers.setAttribute("aria-label", `Page ${currentPage} of ${totalPages}`);

  paginationItems(currentPage, totalPages).forEach((item) => {
    if (item === "...") {
      const ellipsis = document.createElement("span");
      ellipsis.className = "pagination-ellipsis";
      ellipsis.textContent = "...";
      pageNumbers.appendChild(ellipsis);
      return;
    }

    const pageButton = document.createElement("button");
    pageButton.type = "button";
    pageButton.className = "pagination-page";
    pageButton.textContent = String(item);
    pageButton.setAttribute("aria-label", `Page ${item}`);

    if (item === currentPage) {
      pageButton.setAttribute("aria-current", "page");
      pageButton.disabled = true;
    }

    pageButton.addEventListener("click", () => {
      currentPage = item;
      renderCurrentPage();
    });
    pageNumbers.appendChild(pageButton);
  });

  const pageSizeLabel = document.createElement("label");
  pageSizeLabel.className = "page-size-control";
  const pageSizeText = document.createElement("span");
  pageSizeText.textContent = "Per page";

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
    setPageSize(event.target.value);
    currentPage = 1;
    renderCurrentPage();
  });
  pageSizeLabel.append(pageSizeText, pageSizeSelect);

  const next = document.createElement("button");
  next.type = "button";
  next.className = "pagination-arrow";
  next.textContent = "Next";
  next.setAttribute("aria-label", "Next page");
  next.disabled = currentPage === totalPages;
  next.addEventListener("click", () => {
    currentPage += 1;
    renderCurrentPage();
  });

  if (totalPages > 1) {
    controls.append(previous, pageNumbers, next);
    galleryPagination.append(summary, controls, pageSizeLabel);
  } else {
    galleryPagination.append(summary, pageSizeLabel);
  }
}

function paginationItems(page, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const items = [1];
  const windowStart = Math.max(2, page - 1);
  const windowEnd = Math.min(totalPages - 1, page + 1);

  if (windowStart > 2) {
    items.push("...");
  }

  for (let index = windowStart; index <= windowEnd; index += 1) {
    items.push(index);
  }

  if (windowEnd < totalPages - 1) {
    items.push("...");
  }

  items.push(totalPages);
  return items;
}

function renderCategoryOptions() {
  galleryCategory.replaceChildren();

  [allArtworkCategory(), ...galleryCategories].forEach((category) => {
    const option = document.createElement("option");
    option.value = category.id;
    option.textContent = `${category.label} (${category.count})`;
    option.selected = category.id === activeCategory?.id;

    if (category.description) {
      option.title = category.description;
    }

    galleryCategory.appendChild(option);
  });
}

function categoryForArtworkId(artworkId) {
  return galleryCategories.find((category) => Array.isArray(category.ids) && category.ids.includes(artworkId));
}

function setGalleryUrlCategory(category) {
  if (!category) {
    return;
  }

  const url = new URL(window.location.href);
  url.searchParams.set("category", category.id);
  window.history.replaceState({}, "", url);
}

function normalizeLightweightRecord(record) {
  return {
    id: record.id,
    title: record.title || compactId(record.id),
    path: record.path,
    pagePath: record.pagePath,
    searchText: record.searchText || recordSearchText(record)
  };
}

function renderAllArtworkStatus() {
  const loaded = galleryRecords.length;
  const total = galleryTotalCount || loaded;
  const isComplete = galleryLoadComplete && loaded >= total;
  galleryCount.textContent = isComplete
    ? `${loaded} artworks loaded`
    : `${loaded} of ${total} artworks loaded`;
  galleryPagination.innerHTML = `<p class="pagination-summary">${
    isComplete ? "All artwork loaded." : "Scroll to load more artwork."
  }</p>`;
}

async function loadNextAllArtworkCategory(loadToken) {
  if (allArtworkLoading || galleryLoadComplete || !allArtworkMode) {
    return;
  }

  const category = galleryCategories[allArtworkNextCategoryIndex];

  if (!category) {
    galleryLoadComplete = true;
    galleryLoading.hidden = true;
    renderAllArtworkStatus();
    stopAllArtworkObserver();
    return;
  }

  allArtworkLoading = true;
  updateGalleryLoading({
    title: "Loading all artwork",
    step: `Requesting ${category.label}.`,
    loaded: galleryRecords.length,
    total: galleryTotalCount
  });

  try {
    const records = await fetchCategoryRecords(category);

    if (loadToken !== galleryLoadToken || !allArtworkMode) {
      return;
    }

    const startIndex = galleryRecords.length;
    const lightRecords = records.map(normalizeLightweightRecord);
    galleryRecords.push(...lightRecords);
    if (gallerySearch.value.trim()) {
      applyFilters({ renderFilters: false });
    } else {
      filteredRecords = galleryRecords;
      artGrid.append(...lightRecords.map((record, index) => renderLightweightCard(record, startIndex + index)));
    }
    allArtworkNextCategoryIndex += 1;
    galleryLoadComplete = galleryRecords.length >= galleryTotalCount || allArtworkNextCategoryIndex >= galleryCategories.length;
    renderAllArtworkStatus();
    updateGalleryLoading({
      title: "Loading all artwork",
      step: galleryLoadComplete ? "All artwork loaded." : "Ready for more scrolling.",
      loaded: galleryRecords.length,
      total: galleryTotalCount
    });

    if (galleryLoadComplete) {
      galleryLoading.hidden = true;
      stopAllArtworkObserver();
    } else {
      galleryLoading.hidden = true;
    }
  } catch (error) {
    galleryLoading.hidden = true;
    galleryPagination.innerHTML = `<p class="carousel-error">${error.message}</p>`;
  } finally {
    allArtworkLoading = false;

    if (
      loadToken === galleryLoadToken
      && allArtworkMode
      && !galleryLoadComplete
      && allArtworkSentinel
      && allArtworkSentinel.getBoundingClientRect().top < window.innerHeight + 1200
    ) {
      window.setTimeout(() => loadNextAllArtworkCategory(loadToken), 0);
    }
  }
}

function startAllArtworkObserver(loadToken) {
  if (galleryLoadComplete) {
    return;
  }

  allArtworkSentinel = document.createElement("div");
  allArtworkSentinel.className = "gallery-scroll-sentinel";
  allArtworkSentinel.setAttribute("aria-hidden", "true");
  artGrid.after(allArtworkSentinel);

  allArtworkObserver = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      loadNextAllArtworkCategory(loadToken);
    }
  }, {
    rootMargin: "900px 0px 1200px"
  });
  allArtworkObserver.observe(allArtworkSentinel);
}

function renderCurrentPage() {
  const token = ++pageRenderToken;
  const totalPages = Math.max(1, Math.ceil(filteredRecords.length / pageSize));
  currentPage = Math.min(Math.max(currentPage, 1), totalPages);

  if (totalPages <= 1 && galleryAutoplayActive) {
    stopGalleryAutoplay();
  }

  const start = (currentPage - 1) * pageSize;
  const pageRecords = filteredRecords.slice(start, start + pageSize);
  const query = gallerySearch.value.trim();
  const hasColorFilters = includedColorSeeds.size > 0 || excludedColorSeeds.size > 0;
  const loadingSuffix = galleryLoadComplete ? "" : " loaded";
  const categoryLabel = activeCategory ? `${activeCategory.label} category` : "category";

  galleryCount.textContent = query || hasColorFilters
    ? `${filteredRecords.length} of ${galleryRecords.length}${loadingSuffix} in ${categoryLabel}`
    : `${galleryRecords.length}${loadingSuffix} in ${categoryLabel}`;

  if (pageRecords.length === 0) {
    stopGalleryAutoplay();
    updateGalleryAutoplayControls(1);
    artGrid.innerHTML = `<p class="carousel-error">No artworks match your search.</p>`;
    galleryPagination.replaceChildren();
    closeInspector();
    selectedId = "";
    return;
  }

  renderPageCards(pageRecords, start, token);
  renderPagination(totalPages);
  updateGalleryAutoplayControls(totalPages);
  scheduleGalleryAutoplay(totalPages);

  window.setTimeout(() => {
    artGrid.classList.remove("is-autoplay-advance");
  }, AUTOPLAY_PAGE_TRANSITION + 260);
}

function applyFilters({ renderFilters = true } = {}) {
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
  if (renderFilters) {
    renderColorFilters();
  }

  renderCurrentPage();
}

function normalizeGalleryRecord(record) {
  const colors = record.colors || uniqueColors(record.pixels);
  const normalizedColors = colors.map(normalizeColor).filter(Boolean);

  return {
    ...record,
    colors: normalizedColors,
    colorSet: new Set(normalizedColors),
    searchText: record.searchText || recordSearchText({ ...record, colors: normalizedColors })
  };
}

function rebuildGalleryIndexes({ renderFilters = true } = {}) {
  buildColorBuckets(galleryRecords, colorSimilarityThreshold);
  applyFilters({ renderFilters });
}

async function loadGalleryCategory(category, { requestedId = "", updateUrl = true } = {}) {
  if (isAllArtworkCategory(category)) {
    return loadAllArtwork({ requestedId, updateUrl });
  }

  const loadToken = ++galleryLoadToken;
  const startedAt = performance.now();
  stopGalleryAutoplay();
  allArtworkMode = false;
  resetAllArtworkModeState();
  setAnalysisControlsEnabled(true);
  activeCategory = category;
  galleryRecords = [];
  filteredRecords = [];
  colorBuckets = [];
  colorToBucket = new Map();
  includedColorSeeds.clear();
  excludedColorSeeds.clear();
  selectedId = "";
  galleryLoadComplete = false;
  currentPage = 1;
  galleryCategory.disabled = true;
  renderCategoryOptions();

  if (updateUrl) {
    setGalleryUrlCategory(category);
  }

  galleryCount.textContent = "Loading";
  artGrid.replaceChildren();
  galleryPagination.replaceChildren();
  updateGalleryAutoplayControls(1);
  closeInspector();
  updateGalleryLoading({
    title: "Loading category",
    step: `Requesting ${category.label}.`,
    loaded: 0,
    total: category.count,
    startedAt
  });

  const records = await fetchCategoryRecords(category);

  if (loadToken !== galleryLoadToken) {
    return;
  }

  galleryRecords = records.map(normalizeGalleryRecord);
  filteredRecords = galleryRecords;
  galleryCount.textContent = `${galleryRecords.length} / ${category.count}`;
  updateGalleryLoading({
    title: "Loading category",
    step: `${category.label} loaded. Building search and color filters.`,
    loaded: galleryRecords.length,
    total: category.count,
    startedAt
  });

  galleryLoadComplete = true;
  rebuildGalleryIndexes({ renderFilters: true });
  galleryLoading.hidden = true;
  galleryCategory.disabled = false;

  const requestedRecord = requestedId
    ? galleryRecords.find((record) => record.id === requestedId)
    : null;

  if (requestedRecord) {
    openGalleryRecord(requestedRecord);
  }
}

async function loadAllArtwork({ requestedId = "", updateUrl = true } = {}) {
  const loadToken = ++galleryLoadToken;
  const startedAt = performance.now();
  stopGalleryAutoplay();
  allArtworkMode = false;
  resetAllArtworkModeState();
  setAnalysisControlsEnabled(true);
  activeCategory = allArtworkCategory();
  galleryRecords = [];
  filteredRecords = [];
  colorBuckets = [];
  colorToBucket = new Map();
  includedColorSeeds.clear();
  excludedColorSeeds.clear();
  selectedId = "";
  galleryLoadComplete = false;
  currentPage = 1;
  galleryCategory.disabled = true;
  renderCategoryOptions();

  if (updateUrl) {
    setGalleryUrlCategory(activeCategory);
  }

  galleryCount.textContent = "Loading";
  artGrid.replaceChildren();
  galleryPagination.replaceChildren();
  updateGalleryAutoplayControls(1);
  closeInspector();
  updateGalleryLoading({
    title: "Loading all artwork",
    step: `Requesting ${galleryCategories.length} artwork groups in parallel.`,
    loaded: 0,
    total: galleryTotalCount,
    startedAt
  });

  let loadedArtworkCount = 0;
  const loadedCategoryRecords = await mapInParallelBatches(
    galleryCategories,
    ALL_ARTWORK_PARALLEL_BATCH_SIZE,
    async (category, index) => {
      const records = await fetchCategoryRecords(category);
      loadedArtworkCount += records.length;

      if (loadToken === galleryLoadToken) {
        updateGalleryLoading({
          title: "Loading all artwork",
          step: `${category.label} loaded. Merging artwork groups.`,
          loaded: Math.min(galleryTotalCount, loadedArtworkCount),
          total: galleryTotalCount,
          startedAt
        });
      }

      return { index, records };
    }
  );

  if (loadToken !== galleryLoadToken) {
    return;
  }

  galleryRecords = loadedCategoryRecords
    .sort((a, b) => a.index - b.index)
    .flatMap(({ records }) => records)
    .map(normalizeGalleryRecord);
  filteredRecords = galleryRecords;
  galleryCount.textContent = `${galleryRecords.length} / ${galleryTotalCount}`;
  updateGalleryLoading({
    title: "Loading all artwork",
    step: "All artwork loaded. Building search and color filters.",
    loaded: galleryRecords.length,
    total: galleryTotalCount,
    startedAt
  });

  galleryLoadComplete = true;
  rebuildGalleryIndexes({ renderFilters: true });
  galleryLoading.hidden = true;
  galleryCategory.disabled = false;

  if (requestedId) {
    const requestedRecord = galleryRecords.find((record) => record.id === requestedId);

    if (requestedRecord) {
      await openGalleryRecord(requestedRecord);
    }
  }
}

async function renderGallery() {
  const startedAt = performance.now();
  const params = new URLSearchParams(window.location.search);
  const requestedId = params.get("art");
  const requestedCategoryId = params.get("category");
  galleryCount.textContent = "Loading";
  artGrid.replaceChildren();
  galleryPagination.replaceChildren();
  updateGalleryLoading({
    title: "Preparing the collection",
    step: "Requesting the category index.",
    startedAt
  });

  const manifest = await fetchGalleryManifest();
  const artworkIds = Array.isArray(manifest) ? manifest : manifest.artworkIds;
  precomputedColorBucketsByThreshold = !Array.isArray(manifest) && manifest.indexes?.colorBuckets
    ? manifest.indexes.colorBuckets
    : {};
  precomputedColorBucketTotalsByThreshold = !Array.isArray(manifest) && manifest.indexes?.colorBucketTotals
    ? manifest.indexes.colorBucketTotals
    : {};

  if (!Array.isArray(artworkIds) || artworkIds.length === 0) {
    throw new Error("Art manifest does not include any artwork ids.");
  }

  galleryTotalCount = artworkIds.length;
  renderCollectionStats(manifest, artworkIds);
  galleryCategories = !Array.isArray(manifest) && Array.isArray(manifest.categories)
    ? manifest.categories
    : [];

  if (galleryCategories.length === 0) {
    const chunks = !Array.isArray(manifest) && Array.isArray(manifest.chunks) ? manifest.chunks : [];
    galleryCategories = chunks.map((chunk, index) => ({
      id: `chunk-${index}`,
      label: `Group ${index + 1}`,
      description: `${chunk.count} artworks`,
      path: chunk.path,
      count: chunk.count,
      ids: artworkIds.slice(chunk.start, chunk.start + chunk.count)
    }));
  }

  if (galleryCategories.length === 0) {
    throw new Error("Art manifest does not include gallery categories.");
  }

  const urlCategory = requestedCategoryId === ALL_ARTWORK_CATEGORY_ID
    ? allArtworkCategory()
    : galleryCategories.find((category) => category.id === requestedCategoryId);
  const requestedCategory = requestedId && !isAllArtworkCategory(urlCategory)
    ? categoryForArtworkId(requestedId)
    : null;
  activeCategory = requestedCategory || urlCategory || allArtworkCategory();
  renderCategoryOptions();
  await loadGalleryCategory(activeCategory, { requestedId, updateUrl: !requestedId });
}

gallerySearch.addEventListener("input", applyFilters);
galleryImageSize.addEventListener("input", () => {
  setGalleryImageSize(galleryImageSize.value);
});
galleryCategory.addEventListener("change", () => {
  const category = galleryCategory.value === ALL_ARTWORK_CATEGORY_ID
    ? allArtworkCategory()
    : galleryCategories.find((item) => item.id === galleryCategory.value);

  if (category) {
    const url = new URL(window.location.href);
    url.searchParams.delete("art");
    window.history.replaceState({}, "", url);
    loadGalleryCategory(category).catch((error) => {
      galleryCount.textContent = "Error";
      galleryLoading.hidden = true;
      galleryCategory.disabled = false;
      artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
    });
  }
});
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
toggleFilterOutlines.addEventListener("click", () => {
  setFilterOutlinesVisible(!filterOutlinesVisible);
});
galleryAutoplayToggle.addEventListener("click", () => {
  if (galleryAutoplayActive) {
    stopGalleryAutoplay();
  } else {
    startGalleryAutoplay();
  }

  renderCurrentPage();
});
galleryAutoplaySpeed.addEventListener("click", () => {
  setGalleryAutoplaySpeed(nextGalleryAutoplaySpeed());
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
setFilterOutlinesVisible(readPreference(FILTER_OUTLINES_COOKIE) !== "hidden", false);
setGalleryImageSize(readPreference(GALLERY_IMAGE_SIZE_COOKIE) || galleryImageSize.value, false);
setPageSize(readPreference(GALLERY_PAGE_SIZE_COOKIE), false);
setGalleryAutoplaySpeed(readPreference(GALLERY_AUTOPLAY_SPEED_COOKIE), false);
const savedSimilarity = Number(readPreference(COLOR_SIMILARITY_COOKIE));

if (Number.isFinite(savedSimilarity)) {
  colorSimilarity.value = String(savedSimilarity);
  colorSimilarityThreshold = savedSimilarity;
}

updateSimilarityLabel();

renderGallery().catch((error) => {
  galleryCount.textContent = "Error";
  galleryLoading.hidden = true;
  artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
});
