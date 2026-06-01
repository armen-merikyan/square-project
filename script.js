const GALLERY_MANIFEST_PATH = "art/manifest.json";
const fallbackArtworks = [
  "e798a510106039c62cd466e3a193df35e69817bbff017715141867686a309e22",
  "9005ff72981281b13937fc309818c1c83d514385f6bd9736eda5e0e58c6b634a",
  "3900ac21442c473c57d622379bab5ce6abc31eab2d83ad1d8201d4665ec4c6a4",
  "c611632aa6aeb22700c282fae3b5f6f2bf85c9e74820701204f3ef199e17572c",
  "eea806d25b129b7789466507724f10b326e6a92f0b40619a060c7396f95e134d",
  "31a07d498056211fc208eff311d4a11666b9e4c030cdfe7aca71cf1df1eaae73"
];
let artworks = fallbackArtworks;

const coverflow = document.querySelector("#coverflow");
const dots = document.querySelector("#carouselDots");
const counter = document.querySelector("#carouselCounter");
const nextButton = document.querySelector("#nextArtwork");
const prevButton = document.querySelector("#prevArtwork");
const DOT_RANGE = 2;
const CAROUSEL_TRANSITION_MS = 900;

let activeIndex = 0;
let autoAdvanceId;
let isAdvancing = false;
let dragStartX = 0;
let dragStartY = 0;
let isDragging = false;
let didDrag = false;

function normalizeIndex(index) {
  return (index + artworks.length) % artworks.length;
}

function shortestOffset(index) {
  const rawOffset = index - activeIndex;
  const wrappedOffset = rawOffset > artworks.length / 2
    ? rawOffset - artworks.length
    : rawOffset < -artworks.length / 2
      ? rawOffset + artworks.length
      : rawOffset;

  return wrappedOffset;
}

function visibleDotIndexes() {
  if (artworks.length <= (DOT_RANGE * 2) + 1) {
    return artworks.map((_, index) => index);
  }

  const indexes = [];
  for (let offset = -DOT_RANGE; offset <= DOT_RANGE; offset += 1) {
    indexes.push(normalizeIndex(activeIndex + offset));
  }

  return indexes;
}

function shortId(id) {
  return `${id.slice(0, 8)}...${id.slice(-6)}`;
}

function summarizeReasoning(reasoning = "") {
  return reasoning.length > 250 ? `${reasoning.slice(0, 247)}...` : reasoning;
}

async function loadArtwork(id) {
  const response = await fetch(`art/${id}.json`);

  if (!response.ok) {
    throw new Error(`Could not load metadata for ${id}`);
  }

  return response.json();
}

async function loadArtworkIds() {
  const response = await fetch(GALLERY_MANIFEST_PATH);

  if (!response.ok) {
    throw new Error("Could not load art manifest.");
  }

  const manifest = await response.json();
  const ids = Array.isArray(manifest) ? manifest : manifest.artworkIds;

  if (!Array.isArray(ids) || ids.length === 0) {
    throw new Error("Art manifest does not include any artwork ids.");
  }

  return ids;
}

function createMetadataOverlay(data, index) {
  const overlay = document.createElement("div");
  overlay.className = "art-overlay";

  const title = document.createElement("h2");
  title.textContent = data.title || `Square ${index + 1}`;

  const seed = document.createElement("p");
  seed.className = "art-seed";
  seed.textContent = data.seed || "Generated square artwork";

  const details = document.createElement("dl");
  details.className = "art-details";

  const detailItems = [
    ["ID", shortId(data.id || artworks[index])],
    ["Size", `${data.size?.width || 8} x ${data.size?.height || 8}`],
    ["Cells", `${data.pixels?.length || 64}`]
  ];

  detailItems.forEach(([label, value]) => {
    const group = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");

    term.textContent = label;
    description.textContent = value;
    group.append(term, description);
    details.appendChild(group);
  });

  const reasoning = document.createElement("p");
  reasoning.className = "art-reasoning";
  reasoning.textContent = summarizeReasoning(data.reasoning);

  overlay.append(title, seed, details, reasoning);
  return overlay;
}

async function renderCarousel() {
  try {
    artworks = await loadArtworkIds();
  } catch (error) {
    console.warn(error);
    artworks = fallbackArtworks;
  }

  const records = await Promise.all(artworks.map(loadArtwork));

  records.forEach((record, index) => {
    const slide = document.createElement("article");
    slide.className = "carousel-card";
    slide.setAttribute("aria-label", record.title || `Artwork ${index + 1}`);

    const image = document.createElement("img");
    image.src = `art/${artworks[index]}.svg`;
    image.alt = record.title ? `${record.title} square artwork` : "Square artwork";
    image.decoding = "async";

    slide.append(image, createMetadataOverlay(record, index));
    slide.addEventListener("click", (event) => {
      if (didDrag) {
        event.preventDefault();
        return;
      }

      if (index !== activeIndex) {
        advanceTo(index);
        restartAutoAdvance();
      }
    });

    coverflow.appendChild(slide);
  });

  setActive(0);
  startAutoAdvance();
}

