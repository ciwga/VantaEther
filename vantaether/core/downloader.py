from pathlib import Path
from typing import Dict, Any, Optional

import yt_dlp
from yt_dlp.utils import DownloadError
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    Task,
)

from vantaether.core.merger import StreamMerger
from vantaether.utils.i18n import LanguageManager
from vantaether.utils.file_manager import FileManager
from vantaether.utils.report_generator import ReportGenerator
from vantaether.utils.header_factory import HeaderFactory 
from vantaether.utils.ui import (
    NativeYtDlpEtaColumn,
    NativeYtDlpSpeedColumn
)
from vantaether.exceptions import FileSystemError


console = Console()
lang = LanguageManager()


class DownloadManager:
    """
    Manages the downloading of captured streams (Sync Mode).
    
    This class orchestrates the download process for streams intercepted
    by the browser agent, handling cookie injection, header spoofing,
    and manual stream merging logic.
    
    Note: Native URL handling has been moved to vantaether.core.native.NativeDownloader.
    """

    def __init__(self) -> None:
        """Initialize the DownloadManager and its dependencies."""
        self.current_progress: Optional[Progress] = None
        self.dl_task: Optional[Task] = None

        self.file_manager = FileManager()
        self.report_generator = ReportGenerator(self.file_manager.base_path)

    @property
    def download_path(self) -> Path:
        """Proxy property to access download path from FileManager."""
        return self.file_manager.base_path

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        """
        Callback hook for yt-dlp progress updates.
        Captures native 'eta' and 'speed' from yt-dlp and passes them to the UI.
        
        Args:
            d (Dict[str, Any]): The progress dictionary provided by yt-dlp.
        """
        try:
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
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
        except Exception:
            pass

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
        
        Args:
            target (Dict): The captured target metadata.
            fmt (Any): Selected video format options.
            audio_id (Optional[str]): Selected audio format ID.
            sub (Any): Selected subtitle options.
            embed_mode (str): Mode for embedding subtitles/muxing.
            c_file (str): Path to the generated Netscape cookie file.
            filename (str): The desired output filename.
            force_mode (bool): Whether to force best quality/bypass prompts.

        Returns:
            bool: True if download and merge were successful, False otherwise.
        """
        try:
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
                "cookiefile": c_file if c_file else None,
                "concurrent_fragment_downloads": 8,
                "hls_prefer_native": True,
                "socket_timeout": 30,
                "retries": 20,
                "allow_unplayable_formats": False,
                "ignoreerrors": False,
                "postprocessor_args": {
                    "ffmpeg": ["-fflags", "+genpts", "-avoid_negative_ts", "make_zero"]
                },
                "progress_hooks": [self._progress_hook],
            }

            if sub and sub.get("type") == "internal":
                ydl_opts["subtitleslangs"] = [sub["lang"]]
                ydl_opts["writesubtitles"] = True

            success = False

            if not force_mode and fmt and audio_id:
                # Manual Split: Download Video and Audio separately, then merge by yt-dlp or manually
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
                # Standard Auto-Merge or Simple Download
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
                console.print(f"[dim red]{lang.get('download_failed_cleanup')}[/]")
                self.file_manager.clean_up_parts(filename)
                return False

            # Post-Download Detection & Merging
            try:
                found_file, actual_ext, orphan_audio_file = self.file_manager.detect_files(filename)
            except FileSystemError as fse:
                console.print(f"[red]{lang.get('file_detection_failed', error=fse)}[/]")
                return False

            if found_file:
                is_container_mismatch = (
                    (embed_mode == "embed_mkv" and actual_ext != "mkv") or 
                    (embed_mode == "embed_mp4" and actual_ext != "mp4")
                )

                should_merge = (
                    (sub and sub.get("type") == "external") or 
                    (orphan_audio_file is not None) or
                    is_container_mismatch
                )

                if should_merge:
                    try:
                        StreamMerger.process_external_sub_sync(
                            sub["url"] if (sub and sub.get("type") == "external") else None,
                            str(base_output),
                            embed_mode,
                            http_headers,
                            actual_ext,
                            str(orphan_audio_file) if orphan_audio_file else None,
                        )
                    except Exception as e:
                        console.print(f"[red]{lang.get('merge_failed_generic', error=e)}[/]")                        
                return True
            else:
                console.print(f"[bold red]{lang.get('video_not_found')}[/]")
                self.file_manager.clean_up_parts(filename)
                return False

        except Exception as e:
            console.print(f"[bold red]{lang.get('unexpected_download_error', error=e)}[/]")
            return False

    def _start_download(self, opts: Dict[str, Any], url: str, filename: str) -> bool:
        """
        Wrapper to invoke yt-dlp with rich progress bar.
        
        Args:
            opts: yt-dlp options.
            url: URL to download.
            filename: Name to display in UI.

        Returns:
            bool: Success status.
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
            "•", DownloadColumn(), "•", NativeYtDlpSpeedColumn(), "•", NativeYtDlpEtaColumn(),
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