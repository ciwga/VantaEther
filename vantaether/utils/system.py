import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Optional
from rich.console import Console
from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


def clear_screen() -> None:
    """Clears the terminal screen cross-platform."""
    os.system('cls' if os.name == 'nt' else 'clear')

def check_systems() -> None:
    """
    Checks if essential system tools (ffmpeg) are installed using cross-platform detection.
    If found in a known non-standard path, adds it to the system PATH for this session.

    Raises:
        EnvironmentError: If ffmpeg is missing.
    """
    if shutil.which("ffmpeg"):
        return

    paths = []
    
    if sys.platform == "win32":
        paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            # Current directory check
            str(Path.cwd() / "ffmpeg.exe"),
            str(Path.cwd() / "bin" / "ffmpeg.exe")
        ]
    else:
        paths = [
            "/data/data/com.termux/files/usr/bin/ffmpeg",
            "/usr/bin/ffmpeg", 
            "/usr/local/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg"
        ]

    for p in paths:
        path_obj = Path(p)
        if path_obj.exists() and path_obj.is_file():
            # Add the directory to PATH so yt-dlp/subprocess can use 'ffmpeg' command
            bin_dir = str(path_obj.parent)
            if bin_dir not in os.environ["PATH"]:
                os.environ["PATH"] += os.pathsep + bin_dir
            return

    raise EnvironmentError(lang.get("ffmpeg_missing"))


class DirectoryResolver:
    """
    Manages directory resolution logic for file download operations across
    multiple operating systems including Windows, macOS, Linux, and Android.
    
    Ensures all downloads are directed to a specific application subdirectory.
    """

    APP_SUBDIRECTORY: str = "VantaEther"

    def resolve_download_directory(self) -> Path:
        """
        Resolves the most appropriate and writable directory for downloads.

        The resolution strategy follows a strict waterfall approach. It attempts
        to locate a base directory, creates the 'VantaEther' subdirectory inside it,
        and verifies writability.

        Priority Order:
        1. Android specific path (if environment matches).
        2. Standard OS 'Downloads' directory (e.g., ~/Downloads/VantaEther).
        3. User's Home directory (~/VantaEther).
        4. System Temporary directory (guaranteed writable fallback).

        Returns:
            Path: A validated, writable path object ending in '/VantaEther'.
        """
        # Android Detection Logic (Specific to Termux/Android environments)
        if "ANDROID_ROOT" in os.environ:
            android_base = Path("/storage/emulated/0/Download")
            app_dir = self._ensure_app_directory(android_base)
            if app_dir:
                return app_dir

        # Standard OS Downloads Folder
        try:
            home = Path.home()
            downloads_base = home / "Downloads"
            
            downloads_base.mkdir(parents=True, exist_ok=True)

            app_dir = self._ensure_app_directory(downloads_base)
            if app_dir:
                return app_dir

        except (PermissionError, OSError) as e:
            console.print(f"[bold yellow]! {lang.get('downloads_folder_error', error=e)}[/]")

        # User Home Directory Fallback
        # If Downloads is restricted, try creating the app folder directly in Home.
        try:
            home = Path.home()
            app_dir = self._ensure_app_directory(home)
            if app_dir:
                console.print(f"[bold white]➤ {lang.get('fallback_home')}[/]")
                return app_dir
                
        except (PermissionError, OSError) as e:
            console.print(f"[bold yellow]! {lang.get('home_dir_error', error=e)}[/]")

        # System Temp Directory (Last Resort)
        # This is almost guaranteed to be writable.
        temp_base = Path(tempfile.gettempdir())
        
        # Even in temp, we try to create our specific folder
        final_path = temp_base / self.APP_SUBDIRECTORY
        try:
            final_path.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            # If we can't even make a folder in temp, return bare temp as absolute fallback
            final_path = temp_base

        console.print(f"[bold red]! {lang.get('fallback_temp', temp_dir=final_path)}[/]")
        return final_path

    def _ensure_app_directory(self, base_path: Path) -> Optional[Path]:
        """
        Attempts to create the application specific subdirectory within a base path
        and verifies it is writable.

        Args:
            base_path (Path): The parent directory (e.g., Downloads).

        Returns:
            Optional[Path]: The full path to '.../VantaEther' if successful, 
                            None otherwise.
        """
        target_path = base_path / self.APP_SUBDIRECTORY
        
        try:
            target_path.mkdir(parents=True, exist_ok=True)
            
            if self._is_writable_directory(target_path):
                return target_path
        except (PermissionError, OSError):
            return None
            
        return None

    def _is_writable_directory(self, path: Path) -> bool:
        """
        Verifies if a given path is a directory and is writable by the current process.

        Args:
            path (Path): The path to check.

        Returns:
            bool: True if the path exists, is a directory, and is writable.
        """
        try:
            return path.exists() and path.is_dir() and os.access(path, os.W_OK)
        except (PermissionError, OSError):
            return False