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

The script creates separate JSON and SVG files named after the artwork's pixel hash key:

```text
art/9f2c...a81d.json
art/9f2c...a81d.svg
```

Each JSON file includes the artwork key, matching JSON/SVG filenames, seed, title, abstract color reasoning, exact pixel coordinates, hex colors, and a pixel hash used to prevent duplicate arrangements across separate runs.
