# Sylliba CLI

A command-line tool for translating i18n (internationalization) files to multiple languages using the Sylliba translation service.

[![PyPI version](https://badge.fury.io/py/sylliba-cli.svg)](https://badge.fury.io/py/sylliba-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Features

- **Multi-format support**: JSON, YAML, PO/POT, Properties, JavaScript/TypeScript, Python, Rust
- **Batch translation**: Translate to multiple languages in one command
- **Placeholder preservation**: Automatically protects `{variables}`, `%s` printf-style, HTML tags, and ICU syntax
- **Dry-run mode**: Preview what would be translated without making API calls
- **JSON output**: Machine-readable output for CI/CD integration
- **Secure credential storage**: API keys stored securely in `~/.sylliba/`

## Installation

```bash
# Using pip
pip install sylliba-cli

# Using pipx (recommended for CLI tools)
pipx install sylliba-cli

# Using uv
uv tool install sylliba-cli
```

## Quick Start

```bash
# Set your API key (get one from the Sylliba web interface)
sylliba login --api-key sk_live_your_key_here

# Translate a file to French
sylliba translate en.json --to French

# Translate to multiple languages
sylliba translate en.json --to "French,Spanish,German,Japanese"

# Preview a file's contents
sylliba preview en.json

# List supported formats
sylliba formats
```

## Commands

### `sylliba translate`

Translate an i18n file to one or more target languages.

```bash
sylliba translate <file> --to <languages> [options]
```

**Arguments:**
- `<file>`: Path to the i18n file to translate

**Options:**
- `--to, -t`: Target language(s), comma-separated (required)
- `--source, -s`: Source language (default: English)
- `--output, -o`: Output directory (default: same as input file)
- `--dry-run, -n`: Show what would be done without making API calls
- `--json, -j`: Output results as JSON
- `--concurrency, -c`: Maximum concurrent translation requests (default: 5)
- `--no-placeholders`: Disable placeholder preservation
- `--service-url`: Override the translation service URL

**Examples:**

```bash
# Basic translation
sylliba translate locales/en.json --to French

# Multiple languages with custom output directory
sylliba translate src/i18n/en.yaml --to "French,Spanish,German" -o ./translations

# Dry run to see what would happen
sylliba translate en.json --to "French,Spanish" --dry-run

# JSON output for scripting
sylliba translate en.json --to French --json | jq '.output_files'
```

### `sylliba preview`

Preview the contents of an i18n file.

```bash
sylliba preview <file> [options]
```

**Options:**
- `--limit, -l`: Maximum number of strings to show (default: 50)
- `--keys, -k`: Show only keys without values
- `--json, -j`: Output as JSON

**Examples:**

```bash
# Preview with default limit
sylliba preview en.json

# Show only keys
sylliba preview en.json --keys

# Preview as JSON
sylliba preview en.json --json
```

### `sylliba formats`

List all supported i18n file formats.

```bash
sylliba formats [options]
```

**Options:**
- `--json, -j`: Output as JSON

### `sylliba login`

Store your API key for authentication.

```bash
sylliba login --api-key <key> [--service-url <url>]
```

**Options:**
- `--api-key, -k`: Your Sylliba API key (required)
- `--service-url, -u`: Custom translation service URL

### `sylliba logout`

Remove stored credentials.

```bash
sylliba logout
```

### `sylliba whoami`

Show current authentication status.

```bash
sylliba whoami
```

### `sylliba usage`

Display your current usage statistics.

```bash
sylliba usage
```

### `sylliba api-key`

Manage API keys (requires authentication).

```bash
# List your API keys
sylliba api-key list

# Create a new API key
sylliba api-key create --name "CI/CD Key"

# Delete an API key
sylliba api-key delete <key-id>
```

## Supported File Formats

| Format | Extensions | Description |
|--------|------------|-------------|
| JSON | `.json` | Flat or nested JSON objects |
| YAML | `.yaml`, `.yml` | YAML files with nested values |
| PO/POT | `.po`, `.pot` | GNU gettext with msgctxt support |
| Properties | `.properties` | Java properties files |
| JavaScript | `.js`, `.ts`, `.mjs` | ES modules and CommonJS exports |
| Python | `.py` | Python dictionary files |
| Rust | `.rs` | `phf_map!` and `HashMap` literals |

## Placeholder Preservation

The CLI automatically detects and preserves common placeholder patterns during translation:

| Type | Pattern | Example |
|------|---------|---------|
| Python format | `{name}`, `{0}` | `Hello, {name}!` |
| Template double | `{{variable}}` | `Welcome, {{user}}` |
| Printf | `%s`, `%d`, `%.2f` | `You have %d items` |
| Dollar | `$name`, `${expr}` | `Hello, $user` |
| HTML tags | `<b>`, `</b>` | `Click <b>here</b>` |
| HTML entities | `&nbsp;`, `&#8217;` | `Copyright &copy;` |
| ICU plural | `{n, plural, ...}` | `{count, plural, one {# item} other {# items}}` |
| ICU select | `{x, select, ...}` | `{gender, select, male {He} female {She}}` |

To disable placeholder preservation, use `--no-placeholders`.

## Configuration

### Environment Variables

- `TRANSLATION_SERVICE_URL`: Base URL of the translation service
- `SYLLIBA_API_KEY`: API key for authentication (alternative to `sylliba login`)
- `SYLLIBA_SOURCE_LANGUAGE`: Default source language (default: English)
- `SYLLIBA_CONCURRENCY`: Default concurrency limit (default: 5)

### Configuration File

Credentials are stored in `~/.sylliba/config.json` with restricted permissions (0600).

### .env File

The CLI automatically searches for a `.env` file in the current directory and parent directories.

## CI/CD Integration

### GitHub Actions

```yaml
name: Translate i18n
on:
  push:
    paths:
      - 'locales/en.json'

jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Sylliba CLI
        run: pip install sylliba-cli

      - name: Translate
        env:
          SYLLIBA_API_KEY: ${{ secrets.SYLLIBA_API_KEY }}
          TRANSLATION_SERVICE_URL: ${{ secrets.SYLLIBA_SERVICE_URL }}
        run: |
          sylliba translate locales/en.json \
            --to "French,Spanish,German,Japanese" \
            --output locales/

      - name: Commit translations
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: update translations"
```

### JSON Output for Scripts

```bash
# Get list of output files
sylliba translate en.json --to "French,Spanish" --json | jq -r '.output_files | keys[]'

# Check if translation succeeded
if sylliba translate en.json --to French --json | jq -e '.errors | length == 0' > /dev/null; then
  echo "Translation successful"
fi
```

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | General error |
| 2 | Usage error |
| 3 | Service error (API unavailable) |

## Development

```bash
# Clone the repository
git clone https://github.com/hydra-dynamix/sylliba-cli.git
cd sylliba-cli

# Install development dependencies
uv sync --all-extras

# Run tests
uv run pytest -v

# Run linter
uv run ruff check .

# Type checking
uv run mypy src/
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- [Sylliba Web Interface](https://sylliba.com)
- [Documentation](https://github.com/hydra-dynamix/sylliba-cli#readme)
- [Issue Tracker](https://github.com/hydra-dynamix/sylliba-cli/issues)
- [Changelog](https://github.com/hydra-dynamix/sylliba-cli/releases)
