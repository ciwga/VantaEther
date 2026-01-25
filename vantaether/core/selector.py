from typing import List, Dict, Any, Optional

from rich.table import Table
from rich.prompt import Prompt
from rich.console import Console

from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


class FormatSelector:
    """
    Handles the interactive selection of media formats (video/audio).
    Provides robust parsing of yt-dlp format data to prevent UI crashes.
    """

    def select_video_format(
        self, formats: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Displays available video formats and prompts the user to select one.
        
        Args:
            formats: Raw format list from yt-dlp or internal JSON parser.

        Returns:
            Selected format dict or None.
        """
        if not formats:
            return None

        # Filter valid video formats (must have height or be known video codec or come from JSON parser)
        # Sort by resolution (Height) descending, then Bitrate descending
        # Modified for JSON API Support: Handles cases where 'vcodec' or 'tbr' is missing safely.
        video_formats = sorted(
            [f for f in formats if f.get("height") or f.get("vcodec", "none") != "none" or f.get("format_note")],
            key=lambda x: (x.get("height", 0) or 0, x.get("tbr", 0) or 0, x.get("filesize", 0) or 0),
            reverse=True,
        )

        # Deduplication Strategy: Group by resolution string to show clean options
        unique_fmts = []
        seen = set()
        
        for f in video_formats:
            height = f.get("height")
            # Fallback to format_note (often contains label like "1080p" in JSON apis)
            res_str = f"{height}p" if height else (f.get("format_note") or lang.get("unknown"))
            
            # Use URL as part of uniqueness check if format_id is generic
            unique_key = f"{res_str}_{f.get('filesize')}"
            
            if unique_key not in seen:
                unique_fmts.append(f)
                seen.add(unique_key)

        if not unique_fmts:
            return None

        # Build UI Table
        table = Table(title=lang.get("quality_options"), header_style="bold magenta")
        table.add_column(lang.get("table_id"), justify="center", no_wrap=True)
        table.add_column(lang.get("resolution"), no_wrap=True)
        table.add_column(lang.get("size"), no_wrap=True)
        table.add_column(lang.get("table_bitrate"), no_wrap=True)
        table.add_column(lang.get("codec"), no_wrap=True, max_width=12, overflow="ellipsis")
        table.add_column(lang.get("table_ext"), no_wrap=True)
        table.add_column(lang.get("audio_status"), style="cyan")

        for idx, f in enumerate(unique_fmts, 1):
            # Audio Status check
            # For JSON APIs, assume audio exists if codec is unknown to prevent misleading "Video Only" warning
            has_audio = (f.get("acodec") != "none" and f.get("acodec") is not None) or \
                        (f.get("vcodec") == "unknown")
            
            audio_status = lang.get("exists") if has_audio else lang.get("video_only")
            
            # Bitrate formatting
            tbr = f.get("tbr")
            tbr_str = f"{int(tbr)}k" if tbr else "~"
            
            # Size formatting
            fsize = f.get("filesize")
            size_str = f"{int(fsize / 1024 / 1024)} MB" if fsize else "~"

            # Codec formatting
            vcodec = f.get("vcodec", lang.get("unknown"))
            if vcodec == "none": vcodec = lang.get("codec_images")

            table.add_row(
                str(idx),
                f"{f.get('height', '?')}p",
                size_str,
                tbr_str,
                vcodec,
                f.get("ext", "mp4"),
                audio_status,
            )

        console.print(table)
        
        choices = [str(i) for i in range(1, len(unique_fmts) + 1)]
        choice = Prompt.ask(
            lang.get("choice"),
            choices=choices,
            default="1",
        )
        return unique_fmts[int(choice) - 1]

    def select_audio_format(
        self, formats: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Displays available audio-only streams and prompts the user to select one.
        
        Args:
            formats: Raw format list.

        Returns:
            Selected audio format dict or None.
        """
        # Strict filter for audio-only streams
        audio_formats = [
            f for f in formats
            if (f.get("vcodec") == "none" or f.get("vcodec") is None)
            and f.get("acodec") != "none"
        ]

        if not audio_formats:
            return None

        # Deduplicate by Format ID to avoid showing identical streams
        unique_audios = []
        seen_ids = set()
        
        # Sort by bitrate (Quality) descending
        audio_formats.sort(key=lambda x: x.get("tbr", 0) or 0, reverse=True)

        for af in audio_formats:
            fmt_id = af.get("format_id")
            if fmt_id not in seen_ids:
                unique_audios.append(af)
                seen_ids.add(fmt_id)

        if not unique_audios:
            return None

        table = Table(title=lang.get("audio_sources"), header_style="bold yellow")
        table.add_column(lang.get("table_id"), justify="center")
        table.add_column("ID", no_wrap=True, style="dim")
        table.add_column(lang.get("codec"), max_width=10)
        table.add_column(lang.get("language") or lang.get("audio_note"))
        table.add_column(lang.get("table_bitrate"))

        for idx, af in enumerate(unique_audios, 1):
            lang_code = af.get("language") or af.get("format_note") or lang.get("unknown")
            tbr = af.get("tbr")
            tbr_str = f"{int(tbr)}k" if tbr else "~"
            
            table.add_row(
                str(idx),
                af.get("format_id", "?"),
                af.get("acodec", lang.get("unknown")),
                lang_code,
                tbr_str,
            )

        console.print(table)

        choices = [str(i) for i in range(1, len(unique_audios) + 1)]
        a_choice = Prompt.ask(
            lang.get("audio_choice"),
            choices=choices,
            default="1",
        )
        return unique_audios[int(a_choice) - 1]