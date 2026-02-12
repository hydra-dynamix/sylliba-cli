"""Sylliba CLI - Main entry point."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from . import __version__
from .config import (
    CONFIG_FILE,
    EXIT_ERROR,
    EXIT_SERVICE_ERROR,
    EXIT_SUCCESS,
    clear_stored_credentials,
    get_api_key_for_request,
    get_default_concurrency,
    get_default_source_language,
    get_service_url,
    get_stored_api_key,
    load_cli_config,
    load_config,
    set_stored_api_key,
)
from .http import check_service_health, create_client, run_async
from .models import detect_i18n_format
from .output import (
    print_error,
    print_formats_table,
    print_info,
    print_success,
    print_translation_summary,
)
from .parsers import I18nParser
from .translator import I18nTranslator, generate_output_filename
from .extractor import scan_directory, generate_i18n_dict, nest_flat_dict

app = typer.Typer(
    name="sylliba",
    help="Sylliba - i18n file translation CLI",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"sylliba version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
) -> None:
    """Sylliba - i18n file translation CLI.

    Translate i18n files to multiple languages using the Sylliba translation service.
    """
    pass


# =============================================================================
# FORMATS COMMAND
# =============================================================================

SUPPORTED_FORMATS = [
    {
        "format": "JSON",
        "extensions": ".json",
        "description": "Flat or nested JSON objects with string values",
    },
    {
        "format": "YAML",
        "extensions": ".yaml, .yml",
        "description": "YAML files with nested string values",
    },
    {
        "format": "Properties",
        "extensions": ".properties",
        "description": "Java properties files (key=value format)",
    },
    {
        "format": "PO/POT",
        "extensions": ".po, .pot",
        "description": "GNU gettext files with msgctxt support",
    },
    {
        "format": "JavaScript",
        "extensions": ".js, .ts, .mjs",
        "description": "JS/TS files with export default or module.exports",
    },
    {
        "format": "Python",
        "extensions": ".py",
        "description": "Python files with TRANSLATIONS dict",
    },
    {
        "format": "Rust",
        "extensions": ".rs",
        "description": "Rust phf_map! or HashMap literals",
    },
]


@app.command()
def formats(
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """List all supported i18n file formats."""
    if json_output:
        print(json.dumps(SUPPORTED_FORMATS, indent=2))
    else:
        print_formats_table(SUPPORTED_FORMATS)


# =============================================================================
# EXTRACT COMMAND
# =============================================================================


@app.command()
def extract(
    directory: Annotated[
        Path,
        typer.Argument(help="Directory to scan for translatable strings"),
    ] = Path("."),
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (default: <app>.json)"),
    ] = None,
    app_name: Annotated[
        str,
        typer.Option("--app", "-a", help="Application name for key namespace"),
    ] = "app",
    format_type: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: json, yaml, nested-json"),
    ] = "nested-json",
    exclude: Annotated[
        str | None,
        typer.Option("--exclude", "-e", help="Comma-separated patterns to exclude"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be extracted without writing"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output extraction summary as JSON"),
    ] = False,
) -> None:
    """Extract translatable strings from TypeScript/JavaScript source files.

    Scans source files for i18n patterns like t("string"), $t("string"), etc.
    and generates a translation file with namespaced keys.

    Key format: app.module.string_slug (or app.module.slug_hash for uniqueness)

    Examples:

        sylliba extract src/ --output locales/en.json

        sylliba extract . --app myapp --format nested-json

        sylliba extract src/ --exclude "test,spec,mock" --dry-run
    """
    if not directory.exists():
        print_error(f"Directory not found: {directory}")
        raise typer.Exit(EXIT_ERROR)

    if not directory.is_dir():
        print_error(f"Not a directory: {directory}")
        raise typer.Exit(EXIT_ERROR)

    # Parse exclude patterns
    exclude_patterns = ["node_modules", "dist", "build", ".git", "__pycache__", ".next", "coverage"]
    if exclude:
        exclude_patterns.extend(p.strip() for p in exclude.split(",") if p.strip())

    # Scan directory
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Scanning source files...", total=None)
        result = scan_directory(directory, app_name, exclude_patterns)

    if not result.strings:
        print_info("No translatable strings found.")
        console.print(f"Files scanned: {result.files_scanned}")
        console.print("\nMake sure your code uses i18n patterns like:")
        console.print("  t('Hello world')")
        console.print("  i18n.t('Welcome')")
        console.print("  $t('Click here')")
        return

    # Generate i18n dictionary
    i18n_dict = generate_i18n_dict(result, app_name)

    # Convert to nested if requested
    if format_type == "nested-json":
        output_dict = nest_flat_dict(i18n_dict)
    else:
        output_dict = i18n_dict

    # Determine output path
    if output is None:
        lang_code = result.detected_language.lower()[:2]
        output = Path(f"{app_name}.{lang_code}.json")

    # Output results
    if json_output:
        summary = {
            "directory": str(directory),
            "files_scanned": result.files_scanned,
            "strings_found": len(result.strings),
            "detected_language": result.detected_language,
            "output_file": str(output) if not dry_run else None,
            "keys": list(i18n_dict.keys()),
        }
        if result.errors:
            summary["errors"] = result.errors
        print(json.dumps(summary, indent=2))
    else:
        # Print summary table
        console.print(f"\n[bold]Extraction Summary[/bold]")
        console.print(f"Directory: {directory}")
        console.print(f"Files scanned: {result.files_scanned}")
        console.print(f"Strings found: [green]{len(result.strings)}[/green]")
        console.print(f"Detected language: [cyan]{result.detected_language}[/cyan]")

        if result.errors:
            console.print(f"\n[yellow]Warnings ({len(result.errors)}):[/yellow]")
            for err in result.errors[:5]:
                console.print(f"  {err}")
            if len(result.errors) > 5:
                console.print(f"  ... and {len(result.errors) - 5} more")

        # Show sample of extracted strings
        console.print(f"\n[bold]Sample strings:[/bold]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Key", style="cyan", no_wrap=True, max_width=40)
        table.add_column("Value", style="white", max_width=50)
        table.add_column("File", style="dim", max_width=30)

        sample_strings = result.strings[:10]
        sample_keys = list(i18n_dict.keys())[:10]
        for key, extracted in zip(sample_keys, sample_strings):
            short_key = key if len(key) <= 40 else "..." + key[-37:]
            short_val = extracted.text if len(extracted.text) <= 50 else extracted.text[:47] + "..."
            short_file = extracted.file_path if len(extracted.file_path) <= 30 else "..." + extracted.file_path[-27:]
            table.add_row(short_key, short_val, short_file)

        if len(result.strings) > 10:
            table.add_row(f"[dim]... and {len(result.strings) - 10} more[/dim]", "", "")

        console.print(table)

    # Write output file
    if dry_run:
        if not json_output:
            console.print(f"\n[bold]Dry run[/bold] - would write to: {output}")
            console.print("\nPreview of output:")
            preview_json = json.dumps(output_dict, indent=2, ensure_ascii=False)
            # Limit preview size
            lines = preview_json.split("\n")
            if len(lines) > 30:
                console.print("\n".join(lines[:30]))
                console.print(f"[dim]... ({len(lines) - 30} more lines)[/dim]")
            else:
                console.print(preview_json)
    else:
        # Ensure parent directory exists
        output.parent.mkdir(parents=True, exist_ok=True)

        # Write based on format
        if format_type == "yaml":
            try:
                import yaml
                output_content = yaml.dump(output_dict, allow_unicode=True, default_flow_style=False, sort_keys=False)
            except ImportError:
                print_error("PyYAML required for YAML output: pip install pyyaml")
                raise typer.Exit(EXIT_ERROR)
        else:
            output_content = json.dumps(output_dict, indent=2, ensure_ascii=False)

        output.write_text(output_content, encoding="utf-8")

        if not json_output:
            print_success(f"\nExtracted {len(result.strings)} strings to {output}")
            console.print(f"\nNext steps:")
            console.print(f"  1. Review and edit: {output}")
            console.print(f"  2. Translate: sylliba translate {output} --to French,Spanish,German")


# =============================================================================
# PREVIEW COMMAND
# =============================================================================


@app.command()
def preview(
    file: Annotated[
        Path,
        typer.Argument(help="File to preview", exists=True, readable=True),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of strings to show"),
    ] = 50,
    show_keys: Annotated[
        bool,
        typer.Option("--keys", "-k", help="Show only keys without values"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Preview the contents of an i18n file.

    Shows the translatable strings found in the file.
    """
    try:
        # Detect format
        fmt = detect_i18n_format(file.name)
        parser = I18nParser.for_format(fmt)

        # Read and parse file
        content = file.read_text(encoding="utf-8")
        strings = parser.parse(content)

        if json_output:
            output = {
                "file": str(file),
                "format": fmt.value,
                "total_strings": len(strings),
                "strings": dict(list(strings.items())[:limit]) if limit else strings,
            }
            if len(strings) > limit:
                output["truncated"] = True
                output["showing"] = limit
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return

        # Print summary
        console.print(f"\n[bold]File:[/bold] {file}")
        console.print(f"[bold]Format:[/bold] {fmt.value}")
        console.print(f"[bold]Total strings:[/bold] {len(strings)}\n")

        if show_keys:
            # Just list keys
            for i, key in enumerate(strings.keys()):
                if limit and i >= limit:
                    console.print(f"[dim]... and {len(strings) - limit} more keys[/dim]")
                    break
                console.print(f"  {key}")
        else:
            # Show table with keys and values
            table = Table(show_header=True, header_style="bold")
            table.add_column("Key", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")

            for i, (key, value) in enumerate(strings.items()):
                if limit and i >= limit:
                    break
                # Truncate long values
                display_value = value if len(value) <= 60 else value[:57] + "..."
                table.add_row(key, display_value)

            console.print(table)

            if limit and len(strings) > limit:
                console.print(f"\n[dim]Showing {limit} of {len(strings)} strings[/dim]")

    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(EXIT_ERROR) from e
    except Exception as e:
        print_error(f"Failed to preview file: {e}")
        raise typer.Exit(EXIT_ERROR) from e


# =============================================================================
# TRANSLATE COMMAND
# =============================================================================


def parse_languages(languages: str) -> list[str]:
    """Parse comma-separated language string into list."""
    return [lang.strip() for lang in languages.split(",") if lang.strip()]


async def translate_file_async(
    file_path: Path,
    target_languages: list[str],
    source_language: str,
    output_dir: Path | None,
    service_url: str,
    concurrency: int,
    dry_run: bool,
    preserve_placeholders: bool,
) -> tuple[dict[str, Path], dict[str, str], int]:
    """Translate a file to multiple languages.

    Returns:
        Tuple of (output_files, errors, total_strings).
    """
    # Read and parse file
    content = file_path.read_text(encoding="utf-8")
    fmt = detect_i18n_format(file_path.name)
    parser = I18nParser.for_format(fmt)
    strings = parser.parse(content)
    total_strings = len(strings)

    if not strings:
        return {}, {}, 0

    output_files: dict[str, Path] = {}
    errors: dict[str, str] = {}

    if dry_run:
        # Just show what would be done
        for lang in target_languages:
            output_name = generate_output_filename(file_path.name, lang)
            output_path = (output_dir or file_path.parent) / output_name
            output_files[lang] = output_path
        return output_files, errors, total_strings

    # Create translator and translate
    async with create_client(service_url) as client:
        translator = I18nTranslator(
            http_client=client,
            concurrency=concurrency,
            preserve_placeholders=preserve_placeholders,
        )

        results = await translator.translate_to_multiple_languages(
            content=content,
            filename=file_path.name,
            source_language=source_language,
            target_languages=target_languages,
        )

    # Write output files
    for lang, translated_content in results.items():
        if translated_content is None:
            errors[lang] = "Translation failed"
            continue

        output_name = generate_output_filename(file_path.name, lang)
        output_path = (output_dir or file_path.parent) / output_name

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(translated_content, encoding="utf-8")
        output_files[lang] = output_path

    return output_files, errors, total_strings


@app.command()
def translate(
    file: Annotated[
        Path,
        typer.Argument(help="File to translate", exists=True, readable=True),
    ],
    to: Annotated[
        str,
        typer.Option(
            "--to",
            "-t",
            help="Target language(s), comma-separated (e.g., 'French,Spanish,German')",
        ),
    ],
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Source language (default: English)"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory (default: same as input file)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making API calls"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output results as JSON"),
    ] = False,
    concurrency: Annotated[
        int | None,
        typer.Option("--concurrency", "-c", help="Maximum concurrent translation requests (default: 5)"),
    ] = None,
    no_placeholders: Annotated[
        bool,
        typer.Option("--no-placeholders", help="Disable placeholder preservation"),
    ] = False,
    service_url: Annotated[
        str | None,
        typer.Option("--service-url", envvar="TRANSLATION_SERVICE_URL", help="Translation service URL"),
    ] = None,
) -> None:
    """Translate an i18n file to one or more target languages.

    Examples:

        sylliba translate en.json --to French

        sylliba translate en.json --to "French,Spanish,German" -o ./locales

        sylliba translate en.json --to French --dry-run

        sylliba translate en.json --to French --json
    """
    # Load config
    load_config()

    # Get settings
    try:
        url = service_url or get_service_url()
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(EXIT_ERROR) from e

    src_lang = source or get_default_source_language()
    max_concurrency = concurrency or get_default_concurrency()

    # Parse target languages
    target_languages = parse_languages(to)
    if not target_languages:
        print_error("No target languages specified")
        raise typer.Exit(EXIT_ERROR)

    # Check format is supported
    try:
        detect_i18n_format(file.name)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(EXIT_ERROR) from e

    # Check service health (unless dry run)
    if not dry_run:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Checking translation service...", total=None)
            is_healthy, message = run_async(check_service_health(url))

        if not is_healthy:
            print_error(f"Translation service unavailable: {message}")
            print_info(f"Service URL: {url}")
            raise typer.Exit(EXIT_SERVICE_ERROR)

    # Run translation
    if not json_output and not dry_run:
        print_info(f"Translating {file.name} to {', '.join(target_languages)}...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        if not json_output:
            progress.add_task(
                f"{'Analyzing' if dry_run else 'Translating'} {len(target_languages)} language(s)...",
                total=None,
            )

        output_files, errors, total_strings = run_async(
            translate_file_async(
                file_path=file,
                target_languages=target_languages,
                source_language=src_lang,
                output_dir=output,
                service_url=url,
                concurrency=max_concurrency,
                dry_run=dry_run,
                preserve_placeholders=not no_placeholders,
            )
        )

    # Output results
    if json_output:
        result = {
            "source_file": str(file),
            "source_language": src_lang,
            "target_languages": target_languages,
            "total_strings": total_strings,
            "dry_run": dry_run,
            "output_files": {lang: str(path) for lang, path in output_files.items()},
        }
        if errors:
            result["errors"] = errors
        print(json.dumps(result, indent=2))
    else:
        if dry_run:
            console.print("\n[bold]Dry run - no files were written[/bold]")

        print_translation_summary(
            source_file=str(file),
            target_languages=target_languages,
            total_strings=total_strings,
            output_files=output_files,
            errors=errors if errors else None,
        )

        if errors:
            raise typer.Exit(EXIT_ERROR)
        elif not dry_run:
            print_success("\nTranslation complete!")

    raise typer.Exit(EXIT_SUCCESS)


# =============================================================================
# AUTH COMMANDS
# =============================================================================


@app.command()
def login(
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", "-k", help="API key to store (if you already have one)"),
    ] = None,
    service_url: Annotated[
        str | None,
        typer.Option("--service-url", "-u", help="Translation service URL to use"),
    ] = None,
) -> None:
    """Login to Sylliba by storing your API key.

    You can get an API key from:
    1. The Sylliba web interface (Settings > API Keys)
    2. Running: sylliba api-key create --name "My CLI"

    Examples:

        sylliba login --api-key sk_live_abc123...

        sylliba login --api-key sk_live_abc123... --service-url https://api.sylliba.com
    """
    if not api_key:
        print_error("Please provide an API key with --api-key")
        console.print("\nTo create an API key:")
        console.print("  1. Visit the Sylliba web interface")
        console.print("  2. Go to Settings > API Keys")
        console.print("  3. Create a new key and copy it")
        console.print("\nThen run:")
        console.print("  sylliba login --api-key sk_live_YOUR_KEY")
        raise typer.Exit(EXIT_ERROR)

    # Validate API key format
    if not api_key.startswith("sk_live_") and not api_key.startswith("sk_test_"):
        print_error("Invalid API key format. Keys should start with 'sk_live_' or 'sk_test_'")
        raise typer.Exit(EXIT_ERROR)

    # Optionally verify the key works
    url = service_url
    if not url:
        try:
            load_config()
            url = get_service_url()
        except ValueError:
            pass

    if url:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Verifying API key...", total=None)
            is_valid = run_async(verify_api_key_async(url, api_key))

        if not is_valid:
            print_error("API key verification failed. Please check your key and service URL.")
            raise typer.Exit(EXIT_ERROR)

    # Store the credentials
    set_stored_api_key(api_key, service_url)

    print_success("Logged in successfully!")
    console.print(f"\nCredentials stored in: {CONFIG_FILE}")
    if url:
        console.print(f"Service URL: {url}")


