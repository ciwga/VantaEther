from typing import List, Dict, Any, Tuple

from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.prompt import Prompt, Confirm

from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


class PlaylistManager:
    """
    Handles user interaction for playlist selection.
    Provides batch processing options and safe input handling.
    """

    def process_playlist_selection(
        self, info: Dict[str, Any], audio_only: bool
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Displays playlist contents and captures user intent (Bulk vs Single).

        Args:
            info: Playlist metadata from yt-dlp.
            audio_only: Whether the user requested audio-only mode.

        Returns:
            Tuple containing:
            - List of selected video entries.
            - Boolean flag for 'force_best' mode.
        """
        entries = list(info.get("entries", []))
        total_videos = len(entries)
        playlist_title = info.get("title") or lang.get("playlist_unknown_title")

        # 1. UI: Header
        console.print(
            Panel(
                f"[bold white]{lang.get('playlist_detected', count=total_videos)}[/]\n"
                f"[dim]{playlist_title}[/]",
                title=lang.get("playlist_manager"),
                border_style="magenta",
            )
        )

        # 2. UI: Content Table (Limited to first 20 items to prevent spam)
        table = Table(show_header=True, header_style="bold green")
        table.add_column(lang.get("table_id"), style="dim", width=4, justify="center")
        table.add_column(lang.get("table_title"))
        table.add_column("ID", style="cyan")

        display_limit = 20
        # Safe slicing ensures no error even if list is small
        for idx, entry in enumerate(entries[:display_limit], 1):
            if not entry: continue # Skip None entries
            
            title = entry.get("title") or lang.get("unknown")
            vid_id = entry.get("id", "")
            table.add_row(str(idx), title, vid_id)

        if total_videos > display_limit:
            remaining = total_videos - display_limit
            table.add_row(
                "...", 
                f"[dim]{lang.get('playlist_more_items', count=remaining)}[/]", 
                "..."
            )

        console.print(table)

        # 3. User Interaction
        console.print(f"\n[bold yellow]{lang.get('options')}:[/]")
        console.print(f"  [bold white]ID[/]  : {lang.get('menu_specific')}")
        console.print(f"  [bold white]all[/] : {lang.get('menu_all')}")

        choice = Prompt.ask(lang.get("command_prompt"), default="all")
        
        selected_entries = []
        force_best = False

        if choice.lower() == "all":
            # Bulk Download Mode
            if Confirm.ask(
                lang.get("confirm_bulk_download", count=total_videos), default=True
            ):
                if not audio_only:
                    # For video bulk, ask quality preference once
                    console.print(lang.get("bulk_mode_prompt"))
                    mode = Prompt.ask(
                        lang.get("bulk_mode_choice"), choices=["1", "2"], default="1"
                    )
                    force_best = (mode == "1")
                else:
                    # Audio bulk is always 'best' to avoid 100 popups
                    force_best = True
                
                selected_entries = entries

        elif choice.isdigit():
            # Single Item Selection Mode
            idx = int(choice) - 1
            if 0 <= idx < total_videos:
                selected_entries = [entries[idx]]
            else:
                console.print(f"[bold red]{lang.get('invalid_id')}[/]")
        else:
            console.print(f"[yellow]{lang.get('cancelled')}[/]")

        return selected_entries, force_best