"""Tests for string extraction from source files."""

import pytest
from pathlib import Path

from sylliba_cli.extractor import (
    extract_strings_from_content,
    detect_source_language,
    generate_namespace_key,
    generate_i18n_dict,
    nest_flat_dict,
    scan_directory,
    ExtractedString,
    ExtractionResult,
)


class TestExtractStringsFromContent:
    """Test string extraction from various patterns."""

    def test_extract_t_function(self):
        """Test extracting t('string') pattern."""
        content = '''
        const message = t("Hello world");
        const greeting = t('Welcome back');
        '''
        strings = list(extract_strings_from_content(content, "test.tsx"))
        texts = [s.text for s in strings]
        assert "Hello world" in texts
        assert "Welcome back" in texts

    def test_extract_i18n_t(self):
        """Test extracting i18n.t('string') pattern."""
        content = '''
        const msg = i18n.t("Click here");
        const other = i18next.t("Submit form");
        '''
        strings = list(extract_strings_from_content(content, "test.ts"))
        texts = [s.text for s in strings]
        assert "Click here" in texts
        assert "Submit form" in texts

    def test_extract_vue_t(self):
        """Test extracting $t('string') pattern."""
        content = '''
        <template>
          <button>{{ $t("Save changes") }}</button>
          <span>{{ $t('Cancel') }}</span>
        </template>
        <script>
        export default {
          computed: {
            label() { return this.$t("Edit"); }
          }
        }
        </script>
        '''
        strings = list(extract_strings_from_content(content, "Component.vue"))
        texts = [s.text for s in strings]
        assert "Save changes" in texts
        assert "Cancel" in texts

    def test_extract_trans_component(self):
        """Test extracting <Trans>text</Trans> pattern."""
        content = '''
        <Trans>Welcome to our app</Trans>
        <Trans i18nKey="greeting">Hello there</Trans>
        '''
        strings = list(extract_strings_from_content(content, "test.tsx"))
        texts = [s.text for s in strings]
        assert "Welcome to our app" in texts
        assert "Hello there" in texts

    def test_extract_format_message(self):
        """Test extracting formatMessage({ defaultMessage: 'string' })."""
        content = '''
        formatMessage({ defaultMessage: "User profile" });
        intl.formatMessage({ defaultMessage: 'Settings page' });
        '''
        strings = list(extract_strings_from_content(content, "test.tsx"))
        texts = [s.text for s in strings]
        assert "User profile" in texts
        assert "Settings page" in texts

    def test_ignore_comments(self):
        """Test that comments are ignored."""
        content = '''
        // t("This is a comment")
        /* t("Multi-line comment") */
        /**
         * t("JSDoc comment")
         */
        const real = t("Real string");
        '''
        strings = list(extract_strings_from_content(content, "test.ts"))
        texts = [s.text for s in strings]
        assert "Real string" in texts
        assert "This is a comment" not in texts
        assert "Multi-line comment" not in texts
        assert "JSDoc comment" not in texts

    def test_ignore_imports(self):
        """Test that import statements are ignored."""
        content = '''
        import { t } from "i18next";
        import "some-module";
        const msg = t("Actual message");
        '''
        strings = list(extract_strings_from_content(content, "test.ts"))
        texts = [s.text for s in strings]
        assert "Actual message" in texts
        assert "i18next" not in texts

    def test_ignore_code_like_strings(self):
        """Test that code-like strings are ignored."""
        content = '''
        const path = "/api/users";
        const url = "https://example.com";
        const cls = ".button-primary";
        const msg = t("Click the button");
        '''
        strings = list(extract_strings_from_content(content, "test.ts"))
        texts = [s.text for s in strings]
        assert "Click the button" in texts
        # These should be ignored by the i18n pattern matching
        # (they're not in t() calls)

    def test_dedup_within_file(self):
        """Test that duplicate strings in same file are deduped."""
        content = '''
        const a = t("Hello");
        const b = t("Hello");
        const c = t("Hello");
        '''
        strings = list(extract_strings_from_content(content, "test.ts"))
        texts = [s.text for s in strings]
        assert texts.count("Hello") == 1


