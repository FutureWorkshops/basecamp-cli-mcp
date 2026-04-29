from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("basecamp-cli-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
