const palettes = [
  ["#151515", "#f97316", "#16a34a", "#2563eb", "#f8fafc"],
  ["#0f172a", "#eab308", "#db2777", "#14b8a6", "#f1f5f9"],
  ["#27272a", "#ef4444", "#22c55e", "#38bdf8", "#fafafa"],
  ["#1f2937", "#f59e0b", "#84cc16", "#6366f1", "#fff7ed"]
];

const pixelGrid = document.querySelector("#pixelGrid");
const squareId = document.querySelector("#squareId");
const regenerateButton = document.querySelector("#regenerateButton");

let squareCount = 1;

function createPixelColor(x, y, palette, seed) {
  const center = Math.abs(3.5 - x) + Math.abs(3.5 - y);
  const diagonal = x === y || x + y === 7;
  const ring = x === 0 || y === 0 || x === 7 || y === 7;

  if (diagonal) return palette[(seed + x + y) % palette.length];
  if (ring) return palette[(seed + 1) % palette.length];
  if (center < 3) return palette[(seed + 2 + x) % palette.length];
  return palette[(seed + 3 + y) % palette.length];
}

function renderSquare() {
  const seed = squareCount % palettes.length;
  const palette = palettes[seed];
  const fragment = document.createDocumentFragment();

  pixelGrid.innerHTML = "";

  for (let y = 0; y < 8; y += 1) {
    for (let x = 0; x < 8; x += 1) {
      const pixel = document.createElement("span");
      pixel.className = "pixel";
      pixel.style.backgroundColor = createPixelColor(x, y, palette, seed);
      pixel.title = `x:${x}, y:${y}`;
      fragment.appendChild(pixel);
    }
  }

  squareId.textContent = `SQ-08-${String(squareCount).padStart(4, "0")}`;
  pixelGrid.appendChild(fragment);
}

regenerateButton.addEventListener("click", () => {
  squareCount += 1;
  renderSquare();
});

renderSquare();