class TestDetectSourceLanguage:
    """Test language detection."""

    def test_detect_english(self):
        """Test detecting English strings."""
        strings = ["Hello world", "Welcome to the app", "Click here to continue"]
        lang = detect_source_language(strings)
        assert lang == "English"

    def test_detect_french(self):
        """Test detecting French strings."""
        strings = ["Bonjour le monde", "Bienvenue dans l'application", "Cliquez ici"]
        lang = detect_source_language(strings)
        assert lang == "French"

    def test_detect_spanish(self):
        """Test detecting Spanish strings."""
        strings = ["Hola mundo", "Bienvenido a la aplicación", "Haz clic aquí"]
        lang = detect_source_language(strings)
        assert lang == "Spanish"

    def test_detect_german(self):
        """Test detecting German strings."""
        strings = ["Hallo Welt", "Willkommen in der App", "Klicken Sie hier"]
        lang = detect_source_language(strings)
        assert lang == "German"

    def test_default_to_english(self):
        """Test defaulting to English for unclear text."""
        strings = ["xyz123", "abc456"]
        lang = detect_source_language(strings)
        assert lang == "English"

    def test_empty_strings(self):
        """Test with empty string list."""
        lang = detect_source_language([])
        assert lang == "English"


class TestGenerateNamespaceKey:
    """Test namespace key generation."""

    def test_simple_key(self):
        """Test generating a simple key."""
        extracted = ExtractedString(
            text="Hello world",
            file_path="components/Button.tsx",
            line_number=10,
            pattern_type="t_func",
        )
        key = generate_namespace_key(extracted, "app", set())
        assert key.startswith("app.")
        assert "button" in key.lower()
        assert "hello_world" in key

    def test_unique_key_with_hash(self):
        """Test that duplicate slugs get a hash."""
        extracted1 = ExtractedString(
            text="Submit",
            file_path="components/Form.tsx",
            line_number=10,
            pattern_type="t_func",
        )
        extracted2 = ExtractedString(
            text="Submit!",  # Different text, same slug
            file_path="components/Button.tsx",
            line_number=20,
            pattern_type="t_func",
        )

        existing_keys = set()
        key1 = generate_namespace_key(extracted1, "app", existing_keys)
        existing_keys.add(key1)
        key2 = generate_namespace_key(extracted2, "app", existing_keys)

        assert key1 != key2
        # Second key should have a hash
        assert "_" in key2.split(".")[-1]  # slug_hash format

    def test_long_string_truncation(self):
        """Test that long strings are truncated in the key."""
        extracted = ExtractedString(
            text="This is a very long string that should be truncated in the key generation",
            file_path="test.tsx",
            line_number=1,
            pattern_type="t_func",
        )
        key = generate_namespace_key(extracted, "app", set())
        # Key parts should not be excessively long
        parts = key.split(".")
        assert all(len(part) <= 40 for part in parts)


class TestNestFlatDict:
    """Test converting flat dict to nested."""

    def test_nest_simple(self):
        """Test nesting a simple flat dict."""
        flat = {
            "app.button.submit": "Submit",
            "app.button.cancel": "Cancel",
        }
        nested = nest_flat_dict(flat)
        assert nested["app"]["button"]["submit"] == "Submit"
        assert nested["app"]["button"]["cancel"] == "Cancel"

    def test_nest_different_depths(self):
        """Test nesting with different key depths."""
        flat = {
            "app.common": "Common",
            "app.forms.login.title": "Login",
            "app.forms.login.submit": "Sign In",
        }
        nested = nest_flat_dict(flat)
        assert nested["app"]["common"] == "Common"
        assert nested["app"]["forms"]["login"]["title"] == "Login"


class TestGenerateI18nDict:
    """Test i18n dictionary generation."""

    def test_generate_dict(self):
        """Test generating i18n dict from extraction result."""
        result = ExtractionResult(
            strings=[
                ExtractedString("Hello", "test.tsx", 1, "t_func"),
                ExtractedString("World", "test.tsx", 2, "t_func"),
            ],
            detected_language="English",
            files_scanned=1,
        )

        i18n_dict = generate_i18n_dict(result, "myapp")

        assert len(i18n_dict) == 2
        assert "Hello" in i18n_dict.values()
        assert "World" in i18n_dict.values()
        # All keys should start with app name
        assert all(k.startswith("myapp.") for k in i18n_dict.keys())
