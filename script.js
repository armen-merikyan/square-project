const HOMEPAGE_ARTWORK_IDS_PATH = "art/homepage-artwork-ids.json";
const HOMEPAGE_ARTWORK_LIMIT = 40;
const CAROUSEL_IMAGE_LOAD_RADIUS = 3;
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
const pauseButton = document.querySelector("#pauseCarousel");
const DOT_RANGE = 2;
const CAROUSEL_TRANSITION_MS = 1080;
const MAX_DRAG_PROGRESS = 1.18;

let activeIndex = 0;
let autoAdvanceId;
let isPaused = false;
let isAdvancing = false;
let dragStartX = 0;
let dragStartY = 0;
let dragProgress = 0;
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

function appendChildren(parent, children) {
  children.forEach((child) => parent.appendChild(child));
}

function clearChildren(parent) {
  while (parent.firstChild) {
    parent.removeChild(parent.firstChild);
  }
}

function setBooleanAttribute(element, attribute, enabled) {
  if (enabled) {
    element.setAttribute(attribute, "");
    return;
  }

  element.removeAttribute(attribute);
}

function artworkDetailUrl(index) {
  return `gallery.html?art=${encodeURIComponent(artworks[index])}`;
}

function sampleArtworks(ids, limit) {
  const sample = [...ids];
  const sampleSize = Math.min(limit, sample.length);

  for (let index = 0; index < sampleSize; index += 1) {
    const randomIndex = index + Math.floor(Math.random() * (sample.length - index));
    [sample[index], sample[randomIndex]] = [sample[randomIndex], sample[index]];
  }

  return sample.slice(0, sampleSize);
}

async function loadArtwork(id) {
  const response = await fetch(`art/${id}.json`);

  if (!response.ok) {
    throw new Error(`Could not load metadata for ${id}`);
  }

  return response.json();
}

async function loadArtworkIds() {
  const response = await fetch(HOMEPAGE_ARTWORK_IDS_PATH);

  if (!response.ok) {
    throw new Error("Could not load homepage art manifest.");
  }

  const manifest = await response.json();
  const ids = Array.isArray(manifest) ? manifest : manifest.artworkIds;

  if (!Array.isArray(ids) || ids.length === 0) {
    throw new Error("Art manifest does not include any artwork ids.");
  }

  return sampleArtworks(ids, HOMEPAGE_ARTWORK_LIMIT);
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
    ["Size", `${(data.size && data.size.width) || 8} x ${(data.size && data.size.height) || 8}`],
    ["Cells", `${(data.pixels && data.pixels.length) || 64}`]
  ];

  detailItems.forEach(([label, value]) => {
    const group = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");

    term.textContent = label;
    description.textContent = value;
    appendChildren(group, [term, description]);
    details.appendChild(group);
  });

  const reasoning = document.createElement("p");
  reasoning.className = "art-reasoning";
  reasoning.textContent = summarizeReasoning(data.reasoning);

  appendChildren(overlay, [title, seed, details, reasoning]);
  return overlay;
}

function createArtworkFace(image) {
  const face = document.createElement("div");
  face.className = "cover-face";
  face.appendChild(image);
  return face;
}

function createArtworkReflection(image) {
  const reflection = document.createElement("div");
  reflection.className = "cover-reflection";
  reflection.setAttribute("aria-hidden", "true");

  const reflectedImage = image.cloneNode();
  reflectedImage.alt = "";
  reflection.appendChild(reflectedImage);

  return reflection;
}

function loadSlideImages() {
  [...coverflow.children].forEach((slide, slideIndex) => {
    const offset = Math.abs(shortestOffset(slideIndex));

    if (offset > CAROUSEL_IMAGE_LOAD_RADIUS) {
      return;
    }

    slide.querySelectorAll("img[data-src]").forEach((image) => {
      image.src = image.dataset.src;
      image.removeAttribute("data-src");
    });
  });
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
    slide.setAttribute("role", "link");
    slide.tabIndex = 0;

    const image = document.createElement("img");
    image.dataset.src = `art/${artworks[index]}.svg`;
    image.alt = record.title ? `${record.title} square artwork` : "Square artwork";
    image.decoding = "async";
    image.loading = index === 0 ? "eager" : "lazy";

    appendChildren(slide, [
      createArtworkFace(image),
      createArtworkReflection(image),
      createMetadataOverlay(record, index)
    ]);
    slide.addEventListener("click", (event) => {
      if (didDrag) {
        event.preventDefault();
        return;
      }

      if (index !== activeIndex) {
        advanceTo(index);
        restartAutoAdvance();
        return;
      }

      window.location.href = artworkDetailUrl(index);
    });
    slide.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }

      event.preventDefault();
      if (index === activeIndex) {
        window.location.href = artworkDetailUrl(index);
        return;
      }

      advanceTo(index);
      restartAutoAdvance();
    });

    coverflow.appendChild(slide);
  });

  updateCarouselPositions(0);
  startAutoAdvance();
}

