# Square Project

Square Project is an art website dedicated to digital square art. The collection is built around simple pixel-based compositions, with the most popular format being an 8 by 8 pixel square.

The project presents these small digital squares as collectible visual worlds. Each square is minimal in size, but treated as its own complete artwork, pattern, or tiny environment.

## About the Collection

Square Project aims to become the world's largest square art collection. The focus is on digital squares, pixel grids, and small-format artworks that turn a basic geometric shape into a creative system.

The 8 by 8 pixel square is the signature format of the project. Its limited grid creates a clear structure for color, rhythm, abstraction, characters, symbols, and miniature worlds.

## Concept

This website is an art project exploring how much expression can fit inside a square. By working with strict pixel limits, the collection celebrates simplicity, repetition, variation, and the visual language of early digital art.

## Vision

The goal is to build the largest square art collection in the world and create a recognizable home for digital square artworks.

## Local Website Development

Run the local dev server when editing HTML, CSS, JavaScript, or art JSON/SVG files:

```bash
python3 scripts/dev_server.py
```

Then open `http://127.0.0.1:8000/`. The server sends no-cache headers and reloads the browser tab whenever a watched file changes, so you do not need to clear browser history or cache while developing.

## Stripe Payment Links

Customer orders use two reusable Stripe Payment Links, matching the simple outbound
link approach used by Kumquat product cards. The gallery opens the selected
payment link directly instead of creating a Checkout Session through a backend.

Create two reusable Stripe Payment Links in Stripe:

- 8x8 art print, `$24`
- 12x12 framed print with an 8x8 image area, `$39`

Add the public `buy.stripe.com` URLs to `.env`:

```env
STRIPE_PRINT_PAYMENT_LINK=https://buy.stripe.com/...
STRIPE_FRAMED_PAYMENT_LINK=https://buy.stripe.com/...
```

Then publish those URLs into the static browser config:

```bash
python3 scripts/setup_stripe_shop.py
```

`STRIPE_SECRET_KEY` is optional. If it is set and the payment-link URLs are not
already in `.env`, the helper creates or reuses the product, prices, and payment
links through the Stripe API.

Run the local dev server for link testing:

```bash
python3 scripts/dev_server.py
```

The gallery appends `client_reference_id=artworkId_variant_frameType` to framed
payment links, for example `9005ff...634a_framed_black`, so orders can be
reconciled in Stripe without creating a separate product per artwork or frame
color.

## Local Art Job GUI

Run the separate local art job server when you want a basic browser UI for generator scripts:

```bash
.venv/bin/python scripts/art_job_server.py
```

Then open `http://127.0.0.1:8010/`. This server is only a local control panel for running art jobs and viewing job output/status. It is not part of the public static website.

## Generate Pixel Art Locally

The project includes a local Python script for design-time art generation. It asks OpenAI for structured 8 by 8 abstract pixel art data, validates the response, checks for duplicate pixel arrangements, and saves both the JSON record and SVG image in the `art/` directory.

The prompt is designed for abstract art, not literal miniature pictures. Seeds are interpreted as emotional tone, pattern logic, contrast, rhythm, color movement, and collisions of feeling inside the square. Concrete words in a seed are treated as metaphor, not objects to draw.

This script is not part of the public website and should not run in the browser or on a public server. It reads the API key from your local `.env` file only when you run it from your machine.

Set your API key in `.env`:

```env
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

Create the local Python environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Run the generator with a text seed:

```bash
.venv/bin/python scripts/generate_art.py "sunset over a tiny digital city"
```

Generate multiple unique variations from one seed:

```bash
.venv/bin/python scripts/generate_art.py --count 40 "collisions of emotion, contrast, pressure, and release"
```

By default, the generator also loads `scripts/seed.json` as a local art-direction library. For each request it deterministically samples an emotional contrast, 8 by 8 layout, flow, pattern pair, edge style, contrast type, shape seed, palette family, broken-pixel count, and negative-space rule. That structured brief is sent to the model and saved in each generated JSON file as `generationSpec`, which makes batches more varied and easier to audit.

Use a different library or skip it:

```bash
.venv/bin/python scripts/generate_art.py --seed-library scripts/seed.json "fear becoming hope"
.venv/bin/python scripts/generate_art.py --no-seed-library "fear becoming hope"
```

The script creates separate JSON and SVG files named after the artwork's pixel hash key:

```text
art/9f2c...a81d.json
art/9f2c...a81d.svg
```

Each JSON file includes the artwork key, matching JSON/SVG filenames, seed, title, abstract color reasoning, exact pixel coordinates, hex colors, and a pixel hash used to prevent duplicate arrangements across separate runs.

The public gallery reads `art/manifest.json` instead of a manually maintained
JavaScript list. The generator updates that manifest after each successful run.
If you add JSON/SVG artwork files directly to `art/`, rebuild the manifest:

```bash
python3 scripts/build_gallery_manifest.py
```