async def verify_api_key_async(service_url: str, api_key: str) -> bool:
    """Verify an API key against the service."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{service_url}/api/v1/usage",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return response.status_code == 200
    except Exception:
        return False


@app.command()
def logout() -> None:
    """Logout by removing stored credentials."""
    stored_key = get_stored_api_key()
    if not stored_key:
        print_info("No stored credentials found.")
        return

    clear_stored_credentials()
    print_success("Logged out successfully. Credentials removed.")


@app.command()
def whoami() -> None:
    """Show current authentication status."""
    load_config()

    api_key = get_api_key_for_request()
    config = load_cli_config()

    if not api_key:
        console.print("[yellow]Not logged in[/yellow]")
        console.print("\nTo login, run:")
        console.print("  sylliba login --api-key YOUR_API_KEY")
        return

    # Show masked key
    key_prefix = api_key[:16] if len(api_key) > 16 else api_key[:8]
    console.print("[green]Logged in[/green]")
    console.print(f"API Key: {key_prefix}...")

    if config.get("service_url"):
        console.print(f"Service URL: {config['service_url']}")

    console.print(f"Config file: {CONFIG_FILE}")


@app.command()
def usage() -> None:
    """Show your current usage statistics."""
    load_config()

    api_key = get_api_key_for_request()
    if not api_key:
        print_error("Not logged in. Run 'sylliba login' first.")
        raise typer.Exit(EXIT_ERROR)

    try:
        url = get_service_url()
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(EXIT_ERROR) from e

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Fetching usage...", total=None)
        usage_data = run_async(fetch_usage_async(url, api_key))

    if not usage_data:
        print_error("Failed to fetch usage data.")
        raise typer.Exit(EXIT_ERROR)

    # Display usage
    table = Table(title="Usage Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Subscription Tier", usage_data.get("tier", "unknown").upper())
    table.add_row("Status", usage_data.get("status", "unknown"))

    strings_used = usage_data.get("strings_used", 0)
    strings_limit = usage_data.get("strings_limit")
    if strings_limit:
        table.add_row("Strings Used", f"{strings_used:,} / {strings_limit:,}")
        table.add_row("Strings Remaining", f"{usage_data.get('strings_remaining', 0):,}")
        table.add_row("Usage", f"{usage_data.get('usage_percentage', 0):.1f}%")
    else:
        table.add_row("Strings Used", f"{strings_used:,}")
        table.add_row("Strings Limit", "Unlimited")

    languages_limit = usage_data.get("languages_limit")
    table.add_row(
        "Target Languages",
        "Unlimited" if not languages_limit else str(languages_limit)
    )

    console.print(table)


async def fetch_usage_async(service_url: str, api_key: str) -> dict | None:
    """Fetch usage data from the API."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{service_url}/api/v1/usage",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 200:
                return response.json()
            return None
    except Exception:
        return None


