try:
    from importlib.metadata import version
    __version__ = version("projctl")
except Exception:
    __version__ = "0.3.0"
