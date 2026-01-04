import time
from typing import Final
from rich.console import Console
from rich.align import Align
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn
)
from vantaether.config import BANNER, VERSION
from vantaether.utils.i18n import LanguageManager

# Constant delay for the fake loading animation (in seconds)
LOAD_DELAY: Final[float] = 0.04


def render_banner(console: Console) -> None:
    """
    Clears the screen and renders the ASCII banner centered on the terminal.

    It attempts to format the banner string with the version number. If the
    template format in config.py changes and does not support formatting,
    it falls back to printing the raw string to prevent runtime errors.

    Args:
        console (Console): The rich Console instance used for output.
    """
    console.clear()

    try:
        formatted_banner = BANNER.format(version=VERSION)
    except (KeyError, ValueError, AttributeError):
        # Fallback: Print raw banner if formatting fails or placeholders are missing
        formatted_banner = BANNER

    centered_banner = Align.center(formatted_banner)

    console.print(centered_banner)
    console.print()


def show_startup_sequence(console: Console, lang: LanguageManager) -> None:
    """
    Displays a stylized startup progress bar to simulate system initialization.

    This function blocks execution for a short duration to provide a
    professional "loading" feel. The progress bar is transient (disappears
    after completion).

    Args:
        console (Console): The rich Console instance.
        lang (LanguageManager): The localization manager to retrieve strings.
    """
    loading_text = lang.get("system_starting", default="INITIALIZING SYSTEM...")
    ready_text = lang.get("ready_status", default="✔ SYSTEM READY")

    with Progress(
        SpinnerColumn(spinner_name="dots12", style="bold cyan"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None, style="blue", complete_style="bold magenta"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
        expand=True
    ) as progress:

        task = progress.add_task(f"[bold]{loading_text}[/]", total=100)

        # Simulate loading steps
        for _ in range(100):
            time.sleep(LOAD_DELAY)
            progress.update(task, advance=1)

    console.print(Align.center(f"[bold green]{ready_text}[/]"))
    console.print()