# =============================================================================
# API-KEY SUBCOMMANDS
# =============================================================================

api_key_app = typer.Typer(help="Manage API keys")
app.add_typer(api_key_app, name="api-key")


@api_key_app.command("list")
def api_key_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """List your API keys."""
    load_config()

    api_key = get_api_key_for_request()
    if not api_key:
        print_error("Not logged in. Run 'sylliba login' first.")
        raise typer.Exit(EXIT_ERROR)

    try:
        url = get_service_url()
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(EXIT_ERROR) from e

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Fetching API keys...", total=None)
        keys = run_async(fetch_api_keys_async(url, api_key))

    if keys is None:
        print_error("Failed to fetch API keys.")
        raise typer.Exit(EXIT_ERROR)

    if json_output:
        print(json.dumps(keys, indent=2, default=str))
        return

    if not keys:
        console.print("No API keys found.")
        console.print("\nCreate one with:")
        console.print("  sylliba api-key create --name 'My Key'")
        return

    table = Table(title="API Keys")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Prefix", style="green")
    table.add_column("Status", style="white")
    table.add_column("Last Used", style="dim")

    for key in keys:
        status = "[green]Active[/green]" if key.get("is_active") else "[red]Revoked[/red]"
        last_used = key.get("last_used_at", "Never")
        if isinstance(last_used, str) and last_used != "Never":
            # Truncate to just date
            last_used = last_used[:10]
        table.add_row(
            str(key.get("id")),
            key.get("name", ""),
            key.get("key_prefix", ""),
            status,
            str(last_used) if last_used else "Never",
        )

    console.print(table)


