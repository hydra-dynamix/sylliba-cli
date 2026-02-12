"""Tests for CLI commands."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sylliba_cli.main import app


runner = CliRunner()


class TestFormatsCommand:
    """Test the formats command."""

    def test_formats_table(self):
        """Test formats command displays table."""
        result = runner.invoke(app, ["formats"])
        assert result.exit_code == 0
        assert "JSON" in result.stdout
        assert "YAML" in result.stdout
        assert "Properties" in result.stdout

    def test_formats_json(self):
        """Test formats command JSON output."""
        result = runner.invoke(app, ["formats", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert isinstance(data, list)
        formats = [f["format"] for f in data]
        assert "JSON" in formats
        assert "YAML" in formats


class TestPreviewCommand:
    """Test the preview command."""

    @pytest.fixture
    def json_file(self, tmp_path):
        """Create a test JSON file."""
        file_path = tmp_path / "en.json"
        file_path.write_text('{"hello": "Hello", "world": "World"}')
        return file_path

    def test_preview_json(self, json_file):
        """Test previewing a JSON file."""
        result = runner.invoke(app, ["preview", str(json_file)])
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert "world" in result.stdout

    def test_preview_json_output(self, json_file):
        """Test preview with JSON output."""
        result = runner.invoke(app, ["preview", str(json_file), "--json"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["format"] == "json"
        assert data["total_strings"] == 2

    def test_preview_keys_only(self, json_file):
        """Test preview with keys only."""
        result = runner.invoke(app, ["preview", str(json_file), "--keys"])
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert "world" in result.stdout

    def test_preview_nonexistent_file(self, tmp_path):
        """Test preview with nonexistent file."""
        result = runner.invoke(app, ["preview", str(tmp_path / "nonexistent.json")])
        assert result.exit_code != 0


class TestVersionCommand:
    """Test the version flag."""

    def test_version(self):
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "sylliba version" in result.stdout


class TestLoginCommand:
    """Test the login command."""

    def test_login_no_key(self):
        """Test login without API key."""
        result = runner.invoke(app, ["login"])
        assert result.exit_code != 0
        assert "Please provide an API key" in result.stdout

    def test_login_invalid_key_format(self):
        """Test login with invalid key format."""
        result = runner.invoke(app, ["login", "--api-key", "invalid_key"])
        assert result.exit_code != 0
        assert "Invalid API key format" in result.stdout


class TestWhoamiCommand:
    """Test the whoami command."""

    def test_whoami_not_logged_in(self, tmp_path, monkeypatch):
        """Test whoami when not logged in."""
        # Use a temp config directory
        monkeypatch.setattr("sylliba_cli.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("sylliba_cli.config.CONFIG_FILE", tmp_path / "config.json")

        result = runner.invoke(app, ["whoami"])
        assert result.exit_code == 0
        assert "Not logged in" in result.stdout
