"""Models and utilities for i18n file handling."""

from enum import Enum
from pathlib import Path


class I18nFormat(str, Enum):
    """Supported i18n file formats."""

    JSON = "json"
    YAML = "yaml"
    PO = "po"
    PROPERTIES = "properties"
    XLIFF = "xliff"
    JAVASCRIPT = "javascript"
    PYTHON = "python"
    RUST = "rust"


# Map file extensions to formats
EXTENSION_FORMAT_MAP: dict[str, I18nFormat] = {
    ".json": I18nFormat.JSON,
    ".yaml": I18nFormat.YAML,
    ".yml": I18nFormat.YAML,
    ".po": I18nFormat.PO,
    ".pot": I18nFormat.PO,
    ".properties": I18nFormat.PROPERTIES,
    ".xlf": I18nFormat.XLIFF,
    ".xliff": I18nFormat.XLIFF,
    ".js": I18nFormat.JAVASCRIPT,
    ".ts": I18nFormat.JAVASCRIPT,
    ".mjs": I18nFormat.JAVASCRIPT,
    ".py": I18nFormat.PYTHON,
    ".rs": I18nFormat.RUST,
}


def detect_i18n_format(filename: str) -> I18nFormat:
    """Detect i18n format from filename extension."""
    ext = Path(filename).suffix.lower()
    if ext not in EXTENSION_FORMAT_MAP:
        raise ValueError(
            f"Unsupported file format: {ext}. "
            f"Supported: {', '.join(EXTENSION_FORMAT_MAP.keys())}"
        )
    return EXTENSION_FORMAT_MAP[ext]
