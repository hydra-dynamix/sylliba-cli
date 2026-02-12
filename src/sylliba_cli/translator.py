"""Translation service client for i18n files."""

import asyncio
import re
from pathlib import Path

import httpx

from .models import I18nFormat, detect_i18n_format
from .parsers import I18nParser
from .placeholder import PlaceholderHandler


# Language code mapping for output filenames
LANGUAGE_CODES: dict[str, str] = {
    "english": "en",
    "french": "fr",
    "spanish": "es",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "dutch": "nl",
    "russian": "ru",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "arabic": "ar",
    "hindi": "hi",
    "turkish": "tr",
    "polish": "pl",
    "vietnamese": "vi",
    "thai": "th",
    "indonesian": "id",
    "swedish": "sv",
    "danish": "da",
    "norwegian": "no",
    "finnish": "fi",
    "czech": "cs",
    "greek": "el",
    "hebrew": "he",
    "hungarian": "hu",
    "romanian": "ro",
    "ukrainian": "uk",
}


def get_language_code(language: str) -> str:
    """Get ISO language code for a language name."""
    return LANGUAGE_CODES.get(language.lower(), language.lower()[:2])


def generate_output_filename(original_filename: str, target_language: str) -> str:
    """Generate output filename for translated file.

    Examples:
        en.json -> fr.json
        messages.en.json -> messages.fr.json
        en_US.json -> fr_FR.json
    """
    path = Path(original_filename)
    stem = path.stem
    suffix = path.suffix
    lang_code = get_language_code(target_language)

    # Pattern: en.json, fr.json
    if re.match(r"^[a-z]{2}(_[A-Z]{2})?$", stem):
        return f"{lang_code}{suffix}"

    # Pattern: messages.en.json
    parts = stem.rsplit(".", 1)
    if len(parts) == 2 and re.match(r"^[a-z]{2}(_[A-Z]{2})?$", parts[1]):
        return f"{parts[0]}.{lang_code}{suffix}"

    # Default: append language code
    return f"{stem}.{lang_code}{suffix}"


class I18nTranslator:
    """Translates i18n files using the translation service."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        concurrency: int = 5,
        preserve_placeholders: bool = True,
    ):
        """Initialize translator.

        Args:
            http_client: Async HTTP client for API requests.
            concurrency: Maximum concurrent translation requests.
            preserve_placeholders: Whether to protect placeholders during translation.
        """
        self.client = http_client
        self.semaphore = asyncio.Semaphore(concurrency)
        self.preserve_placeholders = preserve_placeholders
        self.placeholder_handler = PlaceholderHandler() if preserve_placeholders else None

    async def translate_to_multiple_languages(
        self,
        content: str,
        filename: str,
        source_language: str,
        target_languages: list[str],
    ) -> dict[str, str | None]:
        """Translate content to multiple target languages.

        Args:
            content: Source file content.
            filename: Original filename (for format detection).
            source_language: Source language name.
            target_languages: List of target language names.

        Returns:
            Dict mapping language to translated content (None if failed).
        """
        # Parse the file
        fmt = detect_i18n_format(filename)
        parser = I18nParser.for_format(fmt)
        strings = parser.parse(content)

        if not strings:
            return {lang: content for lang in target_languages}

        # Translate to each language concurrently
        tasks = []
        for lang in target_languages:
            task = self._translate_file(
                strings=strings,
                parser=parser,
                original_content=content,
                source_language=source_language,
                target_language=lang,
            )
            tasks.append((lang, task))

        results = {}
        for lang, task in tasks:
            try:
                results[lang] = await task
            except Exception:
                results[lang] = None

        return results

    async def _translate_file(
        self,
        strings: dict[str, str],
        parser: I18nParser,
        original_content: str,
        source_language: str,
        target_language: str,
    ) -> str:
        """Translate all strings in a file to a single language."""
        # Translate all strings
        tasks = [
            self._translate_single(text, source_language, target_language)
            for text in strings.values()
        ]
        translated_values = await asyncio.gather(*tasks)

        # Build translated dict
        translated = dict(zip(strings.keys(), translated_values))

        # Serialize back to original format
        return parser.serialize(translated, original_content)

    async def _translate_single(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        """Translate a single string."""
        if not text or not text.strip():
            return text

        # Extract placeholders if enabled
        extraction = None
        text_to_translate = text
        if self.placeholder_handler:
            extraction = self.placeholder_handler.extract(text)
            text_to_translate = extraction.sanitized_text

        # Call translation API
        async with self.semaphore:
            try:
                response = await self.client.post(
                    "/translate",
                    json={
                        "text": text_to_translate,
                        "source_language": source_language,
                        "target_language": target_language,
                        "task": "t2t",
                    },
                )
                response.raise_for_status()
                result = response.json()
                translated = result.get("text", text_to_translate)
            except Exception:
                # On error, return original text
                return text

        # Restore placeholders if we extracted them
        if extraction and self.placeholder_handler:
            translated = self.placeholder_handler.restore(translated, extraction)

        return translated
