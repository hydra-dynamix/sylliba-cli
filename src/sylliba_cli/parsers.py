"""Parse and serialize i18n files in various formats."""

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator

from .models import I18nFormat


class I18nParser(ABC):
    """Abstract base class for i18n file parsers."""

    @abstractmethod
    def parse(self, content: str) -> dict[str, str]:
        """Parse file content into flat key-value pairs."""
        ...

    @abstractmethod
    def serialize(self, translations: dict[str, str], original_content: str) -> str:
        """Serialize translations back to file format, preserving structure."""
        ...

    @classmethod
    def for_format(cls, fmt: I18nFormat) -> "I18nParser":
        """Factory method to get parser for a specific format."""
        parsers: dict[I18nFormat, type[I18nParser]] = {
            I18nFormat.JSON: JsonParser,
            I18nFormat.YAML: YamlParser,
            I18nFormat.PO: PoParser,
            I18nFormat.PROPERTIES: PropertiesParser,
            I18nFormat.JAVASCRIPT: JavaScriptParser,
            I18nFormat.PYTHON: PythonParser,
            I18nFormat.RUST: RustParser,
        }
        if fmt not in parsers:
            raise ValueError(f"No parser available for format: {fmt}")
        return parsers[fmt]()


class JsonParser(I18nParser):
    """Parser for JSON i18n files (flat or nested)."""

    def parse(self, content: str) -> dict[str, str]:
        """Parse JSON into flat key-value pairs with dot notation for nested keys."""
        data = json.loads(content)
        return dict(self._flatten(data))

    def _flatten(
        self, obj: dict | list | str, prefix: str = ""
    ) -> Iterator[tuple[str, str]]:
        """Recursively flatten nested JSON structure."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}.{key}" if prefix else key
                yield from self._flatten(value, new_key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                yield from self._flatten(item, f"{prefix}[{i}]")
        else:
            yield prefix, str(obj)

    def serialize(self, translations: dict[str, str], original_content: str) -> str:
        """Rebuild JSON structure from flat translations."""
        # Parse original to preserve structure
        original = json.loads(original_content)
        result = self._unflatten(translations, original)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _unflatten(
        self, translations: dict[str, str], template: dict | list | str, prefix: str = ""
    ) -> dict | list | str:
        """Rebuild nested structure using translations."""
        if isinstance(template, dict):
            result = {}
            for key, value in template.items():
                new_key = f"{prefix}.{key}" if prefix else key
                result[key] = self._unflatten(translations, value, new_key)
            return result
        elif isinstance(template, list):
            return [
                self._unflatten(translations, item, f"{prefix}[{i}]")
                for i, item in enumerate(template)
            ]
        else:
            # Leaf node - return translation if exists
            return translations.get(prefix, str(template))


class YamlParser(I18nParser):
    """Parser for YAML i18n files."""

    def parse(self, content: str) -> dict[str, str]:
        """Parse YAML into flat key-value pairs."""
        try:
            import yaml
        except ImportError as e:
            raise ImportError("PyYAML required for YAML support: pip install pyyaml") from e

        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return {}
        return dict(self._flatten(data))

    def _flatten(
        self, obj: dict | list | str, prefix: str = ""
    ) -> Iterator[tuple[str, str]]:
        """Recursively flatten nested YAML structure."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}.{key}" if prefix else key
                yield from self._flatten(value, new_key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                yield from self._flatten(item, f"{prefix}[{i}]")
        elif obj is not None:
            yield prefix, str(obj)

    def serialize(self, translations: dict[str, str], original_content: str) -> str:
        """Rebuild YAML structure from flat translations."""
        try:
            import yaml
        except ImportError as e:
            raise ImportError("PyYAML required for YAML support: pip install pyyaml") from e

        original = yaml.safe_load(original_content)
        result = self._unflatten(translations, original)
        return yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def _unflatten(
        self, translations: dict[str, str], template: dict | list | str | None, prefix: str = ""
    ) -> dict | list | str | None:
        """Rebuild nested structure using translations."""
        if isinstance(template, dict):
            result = {}
            for key, value in template.items():
                new_key = f"{prefix}.{key}" if prefix else key
                result[key] = self._unflatten(translations, value, new_key)
            return result
        elif isinstance(template, list):
            return [
                self._unflatten(translations, item, f"{prefix}[{i}]")
                for i, item in enumerate(template)
            ]
        elif template is not None:
            return translations.get(prefix, str(template))
        return None


class PropertiesParser(I18nParser):
    """Parser for Java .properties files."""

    def parse(self, content: str) -> dict[str, str]:
        """Parse properties file into key-value pairs."""
        result = {}
        for line in content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#") or line.startswith("!"):
                continue
            # Handle = or : as separator
            match = re.match(r"^([^=:]+)[=:](.*)$", line)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                result[key] = value
        return result

    def serialize(self, translations: dict[str, str], original_content: str) -> str:
        """Rebuild properties file preserving comments and order."""
        lines = []
        translated_keys = set()

        for line in original_content.splitlines():
            stripped = line.strip()
            # Preserve comments and empty lines
            if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                lines.append(line)
                continue

            match = re.match(r"^([^=:]+)[=:](.*)$", stripped)
            if match:
                key = match.group(1).strip()
                if key in translations:
                    lines.append(f"{key}={translations[key]}")
                    translated_keys.add(key)
                else:
                    lines.append(line)
            else:
                lines.append(line)

        return "\n".join(lines)


class PoParser(I18nParser):
    """
    Parser for GNU gettext .po/.pot files.

    Handles both simple msgid/msgstr pairs and entries with msgctxt (context).
    When msgctxt is present, it is used as the key since msgid values can repeat
    with different contexts.
    """

    def parse(self, content: str) -> dict[str, str]:
        """
        Parse PO file into key->msgid pairs for translation.

        The key is msgctxt if present, otherwise msgid.
        The value is msgid (the source text to translate).
        """
        result = {}
        current_msgctxt: str | None = None
        current_msgid: list[str] = []
        current_msgstr: list[str] = []
        current_field: str | None = None  # 'msgctxt', 'msgid', or 'msgstr'

        def save_entry():
            """Save the current entry to results."""
            msgid = "".join(current_msgid)
            # Skip header entry (empty msgid)
            if not msgid:
                return
            # Use msgctxt as key if present, otherwise use msgid
            key = current_msgctxt if current_msgctxt else msgid
            result[key] = msgid

        for line in content.splitlines():
            stripped = line.strip()

            # Skip comments and empty lines
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("msgctxt "):
                # Save previous entry before starting new one
                if current_msgid:
                    save_entry()
                current_msgctxt = self._extract_string(stripped[8:])
                current_msgid = []
                current_msgstr = []
                current_field = "msgctxt"

            elif stripped.startswith("msgid "):
                # If no msgctxt preceded this, save previous entry
                if current_field != "msgctxt" and current_msgid:
                    save_entry()
                    current_msgctxt = None
                current_msgid = [self._extract_string(stripped[6:])]
                current_msgstr = []
                current_field = "msgid"

            elif stripped.startswith("msgstr "):
                current_msgstr = [self._extract_string(stripped[7:])]
                current_field = "msgstr"

            elif stripped.startswith('"') and stripped.endswith('"'):
                # Continuation line - append to current field
                value = self._extract_string(stripped)
                if current_field == "msgctxt":
                    current_msgctxt = (current_msgctxt or "") + value
                elif current_field == "msgid":
                    current_msgid.append(value)
                elif current_field == "msgstr":
                    current_msgstr.append(value)

        # Save last entry
        if current_msgid:
            save_entry()

        return result

    def _extract_string(self, s: str) -> str:
        """Extract string value from quoted PO string."""
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        # Unescape common escape sequences
        return (
            s.replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\r")
        )

    def _escape_string(self, s: str) -> str:
        """Escape string for PO file format."""
        return (
            s.replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            .replace("\r", "\\r")
        )

    def serialize(self, translations: dict[str, str], original_content: str) -> str:
        """
        Rebuild PO file with translations.

        The translations dict maps key (msgctxt or msgid) -> translated text.
        """
        lines = []
        current_msgctxt: str | None = None
        current_msgid: list[str] = []
        current_field: str | None = None
        skip_msgstr_continuation = False

        def get_key() -> str | None:
            """Get the key for the current entry."""
            msgid = "".join(current_msgid)
            if not msgid:
                return None
            return current_msgctxt if current_msgctxt else msgid

        for line in original_content.splitlines():
            stripped = line.strip()

            if stripped.startswith("msgctxt "):
                current_msgctxt = self._extract_string(stripped[8:])
                current_msgid = []
                current_field = "msgctxt"
                skip_msgstr_continuation = False
                lines.append(line)

            elif stripped.startswith("msgid "):
                if current_field != "msgctxt":
                    current_msgctxt = None
                current_msgid = [self._extract_string(stripped[6:])]
                current_field = "msgid"
                skip_msgstr_continuation = False
                lines.append(line)

            elif stripped.startswith("msgstr "):
                current_field = "msgstr"
                key = get_key()
                if key and key in translations:
                    translated = translations[key]
                    escaped = self._escape_string(translated)
                    lines.append(f'msgstr "{escaped}"')
                    skip_msgstr_continuation = True
                else:
                    lines.append(line)
                    skip_msgstr_continuation = False

            elif stripped.startswith('"') and stripped.endswith('"'):
                # Continuation line
                if current_field == "msgctxt":
                    current_msgctxt = (current_msgctxt or "") + self._extract_string(stripped)
                    lines.append(line)
                elif current_field == "msgid":
                    current_msgid.append(self._extract_string(stripped))
                    lines.append(line)
                elif current_field == "msgstr":
                    # Skip continuation lines if we replaced the msgstr
                    if not skip_msgstr_continuation:
                        lines.append(line)
            else:
                lines.append(line)

        return "\n".join(lines)


class JavaScriptParser(I18nParser):
    """
    Parser for JavaScript/TypeScript i18n files.

    Handles patterns like:
    - export default { key: "value", nested: { key: "value" } }
    - module.exports = { ... }
    - const translations = { ... }
    """

    def parse(self, content: str) -> dict[str, str]:
        """Parse JS object literals into flat key-value pairs."""
        obj_content = self._extract_object(content)
        if not obj_content:
            return {}

        try:
            data = self._parse_js_object(obj_content)
            return dict(self._flatten(data))
        except Exception:
            return {}

    def _extract_object(self, content: str) -> str | None:
        """Extract the main object literal from JS code."""
        patterns = [
            r"export\s+default\s*(\{[\s\S]*\})\s*;?\s*$",
            r"module\.exports\s*=\s*(\{[\s\S]*\})\s*;?\s*$",
            r"(?:const|let|var)\s+\w+\s*=\s*(\{[\s\S]*\})\s*;?\s*$",
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)

        brace_start = content.find("{")
        if brace_start == -1:
            return None

        depth = 0
        for i, char in enumerate(content[brace_start:], brace_start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return content[brace_start : i + 1]

        return None

    def _strip_js_comments(self, content: str) -> str:
        """Remove JavaScript comments while preserving strings."""
        result = []
        i = 0
        length = len(content)

        while i < length:
            # Handle strings - don't strip inside them
            if content[i] in "'\"`":
                quote = content[i]
                result.append(content[i])
                i += 1
                while i < length:
                    if content[i] == "\\" and i + 1 < length:
                        result.append(content[i : i + 2])
                        i += 2
                        continue
                    result.append(content[i])
                    if content[i] == quote:
                        i += 1
                        break
                    i += 1

            # Handle single-line comments
            elif content[i : i + 2] == "//":
                # Skip until end of line
                while i < length and content[i] != "\n":
                    i += 1

            # Handle multi-line comments
            elif content[i : i + 2] == "/*":
                i += 2
                while i < length - 1:
                    if content[i : i + 2] == "*/":
                        i += 2
                        break
                    i += 1

            else:
                result.append(content[i])
                i += 1

        return "".join(result)

    def _parse_js_object(self, content: str) -> dict:
        """Parse JS object literal (more permissive than JSON)."""
        # First, strip comments
        content = self._strip_js_comments(content)

        # Process the content character by character to handle quotes properly
        result = []
        i = 0
        length = len(content)

        while i < length:
            char = content[i]

            # Handle single-quoted strings - convert to double-quoted
            if char == "'":
                j = i + 1
                inner_chars = []
                while j < length:
                    if content[j] == "\\" and j + 1 < length:
                        # Keep escape sequences, but handle \' specially
                        if content[j + 1] == "'":
                            inner_chars.append("'")  # \' becomes just '
                        else:
                            inner_chars.append(content[j : j + 2])
                        j += 2
                        continue
                    if content[j] == "'":
                        break
                    # Escape double quotes inside single-quoted strings
                    if content[j] == '"':
                        inner_chars.append('\\"')
                    else:
                        inner_chars.append(content[j])
                    j += 1

                result.append('"')
                result.append("".join(inner_chars))
                result.append('"')
                i = j + 1

            # Handle double-quoted strings - keep as-is
            elif char == '"':
                j = i + 1
                result.append(char)
                while j < length:
                    if content[j] == "\\" and j + 1 < length:
                        result.append(content[j : j + 2])
                        j += 2
                        continue
                    result.append(content[j])
                    if content[j] == '"':
                        j += 1
                        break
                    j += 1
                i = j

            # Handle template literals (backticks) - convert to double-quoted
            elif char == "`":
                j = i + 1
                inner_chars = []
                while j < length:
                    if content[j] == "\\" and j + 1 < length:
                        inner_chars.append(content[j : j + 2])
                        j += 2
                        continue
                    if content[j] == "`":
                        break
                    # Escape double quotes and handle newlines
                    if content[j] == '"':
                        inner_chars.append('\\"')
                    elif content[j] == "\n":
                        inner_chars.append("\\n")
                    elif content[j] == "\r":
                        inner_chars.append("\\r")
                    else:
                        inner_chars.append(content[j])
                    j += 1

                result.append('"')
                result.append("".join(inner_chars))
                result.append('"')
                i = j + 1

            # Handle unquoted keys (identifiers followed by :)
            elif char.isalpha() or char == "_" or char == "$":
                # Collect the identifier
                j = i
                while j < length and (
                    content[j].isalnum() or content[j] in "_$"
                ):
                    j += 1

                identifier = content[i:j]

                # Skip whitespace
                k = j
                while k < length and content[k] in " \t\n\r":
                    k += 1

                # Check if followed by colon (it's a key)
                if k < length and content[k] == ":":
                    result.append('"')
                    result.append(identifier)
                    result.append('"')
                    i = j
                else:
                    # Not a key, just append as-is (could be true/false/null)
                    result.append(identifier)
                    i = j

            else:
                result.append(char)
                i += 1

        json_str = "".join(result)

        # Remove trailing commas before } or ]
        json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)

        return json.loads(json_str)

    def _flatten(
        self, obj: dict | list | str, prefix: str = ""
    ) -> Iterator[tuple[str, str]]:
        """Recursively flatten nested structure."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}.{key}" if prefix else key
                yield from self._flatten(value, new_key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                yield from self._flatten(item, f"{prefix}[{i}]")
        elif isinstance(obj, str):
            yield prefix, obj

    def serialize(self, translations: dict[str, str], original_content: str) -> str:
        """Rebuild JS file with translations, preserving structure."""
        result = original_content

        for key, translated in translations.items():
            key_parts = key.split(".")
            if not key_parts:
                continue

            escaped = (
                translated.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace('"', '\\"')
                .replace("\n", "\\n")
            )

            last_key = key_parts[-1]
            pattern = rf"({re.escape(last_key)}\s*:\s*)(['\"])(.+?)\2"

            def make_replacer(esc):
                def replacer(m):
                    quote = m.group(2)
                    return f"{m.group(1)}{quote}{esc}{quote}"
                return replacer

            result = re.sub(pattern, make_replacer(escaped), result, count=1)

        return result


class PythonParser(I18nParser):
    """
    Parser for Python i18n dictionary files.

    Handles patterns like:
    - TRANSLATIONS = { "key": "value" }
    - translations = { ... }
    """

    def parse(self, content: str) -> dict[str, str]:
        """Parse Python dict literals into flat key-value pairs."""
        obj_content = self._extract_dict(content)
        if not obj_content:
            return {}

        try:
            import ast
            data = ast.literal_eval(obj_content)
            if isinstance(data, dict):
                return dict(self._flatten(data))
            return {}
        except Exception:
            return {}

    def _extract_dict(self, content: str) -> str | None:
        """Extract the main dictionary from Python code."""
        patterns = [
            r"(?:TRANSLATIONS|translations|STRINGS|strings|MESSAGES|messages)\s*=\s*(\{[\s\S]*\})",
            r"^(\{[\s\S]*\})\s*$",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                return match.group(1)

        brace_start = content.find("{")
        if brace_start == -1:
            return None

        depth = 0
        in_string = False
        string_char = None

        for i, char in enumerate(content[brace_start:], brace_start):
            if not in_string:
                if char in "\"'":
                    in_string = True
                    string_char = char
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return content[brace_start : i + 1]
            else:
                if char == string_char and content[i - 1] != "\\":
                    in_string = False

        return None

    def _flatten(
        self, obj: dict | list | str, prefix: str = ""
    ) -> Iterator[tuple[str, str]]:
        """Recursively flatten nested structure."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}.{key}" if prefix else str(key)
                yield from self._flatten(value, new_key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                yield from self._flatten(item, f"{prefix}[{i}]")
        elif isinstance(obj, str):
            yield prefix, obj

    def serialize(self, translations: dict[str, str], original_content: str) -> str:
        """Rebuild Python file with translations."""
        result = original_content

        for key, translated in translations.items():
            key_parts = key.split(".")
            if not key_parts:
                continue

            escaped = (
                translated.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace('"', '\\"')
                .replace("\n", "\\n")
            )

            last_key = key_parts[-1]
            pattern = rf"(['\"]){re.escape(last_key)}\1\s*:\s*(['\"])(.+?)\2"

            def make_replacer(lk, esc):
                def replacer(m):
                    key_quote = m.group(1)
                    val_quote = m.group(2)
                    return f"{key_quote}{lk}{key_quote}: {val_quote}{esc}{val_quote}"
                return replacer

            result = re.sub(pattern, make_replacer(last_key, escaped), result, count=1)

        return result


class RustParser(I18nParser):
    """
    Parser for Rust i18n files using phf_map or HashMap literals.

    Handles patterns like:
    - static TRANSLATIONS: phf::Map<&str, &str> = phf_map! { "key" => "value" }
    - HashMap::from([("key", "value")])
    """

    def parse(self, content: str) -> dict[str, str]:
        """Parse Rust map literals into key-value pairs."""
        result = {}

        phf_pattern = re.compile(
            r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*=>\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        )

        hashmap_pattern = re.compile(
            r'\(\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*,\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*\)',
        )

        for match in phf_pattern.finditer(content):
            key = self._unescape_rust_string(match.group(1))
            value = self._unescape_rust_string(match.group(2))
            result[key] = value

        for match in hashmap_pattern.finditer(content):
            key = self._unescape_rust_string(match.group(1))
            value = self._unescape_rust_string(match.group(2))
            result[key] = value

        return result

    def _unescape_rust_string(self, s: str) -> str:
        """Unescape Rust string literals."""
        return (
            s.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\r")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )

    def _escape_rust_string(self, s: str) -> str:
        """Escape string for Rust literal."""
        return (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            .replace("\r", "\\r")
        )

    def serialize(self, translations: dict[str, str], original_content: str) -> str:
        """Rebuild Rust file with translations."""
        result = original_content

        for key, translated in translations.items():
            escaped_key = self._escape_rust_string(key)
            escaped_val = self._escape_rust_string(translated)

            phf_pattern = rf'"{re.escape(escaped_key)}"\s*=>\s*"[^"\\]*(?:\\.[^"\\]*)*"'
            result = re.sub(
                phf_pattern,
                f'"{escaped_key}" => "{escaped_val}"',
                result,
            )

            hashmap_pattern = (
                rf'\(\s*"{re.escape(escaped_key)}"\s*,\s*"[^"\\]*(?:\\.[^"\\]*)*"\s*\)'
            )
            result = re.sub(
                hashmap_pattern,
                f'("{escaped_key}", "{escaped_val}")',
                result,
            )

        return result
