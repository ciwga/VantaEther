import sys
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qs, urlparse

import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    Task,
    TextColumn,
)
from rich.prompt import Confirm, Prompt
from yt_dlp.utils import DownloadError

from vantaether.core.playlist import PlaylistManager
from vantaether.core.selector import FormatSelector
from vantaether.exceptions import FileSystemError
from vantaether.utils.file_manager import FileManager
from vantaether.utils.i18n import LanguageManager
from vantaether.utils.report_generator import ReportGenerator
from vantaether.utils.ui import (
    NativeYtDlpEtaColumn,
    NativeYtDlpSpeedColumn,
    RichLogger,
)


console = Console()
lang = LanguageManager()

PLAYER_CLIENTS: List[str] = ["android", "ios", "web", "tv"]


class NativeDownloader:
    """
    Handles 'Native' downloads using yt-dlp directly.

    Prioritizes download stability and resolution selection over strict codec enforcement.
    Ensures safe handling of resources and full localization of UI strings.
    Integrates fallback mechanisms for multi-platform support (Kick, YouTube, Twitch, etc.).
    """

    def __init__(self) -> None:
        """Initializes the NativeDownloader and its dependencies."""
        self.file_manager = FileManager()
        self.report_generator = ReportGenerator(self.file_manager.base_path)
        self.selector = FormatSelector()
        self.playlist_manager = PlaylistManager()

        self.current_progress: Optional[Progress] = None
        self.dl_task: Optional[Task] = None

    @property
    def download_path(self) -> Any:
        """Returns the base download path from FileManager."""
        return self.file_manager.base_path

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        """
        Callback hook for yt-dlp progress updates to render Rich UI.

        Args:
            d (Dict[str, Any]): Dictionary containing download status and metrics.
        """
        try:
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate")

                speed = d.get("speed")
                eta = d.get("eta")

                if self.current_progress and self.dl_task is not None:
                    self.current_progress.update(
                        self.dl_task,
                        completed=downloaded,
                        total=total,
                        speed=speed,
                        eta=eta,
                    )

            elif d["status"] == "finished":
                if self.current_progress and self.dl_task is not None:
                    task_info = self.current_progress.tasks[self.dl_task]
                    self.current_progress.update(
                        self.dl_task,
                        completed=task_info.total or task_info.completed,
                        eta=0,
                    )
        except Exception:
            pass

    def native_download(self, url: str, audio_only: bool = False) -> None:
        """
        Main entry point. Detects content type and routes to handler.

        Args:
            url (str): The target URL to download.
            audio_only (bool): If True, forces audio extraction/conversion.
        """
        console.print(
            Panel(
                lang.get("native_mode_desc", url=url),
                title=lang.get("native_mode_active"),
                border_style="cyan",
            )
        )

        probe_url = url
        try:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            if "list" in query_params and not query_params["list"][0].startswith("RD"):
                probe_url = (
                    f"https://www.youtube.com/playlist?list={query_params['list'][0]}"
                )
                console.print(f"[dim cyan]{lang.get('playlist_id_detected')}[/]")
        except Exception:
            pass

        info: Optional[Dict[str, Any]] = None
        with console.status(lang.get("scanning_platform_database"), spinner="dots"):
            try:
                ydl_opts_probe = {
                    "extract_flat": True,
                    "quiet": True,
                    "no_warnings": True,
                    "ignoreerrors": True,
                }
                with yt_dlp.YoutubeDL(ydl_opts_probe) as ydl:
                    info = ydl.extract_info(probe_url, download=False)
            except Exception as e:
                console.print(f"[bold red]{lang.get('native_mode_error', error=e)}[/]")
                return

        if not info:
            return

        is_playlist = info.get("_type") == "playlist" or (
            "entries" in info and len(info.get("entries", [])) > 1
        )

        if is_playlist:
            self._handle_playlist(info, audio_only)
        else:
            self._process_single_video(url, force_best=False, audio_only=audio_only)

    def _handle_playlist(self, info: Dict[str, Any], audio_only: bool) -> None:
        """
        Iterates through playlist entries.

        Args:
            info (Dict[str, Any]): The extracted playlist information.
            audio_only (bool): Whether to download only audio.
        """
        try:
            (
                selected_entries,
                force_best,
            ) = self.playlist_manager.process_playlist_selection(info, audio_only)
        except Exception as e:
            console.print(f"[red]{lang.get('playlist_manager_error', error=e)}[/]")
            return

        if not selected_entries:
            return

        is_youtube = "youtube" in info.get("extractor_key", "").lower()

        for idx, entry in enumerate(selected_entries, 1):
            if entry:
                video_url = entry.get("url") or entry.get("webpage_url")
                if not video_url and entry.get("id") and is_youtube:
                    video_url = f"https://www.youtube.com/watch?v={entry.get('id')}"

                title = entry.get("title", lang.get("default_video_title", index=idx))

                if video_url:
                    console.rule(
                        lang.get(
                            "processing_item",
                            index=idx,
                            total=len(selected_entries),
                            title=title,
                        )
                    )
                    self._process_single_video(
                        video_url,
                        force_best=force_best,
                        audio_only=audio_only,
                    )

    def _process_single_video(
        self, url: str, force_best: bool = False, audio_only: bool = False
    ) -> None:
        """
        Prepares a single video for download using stable selection logic.

        Args:
            url (str): The video URL.
            force_best (bool): If True, bypasses manual selection and picks best quality.
            audio_only (bool): If True, processes as audio-only.
        """
        console.print(f"[cyan]{lang.get('analyzing')}[/]")

        info: Optional[Dict[str, Any]] = None
        try:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            console.print(f"[bold red]{lang.get('analysis_failed')}[/]: {e}")
            return

        if not info:
            return

        title = info.get("title", lang.get("default_filename_base"))

        try:
            if force_best or audio_only:
                filename = self.file_manager.sanitize_filename(title)
                console.print(f"[dim]{lang.get('filename_detected', name=filename)}[/]")
            else:
                filename = self.file_manager.get_user_filename(title)
        except FileSystemError as e:
            console.print(f"[red]{lang.get('filename_error', error=e)}[/]")
            return

        console.print(
            f"[bold blue]{lang.get('download_location')}[/] [dim]{self.download_path}[/]"
        )

        output_template = str(self.download_path / f"{filename}.%(ext)s")

        format_expr = "bestvideo+bestaudio/best"

        if audio_only:
            console.print(f"[yellow]{lang.get('audio_only_active')}[/]")
            format_expr = "bestaudio/best"
        elif not force_best:
            formats = info.get("formats", [])

            # Check if any video format has a valid resolution (height).
            # This prevents showing a selector with only "?p" (unknown) resolutions.
            has_valid_resolution = any(
                f.get("height") and f.get("vcodec") != "none" for f in formats
            )

            selected_fmt = None
            if has_valid_resolution:
                # Select video format via UI only if valid options exist
                selected_fmt = self.selector.select_video_format(formats)

            if selected_fmt:
                height = selected_fmt.get("height")
                # Default to best audio automatically without prompting
                audio_part = "bestaudio"
                fallback_part = "/best"

                if height:
                    video_part = f"bestvideo[height={height}]"
                    fallback_part = f"/best[height={height}]/best"
                    console.print(
                        f"[dim yellow]ℹ {lang.get('auto_codec_selection', height=height)}[/]"
                    )
                else:
                    # Should rarely hit here if has_valid_resolution check works,
                    # but handles manual selection of a format without height
                    console.print(
                        Panel(
                            lang.get("smart_mode_alert"),
                            border_style="yellow",
                            expand=False,
                        )
                    )
                    video_part = "bestvideo"

                format_expr = f"{video_part}+{audio_part}{fallback_part}"
            else:
                # Fallback logic: either no valid resolution found OR user cancelled selection
                if not has_valid_resolution:
                    console.print(
                        Panel(
                            lang.get("smart_mode_alert"),
                            border_style="yellow",
                            expand=False,
                        )
                    )
                else:
                    console.print(f"[yellow]{lang.get('auto_quality')}[/]")

                format_expr = "bestvideo+bestaudio/best"

        ydl_opts = {
            "outtmpl": output_template,
            "format": format_expr,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "progress_hooks": [self._progress_hook],
            "logger": RichLogger(),
            "concurrent_fragment_downloads": 8,
            "writethumbnail": False,
            "merge_output_format": "mp4",
            "add_metadata": True,
        }

        if audio_only:
            ydl_opts.pop("merge_output_format", None)
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
                {"key": "FFmpegMetadata"},
            ]
        else:
            self._handle_native_subtitles(info, ydl_opts)

        display_ext = "mp3" if audio_only else "mp4"
        display_filename = f"{filename}.{display_ext}"

        success = self._execute_with_fallback(ydl_opts, url, display_filename)

        if success:
            if Confirm.ask(lang.get("create_report_ask"), default=False):
                self.report_generator.create_report(
                    filename,
                    url,
                    format_info={"format_expr": format_expr},
                    is_audio=audio_only,
                )
        else:
            console.print(f"[dim red]{lang.get('cleanup_partial_failure')}[/]")
            self.file_manager.clean_up_parts(filename)

    def _handle_native_subtitles(
        self, info: Dict[str, Any], ydl_opts: Dict[str, Any]
    ) -> None:
        """
        Helper to handle native subtitle prompts and config.

        Args:
            info (Dict[str, Any]): Video info dictionary.
            ydl_opts (Dict[str, Any]): Options dictionary to modify in-place.
        """
        subtitles = info.get("subtitles", {})
        if subtitles and Confirm.ask(lang.get("download_subs"), default=True):
            ydl_opts["writesubtitles"] = True
            ydl_opts["subtitleslangs"] = ["all", "-live_chat"]

            sub_langs = list(subtitles.keys())
            if len(sub_langs) < 10:
                console.print(
                    f"[dim]{lang.get('available_subs', langs=', '.join(sub_langs))}[/]"
                )
            else:
                console.print(
                    f"[dim]{lang.get('subs_count_detected', count=len(sub_langs))}[/]"
                )

            console.print(lang.get("embed_mode_prompt"))
            m = Prompt.ask(
                lang.get("embed_mode_choice"),
                choices=["1", "2", "3", "4"],
                default="3",
            )

            if m == "2" or m == "3":
                ydl_opts["embedsubtitles"] = True
            if m == "3":
                ydl_opts["merge_output_format"] = "mkv"
            elif m == "2":
                ydl_opts["merge_output_format"] = "mp4"

    def _execute_with_fallback(
        self, base_opts: Dict[str, Any], url: str, filename: str
    ) -> bool:
        """
        Executes the download, first trying the default client (for Kick/generic support),
        then iterating through specific PLAYER_CLIENTS on failure (for YouTube).

        Args:
            base_opts (Dict[str, Any]): The base configuration for yt-dlp.
            url (str): The video URL.
            filename (str): Display filename for the UI.

        Returns:
            bool: True if download succeeded, False otherwise.
        """
        console.print("\n")
        console.rule(lang.get("download_starting", filename=filename))

        self.current_progress = Progress(
            SpinnerColumn("dots", style="bold magenta"),
            TextColumn("[bold cyan]{task.fields[filename]}", justify="right"),
            BarColumn(
                bar_width=None,
                style="dim white",
                complete_style="bold green",
                finished_style="bold green",
            ),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            DownloadColumn(),
            "•",
            NativeYtDlpSpeedColumn(),
            "•",
            NativeYtDlpEtaColumn(),
            console=console,
            transient=True,
        )

        download_strategies: List[Optional[str]] = [None] + PLAYER_CLIENTS

        for client in download_strategies:
            client_display_name = client if client else lang.get("standard_client_name")

            display_name = f"{filename} [{client_display_name}]"

            current_opts = base_opts.copy()

            if client:
                current_opts["player_client"] = client
            else:
                current_opts.pop("player_client", None)

            try:
                with self.current_progress:
                    self.dl_task = self.current_progress.add_task(
                        lang.get("task_download_key"),
                        filename=display_name,
                        total=None,
                    )

                    with yt_dlp.YoutubeDL(current_opts) as ydl:
                        ydl.download([url])

                console.print(Panel(lang.get("download_success"), border_style="green"))
                return True

            except Exception as e:
                error_msg = str(e)
                clean_err = error_msg.split("\n")[0] if "\n" in error_msg else error_msg

                console.print(
                    f"[dim yellow]{lang.get('client_attempt_failed', client=client_display_name, error=clean_err)}[/]"
                )

                if "Permission denied" in error_msg or "FileSystem" in str(type(e)):
                    console.print(
                        f"[bold red]{lang.get('critical_filesystem_error')}[/]"
                    )
                    return False
                continue

        console.print(f"[bold red]{lang.get('all_clients_failed')}[/]")
        return False