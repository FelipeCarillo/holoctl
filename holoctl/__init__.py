try:
    from importlib.metadata import version
    __version__ = version("holoctl")
except Exception:
    __version__ = "0.7.1"