function renderDots() {
  clearChildren(dots);

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

function updateCarouselPositions(nextIndex = activeIndex) {
  activeIndex = normalizeIndex(nextIndex);
  const slides = [...coverflow.children];

  slides.forEach((slide, slideIndex) => {
    const offset = shortestOffset(slideIndex);
    const draggedOffset = offset + dragProgress;
    const direction = Math.sign(draggedOffset || offset);
    const hidden = Math.abs(draggedOffset) > 2.65;
    const displayOffset = hidden ? direction * 3 : draggedOffset;
    const displayAbsoluteOffset = Math.abs(displayOffset);
    const displayDirection = Math.sign(displayOffset);
    const normalizedProximity = Math.max(0, 1 - Math.min(displayAbsoluteOffset, 1));

    slide.style.setProperty("--offset", offset);
    slide.style.setProperty("--abs-offset", Math.abs(offset));
    slide.style.setProperty("--direction", direction);
    slide.style.setProperty("--display-offset", displayOffset);
    slide.style.setProperty("--display-abs-offset", displayAbsoluteOffset);
    slide.style.setProperty("--display-direction", displayDirection);
    slide.style.setProperty("--active-proximity", normalizedProximity.toFixed(3));
    slide.dataset.offset = String(offset);
    setBooleanAttribute(slide, "aria-hidden", slideIndex !== activeIndex);
    slide.classList.toggle("is-active", slideIndex === activeIndex);
    slide.classList.toggle("is-hidden", hidden);
    slide.tabIndex = slideIndex === activeIndex ? 0 : -1;
  });

  renderDots();
  loadSlideImages();
  counter.textContent = `${String(activeIndex + 1).padStart(2, "0")} / ${String(artworks.length).padStart(2, "0")}`;
}

function advanceTo(index) {
  if (isAdvancing) {
    return;
  }

  isAdvancing = true;
  dragProgress = 0;
  coverflow.classList.remove("is-dragging");
  updateCarouselPositions(index);
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
  if (isPaused) {
    return;
  }

  window.clearInterval(autoAdvanceId);
  autoAdvanceId = window.setInterval(nextArtwork, 4600);
}

function restartAutoAdvance() {
  window.clearInterval(autoAdvanceId);

  if (!isPaused) {
    startAutoAdvance();
  }
}

function updatePauseButton() {
  pauseButton.setAttribute("aria-label", isPaused ? "Resume carousel" : "Pause carousel");
  pauseButton.setAttribute("aria-pressed", String(isPaused));
  pauseButton.textContent = isPaused ? "▶" : "Ⅱ";
}

function pauseAutoAdvance() {
  isPaused = true;
  window.clearInterval(autoAdvanceId);
  updatePauseButton();
}

function resumeAutoAdvance() {
  isPaused = false;
  updatePauseButton();
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

pauseButton.addEventListener("click", () => {
  if (isPaused) {
    resumeAutoAdvance();
    return;
  }

  pauseAutoAdvance();
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
coverflow.addEventListener("mouseleave", () => {
  if (!isPaused) {
    startAutoAdvance();
  }
});

coverflow.addEventListener("pointerdown", (event) => {
  dragStartX = event.clientX;
  dragStartY = event.clientY;
  dragProgress = 0;
  isDragging = true;
  didDrag = false;
  coverflow.classList.add("is-dragging");
  window.clearInterval(autoAdvanceId);
  const captureTarget = event.target.closest(".carousel-card") || coverflow;

  if (typeof captureTarget.setPointerCapture === "function") {
    captureTarget.setPointerCapture(event.pointerId);
  }
});

coverflow.addEventListener("pointermove", (event) => {
  if (!isDragging) {
    return;
  }

  const dragX = event.clientX - dragStartX;
  const dragY = event.clientY - dragStartY;

  if (Math.abs(dragX) > 8 || Math.abs(dragY) > 8) {
    didDrag = true;
  }

  if (Math.abs(dragX) > Math.abs(dragY)) {
    event.preventDefault();
  }

  const slotWidth = Number.parseFloat(getComputedStyle(coverflow).getPropertyValue("--cover-slot")) || 220;
  dragProgress = Math.max(-MAX_DRAG_PROGRESS, Math.min(MAX_DRAG_PROGRESS, dragX / slotWidth));
  updateCarouselPositions();
});

coverflow.addEventListener("pointerup", (event) => {
  if (!isDragging) {
    return;
  }

  const dragX = event.clientX - dragStartX;
  const dragY = event.clientY - dragStartY;
  const targetIndex = Math.abs(dragX) > 42 && Math.abs(dragX) > Math.abs(dragY)
    ? activeIndex + (dragX < 0 ? 1 : -1)
    : activeIndex;

  isDragging = false;
  coverflow.classList.remove("is-dragging");

  dragProgress = 0;
  advanceTo(targetIndex);

  restartAutoAdvance();
  window.setTimeout(() => {
    didDrag = false;
  }, 0);
});

coverflow.addEventListener("pointercancel", () => {
  isDragging = false;
  dragProgress = 0;
  coverflow.classList.remove("is-dragging");
  updateCarouselPositions();
  restartAutoAdvance();
});

updatePauseButton();
renderCarousel().catch((error) => {
  coverflow.innerHTML = `<p class="carousel-error">${error.message}</p>`;
});

function setupPageReveals() {
  const revealTargets = document.querySelectorAll(".intro, .section-heading, .data-section > div, .data-section pre, .identity > .eyebrow, .identity > h2");
  const staggerTargets = document.querySelectorAll(".steps, .identity-grid");

  revealTargets.forEach((element) => {
    element.classList.add("reveal");
  });

  staggerTargets.forEach((element) => {
    element.classList.add("reveal-stagger");
    [...element.children].forEach((child, index) => {
      child.style.setProperty("--reveal-index", index);
    });
  });

  const animatedTargets = [...revealTargets, ...staggerTargets];

  if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    animatedTargets.forEach((element) => element.classList.add("is-visible"));
    return;
  }

  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) {
        return;
      }

      entry.target.classList.add("is-visible");
      revealObserver.unobserve(entry.target);
    });
  }, {
    rootMargin: "0px 0px -12% 0px",
    threshold: 0.18
  });

  animatedTargets.forEach((element) => revealObserver.observe(element));
}

setupPageReveals();
