"""Extract translatable strings from TypeScript/JavaScript source files."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Common i18n function patterns in TypeScript frameworks
I18N_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # React i18next: t("string"), t('string')
    ("t_func", re.compile(r"""\bt\s*\(\s*["']([^"']+)["']""", re.MULTILINE)),

    # i18n.t("string"), i18next.t("string")
    ("i18n_t", re.compile(r"""(?:i18n|i18next)\.t\s*\(\s*["']([^"']+)["']""", re.MULTILINE)),

    # useTranslation hook with t: const { t } = useTranslation(); t("string")
    # This is covered by t_func above

    # $t("string") - Vue i18n
    ("vue_t", re.compile(r"""\$t\s*\(\s*["']([^"']+)["']""", re.MULTILINE)),

    # {{ $t("string") }} - Vue template
    ("vue_template", re.compile(r"""\{\{\s*\$t\s*\(\s*["']([^"']+)["']\s*\)\s*\}\}""", re.MULTILINE)),

    # <Trans>text</Trans> - React i18next component
    ("trans_component", re.compile(r"""<Trans[^>]*>([^<]+)</Trans>""", re.MULTILINE)),

    # __("string") - generic gettext-style
    ("underscore", re.compile(r"""__\s*\(\s*["']([^"']+)["']""", re.MULTILINE)),

    # formatMessage({ defaultMessage: "string" }) - react-intl
    ("format_message", re.compile(r"""defaultMessage\s*:\s*["']([^"']+)["']""", re.MULTILINE)),

    # Angular i18n: $localize`string`
    ("angular_localize", re.compile(r"""\$localize\s*`([^`]+)`""", re.MULTILINE)),
]

# Patterns to ignore (comments, imports, etc.)
IGNORE_PATTERNS: list[re.Pattern[str]] = [
    # Single-line comments
    re.compile(r"//.*$", re.MULTILINE),
    # Multi-line comments (non-greedy)
    re.compile(r"/\*[\s\S]*?\*/", re.MULTILINE),
    # JSDoc comments
    re.compile(r"/\*\*[\s\S]*?\*/", re.MULTILINE),
    # Import statements
    re.compile(r"^import\s+.*$", re.MULTILINE),
    # Export type/interface
    re.compile(r"^export\s+(?:type|interface)\s+.*$", re.MULTILINE),
    # Console statements
    re.compile(r"console\.\w+\s*\([^)]*\)", re.MULTILINE),
    # Type annotations (basic)
    re.compile(r":\s*['\"][^'\"]+['\"]", re.MULTILINE),
]

# Strings to skip (likely not user-facing)
SKIP_STRINGS: set[str] = {
    "", " ", "\n", "\t",
    "true", "false", "null", "undefined",
    "GET", "POST", "PUT", "DELETE", "PATCH",
    "utf-8", "utf8", "ascii",
    "development", "production", "test",
    "error", "warning", "info", "debug",
}

# File extensions to scan
TYPESCRIPT_EXTENSIONS: set[str] = {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte"}


@dataclass
class ExtractedString:
    """A string extracted from source code."""

    text: str
    file_path: str
    line_number: int
    pattern_type: str

    @property
    def key_slug(self) -> str:
        """Generate a slug from the string for use as a key."""
        # Clean the string
        clean = self.text.lower().strip()
        # Replace non-alphanumeric with underscore
        clean = re.sub(r"[^a-z0-9]+", "_", clean)
        # Remove leading/trailing underscores
        clean = clean.strip("_")
        # Truncate if too long
        if len(clean) > 30:
            clean = clean[:30].rstrip("_")
        return clean or "string"

    @property
    def mini_hash(self) -> str:
        """Generate a short hash for uniqueness."""
        return hashlib.md5(self.text.encode()).hexdigest()[:6]


@dataclass
class ExtractionResult:
    """Result of string extraction from a codebase."""

    strings: list[ExtractedString] = field(default_factory=list)
    detected_language: str = "English"
    files_scanned: int = 0
    errors: list[str] = field(default_factory=list)


def detect_source_language(strings: list[str], sample_size: int = 5) -> str:
    """Detect the source language from a sample of strings.

    Uses simple heuristics based on common words/patterns.
    """
    if not strings:
        return "English"

    sample = strings[:sample_size]
    combined = " ".join(sample).lower()

    # Language detection based on common words
    language_indicators: dict[str, list[str]] = {
        "English": ["the", "is", "are", "you", "your", "hello", "welcome", "click", "submit", "cancel"],
        "French": ["le", "la", "les", "est", "sont", "vous", "votre", "bonjour", "bienvenue", "cliquez"],
        "Spanish": ["el", "la", "los", "es", "son", "tu", "su", "hola", "bienvenido", "clic"],
        "German": ["der", "die", "das", "ist", "sind", "sie", "ihr", "hallo", "willkommen", "klicken"],
        "Italian": ["il", "la", "i", "è", "sono", "tu", "tuo", "ciao", "benvenuto", "clicca"],
        "Portuguese": ["o", "a", "os", "é", "são", "você", "seu", "olá", "bem-vindo", "clique"],
        "Dutch": ["de", "het", "is", "zijn", "je", "jouw", "hallo", "welkom", "klik"],
        "Japanese": ["の", "は", "が", "を", "に", "こんにちは"],
        "Chinese": ["的", "是", "在", "了", "你好", "欢迎"],
        "Korean": ["의", "는", "이", "을", "안녕하세요"],
    }

    scores: dict[str, int] = {}
    for lang, indicators in language_indicators.items():
        score = sum(1 for word in indicators if word in combined)
        if score > 0:
            scores[lang] = score

    if scores:
        return max(scores, key=scores.get)

    # Default to English if no clear match
    return "English"


def strip_ignored_content(content: str) -> str:
    """Remove comments, imports, and other non-translatable content."""
    result = content
    for pattern in IGNORE_PATTERNS:
        result = pattern.sub(" ", result)
    return result


def extract_strings_from_content(
    content: str,
    file_path: str,
) -> Iterator[ExtractedString]:
    """Extract translatable strings from file content."""
    # Strip comments and other ignored content
    clean_content = strip_ignored_content(content)

    # Track line numbers in original content
    lines = content.split("\n")

    seen_strings: set[str] = set()

    for pattern_name, pattern in I18N_PATTERNS:
        for match in pattern.finditer(clean_content):
            text = match.group(1).strip()

            # Skip empty or common non-translatable strings
            if not text or text in SKIP_STRINGS:
                continue

            # Skip if already seen (dedup within file)
            if text in seen_strings:
                continue
            seen_strings.add(text)

            # Skip strings that look like code/paths
            if _looks_like_code(text):
                continue

            # Find line number
            line_num = content[:match.start()].count("\n") + 1

            yield ExtractedString(
                text=text,
                file_path=file_path,
                line_number=line_num,
                pattern_type=pattern_name,
            )


def _looks_like_code(text: str) -> bool:
    """Check if a string looks like code rather than user-facing text."""
    # File paths
    if re.match(r"^[./\\]|^\w+[./\\]", text):
        return True
    # URLs
    if re.match(r"^https?://|^www\.", text):
        return True
    # Likely variable/class names (camelCase, snake_case, PascalCase)
    if re.match(r"^[a-z]+[A-Z]|^[A-Z][a-z]+[A-Z]|^[a-z]+_[a-z]+$", text):
        return True
    # CSS classes or IDs
    if re.match(r"^[.#][a-zA-Z]", text):
        return True
    # JSON-like or code-like
    if text.startswith("{") or text.startswith("["):
        return True
    # Very short single words that are likely code
    if len(text) <= 2 and text.isalpha():
        return True
    return False


def generate_namespace_key(
    extracted: ExtractedString,
    app_name: str,
    existing_keys: set[str],
) -> str:
    """Generate a namespaced key for an extracted string.

    Format: app.module.string_slug or app.module.truncated_hash
    """
    # Get module from file path
    path = Path(extracted.file_path)

    # Remove common prefixes and extension
    parts = list(path.with_suffix("").parts)

    # Remove common root folders
    skip_parts = {"src", "app", "lib", "components", "pages", "views", "modules"}
    while parts and parts[0].lower() in skip_parts:
        parts.pop(0)

    # Convert to module path
    if parts:
        module = ".".join(p.lower() for p in parts)
    else:
        module = "common"

    # Clean module name
    module = re.sub(r"[^a-z0-9.]+", "_", module).strip("_.")

    # Generate string key
    slug = extracted.key_slug

    # Build full key
    base_key = f"{app_name}.{module}.{slug}"

    # Ensure uniqueness
    if base_key not in existing_keys:
        return base_key

    # Add hash for uniqueness
    key_with_hash = f"{app_name}.{module}.{slug}_{extracted.mini_hash}"
    return key_with_hash


def scan_directory(
    directory: Path,
    app_name: str = "app",
    exclude_patterns: list[str] | None = None,
) -> ExtractionResult:
    """Scan a directory for translatable strings.

    Args:
        directory: Root directory to scan.
        app_name: Application name for key namespace.
        exclude_patterns: Glob patterns to exclude.

    Returns:
        ExtractionResult with all extracted strings.
    """
    result = ExtractionResult()
    exclude_patterns = exclude_patterns or ["node_modules", "dist", "build", ".git", "__pycache__"]

    # Find all TypeScript/JavaScript files
    files: list[Path] = []
    for ext in TYPESCRIPT_EXTENSIONS:
        files.extend(directory.rglob(f"*{ext}"))

    # Filter out excluded paths
    def should_exclude(path: Path) -> bool:
        path_str = str(path)
        return any(excl in path_str for excl in exclude_patterns)

    files = [f for f in files if not should_exclude(f)]

    all_strings: list[ExtractedString] = []
    existing_keys: set[str] = set()

    for file_path in sorted(files):
        result.files_scanned += 1

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            result.errors.append(f"Error reading {file_path}: {e}")
            continue

        # Get relative path for cleaner output
        try:
            rel_path = str(file_path.relative_to(directory))
        except ValueError:
            rel_path = str(file_path)

        for extracted in extract_strings_from_content(content, rel_path):
            all_strings.append(extracted)

    # Detect language from first strings
    if all_strings:
        texts = [s.text for s in all_strings]
        result.detected_language = detect_source_language(texts)

    result.strings = all_strings
    return result


def generate_i18n_dict(
    extraction: ExtractionResult,
    app_name: str = "app",
) -> dict[str, str]:
    """Generate an i18n dictionary from extracted strings.

    Args:
        extraction: The extraction result.
        app_name: Application name for key namespace.

    Returns:
        Dictionary mapping keys to source strings.
    """
    i18n_dict: dict[str, str] = {}
    existing_keys: set[str] = set()

    for extracted in extraction.strings:
        key = generate_namespace_key(extracted, app_name, existing_keys)
        existing_keys.add(key)
        i18n_dict[key] = extracted.text

    return i18n_dict


def nest_flat_dict(flat_dict: dict[str, str]) -> dict:
    """Convert flat dot-notation dict to nested dict.

    Example:
        {"app.button.submit": "Submit"} -> {"app": {"button": {"submit": "Submit"}}}
    """
    nested: dict = {}

    for key, value in flat_dict.items():
        parts = key.split(".")
        current = nested

        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value

    return nested
