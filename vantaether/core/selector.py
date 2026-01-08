from rich.table import Table
from rich.prompt import Prompt
from rich.console import Console
from typing import List, Dict, Any, Optional
from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


class FormatSelector:
    """
    Handles the interactive selection of media formats (video/audio).
    This encapsulates the business logic for presenting options to the user
    and parsing their choice.
    """

    def select_video_format(
        self, formats: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Displays available video formats and prompts the user to select one.

        Args:
            formats (List[Dict[str, Any]]): List of raw format dictionaries from yt-dlp.

        Returns:
            Optional[Dict[str, Any]]: The selected format dictionary, or None if no valid formats found.
        """
        # Filter and sort formats by height (resolution)
        video_formats = sorted(
            [f for f in formats if f.get("height")],
            key=lambda x: x.get("height", 0),
            reverse=True,
        )

        # Deduplicate based on resolution string (e.g., '1080p')
        unique_fmts = []
        seen = set()
        for f in video_formats:
            res = f"{f.get('height')}p"
            if res not in seen:
                unique_fmts.append(f)
                seen.add(res)

        if not unique_fmts:
            return None

        # Build the Table
        table = Table(title=lang.get("quality_options"), header_style="bold magenta")
        table.add_column(lang.get("table_id"), justify="center", no_wrap=True)
        table.add_column(lang.get("resolution"), no_wrap=True)
        table.add_column(lang.get("table_bitrate"), no_wrap=True)
        table.add_column(
            lang.get("codec"), no_wrap=True, overflow="ellipsis", max_width=10
        )
        table.add_column(lang.get("table_ext"), no_wrap=True)
        table.add_column(lang.get("audio_status"), style="cyan")

        for idx, f in enumerate(unique_fmts, 1):
            audio_status = (
                lang.get("exists")
                if f.get("acodec") != "none" and f.get("acodec") is not None
                else lang.get("video_only")
            )
            tbr = f"{int(f.get('tbr', 0) or 0)}k"
            vcodec = f.get("vcodec", "unknown")
            if vcodec == "none":
                vcodec = "images"

            table.add_row(
                str(idx),
                f"{f.get('height')}p",
                tbr,
                vcodec,
                f.get("ext", "mp4"),
                audio_status,
            )

        console.print(table)
        
        # Prompt User
        choice = Prompt.ask(
            lang.get("choice"),
            choices=[str(i) for i in range(1, len(unique_fmts) + 1)],
            default="1",
        )
        return unique_fmts[int(choice) - 1]

    def select_audio_format(
        self, formats: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Displays available audio-only streams and prompts the user to select one.
        Used when a video-only format is selected or for audio extraction.

        Args:
            formats (List[Dict[str, Any]]): List of raw format dictionaries.

        Returns:
            Optional[Dict[str, Any]]: The selected audio format dictionary.
        """
        # Filter purely audio formats
        audio_formats = [
            f
            for f in formats
            if (
                (f.get("vcodec") == "none" or f.get("vcodec") is None)
                and f.get("height") is None
                and f.get("width") is None
            )
            and f.get("acodec") != "none"
        ]

        if not audio_formats:
            return None

        # Deduplicate audio by ID
        unique_audios = []
        seen_audio = set()
        for af in audio_formats:
            aud_id = af.get("format_id")
            if aud_id not in seen_audio:
                unique_audios.append(af)
                seen_audio.add(aud_id)

        if not unique_audios:
            return None

        # Build Table
        table = Table(title=lang.get("audio_sources"), header_style="bold yellow")
        table.add_column(lang.get("table_id"), justify="center", no_wrap=True)
        table.add_column(lang.get("table_format_id", default="Format ID"), no_wrap=True)
        table.add_column(
            lang.get("codec"), no_wrap=True, overflow="ellipsis", max_width=10
        )
        header_note = f"{lang.get('language')}{lang.get('table_note_suffix', default=' / Note')}"
        table.add_column(header_note)
        table.add_column(lang.get("table_bitrate"), no_wrap=True)

        for idx, af in enumerate(unique_audios, 1):
            curr_lang = af.get("language") or af.get("format_note") or lang.get("unknown", default="Unknown")
            tbr = f"{int(af.get('tbr', 0) or 0)}k"
            acodec = af.get("acodec", "unknown")
            table.add_row(
                str(idx),
                af["format_id"],
                acodec,
                curr_lang,
                tbr,
            )

        console.print(table)

        # Prompt User
        a_choice = Prompt.ask(
            lang.get("audio_choice"),
            choices=[str(i) for i in range(1, len(unique_audios) + 1)],
            default="1",
        )
        return unique_audios[int(a_choice) - 1]