@api_key_app.command("create")
def api_key_create(
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Name for the API key"),
    ] = "CLI Key",
) -> None:
    """Create a new API key."""
    load_config()

    api_key = get_api_key_for_request()
    if not api_key:
        print_error("Not logged in. Run 'sylliba login' first.")
        raise typer.Exit(EXIT_ERROR)

    try:
        url = get_service_url()
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(EXIT_ERROR) from e

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Creating API key...", total=None)
        result = run_async(create_api_key_async(url, api_key, name))

    if not result:
        print_error("Failed to create API key.")
        raise typer.Exit(EXIT_ERROR)

    print_success("API key created successfully!")
    console.print()
    console.print(f"Name: {result.get('name')}")
    console.print(f"Prefix: {result.get('key_prefix')}")
    console.print()
    console.print("[bold yellow]Your API key (save this - it won't be shown again):[/bold yellow]")
    console.print(f"[bold green]{result.get('key')}[/bold green]")
    console.print()
    console.print("To use this key, run:")
    console.print(f"  sylliba login --api-key {result.get('key')}")


@api_key_app.command("delete")
def api_key_delete(
    key_id: Annotated[
        int,
        typer.Argument(help="ID of the API key to delete"),
    ],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
) -> None:
    """Delete an API key."""
    load_config()

    api_key = get_api_key_for_request()
    if not api_key:
        print_error("Not logged in. Run 'sylliba login' first.")
        raise typer.Exit(EXIT_ERROR)

    try:
        url = get_service_url()
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(EXIT_ERROR) from e

    if not force:
        confirm = typer.confirm(f"Delete API key {key_id}?")
        if not confirm:
            print_info("Cancelled.")
            return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Deleting API key...", total=None)
        success = run_async(delete_api_key_async(url, api_key, key_id))

    if success:
        print_success(f"API key {key_id} deleted.")
    else:
        print_error(f"Failed to delete API key {key_id}.")
        raise typer.Exit(EXIT_ERROR)


async def fetch_api_keys_async(service_url: str, api_key: str) -> list[dict] | None:
    """Fetch API keys from the service."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{service_url}/api/v1/api-keys",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 200:
                return response.json()
            return None
    except Exception:
        return None


async def create_api_key_async(service_url: str, api_key: str, name: str) -> dict | None:
    """Create a new API key via the service."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{service_url}/api/v1/api-keys",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"name": name},
            )
            if response.status_code == 201:
                return response.json()
            return None
    except Exception:
        return None


async def delete_api_key_async(service_url: str, api_key: str, key_id: int) -> bool:
    """Delete an API key via the service."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{service_url}/api/v1/api-keys/{key_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return response.status_code == 204
    except Exception:
        return False


if __name__ == "__main__":
    app()
