"""Local history imports are restricted to the Home Assistant config directory."""
from pathlib import Path


def import_source(base, filename, suffixes):
    base = Path(base).resolve()
    source = (base / filename).resolve()
    if not source.is_relative_to(base) or source.suffix.lower() not in suffixes:
        raise ValueError('Import file must have a supported extension and be inside the Home Assistant config directory')
    if not source.is_file():
        raise ValueError(f'File not found: {source}')
    return source
