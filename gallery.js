const galleryArtworkIds = [
  "054a0b94e83f088f03b505a707de4ca964d6deea1942bb4a8d281a7147629537",
  "08b1548f5260b8ff35ec85fc2b030330acd79f77332ccd059ee880c69fee0179",
  "0af43a9e8e6f5a9a48aca2134ca37dc49d1804f4c3a4494a845302fcb6d966e6",
  "0d6b4b17133cdcd7f1065073863d7b1834470c2e8491c9a466a778facdd0b514",
  "10db34c762c97e1ee683f31bebe82fa719daa20dcb3fb657003a65861f6cf4cb",
  "18dd0b3302b58c61ac490a7ee21f2c3b2caab512e86332e5cc7e73f85999dd46",
  "1dbbfe6c1b9da49aa51d3c71103f94cb46d4a0cf26f4adc4f893cd17d7643ded",
  "1fe3d0b60c8d47b955c39d4604872784758357a7851f0b7b448a464fb4e84405",
  "2066718883ca12e1139cb1bff6e5349e857d0a58537782ec5c35f7ec2b764b73",
  "27cecfa21ba31fc2919aa6f80eb91c41bcd6d739358f217597bcf6e109f1e54d",
  "2a5c3a224e2cfe82853ebd3dc985fb22667ec46320c2bcb6028272488521f06c",
  "2eece28eb9cb6341b3fdd199a686018a64515d16a82e40b96fad7d11663a86db",
  "301b7a41b3b279fb39b24a5c44e41a4a0d4da3d6f579ac1efeb973f7ca3911da",
  "31a07d498056211fc208eff311d4a11666b9e4c030cdfe7aca71cf1df1eaae73",
  "34a84a7529e83a1d9aeeeabd193cac5186d6c1333a810bd5843e91a138bfc579",
  "3523b0244fac48ac8150614de7818fdc5bf7f518996faa93a0f9ff4c3558fcc1",
  "359c4102d697965b225d90bf999eff9b69796c7b5d1a65e7ad7c40ba724a7a86",
  "37796df6968adb4ea0165b9f5f2d72cee8227f0d0c9e8a2700a1482fbe0e98f6",
  "3864ef82d7c8cdbca72c6df4717f106bea0e872f31232b10c6a993b64fafad9f",
  "38bedf272f14695514792f1294bad57bfbb7ea5104ff447b5b2dfe416dafab4f",
  "3900ac21442c473c57d622379bab5ce6abc31eab2d83ad1d8201d4665ec4c6a4",
  "391b427d75cbd8a10734f3a8869ff845e18b44b39522b49604afdd88e0fc09cd",
  "39fc56dd12c6318b09b463886d6753775187e1fd298e715b2e2cf1ba24d96f10",
  "3bf92e334340d3fef2690f06c36548ab8148159e92ef4c027b290a08c19a2672",
  "3c5797b889eabc7e014fe9f942ee0779ea8955056324778f1107179b3b12cbe4",
  "3df78a45ada717fe85c2695e00a3528afa6fa115f88f04b662c497cf94ad154e",
  "3ef500ce6201709c86298d3dd4814f6b54db8ce905bcea49b7dbedc06032f558",
  "3fb767aafcdcd32e5ecd5e5416bd346fb71bd4707d256f0de351e63aec61f3dc",
  "439ac62ba0e0eb83671fed1e12d9ac23a656a86e8f8f3f15a24c02704ebe41b9",
  "46ad6e36e07d2b7e896f0f40506ef648579ac8d3bf6405a0666829be6b9db1f6",
  "4b4a46b83b524be545d874502d8fdf7de613497cc0f502007e2f46cad0babf81",
  "4b6b8a6e090e418318634a1377820c383dba59e689eb0450c26de848bbcdd297",
  "4f4b329e6a0cb6e64441187d4510f9ec05a1fbb078d08d43e8c9418cb5678237",
  "551dfdafa41703a440ff3a1b9998a21b48f0382541aed58300259b69e6a6b83e",
  "59162f8895a52aa2c369f3f9ec28b1447b2113f59e6bdfc85e1d82c31629ea73",
  "5cfffbd5390e29e7054775c709da167b639e10aa5a596b9f4bf624c107e28fe6",
  "67690faaaf147800f297399aa0e3bd0fd04e6effb3912c0ad61a99ac4f41c489",
  "6d3796cf44172e83ce9968dc3948600c8ef08c356ae8eaffca318131b7788c0a",
  "79d8881faf1e695ded25c4f5efc3a8d1425310d27f6dad9323052f67efd9a42e",
  "7bdacdf54c8f1aca9d5ee1ca424d2643da5b0024b6df0e07a5c25c385efeeb6d",
  "7cf3f8a9cff7a5b30bb1f5067d99038db3a599a3e069e7d720a5b718e2a0d8e4",
  "81879e16fa7254e8c2f729bd576d7d15545c0512260844d028eddca796f27937",
  "8447aba824bdd84d6902490dd50920be508aa0aaa35f4238b2483be86691598e",
  "8bf594e1b295fc0110cb9cbe8d59d867f66cd8f3b724dcda1c59b584e044b6d9",
  "9005ff72981281b13937fc309818c1c83d514385f6bd9736eda5e0e58c6b634a",
  "9253a323a3de545256ca2aeadd57f886cc5f3ace6c5968f940794ee7f55a3819",
  "92f5372e80875cf981d76766344d1d229f86ba39e619e3bbeda544cc48d54973",
  "93d8208046ed614b36d647b747f487a377dcffa98a7895fea77118a180b792f9",
  "95716532b087b46ffce2502cddc5d20c2deb5bb782d2d8ca1feb13711df1012a",
  "99220fd43bf8905ecf09eff8991fb20ef0aa93f07cb2926395fab6dea878e967",
  "9b996b583106061dfa9d41b35134cb76aa01051dce945b87e2a819e5246511ee",
  "a127ea1a6a578b36016fd82c7f78fe653ad1130a705a419accfce6dd36c89cd2",
  "a20d746ae493ca031e39b8a4db1e4c2c0a31fa167d105c6080cc4e52ed4bb349",
  "a5372c8fe3f5bc5a162057010ba1e2bf2e57e37a54bdeedcc736b943ada3fe75",
  "a9198f5a6601a2eadaadf5096f3c495ef5d8399e5b99f1c4417ac8e5f40665ae",
  "a9eee41b4e1d470ab6bb42bef898d1facf23ef263b102bd4bf4135ee28b8f292",
  "b63d16c15801062ad79e67b31aa4cbf76fde7ff36dd16d2849e6da01220944f6",
  "b9c7b1c65a695c6573732bcd5bb2adb6977ca4ccda01c2a60a609acdffc1cef0",
  "bc16c4ce53a0ac36ffc723dec14b22cbe2e71c4e334fa7f53fbf61882a4fa09f",
  "bd5e458d61c944966786f49eecc7a0bc696e92847d244645d267e0b1e2a7bd9a",
  "bf1cf407a91ae0fa1e53e0c59c9bd8b806739d6c78a334ea42ff30ec11ac4e6f",
  "c3f6fbd9f85e2eac0ac7f61741cd4291ce11482f6a0016f880b221380bc0f552",
  "c611632aa6aeb22700c282fae3b5f6f2bf85c9e74820701204f3ef199e17572c",
  "d31d953ee864eee91add4f6fc093fa61eebf54fe51f61a7ed42626549c9c284f",
  "d400c6b10163b94e096939b2739b7afee5946826d194b85d2755bca844e98839",
  "d441fbbf6612210ca7c20906941b883526ef524c1c4791367e5d5bfc1bae6ae8",
  "d44bf81d32bdc9befb9a8606f98fd64edbfedc030f505ca2069047cf70ef74d6",
  "d4946e0a3a5fe027e22086f5674acd97454d6528fc740d3e0f3b947db7049e26",
  "daf18cedb3035628e024668e282e9800281701b559d628ec3715a047d0ab6c38",
  "dcc24443ffd0f18ea3eb3ca0d75217c8ba66821670e231ec3e61ec89b07d7a14",
  "de674f5227e15f0d6cfde614d9f07786fa8072da5b10087d9b99a3e81ec900c7",
  "e6cf0442a89c416a86706e16e06834803555a3b9c794e7963fa2ac0f369658a7",
  "e798a510106039c62cd466e3a193df35e69817bbff017715141867686a309e22",
  "ee69c11e4a1c7689e79686d9731f69f0aeb602243bf47e7f627793bfd6cf1ea0",
  "eea806d25b129b7789466507724f10b326e6a92f0b40619a060c7396f95e134d",
  "eed727999796ea54a0e5f30404a60f65f29814756cd2a506aeea80e898c654c6",
  "f94bac01d71bab46f49dc0df176852e86acf55d722d94edb0973fba2b670ed6b",
  "faaeec44ee67dcf4483045c1266379ca5381c2d83c5196f4b56600d40f6f5728",
  "fc31816d37f81190a8659bde120e63361adb5a8fda25e01e756b9a5a6457a87b",
  "ffc8d02491cf82aa4312cf88475f81c47eeb1238ead8133cca96d6bfa96ac64b"
];

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
  if (artInspector.open) {
    artInspector.close();
  }
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

  if (!artInspector.open) {
    artInspector.showModal();
  }

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

  galleryRecords = (await Promise.all(galleryArtworkIds.map(fetchArtwork))).map((record) => ({
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
  if (previousFocus) {
    previousFocus.focus();
    previousFocus = null;
  }
});

renderGallery().catch((error) => {
  galleryCount.textContent = "Error";
  artGrid.innerHTML = `<p class="carousel-error">${error.message}</p>`;
});