function renderDots() {
  dots.replaceChildren();

  visibleDotIndexes().forEach((dotIndex) => {
    const dot = document.createElement("button");
    dot.className = "carousel-dot";
    dot.type = "button";
    dot.setAttribute("aria-label", `Show artwork ${dotIndex + 1}`);
    dot.classList.toggle("is-active", dotIndex === activeIndex);
    dot.setAttribute("aria-current", dotIndex === activeIndex ? "true" : "false");
    dot.addEventListener("click", () => {
      advanceTo(dotIndex);
      restartAutoAdvance();
    });
    dots.appendChild(dot);
  });
}

function setActive(index) {
  activeIndex = normalizeIndex(index);
  const slides = [...coverflow.children];

  slides.forEach((slide, slideIndex) => {
    const offset = shortestOffset(slideIndex);
    const absoluteOffset = Math.abs(offset);
    const direction = Math.sign(offset);
    const hidden = Math.abs(offset) > 2;
    const displayOffset = hidden ? direction * 3 : offset;
    const displayAbsoluteOffset = Math.abs(displayOffset);
    const displayDirection = Math.sign(displayOffset);

    slide.style.setProperty("--offset", offset);
    slide.style.setProperty("--abs-offset", absoluteOffset);
    slide.style.setProperty("--direction", direction);
    slide.style.setProperty("--display-offset", displayOffset);
    slide.style.setProperty("--display-abs-offset", displayAbsoluteOffset);
    slide.style.setProperty("--display-direction", displayDirection);
    slide.dataset.offset = String(offset);
    slide.toggleAttribute("aria-hidden", slideIndex !== activeIndex);
    slide.classList.toggle("is-active", slideIndex === activeIndex);
    slide.classList.toggle("is-hidden", hidden);
  });

  renderDots();
  counter.textContent = `${String(activeIndex + 1).padStart(2, "0")} / ${String(artworks.length).padStart(2, "0")}`;
}

function advanceTo(index) {
  if (isAdvancing) {
    return;
  }

  isAdvancing = true;
  setActive(index);
  window.setTimeout(() => {
    isAdvancing = false;
  }, CAROUSEL_TRANSITION_MS);
}

function nextArtwork() {
  advanceTo(activeIndex + 1);
}

function previousArtwork() {
  advanceTo(activeIndex - 1);
}

function startAutoAdvance() {
  window.clearInterval(autoAdvanceId);
  autoAdvanceId = window.setInterval(nextArtwork, 4200);
}

function restartAutoAdvance() {
  window.clearInterval(autoAdvanceId);
  startAutoAdvance();
}

nextButton.addEventListener("click", () => {
  nextArtwork();
  restartAutoAdvance();
});

prevButton.addEventListener("click", () => {
  previousArtwork();
  restartAutoAdvance();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight") {
    nextArtwork();
    restartAutoAdvance();
  }

  if (event.key === "ArrowLeft") {
    previousArtwork();
    restartAutoAdvance();
  }
});

coverflow.addEventListener("mouseenter", () => window.clearInterval(autoAdvanceId));
coverflow.addEventListener("mouseleave", startAutoAdvance);

coverflow.addEventListener("pointerdown", (event) => {
  dragStartX = event.clientX;
  dragStartY = event.clientY;
  isDragging = true;
  didDrag = false;
  window.clearInterval(autoAdvanceId);
  coverflow.setPointerCapture(event.pointerId);
});

coverflow.addEventListener("pointermove", (event) => {
  if (!isDragging) {
    return;
  }

  if (Math.abs(event.clientX - dragStartX) > 8 || Math.abs(event.clientY - dragStartY) > 8) {
    didDrag = true;
  }
});

coverflow.addEventListener("pointerup", (event) => {
  if (!isDragging) {
    return;
  }

  const dragX = event.clientX - dragStartX;
  const dragY = event.clientY - dragStartY;
  isDragging = false;

  if (Math.abs(dragX) > 42 && Math.abs(dragX) > Math.abs(dragY)) {
    dragX < 0 ? nextArtwork() : previousArtwork();
  }

  restartAutoAdvance();
  window.setTimeout(() => {
    didDrag = false;
  }, 0);
});

coverflow.addEventListener("pointercancel", () => {
  isDragging = false;
  restartAutoAdvance();
});

renderCarousel().catch((error) => {
  coverflow.innerHTML = `<p class="carousel-error">${error.message}</p>`;
});
