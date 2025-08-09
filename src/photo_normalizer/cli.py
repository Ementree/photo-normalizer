import os
import re
import sys
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple

import click
from PIL import Image, ExifTags, ImageOps
from tqdm import tqdm

# Enable HEIC/HEIF support if available. If not, JPEG/PNG/etc. still work.
try:
    from pillow_heif import register_heif_opener  # type: ignore

    try:
        register_heif_opener()
    except Exception:
        pass
except Exception:
    register_heif_opener = None  # type: ignore


SUPPORTED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"}
OUTPUT_FORMAT_TO_EXT = {
    "jpeg": ".jpg",
    "png": ".png",
    "webp": ".webp",
    "tiff": ".tiff",
}


DATETIME_NAME_PATTERNS = [
    # IMG_20210102_153045, 2021-01-02 15.30.45, 20210102_153045, etc.
    re.compile(r"(?P<y>20\d{2})[-_\.]?(?P<m>0[1-9]|1[0-2])[-_\.]?(?P<d>[0-2]\d|3[01])[_\-\s\.]?(?P<h>[01]\d|2[0-3])[:\._-]?(?P<min>[0-5]\d)[:\._-]?(?P<s>[0-5]\d)"),
]


def try_parse_from_name(name: str) -> Optional[datetime]:
    for pattern in DATETIME_NAME_PATTERNS:
        match = pattern.search(name)
        if match:
            try:
                return datetime(
                    int(match.group("y")),
                    int(match.group("m")),
                    int(match.group("d")),
                    int(match.group("h")),
                    int(match.group("min")),
                    int(match.group("s")),
                )
            except Exception:
                continue
    return None


def get_exif_datetime(img: Image.Image) -> Optional[datetime]:
    try:
        exif_raw = img.getexif()
        if not exif_raw:
            return None
        exif = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif_raw.items()}
        for key in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
            value = exif.get(key)
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", "ignore")
                except Exception:
                    pass
            if isinstance(value, str):
                # Typical format: 2021:01:02 15:30:45
                value = value.strip().replace("/", ":")
                try:
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                except Exception:
                    # Try more relaxed variants
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                        try:
                            return datetime.strptime(value, fmt)
                        except Exception:
                            continue
        return None
    except Exception:
        return None


def get_file_times(path: Path) -> datetime:
    stat = path.stat()
    # Prefer birth time if available on macOS, else fallback to mtime
    try:
        birth_ts = getattr(stat, "st_birthtime", None)
    except Exception:
        birth_ts = None
    ts = birth_ts or stat.st_mtime
    return datetime.fromtimestamp(ts)


def determine_capture_datetime(path: Path) -> datetime:
    # 1) EXIF
    try:
        with Image.open(path) as img:
            dt = get_exif_datetime(img)
            if dt:
                return dt
    except Exception:
        pass

    # 2) Filename patterns
    dt_from_name = try_parse_from_name(path.name)
    if dt_from_name:
        return dt_from_name

    # 3) File times
    return get_file_times(path)


def iter_input_files(root: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTS:
                yield path
    else:
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTS:
                yield path


@dataclass
class PlanItem:
    source: Path
    target: Path
    capture_dt: datetime
    needs_reencode: bool


def build_target_path(
    output_dir: Path,
    capture_dt: datetime,
    idx: int,
    subfolders: str,
    target_ext: str,
) -> Path:
    base_name = capture_dt.strftime("%Y-%m-%d_%H-%M-%S") + f"_{idx:04d}" + target_ext
    if subfolders == "none":
        return output_dir / base_name
    if subfolders == "day":
        return output_dir / capture_dt.strftime("%Y/%m/%d") / base_name
    if subfolders == "month":
        return output_dir / capture_dt.strftime("%Y/%m") / base_name
    if subfolders == "year":
        return output_dir / capture_dt.strftime("%Y") / base_name
    return output_dir / base_name


def ensure_unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, ext = path.stem, path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}__{counter}{ext}")
        if not candidate.exists():
            return candidate
        counter += 1


