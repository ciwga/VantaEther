import re
from pathlib import Path
from typing import Tuple, Optional, List
from rich.console import Console
from rich.prompt import Prompt

from vantaether.utils.i18n import LanguageManager
from vantaether.utils.system import DirectoryResolver

console = Console()
lang = LanguageManager()


class FileManager:
    """
    Manages file system operations including path resolution, sanitization,
    file detection, and user interaction regarding filenames.
    """

    def __init__(self) -> None:
        """Initializes the FileManager with a directory resolver."""
        self._resolver = DirectoryResolver()
        self.download_path: Path = self._resolver.resolve_download_directory()

    @property
    def base_path(self) -> Path:
        """Returns the resolved download directory path."""
        return self.download_path

    def sanitize_filename(self, name: str) -> str:
        """
        Sanitizes the filename to prevent filesystem errors and removes illegal characters.

        Args:
            name (str): The original filename.

        Returns:
            str: A safe filename string, truncated to 50 chars.
        """
        # Remove characters invalid in Windows/Linux filenames
        cleaned = re.sub(r'[<>:"/\\|?*]', "", name).strip()
        return cleaned[:50]

    def get_user_filename(self, default_name: str) -> str:
        """
        Prompts the user for a filename, defaulting to the sanitized video title.

        Args:
            default_name (str): The proposed default filename.

        Returns:
            str: The final filename chosen by the user.
        """
        clean_default = self.sanitize_filename(default_name)
        if not clean_default or clean_default.lower() == "cyber_media":
            clean_default = "video_download"

        console.print(f"\n[dim]{lang.get('filename_detected', name=clean_default)}[/]")
        user_name = Prompt.ask(lang.get("filename_prompt"), default=clean_default)
        return user_name.strip()

    def detect_files(
        self, filename_base: str
    ) -> Tuple[Optional[Path], Optional[str], Optional[Path]]:
        """
        Identifies main video and potential audio parts in the download directory.
        Uses heuristics to distinguish between the main file and orphaned audio tracks.

        Args:
            filename_base (str): The base filename (without extension) to search for.

        Returns:
            Tuple[Optional[Path], Optional[str], Optional[Path]]:
                (Main Video File Path, Main Extension, Orphan Audio File Path)
        """
        # 1. Find the Main Video File
        # Search for files starting with base name but NOT containing '.audio.'
        candidates = list(self.download_path.glob(f"{filename_base}.*"))

        # Strict Filter: Exclude metadata, partials, and explicit audio files
        video_candidates = [
            f
            for f in candidates
            if f.suffix not in [".json", ".srt", ".vtt", ".part", ".ytdl"]
            and ".part" not in f.name
            and ".audio." not in f.name  # Exclude our explicit audio files
            and f.stat().st_size > 1024  # Ignore empty files
        ]

        found_file: Optional[Path] = None
        actual_ext: Optional[str] = None
        orphan_audio_file: Optional[Path] = None

        if video_candidates:
            # Assume the largest file is the video stream
            found_file = max(video_candidates, key=lambda p: p.stat().st_size)
            actual_ext = found_file.suffix.lstrip(".")

        # 2. Find the Explicit Audio File
        # Search for the specific pattern: filename.audio.ext
        audio_candidates = list(self.download_path.glob(f"{filename_base}.audio.*"))

        valid_audio = [
            f
            for f in audio_candidates
            if f.suffix not in [".json", ".srt", ".vtt", ".part", ".ytdl"]
            and ".part" not in f.name
            and f.stat().st_size > 1024
        ]

        if valid_audio:
            orphan_audio_file = max(valid_audio, key=lambda p: p.stat().st_size)

        # Fallback: If no explicit '.audio.' file, try the old size heuristic
        if not orphan_audio_file and found_file:
            valid_others = [
                f
                for f in candidates
                if f != found_file
                and f.suffix not in [".json", ".srt", ".vtt", ".part", ".ytdl"]
                and ".part" not in f.name
                and f.stat().st_size > 1024
            ]
            if valid_others:
                orphan_audio_file = max(valid_others, key=lambda p: p.stat().st_size)

        return found_file, actual_ext, orphan_audio_file