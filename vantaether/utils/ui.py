import time
from typing import Final, Optional

from rich.console import Console
from rich.align import Align
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    ProgressColumn,
    Task
)
from rich.text import Text

import vantaether.config as config
from vantaether.config import BANNER, VERSION
from vantaether.utils.i18n import LanguageManager

# Constant delay for the fake loading animation (in seconds)
LOAD_DELAY: Final[float] = 0.04

console = Console()
lang = LanguageManager()


class RichLogger:
    """
    Custom logger to integrate yt-dlp output with Rich console.
    Suppresses debug and warning messages to keep the UI clean.
    """

    def debug(self, msg: str) -> None:
        """Ignores debug messages."""
        pass

    def warning(self, msg: str) -> None:
        """Ignores warning messages."""
        pass

    def error(self, msg: str) -> None:
        """
        Prints error messages to the console using the configured language.

        Args:
            msg (str): The error message from yt-dlp.
        """
        console.print(f"[red]{lang.get('download_error', error=msg)}[/]")


class NativeYtDlpEtaColumn(ProgressColumn):
    """
    Renders the Estimated Time of Arrival (ETA) calculated directly by yt-dlp.
    This bypasses Rich's internal estimation to match yt-dlp's native accuracy.
    """

    def render(self, task: Task) -> Text:
        """
        Renders the ETA from the task fields provided by the hook.

        Args:
            task (Task): The progress task.

        Returns:
            Text: Formatted time string (HH:MM:SS or MM:SS).
        """
        eta = task.fields.get("eta")
        if eta is None:
            return Text("-:--:--", style="progress.remaining")

        try:
            seconds = int(eta)
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)

            if h > 0:
                return Text(f"{h}:{m:02d}:{s:02d}", style="progress.remaining")
            return Text(f"{m:02d}:{s:02d}", style="progress.remaining")
        except (ValueError, TypeError):
            return Text("-:--:--", style="progress.remaining")


class NativeYtDlpSpeedColumn(ProgressColumn):
    """
    Renders the download speed calculated directly by yt-dlp.
    """

    def render(self, task: Task) -> Text:
        """
        Renders the speed from the task fields provided by the hook.

        Args:
            task (Task): The progress task.

        Returns:
            Text: Formatted speed string (e.g., 1.5 MiB/s).
        """
        speed = task.fields.get("speed")
        if speed is None:
            return Text("? /s", style="progress.data.speed")

        try:
            val = float(speed)
            if val < 1024:
                return Text(f"{val:.1f} B/s", style="progress.data.speed")
            elif val < 1024 * 1024:
                return Text(f"{val/1024:.1f} KiB/s", style="progress.data.speed")
            else:
                return Text(f"{val/1024/1024:.2f} MiB/s", style="progress.data.speed")
        except (ValueError, TypeError):
            return Text("? /s", style="progress.data.speed")


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
    Respects the SKIP_STARTUP_ANIMATION flag in config.
    """
    if config.SKIP_STARTUP_ANIMATION:
        return

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