"""RSS reader application."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("feeds")
except PackageNotFoundError:
    __version__ = "unknown"
