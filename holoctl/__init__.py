"""holoctl — single source of truth for the package version.

`__version__` is derived solely from the installed distribution metadata
(`importlib.metadata.version("holoctl")`), which is populated from
`pyproject.toml`'s `[project].version` at build/install time. There is no
hardcoded fallback string to drift out of sync — if the package is somehow not
installed (e.g. running from a bare source tree without an editable install),
we surface that explicitly as ``0.0.0+unknown`` rather than lying about a real
version number.
"""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("holoctl")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
