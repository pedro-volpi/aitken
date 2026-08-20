"""mentat — treinador CLI de aritmética mental."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mentat")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
