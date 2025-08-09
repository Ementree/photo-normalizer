"""Photo Normalizer package."""

from importlib.metadata import version, PackageNotFoundError


def get_version() -> str:
    try:
        return version("photo-normalizer")
    except PackageNotFoundError:
        return "0.0.0"


__all__ = ["get_version"]

