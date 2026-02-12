"""Tests for i18n file parsers."""

import pytest

from sylliba_cli.parsers import (
    JsonParser,
    YamlParser,
    PropertiesParser,
    PoParser,
    I18nParser,
)
from sylliba_cli.models import I18nFormat


class TestJsonParser:
    """Test cases for JSON parser."""

    @pytest.fixture
    def parser(self):
        """Create a JsonParser instance."""
        return JsonParser()

    def test_parse_flat_json(self, parser):
        """Test parsing flat JSON."""
        content = '{"hello": "Hello", "world": "World"}'
        result = parser.parse(content)
        assert result == {"hello": "Hello", "world": "World"}

    def test_parse_nested_json(self, parser):
        """Test parsing nested JSON."""
        content = '{"messages": {"greeting": "Hello", "farewell": "Goodbye"}}'
        result = parser.parse(content)
        assert result == {
            "messages.greeting": "Hello",
            "messages.farewell": "Goodbye",
        }

    def test_serialize_flat_json(self, parser):
        """Test serializing flat JSON."""
        original = '{"hello": "Hello", "world": "World"}'
        translations = {"hello": "Bonjour", "world": "Monde"}
        result = parser.serialize(translations, original)

        import json
        parsed = json.loads(result)
        assert parsed["hello"] == "Bonjour"
        assert parsed["world"] == "Monde"

    def test_serialize_nested_json(self, parser):
        """Test serializing nested JSON."""
        original = '{"messages": {"greeting": "Hello"}}'
        translations = {"messages.greeting": "Bonjour"}
        result = parser.serialize(translations, original)

        import json
        parsed = json.loads(result)
        assert parsed["messages"]["greeting"] == "Bonjour"


class TestYamlParser:
    """Test cases for YAML parser."""

    @pytest.fixture
    def parser(self):
        """Create a YamlParser instance."""
        return YamlParser()

    def test_parse_flat_yaml(self, parser):
        """Test parsing flat YAML."""
        content = "hello: Hello\nworld: World"
        result = parser.parse(content)
        assert result == {"hello": "Hello", "world": "World"}

    def test_parse_nested_yaml(self, parser):
        """Test parsing nested YAML."""
        content = "messages:\n  greeting: Hello\n  farewell: Goodbye"
        result = parser.parse(content)
        assert result == {
            "messages.greeting": "Hello",
            "messages.farewell": "Goodbye",
        }


class TestPropertiesParser:
    """Test cases for Properties parser."""

    @pytest.fixture
    def parser(self):
        """Create a PropertiesParser instance."""
        return PropertiesParser()

    def test_parse_properties(self, parser):
        """Test parsing properties file."""
        content = "hello=Hello\nworld=World"
        result = parser.parse(content)
        assert result == {"hello": "Hello", "world": "World"}

    def test_parse_with_comments(self, parser):
        """Test parsing properties with comments."""
        content = "# Comment\nhello=Hello\n! Another comment\nworld=World"
        result = parser.parse(content)
        assert result == {"hello": "Hello", "world": "World"}

    def test_serialize_preserves_comments(self, parser):
        """Test that serialization preserves comments."""
        original = "# Comment\nhello=Hello"
        translations = {"hello": "Bonjour"}
        result = parser.serialize(translations, original)
        assert "# Comment" in result
        assert "hello=Bonjour" in result


class TestPoParser:
    """Test cases for PO parser."""

    @pytest.fixture
    def parser(self):
        """Create a PoParser instance."""
        return PoParser()

    def test_parse_simple_po(self, parser):
        """Test parsing simple PO file."""
        content = '''
msgid "Hello"
msgstr "Hello"

msgid "World"
msgstr "World"
'''
        result = parser.parse(content)
        assert "Hello" in result
        assert "World" in result

    def test_parse_po_with_msgctxt(self, parser):
        """Test parsing PO with msgctxt."""
        content = '''
msgctxt "menu.file"
msgid "Open"
msgstr "Open"

msgctxt "menu.edit"
msgid "Open"
msgstr "Open"
'''
        result = parser.parse(content)
        # With msgctxt, the context becomes the key
        assert "menu.file" in result
        assert "menu.edit" in result


class TestParserFactory:
    """Test the parser factory method."""

    def test_get_json_parser(self):
        """Test getting JSON parser."""
        parser = I18nParser.for_format(I18nFormat.JSON)
        assert isinstance(parser, JsonParser)

    def test_get_yaml_parser(self):
        """Test getting YAML parser."""
        parser = I18nParser.for_format(I18nFormat.YAML)
        assert isinstance(parser, YamlParser)

    def test_get_properties_parser(self):
        """Test getting Properties parser."""
        parser = I18nParser.for_format(I18nFormat.PROPERTIES)
        assert isinstance(parser, PropertiesParser)

    def test_get_po_parser(self):
        """Test getting PO parser."""
        parser = I18nParser.for_format(I18nFormat.PO)
        assert isinstance(parser, PoParser)

    def test_unsupported_format(self):
        """Test error on unsupported format."""
        with pytest.raises(ValueError):
            I18nParser.for_format(I18nFormat.XLIFF)
