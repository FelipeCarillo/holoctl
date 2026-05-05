from rich.console import Console

# Force modern Windows terminal rendering — avoids cp1252 encoding errors on legacy console.
console = Console(legacy_windows=False)
