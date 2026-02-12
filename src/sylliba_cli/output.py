"""Output formatting utilities for CLI."""

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.syntax import Syntax


# Console instances
console = Console()
error_console = Console(stderr=True)


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    error_console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]{message}[/green]")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]{message}[/blue]")


def print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    console.print_json(json.dumps(data, indent=2, ensure_ascii=False))


def print_file_preview(content: str, filename: str, limit: int = 50) -> None:
    """Print a preview of file content with syntax highlighting.

    Args:
        content: File content to preview.
        filename: Filename for syntax detection.
        limit: Maximum number of lines to show.
    """
    # Determine language from extension
    ext = Path(filename).suffix.lower()
    lang_map = {
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".rs": "rust",
        ".properties": "properties",
        ".po": "gettext",
        ".pot": "gettext",
    }
    language = lang_map.get(ext, "text")

    # Limit lines
    lines = content.split("\n")
    if len(lines) > limit:
        preview_content = "\n".join(lines[:limit])
        truncated = True
    else:
        preview_content = content
        truncated = False

    syntax = Syntax(preview_content, language, line_numbers=True)
    console.print(Panel(syntax, title=f"[bold]{filename}[/bold]"))

    if truncated:
        console.print(f"[dim]... and {len(lines) - limit} more lines[/dim]")


def create_progress() -> Progress:
    """Create a progress bar for translation tasks."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def print_translation_summary(
    source_file: str,
    target_languages: list[str],
    total_strings: int,
    output_files: dict[str, Path],
    errors: dict[str, str] | None = None,
) -> None:
    """Print a summary of translation results.

    Args:
        source_file: Source file path.
        target_languages: List of target languages.
        total_strings: Number of translated strings.
        output_files: Dict mapping language to output path.
        errors: Dict mapping language to error message (if any).
    """
    table = Table(title="Translation Summary")
    table.add_column("Language", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Output File", style="blue")

    for lang in target_languages:
        if errors and lang in errors:
            status = f"[red]Failed: {errors[lang]}[/red]"
            output = "-"
        elif lang in output_files:
            status = "[green]Success[/green]"
            output = str(output_files[lang])
        else:
            status = "[yellow]Unknown[/yellow]"
            output = "-"

        table.add_row(lang, status, output)

    console.print()
    console.print(f"Source: [bold]{source_file}[/bold]")
    console.print(f"Strings translated: [bold]{total_strings}[/bold]")
    console.print(table)


def print_formats_table(formats: list[dict[str, str]]) -> None:
    """Print a table of supported file formats.

    Args:
        formats: List of dicts with 'format', 'extensions', 'description' keys.
    """
    table = Table(title="Supported i18n File Formats")
    table.add_column("Format", style="cyan", no_wrap=True)
    table.add_column("Extensions", style="green")
    table.add_column("Description", style="white")

    for fmt in formats:
        table.add_row(
            fmt["format"],
            fmt["extensions"],
            fmt["description"],
        )

    console.print(table)
