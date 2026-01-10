import re
import os
import sys
import json
import yt_dlp
from yt_dlp.utils import DownloadError
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
from urllib.parse import urlparse, parse_qs

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    Task,
)

from vantaether.core.merger import StreamMerger
from vantaether.core.selector import FormatSelector
from vantaether.core.playlist import PlaylistManager
from vantaether.utils.i18n import LanguageManager
from vantaether.utils.file_manager import FileManager
from vantaether.utils.report_generator import ReportGenerator
from vantaether.utils.header_factory import HeaderFactory 
from vantaether.utils.ui import (
    RichLogger,
    NativeYtDlpEtaColumn,
    NativeYtDlpSpeedColumn
)


console = Console()
lang = LanguageManager()


class DownloadManager:
    """
    Orchestrates file downloads by coordinating between:
    - FileManager (Disk Ops)
    - FormatSelector (User Choice)
    - PlaylistManager (Batch Ops)
    - ReportGenerator (Logging)
    """

    def __init__(self) -> None:
        """Initialize the DownloadManager and its dependencies."""
        self.current_progress: Optional[Progress] = None
        self.dl_task: Optional[Task] = None

        self.file_manager = FileManager()
        self.report_generator = ReportGenerator(self.file_manager.base_path)
        self.selector = FormatSelector()
        self.playlist_manager = PlaylistManager()

    @property
    def download_path(self) -> Path:
        """Proxy property to access download path from FileManager."""
        return self.file_manager.base_path

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        """
        Callback hook for yt-dlp progress updates.
        Captures native 'eta' and 'speed' from yt-dlp and passes them to the UI.
        """
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)

            # Capture native metrics from yt-dlp
            eta = d.get("eta")
            speed = d.get("speed")

            if self.current_progress and self.dl_task is not None:
                self.current_progress.update(
                    self.dl_task,
                    completed=downloaded,
                    total=total if total > 0 else None,
                    eta=eta,
                    speed=speed,
                )

    def _process_single_native_video(
        self, url: str, force_best: bool = False, audio_only: bool = False
    ) -> None:
        """
        Analyzes and downloads a single video with interactive format selection.
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
            console.print(f"[bold red]{lang.get('analysis_failed')}[/]")
            return

        title = info.get("title", lang.get("default_filename_base"))
        if force_best or audio_only:
            filename = self.file_manager.sanitize_filename(title)
            console.print(f"[dim]{lang.get('filename_detected', name=filename)}[/]")
        else:
            filename = self.file_manager.get_user_filename(title)

        console.print(
            f"[bold blue]{lang.get('download_location')}[/] [dim]{self.download_path}[/]"
        )

        output_template = str(self.download_path / f"{filename}.%(ext)s")
        selected_format_id = "bestvideo+bestaudio/best"
        
        ydl_opts = {
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "progress_hooks": [self._progress_hook],
            "logger": RichLogger(),
            "concurrent_fragment_downloads": 8,
            "writethumbnail": False,
            "merge_output_format": "mp4",
        }

        if audio_only:
            console.print(f"[yellow]{lang.get('audio_only_active')}[/]")
            selected_format_id = "bestaudio/best"
            ydl_opts.pop("merge_output_format", None)
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        elif not force_best:
            # --- Interactive Video Selection ---
            selected_fmt = self.selector.select_video_format(info.get("formats", []))

            if selected_fmt:
                v_id = selected_fmt["format_id"]
                selected_audio_id = "bestaudio"
                
                all_formats = info.get("formats", [])
                needs_audio = selected_fmt.get("acodec") == "none"

                if Confirm.ask(f"[cyan]{lang.get('select_audio')}[/]", default=False):
                    audio_fmt = self.selector.select_audio_format(all_formats)
                    if audio_fmt:
                        selected_audio_id = audio_fmt["format_id"]
                        needs_audio = True

                selected_format_id = f"{v_id}+{selected_audio_id}"
            else:
                console.print(f"[yellow]{lang.get('auto_quality')}[/]")

            # --- Subtitle Selection ---
            subtitles = info.get("subtitles", {})
            if subtitles and Confirm.ask(lang.get("download_subs"), default=True):
                ydl_opts["writesubtitles"] = True
                ydl_opts["subtitleslangs"] = ["all", "-live_chat"]

                sub_langs = list(subtitles.keys())
                langs_str = ", ".join(sub_langs)
                if len(sub_langs) < 10:
                    console.print(f"[dim]{lang.get('available_subs', langs=langs_str)}[/]")
                else:
                    console.print(f"[dim]{lang.get('subs_count_detected', count=len(sub_langs))}[/]")

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

        ydl_opts["format"] = selected_format_id

        display_filename = f"{filename}.mp3" if audio_only else f"{filename}.mp4"
        success = self._start_download(ydl_opts, url, display_filename)

        if success:
            if Confirm.ask(lang.get("create_report_ask"), default=False):
                self.report_generator.create_report(
                    filename,
                    url,
                    format_info={"format_id": selected_format_id},
                    is_audio=audio_only,
                )

    def native_download(self, url: str, audio_only: bool = False) -> None:
        """
        Entry point for native downloads. Handles Playlists vs Single Videos.
        """
        console.print(
            Panel(
                lang.get("native_mode_desc", url=url),
                title=lang.get("native_mode_active"),
                border_style="cyan",
            )
        )

        # URL Pre-processing for Playlist detection
        probe_url = url
        try:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            if "list" in query_params and not query_params["list"][0].startswith("RD"):
                probe_url = f"https://www.youtube.com/playlist?list={query_params['list'][0]}"
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
            # Delegate playlist interaction to PlaylistManager
            selected_entries, force_best = self.playlist_manager.process_playlist_selection(
                info, audio_only
            )

            if not selected_entries:
                return

            is_youtube = "youtube" in info.get("extractor_key", "").lower()

            for idx, entry in enumerate(selected_entries, 1):
                if entry:
                    video_url = entry.get("url") or entry.get("webpage_url")
                    if not video_url and entry.get("id") and is_youtube:
                        video_url = f"https://www.youtube.com/watch?v={entry.get('id')}"

                    title = entry.get("title", f"Video {idx}")

                    if video_url:
                        console.rule(lang.get("processing_item", index=idx, total=len(selected_entries), title=title))
                        try:
                            self._process_single_native_video(
                                video_url,
                                force_best=force_best,
                                audio_only=audio_only,
                            )
                        except Exception as e:
                            console.print(f"[red]{lang.get('error_on_item', index=idx, error=e)}[/]")
        else:
            self._process_single_native_video(
                url, force_best=False, audio_only=audio_only
            )

    def download_stream(
        self,
        target: Dict[str, Any],
        fmt: Any,
        audio_id: Optional[str],
        sub: Any,
        embed_mode: str,
        c_file: str,
        filename: str,
        force_mode: bool = False,
    ) -> bool:
        """
        Executes the download for a manually selected stream (Sync Mode).
        Uses HeaderFactory to generate appropriate headers.
        """
        console.print(f"[bold blue]{lang.get('download_location')}[/] [dim]{self.download_path}[/]")

        http_headers = HeaderFactory.get_headers(
            target_url=target["url"],
            page_url=target.get("page", target["url"]),
            user_agent=target.get("agent", "Mozilla/5.0")
        )

        base_output = self.download_path / filename

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "noprogress": True,
            "http_headers": http_headers,
            "cookiefile": c_file,
            "concurrent_fragment_downloads": 8,
            "hls_prefer_native": True,
            "socket_timeout": 30,
            "retries": 20,
            "allow_unplayable_formats": True,
            "ignoreerrors": False,
            "postprocessor_args": {
                "ffmpeg": ["-fflags", "+genpts", "-avoid_negative_ts", "make_zero"]
            },
            "progress_hooks": [self._progress_hook],
        }

        if sub and sub["type"] == "internal":
            ydl_opts["subtitleslangs"] = [sub["lang"]]
            ydl_opts["writesubtitles"] = True

        success = False

        if not force_mode and fmt and audio_id:
            console.print(f"[cyan]{lang.get('processing_video', format_id=fmt['format_id'])}[/]")
            opts_video = ydl_opts.copy()
            opts_video["format"] = fmt["format_id"]
            opts_video["outtmpl"] = f"{base_output}.%(ext)s"
            opts_video["ignoreerrors"] = False

            video_fname = f"{filename}{lang.get('suffix_video')}"
            v_success = self._start_download(opts_video, target["url"], video_fname)

            console.print(f"[cyan]{lang.get('processing_audio', format_id=audio_id)}[/]")
            opts_audio = ydl_opts.copy()
            opts_audio["format"] = audio_id
            opts_audio["outtmpl"] = f"{base_output}.audio.%(ext)s"
            opts_audio["writesubtitles"] = False
            opts_audio["concurrent_fragment_downloads"] = 1
            opts_audio["ignoreerrors"] = False

            audio_fname = f"{filename}{lang.get('suffix_audio')}"
            a_success = self._start_download(opts_audio, target["url"], audio_fname)
            success = v_success and a_success
        else:
            if force_mode:
                ydl_opts["format"] = "bestvideo+bestaudio/best"
            else:
                ydl_opts["format"] = fmt["format_id"] if fmt else "best"

            ydl_opts["outtmpl"] = f"{base_output}.%(ext)s"

            if embed_mode == "embed_mkv":
                ydl_opts["merge_output_format"] = "mkv"
            elif embed_mode == "embed_mp4":
                ydl_opts["merge_output_format"] = "mp4"

            success = self._start_download(ydl_opts, target["url"], filename)

        if not success:
            return False

        # Check resulting files
        found_file, actual_ext, orphan_audio_file = self.file_manager.detect_files(filename)

        if found_file:
            is_container_mismatch = (
                (embed_mode == "embed_mkv" and actual_ext != "mkv") or 
                (embed_mode == "embed_mp4" and actual_ext != "mp4")
            )

            should_merge = (
                (sub and sub["type"] == "external") or 
                (orphan_audio_file is not None) or
                is_container_mismatch
            )

            if should_merge:
                StreamMerger.process_external_sub_sync(
                    sub["url"] if (sub and sub["type"] == "external") else None,
                    str(base_output),
                    embed_mode,
                    http_headers,
                    actual_ext,
                    str(orphan_audio_file) if orphan_audio_file else None,
                )
            return True
        else:
            console.print(f"[bold red]{lang.get('video_not_found')}[/]")
            return False

    def _start_download(self, opts: Dict[str, Any], url: str, filename: str) -> bool:
        """
        Wrapper to invoke yt-dlp with rich progress bar.
        Handles specific exceptions like 403 and DRM using localized strings.
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
        )

        try:
            with self.current_progress:
                self.dl_task = self.current_progress.add_task(
                    lang.get("task_download_key"), filename=filename, total=None
                )
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

            console.print(Panel(lang.get("download_success"), border_style="green"))
            return True
            
        except DownloadError as e:
            err_msg = str(e)
            
            if "403" in err_msg:
                console.print(f"[bold red]{lang.get('download_error_403')}[/]")
            elif "DRM" in err_msg or "copyright" in err_msg.lower():
                console.print(f"[bold red]{lang.get('download_error_drm')}[/]")
            else:
                console.print(f"[red]{lang.get('download_error', error=err_msg)}[/]")
            
            return False
            
        except Exception as e:
            console.print(f"[red]{lang.get('download_error', error=str(e))}[/]")
            return False