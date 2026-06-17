"""RSS reader application."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = f"v{version('feeds')}"
except PackageNotFoundError:
    __version__ = "unknown"
