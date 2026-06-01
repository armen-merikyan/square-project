const galleryArtworkIds = [
  "08b1548f5260b8ff35ec85fc2b030330acd79f77332ccd059ee880c69fee0179",
  "0af43a9e8e6f5a9a48aca2134ca37dc49d1804f4c3a4494a845302fcb6d966e6",
  "0d6b4b17133cdcd7f1065073863d7b1834470c2e8491c9a466a778facdd0b514",
  "1fe3d0b60c8d47b955c39d4604872784758357a7851f0b7b448a464fb4e84405",
  "27cecfa21ba31fc2919aa6f80eb91c41bcd6d739358f217597bcf6e109f1e54d",
  "2eece28eb9cb6341b3fdd199a686018a64515d16a82e40b96fad7d11663a86db",
  "301b7a41b3b279fb39b24a5c44e41a4a0d4da3d6f579ac1efeb973f7ca3911da",
  "31a07d498056211fc208eff311d4a11666b9e4c030cdfe7aca71cf1df1eaae73",
  "3523b0244fac48ac8150614de7818fdc5bf7f518996faa93a0f9ff4c3558fcc1",
  "37796df6968adb4ea0165b9f5f2d72cee8227f0d0c9e8a2700a1482fbe0e98f6",
  "38bedf272f14695514792f1294bad57bfbb7ea5104ff447b5b2dfe416dafab4f",
  "3900ac21442c473c57d622379bab5ce6abc31eab2d83ad1d8201d4665ec4c6a4",
  "391b427d75cbd8a10734f3a8869ff845e18b44b39522b49604afdd88e0fc09cd",
  "3c5797b889eabc7e014fe9f942ee0779ea8955056324778f1107179b3b12cbe4",
  "3df78a45ada717fe85c2695e00a3528afa6fa115f88f04b662c497cf94ad154e",
  "3fb767aafcdcd32e5ecd5e5416bd346fb71bd4707d256f0de351e63aec61f3dc",
  "439ac62ba0e0eb83671fed1e12d9ac23a656a86e8f8f3f15a24c02704ebe41b9",
  "4b4a46b83b524be545d874502d8fdf7de613497cc0f502007e2f46cad0babf81",
  "5cfffbd5390e29e7054775c709da167b639e10aa5a596b9f4bf624c107e28fe6",
  "6d3796cf44172e83ce9968dc3948600c8ef08c356ae8eaffca318131b7788c0a",
  "79d8881faf1e695ded25c4f5efc3a8d1425310d27f6dad9323052f67efd9a42e",
  "7bdacdf54c8f1aca9d5ee1ca424d2643da5b0024b6df0e07a5c25c385efeeb6d",
  "9005ff72981281b13937fc309818c1c83d514385f6bd9736eda5e0e58c6b634a",
  "93d8208046ed614b36d647b747f487a377dcffa98a7895fea77118a180b792f9",
  "95716532b087b46ffce2502cddc5d20c2deb5bb782d2d8ca1feb13711df1012a",
  "9b996b583106061dfa9d41b35134cb76aa01051dce945b87e2a819e5246511ee",
  "a5372c8fe3f5bc5a162057010ba1e2bf2e57e37a54bdeedcc736b943ada3fe75",
  "a9eee41b4e1d470ab6bb42bef898d1facf23ef263b102bd4bf4135ee28b8f292",
  "b9c7b1c65a695c6573732bcd5bb2adb6977ca4ccda01c2a60a609acdffc1cef0",
  "bc16c4ce53a0ac36ffc723dec14b22cbe2e71c4e334fa7f53fbf61882a4fa09f",
  "bd5e458d61c944966786f49eecc7a0bc696e92847d244645d267e0b1e2a7bd9a",
  "c3f6fbd9f85e2eac0ac7f61741cd4291ce11482f6a0016f880b221380bc0f552",
  "c611632aa6aeb22700c282fae3b5f6f2bf85c9e74820701204f3ef199e17572c",
  "d400c6b10163b94e096939b2739b7afee5946826d194b85d2755bca844e98839",
  "d4946e0a3a5fe027e22086f5674acd97454d6528fc740d3e0f3b947db7049e26",
  "daf18cedb3035628e024668e282e9800281701b559d628ec3715a047d0ab6c38",
  "e798a510106039c62cd466e3a193df35e69817bbff017715141867686a309e22",
  "ee69c11e4a1c7689e79686d9731f69f0aeb602243bf47e7f627793bfd6cf1ea0",
  "eea806d25b129b7789466507724f10b326e6a92f0b40619a060c7396f95e134d",
  "eed727999796ea54a0e5f30404a60f65f29814756cd2a506aeea80e898c654c6"
];

const artGrid = document.querySelector("#artGrid");
const artInspector = document.querySelector("#artInspector");
const galleryCount = document.querySelector("#galleryCount");

let galleryRecords = [];
let selectedId = "";

function compactId(id) {
  return `${id.slice(0, 10)}...${id.slice(-8)}`;
}

function uniqueColors(pixels = []) {
  return [...new Set(pixels.map((pixel) => pixel.color).filter(Boolean))];
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

function renderInspector(record) {
  selectedId = record.id;
  const colors = uniqueColors(record.pixels);
  const width = record.size?.width || 8;
  const height = record.size?.height || 8;

  artInspector.replaceChildren();

  const frame = document.createElement("div");
  frame.className = "inspector-frame";

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

  const jsonLabel = document.createElement("h3");
  jsonLabel.textContent = "JSON record";

  const rawJson = document.createElement("pre");
  rawJson.className = "json-record";
  const code = document.createElement("code");
  code.textContent = JSON.stringify(record, null, 2);
  rawJson.appendChild(code);

  content.append(
    eyebrow,
    title,
    seed,
    metrics,
    reasoningLabel,
    reasoning,
    paletteLabel,
    renderSwatches(colors),
    jsonLabel,
    rawJson
  );

  frame.append(image, content);
  artInspector.appendChild(frame);

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

async function renderGallery() {
  galleryCount.textContent = "Loading";

  galleryRecords = await Promise.all(galleryArtworkIds.map(fetchArtwork));
  galleryCount.textContent = `${galleryRecords.length} artworks`;
  artGrid.replaceChildren(...galleryRecords.map(renderCard));
  renderInspector(galleryRecords[0]);
}

renderGallery().catch((error) => {
  galleryCount.textContent = "Error";
  artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
});
