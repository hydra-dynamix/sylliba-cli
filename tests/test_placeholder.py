"""Tests for placeholder extraction and restoration."""

import pytest

from sylliba_cli.placeholder import PlaceholderHandler, ExtractionResult


class TestPlaceholderHandler:
    """Test cases for PlaceholderHandler."""

    @pytest.fixture
    def handler(self):
        """Create a PlaceholderHandler instance."""
        return PlaceholderHandler()

    def test_empty_text(self, handler):
        """Test with empty text."""
        result = handler.extract("")
        assert result.sanitized_text == ""
        assert result.placeholders == []
        assert result.token_map == {}

    def test_no_placeholders(self, handler):
        """Test text without any placeholders."""
        text = "Hello, world!"
        result = handler.extract(text)
        assert result.sanitized_text == text
        assert result.placeholders == []

    def test_python_format_placeholder(self, handler):
        """Test Python format string placeholders."""
        text = "Hello, {name}!"
        result = handler.extract(text)
        assert "{name}" not in result.sanitized_text
        assert "__PH_" in result.sanitized_text
        assert len(result.placeholders) == 1
        assert result.placeholders[0].original == "{name}"
        assert result.placeholders[0].pattern_type == "python_format"

    def test_python_index_placeholder(self, handler):
        """Test Python index placeholders."""
        text = "Value: {0}"
        result = handler.extract(text)
        assert "{0}" not in result.sanitized_text
        assert len(result.placeholders) == 1
        assert result.placeholders[0].original == "{0}"

    def test_template_double_braces(self, handler):
        """Test template double brace placeholders."""
        text = "Hello, {{username}}!"
        result = handler.extract(text)
        assert "{{username}}" not in result.sanitized_text
        assert len(result.placeholders) == 1
        assert result.placeholders[0].original == "{{username}}"
        assert result.placeholders[0].pattern_type == "template_double"

    def test_printf_placeholders(self, handler):
        """Test printf-style placeholders."""
        text = "You have %d items worth %s"
        result = handler.extract(text)
        assert "%d" not in result.sanitized_text
        assert "%s" not in result.sanitized_text
        assert len(result.placeholders) == 2

    def test_dollar_placeholders(self, handler):
        """Test dollar variable placeholders."""
        text = "Hello, $user! Your balance is ${amount}"
        result = handler.extract(text)
        assert "$user" not in result.sanitized_text
        assert "${amount}" not in result.sanitized_text
        assert len(result.placeholders) == 2

    def test_html_tags(self, handler):
        """Test HTML tag preservation."""
        text = "Click <b>here</b> for <a href='url'>more</a>"
        result = handler.extract(text)
        assert "<b>" not in result.sanitized_text
        assert "</b>" not in result.sanitized_text
        assert len(result.placeholders) >= 4

    def test_html_entities(self, handler):
        """Test HTML entity preservation."""
        text = "Copyright &copy; 2024&nbsp;Company"
        result = handler.extract(text)
        assert "&copy;" not in result.sanitized_text
        assert "&nbsp;" not in result.sanitized_text
        assert len(result.placeholders) == 2

    def test_restore_placeholders(self, handler):
        """Test placeholder restoration."""
        original = "Hello, {name}!"
        extraction = handler.extract(original)

        # Simulate translation (just the text around the placeholder)
        translated = extraction.sanitized_text.replace("Hello", "Bonjour")

        # Restore
        result = handler.restore(translated, extraction)
        assert "{name}" in result
        assert "Bonjour" in result

    def test_restore_multiple_placeholders(self, handler):
        """Test restoring multiple placeholders."""
        original = "Hello, {name}! You have {count} messages."
        extraction = handler.extract(original)

        translated = extraction.sanitized_text
        result = handler.restore(translated, extraction)

        assert "{name}" in result
        assert "{count}" in result

    def test_validate_success(self, handler):
        """Test validation with all placeholders present."""
        original = "Hello, {name}!"
        extraction = handler.extract(original)
        translated = handler.restore(extraction.sanitized_text, extraction)

        errors = handler.validate(original, translated, extraction)
        assert errors == []

    def test_validate_missing_placeholder(self, handler):
        """Test validation with missing placeholder."""
        original = "Hello, {name}!"
        extraction = handler.extract(original)

        # Simulate bad translation that removed the placeholder
        bad_translation = "Bonjour!"

        errors = handler.validate(original, bad_translation, extraction)
        assert len(errors) == 1
        assert "Missing" in errors[0]

    def test_count_placeholders(self, handler):
        """Test placeholder counting."""
        text = "Hello, {name}! You have %d items worth $amount"
        counts = handler.count_placeholders(text)

        assert "python_format" in counts
        assert counts["python_format"] == 1
        assert "printf" in counts
        assert counts["printf"] == 1
        assert "dollar_name" in counts
        assert counts["dollar_name"] == 1

    def test_overlapping_patterns(self, handler):
        """Test that overlapping patterns are handled correctly."""
        # ${name} could match both dollar_brace and other patterns
        text = "Value: ${variable}"
        result = handler.extract(text)

        # Should only have one placeholder (no duplicates)
        assert len(result.placeholders) == 1
        assert result.placeholders[0].original == "${variable}"
