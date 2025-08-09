# Photo Normalizer

Convert photos from various smartphones and cameras into a consistent format, name, and folder structure.

## Features
- Normalize formats: JPEG, PNG, WebP, TIFF
- Chronological ordering by capture date (EXIF → filename → file time)
- Consistent names: `YYYY-MM-DD_HH-MM-SS_####.ext`
- Optional subfolders: none, year, month, or day
- Keep or strip metadata
- Auto-apply EXIF orientation on re-encode
- HEIC/HEIF support via `pillow-heif`
- Web UI with live progress

## Installation

Using a virtual environment is recommended.

```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

This installs two commands:
- `photo-normalizer` (CLI)
- `photo-normalizer-web` (Web UI)

If your shell cannot find these commands, run via Python:
- `python -m photo_normalizer.web_cli ...`

## CLI Usage

```
photo-normalizer <input_dir> -o <output_dir> [options]
```

Key options:
- `--format {jpeg,png,webp,tiff}` (default: `jpeg`)
- `--quality 1..100` (default: `90`)
- `--keep-metadata/--strip-metadata` (default: keep)
- `--subfolders {none,day,month,year}` (default: `none`)
- `--copy-unchanged/--reencode` (default: copy unchanged)
- `-r, --recursive`
- `--dry-run`
- `-v, --verbose`

Examples:

```
photo-normalizer ~/Pictures/Unsorted -o ~/Pictures/Normalized
photo-normalizer ~/iPhone/HEIC -o ~/Pictures/JPEG --format jpeg --quality 95 -r
photo-normalizer ./input -o ./output --subfolders day --strip-metadata -r
photo-normalizer ./input -o ./output --dry-run -v
```

## Web UI

Start the web interface:

```
photo-normalizer-web --host 127.0.0.1 --port 5000 --debug
# or
python -m photo_normalizer.web_cli --host 127.0.0.1 --port 5000 --debug
```

Open `http://127.0.0.1:5000` in your browser.

In the UI you can:
- Choose the input folder containing photos
- Choose the output folder where converted files will be saved
- Set output format, quality, date subfolders
- Toggle recursion, metadata retention, and fast copy
- Start processing and track progress in real time

Notes:
- On macOS, the Browse buttons use a native folder picker. On other OSes, paste paths manually.
- All converted photos are written into the output folder you select.

## Processing options

- **Output Format** (jpeg/png/webp/tiff; default: jpeg):
  - Target file type and extension.
  - JPEG: best compatibility; lossy compression.
  - PNG: lossless; larger files; good for graphics.
  - WebP: modern; small files; variable compatibility on older systems.
  - TIFF: large/archival; minimal compression.

- **Quality (1–100)** (default: 90):
  - Compression quality for JPEG output. Higher = larger files, better quality.
  - For other formats, encoder defaults are used (the slider has no effect).

- **Organization** (none/day/month/year; default: none):
  - Controls the output folder structure:
    - none: all files in the root of the output folder
    - day: YYYY/MM/DD/
    - month: YYYY/MM/
    - year: YYYY/

- **Include subfolders** (default: on):
  - Recursively process images in all subdirectories of the input folder.

- **Keep photo metadata** (default: on):
  - Preserve EXIF metadata when saving JPEGs. If off, metadata is stripped.
  - For other formats, metadata is typically not preserved.

- **Fast mode (copy unchanged files)** (default: on):
  - If the input already matches the chosen output format, copy the file as-is instead of re-encoding.
  - Faster, lossless, and preserves the original bytes (including metadata and color profiles).

## How It Works

Capture date detection order:
1. EXIF (`DateTimeOriginal`, `DateTime`, `DateTimeDigitized`)
2. Filename pattern (e.g., `IMG_20240115_143045.jpg`, `2021-01-02 15.30.45`)
3. File timestamps (birth time on macOS if available, else modification time)

Output filename format:

```
YYYY-MM-DD_HH-MM-SS_####.ext
```

`####` is a per-second sequence; if a name collision occurs, a `__N` suffix is appended.

## Troubleshooting

- HEIC/HEIF: Ensure `pillow-heif` is installed. If problems persist, convert to JPEG/PNG first or install OS codecs.
- Command not found: Activate your virtual environment or run via `python -m photo_normalizer.web_cli`.
- Permissions: Ensure you have write access to the output directory.

## Development

```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

Run CLI:

```
photo-normalizer --help
```

Run Web UI (dev):

```
python -m photo_normalizer.web_cli --host 127.0.0.1 --port 5000 --debug
```
