"""Placeholder extraction and restoration for i18n translation.

Protects placeholders, ICU syntax, and HTML tags during translation.
"""

import re
from dataclasses import dataclass, field
from typing import NamedTuple


class PlaceholderMatch(NamedTuple):
    """A single placeholder match with its position."""

    start: int
    end: int
    original: str
    pattern_type: str


@dataclass
class ExtractionResult:
    """Result of placeholder extraction."""

    sanitized_text: str
    placeholders: list[PlaceholderMatch] = field(default_factory=list)
    token_map: dict[str, str] = field(default_factory=dict)


class PlaceholderHandler:
    """Handles extraction and restoration of placeholders in translatable text.

    Supported patterns:
    - Python format: {name}, {0}, {key.nested}
    - Template double braces: {{variable}}
    - Printf: %s, %d, %f, %.2f, %03d
    - Dollar: $name, ${expression}
    - HTML tags: <b>, </b>, <br/>, <a href="...">
    - HTML entities: &nbsp;, &#8217;, &#x2019;
    - ICU plural: {count, plural, one {# item} other {# items}}
    - ICU select: {gender, select, male {He} female {She}}
    - ICU selectordinal: {pos, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}
    """

    # Token prefix used for placeholder replacement
    TOKEN_PREFIX = "__PH_"
    TOKEN_SUFFIX = "__"

    # Regex patterns for different placeholder types
    # Order matters - more specific patterns should come first
    PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        # ICU message format (plural, select, selectordinal)
        # Match the full ICU expression including nested braces
        ("icu", re.compile(
            r"\{[^,}]+,\s*(?:plural|select|selectordinal)\s*,"
            r"(?:[^{}]*\{[^{}]*\})*[^{}]*\}",
            re.IGNORECASE
        )),

        # Template double braces {{variable}} - must come before single braces
        ("template_double", re.compile(r"\{\{[^}]+\}\}")),

        # Python/JS format strings {name}, {0}, {key.nested}, {name:format}
        ("python_format", re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_.]*(?::[^}]*)?\}")),
        ("python_index", re.compile(r"\{[0-9]+(?::[^}]*)?\}")),

        # Printf format: %s, %d, %f, %.2f, %03d, etc.
        ("printf", re.compile(r"%[-+0 #]*(?:[0-9]+|\*)?(?:\.(?:[0-9]+|\*))?[hlL]?[diouxXeEfFgGcrsn%]")),

        # Dollar variables: $name, ${expression}
        ("dollar_brace", re.compile(r"\$\{[^}]+\}")),
        ("dollar_name", re.compile(r"\$[a-zA-Z_][a-zA-Z0-9_]*")),

        # HTML/XML tags (self-closing and paired)
        ("html_tag", re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s+[^>]*)?\s*/?>", re.IGNORECASE)),

        # HTML entities: &nbsp;, &#8217;, &#x2019;
        ("html_entity", re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);")),
    ]

    def __init__(self, custom_patterns: list[tuple[str, re.Pattern[str]]] | None = None):
        """Initialize with optional custom patterns.

        Args:
            custom_patterns: Additional patterns to match. Each tuple is (name, compiled_regex).
        """
        self.patterns = list(self.PATTERNS)
        if custom_patterns:
            self.patterns.extend(custom_patterns)

    def extract(self, text: str) -> ExtractionResult:
        """Extract all placeholders from text, replacing them with tokens.

        Args:
            text: The text to process.

        Returns:
            ExtractionResult with sanitized text and placeholder information.
        """
        if not text:
            return ExtractionResult(sanitized_text=text)

        # Find all matches from all patterns
        all_matches: list[PlaceholderMatch] = []

        for pattern_type, pattern in self.patterns:
            for match in pattern.finditer(text):
                all_matches.append(PlaceholderMatch(
                    start=match.start(),
                    end=match.end(),
                    original=match.group(),
                    pattern_type=pattern_type,
                ))

        if not all_matches:
            return ExtractionResult(sanitized_text=text)

        # Sort by start position (descending) to replace from end to start
        # This preserves positions for earlier matches
        all_matches.sort(key=lambda m: m.start)

        # Remove overlapping matches (keep the first one by position)
        filtered_matches: list[PlaceholderMatch] = []
        last_end = -1
        for match in all_matches:
            if match.start >= last_end:
                filtered_matches.append(match)
                last_end = match.end

        # Build sanitized text and token map
        token_map: dict[str, str] = {}
        result_parts: list[str] = []
        last_pos = 0

        for i, match in enumerate(filtered_matches):
            # Add text before this match
            result_parts.append(text[last_pos:match.start])

            # Generate token
            token = f"{self.TOKEN_PREFIX}{i}{self.TOKEN_SUFFIX}"
            token_map[token] = match.original
            result_parts.append(token)

            last_pos = match.end

        # Add remaining text
        result_parts.append(text[last_pos:])

        return ExtractionResult(
            sanitized_text="".join(result_parts),
            placeholders=filtered_matches,
            token_map=token_map,
        )

    def restore(self, translated_text: str, extraction: ExtractionResult) -> str:
        """Restore placeholders in translated text.

        Args:
            translated_text: The translated text with tokens.
            extraction: The ExtractionResult from extract().

        Returns:
            Translated text with original placeholders restored.
        """
        if not extraction.token_map:
            return translated_text

        result = translated_text
        for token, original in extraction.token_map.items():
            result = result.replace(token, original)

        return result

    def validate(self, original: str, translated: str, extraction: ExtractionResult) -> list[str]:
        """Validate that all placeholders are preserved in translation.

        Args:
            original: Original text.
            translated: Translated text after restoration.
            extraction: The ExtractionResult from extract().

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        # Check each placeholder is present in the translation
        for placeholder in extraction.placeholders:
            if placeholder.original not in translated:
                errors.append(
                    f"Missing {placeholder.pattern_type} placeholder: {placeholder.original}"
                )

        # Check for unreplaced tokens
        token_pattern = re.compile(rf"{re.escape(self.TOKEN_PREFIX)}\d+{re.escape(self.TOKEN_SUFFIX)}")
        unreplaced = token_pattern.findall(translated)
        if unreplaced:
            errors.append(f"Unreplaced tokens found: {', '.join(unreplaced)}")

        return errors

    def count_placeholders(self, text: str) -> dict[str, int]:
        """Count placeholders by type in text.

        Args:
            text: Text to analyze.

        Returns:
            Dict mapping pattern_type to count.
        """
        extraction = self.extract(text)
        counts: dict[str, int] = {}
        for placeholder in extraction.placeholders:
            counts[placeholder.pattern_type] = counts.get(placeholder.pattern_type, 0) + 1
        return counts


class ICUParser:
    """Parser for ICU MessageFormat syntax.

    Handles complex nested ICU expressions by extracting only the
    translatable parts while preserving the structure.
    """

    # ICU keywords that should not be translated
    ICU_KEYWORDS = frozenset([
        "plural", "select", "selectordinal",
        "zero", "one", "two", "few", "many", "other",
        "male", "female", "neuter",
        "=0", "=1", "=2",
    ])

    @staticmethod
    def is_icu_message(text: str) -> bool:
        """Check if text contains ICU message format syntax."""
        return bool(re.search(
            r"\{[^,}]+,\s*(?:plural|select|selectordinal)\s*,",
            text,
            re.IGNORECASE
        ))

    @staticmethod
    def extract_translatable_parts(icu_text: str) -> list[tuple[int, int, str]]:
        """Extract translatable parts from ICU message.

        Returns list of (start, end, text) tuples for translatable content.
        """
        # This is a simplified implementation
        # A full ICU parser would be more complex
        parts: list[tuple[int, int, str]] = []

        # Find content between { } that isn't a variable or keyword
        # Looking for patterns like: one {# item} other {# items}
        pattern = re.compile(
            r"(?:zero|one|two|few|many|other|male|female|neuter|=[0-9]+)\s*\{([^{}]+)\}",
            re.IGNORECASE
        )

        for match in pattern.finditer(icu_text):
            content = match.group(1).strip()
            if content and content != "#":
                parts.append((match.start(1), match.end(1), content))

        return parts
