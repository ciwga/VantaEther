from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.prompt import Prompt, Confirm
from typing import List, Dict, Any, Tuple
from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


class PlaylistManager:
    """
    Handles interactions related to playlists, including displaying contents
    and capturing user selection for bulk or specific downloads.
    """

    def process_playlist_selection(
        self, info: Dict[str, Any], audio_only: bool
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Displays the playlist entries and prompts the user for action.

        Args:
            info (Dict[str, Any]): The playlist metadata extracted by yt-dlp.
            audio_only (bool): Flag indicating if audio-only mode is active.

        Returns:
            Tuple[List[Dict[str, Any]], bool]: 
                - A list of entries (videos) to be downloaded.
                - A boolean flag indicating if 'force_best' mode should be used.
        """
        entries = list(info.get("entries", []))
        total_videos = len(entries)
        playlist_title = info.get("title", lang.get("unknown_playlist", default="Unknown Playlist"))

        # 1. Display Header
        console.print(
            Panel(
                f"[bold white]{lang.get('playlist_detected', count=total_videos)}[/]\n"
                f"[dim]{playlist_title}[/]",
                title=lang.get("playlist_manager"),
                border_style="magenta",
            )
        )

        # 2. Display Table
        table = Table(show_header=True, header_style="bold green")
        table.add_column(lang.get("table_id"), style="dim", width=4)
        table.add_column(lang.get("table_title"))
        table.add_column(lang.get("table_url"), style="cyan")

        # Limit display to avoid flooding the terminal
        display_limit = 20
        for idx, entry in enumerate(entries[:display_limit], 1):
            title = entry.get("title", lang.get("unknown", default="Unknown"))
            vid_id = entry.get("id", "")
            table.add_row(str(idx), title, vid_id)

        if total_videos > display_limit:
            table.add_row(
                "...", f"... and {total_videos - display_limit} more", "..."
            )

        console.print(table)

        # 3. Prompt User Options
        console.print(f"\n[bold yellow]{lang.get('options')}:[/]")
        console.print(f"  [bold white]ID[/] {lang.get('menu_specific')}")
        console.print(f"  [bold white]all[/] {lang.get('menu_all')}")

        choice = Prompt.ask(lang.get("command_prompt"), default="all")
        
        selected_entries = []
        force_best = False

        if choice.lower() == "all":
            # Bulk Mode
            if Confirm.ask(
                lang.get("confirm_bulk_download", count=total_videos), default=True
            ):
                if not audio_only:
                    console.print(lang.get("bulk_mode_prompt"))
                    mode = Prompt.ask(
                        lang.get("bulk_mode_choice"), choices=["1", "2"], default="1"
                    )
                    force_best = mode == "1"
                else:
                    force_best = True  # Always best for bulk audio to avoid spamming prompts
                
                selected_entries = entries

        elif choice.isdigit():
            # Specific ID Mode
            idx = int(choice) - 1
            if 0 <= idx < total_videos:
                selected_entries = [entries[idx]]
            else:
                console.print(f"[red]{lang.get('invalid_id')}[/]")
        else:
            console.print(f"[red]{lang.get('cancelled')}[/]")

        return selected_entries, force_best