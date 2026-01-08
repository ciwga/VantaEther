import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from rich.console import Console

from vantaether.core.analyzer import MediaAnalyzer
from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


class ReportGenerator:
    """
    Handles the generation of technical JSON reports for downloaded media.
    Encapsulates dependencies on MediaAnalyzer to keep the main downloader clean.
    """

    def __init__(self, download_path: Path) -> None:
        """
        Initialize the ReportGenerator.

        Args:
            download_path (Path): The directory where reports should be saved.
        """
        self.download_path = download_path
        self.analyzer = MediaAnalyzer()

    def create_report(
        self,
        filename_base: str,
        url: str,
        format_info: Optional[Dict[str, Any]] = None,
        is_audio: bool = False,
        subtitle_info: Optional[Any] = None,
    ) -> None:
        """
        Generates a JSON technical report for the downloaded media using ffprobe.

        Args:
            filename_base (str): The base filename (without path) chosen by user.
            url (str): The source URL.
            format_info (Optional[Dict[str, Any]]): Format metadata used for download.
            is_audio (bool): Whether the content is audio-only.
            subtitle_info (Optional[Any]): Information about downloaded subtitles.
        """
        try:
            media_info = {}
            target_file: Optional[Path] = None

            # Construct potential full paths in the download directory
            possible_exts = [".mp4", ".mkv", ".webm", ".mp3", ".m4a"]

            for ext in possible_exts:
                candidate = self.download_path / f"{filename_base}{ext}"
                if candidate.exists():
                    target_file = candidate
                    break

            if target_file:
                media_info = self.analyzer.get_media_info(str(target_file))

            # Normalize quality string
            quality_val = "Raw/Unknown"
            if format_info:
                quality_val = format_info.get("format_id", "Best/Auto")

            log_data = {
                "timestamp": str(datetime.now()),
                "source": url,
                "type": "audio" if is_audio else "video",
                "storage_path": str(self.download_path),
                "media_info": media_info,
                "options": {
                    "quality": quality_val,
                    "forced_audio": is_audio,
                    "subtitle": subtitle_info,
                },
            }

            report_path = self.download_path / f"{filename_base}_REPORT.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=4)

            console.print(f"[green]{lang.get('report_created', path=str(report_path))}[/]")

        except Exception as e:
            console.print(f"[red]{lang.get('report_failed', error=str(e))}[/]")