def save_image(
    src_path: Path,
    dest_path: Path,
    output_format: str,
    quality: int,
    keep_metadata: bool,
    reencode: bool,
) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if not reencode:
        shutil.copy2(src_path, dest_path)
        return
    with Image.open(src_path) as img:
        # Respect EXIF orientation when re-encoding
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        save_kwargs = {}
        if output_format == "jpeg":
            save_kwargs.update({"quality": quality, "optimize": True})
        exif_bytes = None
        if keep_metadata and output_format == "jpeg":
            exif_bytes = img.info.get("exif")
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
        if not keep_metadata:
            img.info.clear()
        img.convert("RGB").save(dest_path, format=output_format.upper(), **save_kwargs)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--output", "output_dir", required=True, type=click.Path(file_okay=False, path_type=Path), help="Output directory")
@click.option("--format", "output_format", type=click.Choice(sorted(OUTPUT_FORMAT_TO_EXT.keys())), default="jpeg", show_default=True, help="Output format")
@click.option("--quality", type=click.IntRange(1, 100), default=90, show_default=True, help="Quality for compressed formats")
@click.option("--keep-metadata/--strip-metadata", default=True, show_default=True, help="Keep or strip metadata")
@click.option("--subfolders", type=click.Choice(["none", "day", "month", "year"]), default="none", show_default=True, help="Date-based subfolders")
@click.option("--hash-duplicates/--no-hash-duplicates", default=False, show_default=True, help="Enable perceptual hash duplicate detection (not implemented; reserved)")
@click.option("--copy-unchanged/--reencode", "copy_unchanged", default=True, show_default=True, help="Copy images that already match target format instead of re-encoding")
@click.option("-r", "--recursive", is_flag=True, help="Recurse into subdirectories")
@click.option("--dry-run", is_flag=True, help="Show planned actions without writing files")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def main(
    input_dir: Path,
    output_dir: Path,
    output_format: str,
    quality: int,
    keep_metadata: bool,
    subfolders: str,
    hash_duplicates: bool,  # placeholder
    copy_unchanged: bool,
    recursive: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Convert photos to a uniform format and order them by capture date."""
    del hash_duplicates  # not implemented in initial version

    target_ext = OUTPUT_FORMAT_TO_EXT[output_format]
    input_files = list(iter_input_files(input_dir, recursive))
    if not input_files:
        click.echo("No supported images found.")
        sys.exit(1)

    plan: list[PlanItem] = []
    for path in input_files:
        try:
            capture_dt = determine_capture_datetime(path)
        except Exception:
            capture_dt = get_file_times(path)

        needs_reencode = True
        if copy_unchanged and path.suffix.lower() == target_ext:
            needs_reencode = False

        plan.append(
            PlanItem(
                source=path,
                capture_dt=capture_dt,
                target=Path(),  # placeholder filled below
                needs_reencode=needs_reencode,
            )
        )

    # Sort by capture date then by name for stable ordering
    plan.sort(key=lambda p: (p.capture_dt, p.source.name))

    # Assign target paths with sequence per second to avoid collisions
    last_second: Optional[datetime] = None
    seq_in_second = 0
    for item in plan:
        current_second = item.capture_dt.replace(microsecond=0)
        if last_second is None or current_second != last_second:
            seq_in_second = 1
            last_second = current_second
        else:
            seq_in_second += 1
        target_path = build_target_path(output_dir, item.capture_dt, seq_in_second, subfolders, target_ext)
        item.target = ensure_unique(target_path)

    if dry_run or verbose:
        for item in plan:
            action = "COPY" if not item.needs_reencode else f"ENCODE->{output_format}"
            click.echo(f"{item.source} -> {item.target} [{item.capture_dt:%Y-%m-%d %H:%M:%S}] {action}")

    if dry_run:
        return

    for item in tqdm(plan, desc="Processing", unit="img"):
        save_image(
            src_path=item.source,
            dest_path=item.target,
            output_format=output_format,
            quality=quality,
            keep_metadata=keep_metadata,
            reencode=item.needs_reencode,
        )

    click.echo(f"Done. Wrote {len(plan)} images to {output_dir}")


if __name__ == "__main__":
    main()


