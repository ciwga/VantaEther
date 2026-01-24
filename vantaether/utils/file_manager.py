import re
import time
import glob
from pathlib import Path
from typing import Tuple, Optional, List, Union

from rich.console import Console
from rich.prompt import Prompt

from vantaether.utils.i18n import LanguageManager
from vantaether.utils.system import DirectoryResolver


console = Console()
lang = LanguageManager()


class FileManager:
    """
    Manages file system operations including path resolution, sanitization,
    smart file detection, and cleanup operations.

    This class adheres to strict type safety and filesystem abstraction principles.
    """

    def __init__(self) -> None:
        """
        Initializes the FileManager instance.
        
        Sets up the directory resolver to determine the safest download path
        based on the operating system and environment.
        """
        self._resolver = DirectoryResolver()
        self._download_path: Path = self._resolver.resolve_download_directory()

    @property
    def base_path(self) -> Path:
        """
        Returns the resolved download directory path (Read-Only).

        Returns:
            Path: The absolute path to the download directory.
        """
        return self._download_path

    def sanitize_filename(self, name: str) -> str:
        """
        Sanitizes a filename string to ensure filesystem compatibility.

        Removes illegal characters and enforces a maximum length to prevent
        OS-level errors (e.g., Windows MAX_PATH issues).

        Args:
            name (str): The raw filename input.

        Returns:
            str: A safe, stripped filename truncated to 50 characters.
        """
        # Remove characters invalid in Windows/Linux filenames (e.g., < > : " / \ | ? *)
        cleaned = re.sub(r'[<>:"/\\|?*]', "", name).strip()
        
        # Enforce strict length limit for UI consistency and OS safety
        return cleaned[:50]

    def get_user_filename(self, default_name: str) -> str:
        """
        Prompts the user via CLI to confirm or modify the filename.

        Args:
            default_name (str): The proposed default filename derived from metadata.

        Returns:
            str: The final filename approved by the user.
        """
        clean_default = self.sanitize_filename(default_name)
        
        if not clean_default:
            clean_default = lang.get("default_download_name")

        console.print(f"\n[dim]{lang.get('filename_detected', name=clean_default)}[/]")
        
        user_name = Prompt.ask(lang.get("filename_prompt"), default=clean_default)
        return self.sanitize_filename(user_name.strip())

    def detect_files(
        self, filename_base: str
    ) -> Tuple[Optional[Path], Optional[str], Optional[Path]]:
        """
        Intelligently scans the download directory for the downloaded video and
        potential detached audio files using size heuristics and extension filtering.

        This is superior to simple globbing as it ignores temp files (.part, .ytdl)
        and explicitly looks for the largest media file.

        Args:
            filename_base (str): The base name of the file (without extension).

        Returns:
            Tuple containing:
                - Path to the main video file (or None).
                - Extension of the main video file (str or None).
                - Path to the orphaned audio file (or None).
        """
        safe_base = glob.escape(filename_base)

        # 1. Broad Search: Find all files matching the basename using the safe pattern
        candidates = list(self.base_path.glob(f"{safe_base}.*"))

        # 2. Filter: Exclude metadata, partial downloads, and known temp files
        video_candidates = [
            f
            for f in candidates
            if f.suffix not in [".json", ".srt", ".vtt", ".part", ".ytdl"]
            and ".part" not in f.name
            and ".audio." not in f.name  # Exclude explicit audio tracks from video search
            and f.stat().st_size > 1024  # Ignore empty/corrupt files (< 1KB)
        ]

        found_file: Optional[Path] = None
        actual_ext: Optional[str] = None
        orphan_audio_file: Optional[Path] = None

        if video_candidates:
            # Heuristic: The largest file is likely the video stream
            found_file = max(video_candidates, key=lambda p: p.stat().st_size)
            actual_ext = found_file.suffix.lstrip(".")

        # 3. Audio Search: specific pattern 'filename.audio.ext'
        # We also need the safe base pattern here
        audio_candidates = list(self.base_path.glob(f"{safe_base}.audio.*"))

        valid_audio = [
            f
            for f in audio_candidates
            if f.suffix not in [".json", ".srt", ".vtt", ".part", ".ytdl"]
            and ".part" not in f.name
            and f.stat().st_size > 1024
        ]

        if valid_audio:
            orphan_audio_file = max(valid_audio, key=lambda p: p.stat().st_size)

        # 4. Fallback Audio Search: If no explicit audio file, check for secondary large media files
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

    def clean_up_parts(self, base_name: str) -> None:
        """
        Removes temporary partial files and artifacts generated during the download process.
        
        This method safely suppresses FileNotFoundError to prevent crashes during cleanup.

        Args:
            base_name (str): The base filename used to identify partial files.
        """
        if not base_name:
            return

        safe_pattern = glob.escape(base_name) + "*"

        try:
            for p in self.base_path.glob(safe_pattern):
                name_lower = p.name.lower()
                
                is_partial = (
                    ".part" in name_lower or 
                    ".ytdl" in name_lower or 
                    ".temp" in name_lower or 
                    ".aria2" in name_lower or
                    "frag" in name_lower
                )

                if is_partial and p.is_file():
                    for attempt in range(3):
                        try:
                            p.unlink(missing_ok=True)
                            break
                        except (PermissionError, OSError):
                            if attempt < 2:
                                time.sleep(0.5)
                            else:
                                pass

        except Exception:
            pass