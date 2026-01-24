import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List

from rich.console import Console

from vantaether.exceptions import DependencyError, FileSystemError
from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


def clear_screen() -> None:
    """
    Clears the terminal screen in a cross-platform manner.
    
    Handles OS-specific commands ('cls' for Windows, 'clear' for Unix).
    Suppresses errors if running in an environment without a TTY (e.g., IDEs).
    """
    try:
        command = 'cls' if os.name == 'nt' else 'clear'
        os.system(command)
    except Exception:
        pass


def check_systems() -> None:
    """
    Verifies that critical system dependencies (specifically FFmpeg) are installed.
    
    If FFmpeg is found in known non-standard locations (like Termux or local bin),
    it temporarily adds that location to the system PATH for the current process.

    Raises:
        DependencyError: If FFmpeg cannot be found anywhere.
    """
    try:
        if shutil.which("ffmpeg"):
            return

        paths: List[str] = []
        
        if sys.platform == "win32":
            paths = [
                r"C:\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
                # Portable checks relative to CWD
                str(Path.cwd() / "ffmpeg.exe"),
                str(Path.cwd() / "bin" / "ffmpeg.exe")
            ]
        else:
            # Linux / macOS / Android (Termux)
            paths = [
                "/data/data/com.termux/files/usr/bin/ffmpeg",
                "/usr/bin/ffmpeg", 
                "/usr/local/bin/ffmpeg",
                "/opt/homebrew/bin/ffmpeg",
                "/usr/local/sbin/ffmpeg"
            ]

        found = False
        for p in paths:
            try:
                path_obj = Path(p)
                if path_obj.exists() and path_obj.is_file():
                    # Add the directory to PATH so subprocesses can find 'ffmpeg'
                    bin_dir = str(path_obj.parent)
                    current_path = os.environ.get("PATH", "")
                    
                    if bin_dir not in current_path:
                        os.environ["PATH"] = bin_dir + os.pathsep + current_path
                        console.print(f"[dim green]{lang.get('ffmpeg_added_to_path', path=bin_dir)}[/]")
                    
                    found = True
                    break
            except OSError:
                continue

        if not found:
            raise DependencyError(lang.get("ffmpeg_missing"))

    except Exception as e:
        if isinstance(e, DependencyError):
            raise
        raise DependencyError(lang.get("system_check_failed", error=str(e)))


class DirectoryResolver:
    """
    Manages logic for determining the optimal download directory.
    
    Supports Windows, macOS, Linux, and Android (Termux) environments.
    Enforces a strict waterfall strategy to ensure a writable path is always returned.
    """

    APP_SUBDIRECTORY: str = "VantaEther"

    def resolve_download_directory(self) -> Path:
        """
        Determines the best available directory for storing downloads.

        Priority Order:
        1. Android/Termux external storage (if accessible).
        2. OS Standard 'Downloads' folder.
        3. User's Home directory.
        4. System Temporary directory (Fallback).

        Returns:
            Path: A validated, writable path ending with the app subdirectory.
        """
        # 1. Android / Termux Detection
        if "ANDROID_ROOT" in os.environ:
            try:
                # Common path for Android internal storage
                android_base = Path("/storage/emulated/0/Download")
                app_dir = self._ensure_app_directory(android_base)
                if app_dir:
                    return app_dir
            except (PermissionError, OSError) as e:
                console.print(f"[dim yellow]{lang.get('android_dir_error', error=e)}[/]")

        # 2. Standard OS Downloads Folder
        try:
            home = Path.home()
            downloads_base = home / "Downloads"
            
            # Attempt to create standard Downloads if it doesn't exist (rare but possible)
            try:
                downloads_base.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

            app_dir = self._ensure_app_directory(downloads_base)
            if app_dir:
                return app_dir

        except (PermissionError, OSError) as e:
            console.print(f"[bold yellow]! {lang.get('downloads_folder_error', error=e)}[/]")

        # 3. User Home Directory Fallback
        try:
            home = Path.home()
            app_dir = self._ensure_app_directory(home)
            if app_dir:
                console.print(f"[bold white]➤ {lang.get('fallback_home')}[/]")
                return app_dir
                
        except (PermissionError, OSError) as e:
            console.print(f"[bold yellow]! {lang.get('home_dir_error', error=e)}[/]")

        # 4. System Temp Directory (Last Resort)
        try:
            temp_base = Path(tempfile.gettempdir())
            final_path = temp_base / self.APP_SUBDIRECTORY
            final_path.mkdir(parents=True, exist_ok=True)
            console.print(f"[bold red]! {lang.get('fallback_temp', temp_dir=final_path)}[/]")
            return final_path
        except (PermissionError, OSError) as e:
            console.print(f"[bold red]{lang.get('critical_io_error_cwd', error=e)}[/]")
            return Path.cwd()

    def _ensure_app_directory(self, base_path: Path) -> Optional[Path]:
        """
        Attempts to create the app subdirectory within a base path and checks permissions.

        Args:
            base_path (Path): The parent directory.

        Returns:
            Optional[Path]: The valid path if successful, None otherwise.
        """
        try:
            target_path = base_path / self.APP_SUBDIRECTORY
            target_path.mkdir(parents=True, exist_ok=True)
            
            if self._is_writable_directory(target_path):
                return target_path
        except (PermissionError, OSError):
            return None
            
        return None

    def _is_writable_directory(self, path: Path) -> bool:
        """
        Verifies if a path exists, is a directory, and is writable.

        Args:
            path (Path): The path to verify.

        Returns:
            bool: True if usable.
        """
        try:
            return path.exists() and path.is_dir() and os.access(path, os.W_OK)
        except (PermissionError, OSError):
            return False