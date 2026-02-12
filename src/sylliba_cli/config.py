"""CLI configuration and environment loading."""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# Configuration directory and file
CONFIG_DIR = Path.home() / ".sylliba"
CONFIG_FILE = CONFIG_DIR / "config.json"


def find_env_file(start_path: Path | None = None) -> Path | None:
    """Search for .env file upward from the given path.

    Args:
        start_path: Starting directory. Defaults to current working directory.

    Returns:
        Path to .env file if found, None otherwise.
    """
    current = start_path or Path.cwd()

    for _ in range(10):  # Limit search depth
        env_path = current / ".env"
        if env_path.exists():
            return env_path

        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    return None


def load_config() -> None:
    """Load configuration from .env file."""
    env_path = find_env_file()
    if env_path:
        load_dotenv(env_path, override=True)


def get_service_url() -> str:
    """Get the translation service URL from environment or config.

    Returns:
        Translation service base URL.

    Raises:
        ValueError: If not configured.
    """
    # First check environment variable
    url = os.environ.get("TRANSLATION_SERVICE_URL")
    if url:
        return url.rstrip("/")

    # Then check config file
    config = load_cli_config()
    url = config.get("service_url")
    if url:
        return url.rstrip("/")

    raise ValueError(
        "Translation service URL not configured.\n"
        "Set it via:\n"
        "  1. Environment variable: export TRANSLATION_SERVICE_URL=http://localhost:8000\n"
        "  2. CLI login: sylliba login --service-url http://localhost:8000"
    )


def get_default_source_language() -> str:
    """Get default source language from environment."""
    return os.environ.get("SYLLIBA_SOURCE_LANGUAGE", "English")


def get_default_concurrency() -> int:
    """Get default concurrency limit from environment."""
    return int(os.environ.get("SYLLIBA_CONCURRENCY", "5"))


# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_SERVICE_ERROR = 3


# =============================================================================
# CLI Config File Management
# =============================================================================


def ensure_config_dir() -> Path:
    """Ensure the config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def load_cli_config() -> dict[str, Any]:
    """Load CLI configuration from file.

    Returns:
        Configuration dictionary (empty if file doesn't exist).
    """
    if not CONFIG_FILE.exists():
        return {}

    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_cli_config(config: dict[str, Any]) -> None:
    """Save CLI configuration to file.

    Args:
        config: Configuration dictionary to save.
    """
    ensure_config_dir()
    CONFIG_FILE.write_text(json.dumps(config, indent=2))

    # Set restrictive permissions (readable only by user)
    CONFIG_FILE.chmod(0o600)


def get_stored_api_key() -> str | None:
    """Get the stored API key from config.

    Returns:
        API key string if stored, None otherwise.
    """
    config = load_cli_config()
    return config.get("api_key")


def set_stored_api_key(api_key: str, service_url: str | None = None) -> None:
    """Store API key in config file.

    Args:
        api_key: API key to store.
        service_url: Optional service URL to store alongside.
    """
    config = load_cli_config()
    config["api_key"] = api_key
    if service_url:
        config["service_url"] = service_url
    save_cli_config(config)


def clear_stored_credentials() -> None:
    """Clear stored credentials from config file."""
    config = load_cli_config()
    config.pop("api_key", None)
    save_cli_config(config)


def get_api_key_for_request() -> str | None:
    """Get API key for making requests.

    Checks in order:
    1. SYLLIBA_API_KEY environment variable
    2. Stored API key in config file

    Returns:
        API key string if available, None otherwise.
    """
    # Check environment variable first
    api_key = os.environ.get("SYLLIBA_API_KEY")
    if api_key:
        return api_key

    # Check config file
    return get_stored_api_key()
