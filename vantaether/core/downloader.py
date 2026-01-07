import re
import os
import sys
import json
import yt_dlp
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    TaskID,
)

from vantaether.core.merger import StreamMerger
from vantaether.utils.i18n import LanguageManager
from vantaether.core.analyzer import MediaAnalyzer
from vantaether.utils.system import DirectoryResolver


console = Console()
lang = LanguageManager()


class RichLogger:
    """
    Custom logger to integrate yt-dlp output with Rich console.
    Suppresses debug and warning messages to keep the UI clean.
    """

    def debug(self, msg: str) -> None:
        """Ignores debug messages."""
        pass

    def warning(self, msg: str) -> None:
        """Ignores warning messages."""
        pass

    def error(self, msg: str) -> None:
        """
        Prints error messages to the console using the configured language.

        Args:
            msg (str): The error message from yt-dlp.
        """
        console.print(f"[red]{lang.get('download_error', error=msg)}[/]")


class Downloader:
    """
    Handles file downloads using yt-dlp with interactive native support.
    Manages progress bars, format selection, playlist processing, and reporting.
    Now includes universal path resolution for cross-platform support.
    """

    def __init__(self) -> None:
        """Initialize the Downloader instance."""
        self.current_progress: Optional[Progress] = None
        self.dl_task: Optional[TaskID] = None
        self.analyzer = MediaAnalyzer()

        resolver = DirectoryResolver()
        self.download_path = resolver.resolve_download_directory()

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        """
        Callback hook for yt-dlp progress updates.

        Args:
            d (Dict[str, Any]): The progress dictionary provided by yt-dlp.
        """
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if self.current_progress and self.dl_task is not None:
                if total > 0:
                    self.current_progress.update(
                        self.dl_task, completed=downloaded, total=total
                    )
                else:
                    self.current_progress.update(self.dl_task, completed=downloaded)

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitizes the filename to prevent filesystem errors.

        Args:
            name (str): The original filename.

        Returns:
            str: A safe filename string.
        """
        return re.sub(r'[<>:"/\\|?*]', "", name).strip()[:50]

    def _get_user_filename(self, default_name: str) -> str:
        """
        Prompts the user for a filename, defaulting to the sanitized video title.

        Args:
            default_name (str): The proposed default filename.

        Returns:
            str: The final filename chosen by the user.
        """
        clean_default = self._sanitize_filename(default_name)
        if not clean_default:
            clean_default = "video_download"

        console.print(f"\n[dim]{lang.get('filename_detected', name=clean_default)}[/]")
        user_name = Prompt.ask(lang.get("filename_prompt"), default=clean_default)
        return user_name.strip()

    def create_pro_log(
        self,
        filename_base: str,
        url: str,
        format_info: Optional[Dict[str, Any]] = None,
        is_audio: bool = False,
    ) -> None:
        """
        Generates a JSON technical report for the downloaded media using ffprobe.
        
        Args:
            filename_base (str): The base filename (without path) chosen by user.
            url (str): The source URL.
            format_info (Optional[Dict[str, Any]]): Format metadata used for download.
            is_audio (bool): Whether the content is audio-only.
        """
        try:
            media_info = {}
            target_file = None
            
            # Construct potential full paths in the download directory
            possible_exts = [".mp4", ".mkv", ".webm", ".mp3", ".m4a"]
            
            for ext in possible_exts:
                candidate = self.download_path / f"{filename_base}{ext}"
                if candidate.exists():
                    target_file = candidate
                    break
            
            if target_file and self.analyzer:
                media_info = self.analyzer.get_media_info(str(target_file))

            log_data = {
                "timestamp": str(datetime.now()),
                "source": url,
                "type": "audio" if is_audio else "video",
                "storage_path": str(self.download_path),
                "media_info": media_info,
                "options": {
                    "quality": format_info.get("format_id") if format_info else "Best/Auto",
                    "forced_audio": is_audio,
                },
            }
            
            report_path = self.download_path / f"{filename_base}_REPORT.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=4)
            
            console.print(f"[green]{lang.get('report_created', path=str(report_path))}[/]")
        except Exception as e:
            console.print(f"[red]{lang.get('report_failed', error=str(e))}[/]")

    def _display_formats_table(
        self, formats: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Displays available video formats and asks the user to select one.

        Args:
            formats (List[Dict[str, Any]]): List of format dictionaries.

        Returns:
            Optional[Dict[str, Any]]: The selected format dictionary or None.
        """
        video_formats = sorted(
            [f for f in formats if f.get("height")],
            key=lambda x: x.get("height", 0),
            reverse=True,
        )

        unique_fmts = []
        seen = set()
        for f in video_formats:
            res = f"{f.get('height')}p"
            if res not in seen:
                unique_fmts.append(f)
                seen.add(res)

        if not unique_fmts:
            return None

        table = Table(title=lang.get("quality_options"), header_style="bold magenta")
        
        # Adding columns with no_wrap=True to guarantee layout stability on smaller screens
        table.add_column(lang.get("table_id"), justify="center", no_wrap=True)
        table.add_column(lang.get("resolution"), no_wrap=True)
        table.add_column(lang.get("table_bitrate"), no_wrap=True)
        
        # Codec column: Added with overflow protection
        table.add_column(lang.get("codec"), no_wrap=True, overflow="ellipsis", max_width=10)
        
        table.add_column(lang.get("table_ext"), no_wrap=True)
        table.add_column(lang.get("audio_status"), style="cyan")

        for idx, f in enumerate(unique_fmts, 1):
            audio_status = (
                lang.get("exists")
                if f.get("acodec") != "none" and f.get("acodec") is not None
                else lang.get("video_only")
            )
            tbr = f"{int(f.get('tbr', 0) or 0)}k"
            
            # Extract video codec
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
        choice = Prompt.ask(
            lang.get("choice"),
            choices=[str(i) for i in range(1, len(unique_fmts) + 1)],
            default="1",
        )
        return unique_fmts[int(choice) - 1]

    def _process_single_native_video(
        self, url: str, force_best: bool = False, audio_only: bool = False
    ) -> None:
        """
        Analyzes and downloads a single video with interactive format selection.

        Args:
            url (str): The video URL.
            force_best (bool): If True, skips prompts and selects best quality.
            audio_only (bool): If True, downloads only audio (converts to mp3).
        """
        console.print(f"[cyan]{lang.get('analyzing')}[/]")

        # Extract Info (Full Meta)
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

        title = info.get("title", "video")
        if force_best or audio_only:
            filename = self._sanitize_filename(title)
            console.print(f"[dim]{lang.get('filename_detected', name=filename)}[/]")
        else:
            filename = self._get_user_filename(title)

        # Notify user about the download location
        console.print(f"[bold blue]{lang.get('download_location')}[/] [dim]{self.download_path}[/]")

        # Prepare the output template with the full path
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

        # AUDIO ONLY MODE
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
            # NORMAL VIDEO MODE (Interactive)
            selected_fmt = self._display_formats_table(info.get("formats", []))

            if selected_fmt:
                v_id = selected_fmt["format_id"]

                # Audio Selection Logic
                # STRICT FILTERING: Exclude anything with height/width
                audio_formats = [
                    f for f in info.get("formats", [])
                    if (
                        (f.get("vcodec") == "none" or f.get("vcodec") is None)
                        and f.get("height") is None 
                        and f.get("width") is None
                    )
                    and f.get("acodec") != "none"
                ]

                selected_audio_id = "bestaudio"
                needs_audio = selected_fmt.get("acodec") == "none"

                if audio_formats and not needs_audio and len(audio_formats) > 1:
                    if Confirm.ask(
                        f"[cyan]{lang.get('select_audio')}[/]", default=False
                    ):
                        needs_audio = True

                if needs_audio and audio_formats:
                    # Deduplicate audio by ID
                    unique_audios = []
                    seen_audio = set()
                    for af in audio_formats:
                        aud_id = af.get("format_id")
                        if aud_id not in seen_audio:
                            unique_audios.append(af)
                            seen_audio.add(aud_id)

                    if unique_audios:
                        table = Table(
                            title=lang.get("audio_sources"), header_style="bold yellow"
                        )
                        table.add_column(lang.get("table_id"), justify="center", no_wrap=True)
                        table.add_column("Format ID", no_wrap=True)
                        # Added codec column with overflow protection
                        table.add_column(lang.get("codec"), no_wrap=True, overflow="ellipsis", max_width=10)
                        table.add_column(lang.get("language") + " / Note")
                        table.add_column(lang.get("table_bitrate"), no_wrap=True)

                        for idx, af in enumerate(unique_audios, 1):
                            curr_lang = (
                                af.get("language") or af.get("format_note") or "Unknown"
                            )
                            tbr = f"{int(af.get('tbr', 0) or 0)}k"
                            acodec = af.get("acodec", "unknown")
                            table.add_row(
                                str(idx), 
                                af["format_id"], 
                                acodec,
                                curr_lang, 
                                tbr
                            )

                        console.print(table)
                        a_choice = Prompt.ask(
                            lang.get("audio_choice"),
                            choices=[str(i) for i in range(1, len(unique_audios) + 1)],
                            default="1",
                        )
                        selected_audio_id = unique_audios[int(a_choice) - 1][
                            "format_id"
                        ]

                selected_format_id = f"{v_id}+{selected_audio_id}"
            else:
                console.print(f"[yellow]{lang.get('auto_quality')}[/]")

            # Subtitle Selection (Only for Video)
            subtitles = info.get("subtitles", {})
            if subtitles and Confirm.ask(lang.get("download_subs"), default=True):
                ydl_opts["writesubtitles"] = True
                ydl_opts["subtitleslangs"] = ["all", "-live_chat"]

                sub_langs = list(subtitles.keys())
                if len(sub_langs) < 10:
                    console.print(f"[dim]Available: {', '.join(sub_langs)}[/]")

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
                self.create_pro_log(
                    filename,
                    url,
                    format_info={"format_id": selected_format_id},
                    is_audio=audio_only,
                )

    def native_download(self, url: str, audio_only: bool = False) -> None:
        """
        Entry point for native downloads. Handles Playlists vs Single Videos.

        Args:
            url (str): The target URL.
            audio_only (bool): If True, downloads only audio.
        """
        console.print(
            Panel(
                lang.get("native_mode_desc", url=url),
                title=lang.get("native_mode_active"),
                border_style="cyan",
            )
        )

        # Initial probe to check if playlist using extract_flat
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
                    info = ydl.extract_info(url, download=False)
            except Exception as e:
                console.print(f"[bold red]{lang.get('native_mode_error', error=e)}[/]")
                return

        if not info:
            return

        # DETECT PLAYLIST
        is_playlist = info.get("_type") == "playlist" or (
            "entries" in info and len(info["entries"]) > 1
        )

        if is_playlist:
            # Detect if we are on YouTube to handle ID-based URL reconstruction
            extractor_key = info.get("extractor_key", "").lower()
            is_youtube_playlist = "youtube" in extractor_key

            entries = list(info.get("entries", []))
            total_videos = len(entries)

            console.print(
                Panel(
                    f"[bold white]{lang.get('playlist_detected', count=total_videos)}[/]\n"
                    f"[dim]{info.get('title', 'Unknown Playlist')}[/]",
                    title=lang.get("playlist_manager"),
                    border_style="magenta",
                )
            )

            # Show Playlist Table
            table = Table(show_header=True, header_style="bold green")
            table.add_column(lang.get("table_id"), style="dim", width=4)
            table.add_column(lang.get("table_title"))
            table.add_column(lang.get("table_url"), style="cyan")

            # Limit display to avoid flooding the terminal
            display_limit = 20
            for idx, entry in enumerate(entries[:display_limit], 1):
                title = entry.get("title", "Unknown")
                vid_id = entry.get("id", "")
                table.add_row(str(idx), title, vid_id)

            if total_videos > display_limit:
                table.add_row(
                    "...", f"... and {total_videos - display_limit} more", "..."
                )

            console.print(table)

            console.print(f"\n[bold yellow]{lang.get('options')}:[/]")
            console.print(f"  [bold white]ID[/] {lang.get('menu_specific')}")
            console.print(f"  [bold white]all[/]{lang.get('menu_all')}")

            choice = Prompt.ask(lang.get("command_prompt"), default="all")

            if choice.lower() == "all":
                if Confirm.ask(
                    lang.get("confirm_bulk_download", count=total_videos), default=True
                ):

                    force_best = False
                    if not audio_only:
                        console.print(lang.get("bulk_mode_prompt"))
                        mode = Prompt.ask(
                            lang.get("bulk_mode_choice"), choices=["1", "2"], default="1"
                        )
                        force_best = mode == "1"

                    for idx, entry in enumerate(entries, 1):
                        if entry:
                            video_url = entry.get("url") or entry.get("webpage_url")

                            if (
                                not video_url
                                and entry.get("id")
                                and is_youtube_playlist
                            ):
                                video_url = (
                                    f"https://www.youtube.com/watch?v={entry.get('id')}"
                                )

                            title = entry.get("title", f"Video {idx}")

                            if video_url:
                                console.rule(
                                    lang.get(
                                        "processing_item",
                                        index=idx,
                                        total=total_videos,
                                        title=title,
                                    )
                                )
                                try:
                                    self._process_single_native_video(
                                        video_url,
                                        force_best=force_best,
                                        audio_only=audio_only,
                                    )
                                except Exception as e:
                                    console.print(f"[red]Error on item {idx}: {e}[/]")

            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < total_videos:
                    entry = entries[idx]
                    video_url = entry.get("url") or entry.get("webpage_url")

                    if not video_url and entry.get("id") and is_youtube_playlist:
                        video_url = f"https://www.youtube.com/watch?v={entry.get('id')}"

                    if video_url:
                        self._process_single_native_video(
                            video_url, force_best=False, audio_only=audio_only
                        )
                else:
                    console.print(f"[red]{lang.get('invalid_id')}[/]")
            else:
                console.print(f"[red]{lang.get('cancelled')}[/]")

        else:
            # SINGLE VIDEO
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
    ) -> None:
        """
        Executes the download for a manually selected stream (Sync Mode).
        Uses a 'Double Tap' strategy: Explicitly downloads video and audio separately
        to guarantee that the audio stream is retrieved.
        """
        console.print(f"[bold blue]{lang.get('download_location')}[/] [dim]{self.download_path}[/]")
        
        requested_ext = "mkv" if embed_mode == "embed_mkv" else "mp4"

        http_headers = {
            "User-Agent": target.get("agent", "Mozilla/5.0"),
            "Referer": target.get("page", target["url"]),
            "Origin": "/".join(target.get("page", "").split("/")[:3]),
            "Accept": "*/*",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }

        # Use the resolved path for output
        base_output = self.download_path / filename

        post_processors = []

        # Common options base
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
            "ignoreerrors": True,
            "postprocessor_args": {
                "ffmpeg": ["-fflags", "+genpts", "-avoid_negative_ts", "make_zero"]
            },
        }

        # Subtitle Handling Setup
        if sub and sub["type"] == "internal":
            ydl_opts["subtitleslangs"] = [sub["lang"]]
            ydl_opts["writesubtitles"] = True
            if embed_mode == "convert_srt":
                post_processors.append(
                    {"key": "FFmpegSubtitlesConvertor", "format": "srt"}
                )
            elif "embed" in embed_mode:
                ydl_opts["embedsubtitles"] = True
        
        if post_processors:
            ydl_opts["postprocessors"] = post_processors

        ydl_opts["progress_hooks"] = [self._progress_hook]

        # --- EXECUTION STRATEGY: SPLIT DOWNLOAD ---
        # If the user selected a specific audio ID, we download video and audio separately
        # to prevent yt-dlp from implicitly skipping the audio merge.
        
        success_video = False
        success_audio = False
        
        if not force_mode and fmt and audio_id:
            # 1. Download Video
            console.print(f"[cyan]{lang.get('processing_video', format=fmt['format_id'])}[/]")
        
            opts_video = ydl_opts.copy()
            opts_video["format"] = fmt["format_id"]
            # Force standard filename for video
            opts_video["outtmpl"] = f"{base_output}.%(ext)s"
            # IMPORTANT: We want to know if video fails
            opts_video["ignoreerrors"] = False
            
            success_video = self._start_download(opts_video, target["url"], f"{filename} [Video]")
            
            # 2. Download Audio
            console.print(f"[cyan]{lang.get('processing_audio', format=audio_id)}[/]")
            
            opts_audio = ydl_opts.copy()
            opts_audio["format"] = audio_id
            # Force a distinct filename for audio so it doesn't conflict or get skipped
            opts_audio["outtmpl"] = f"{base_output}.audio.%(ext)s"
            # Disable subtitle writing for audio pass to avoid duplicates
            opts_audio["writesubtitles"] = False
            
            # CRITICAL FIXES FOR AUDIO STABILITY
            # Disable concurrency for audio segments to prevent corrupted part files
            opts_audio["concurrent_fragment_downloads"] = 1
            # Ensure we fail hard if audio doesn't download
            opts_audio["ignoreerrors"] = False
            
            success_audio = self._start_download(opts_audio, target["url"], f"{filename} [Audio]")
            
            # For merge to work, we ideally need both, or at least video.
            # But if audio failed (success_audio is False), we should probably not report full success.
            # However, if video downloaded, user at least has that.
            success = success_video

        else:
            # Standard single-pass behavior (Auto quality or no specific audio selected)
            if force_mode:
                ydl_opts["format"] = "bestvideo+bestaudio/best"
                ydl_opts["outtmpl"] = f"{base_output}.%(ext)s"
            else:
                if fmt:
                    # Video only or implicitly merged
                    ydl_opts["format"] = fmt["format_id"]
                    ydl_opts["outtmpl"] = f"{base_output}.%(ext)s"
                else:
                    ydl_opts["format"] = "best"

            if embed_mode == "embed_mkv":
                ydl_opts["merge_output_format"] = "mkv"
            elif embed_mode == "embed_mp4":
                ydl_opts["merge_output_format"] = "mp4"
            
            success = self._start_download(ydl_opts, target["url"], filename)

        if not success:
            return

        # --- HEURISTICS & MERGING ---
        # Look for files in the download path
        found_file, actual_ext, orphan_audio_file = self._detect_files(filename)

        if found_file:
            # Check if merging is required
            should_merge = (sub and sub["type"] == "external") or (
                orphan_audio_file is not None
            )

            if should_merge:
                StreamMerger.process_external_sub_sync(
                    sub["url"] if (sub and sub["type"] == "external") else None,
                    str(base_output), # Pass full base path (without extension)
                    embed_mode,
                    http_headers,
                    actual_ext,
                    str(orphan_audio_file) if orphan_audio_file else None,
                )
        else:
            console.print(f"[bold red]{lang.get('video_not_found')}[/]")

    def _start_download(self, opts: Dict[str, Any], url: str, filename: str) -> bool:
        """Wrapper to invoke yt-dlp with rich progress bar."""
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
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            console=console,
        )

        try:
            with self.current_progress:
                self.dl_task = self.current_progress.add_task(
                    "dl", filename=filename, total=None
                )
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

            console.print(Panel(lang.get("download_success"), border_style="green"))
            return True
        except Exception as e:
            console.print(f"[red]{lang.get('download_error', error=str(e))}[/]")
            return False

    def _detect_files(
        self, filename_base: str
    ) -> Tuple[Optional[Path], Optional[str], Optional[Path]]:
        """
        Identifies main video and potential audio parts in the DOWNLOAD DIRECTORY.
        Now specifically looks for the '.audio.' pattern created by the split download strategy.
        """
        # 1. Find the Main Video File
        # Search for files starting with base name but NOT containing '.audio.'
        candidates = list(self.download_path.glob(f"{filename_base}.*"))
        
        # Filter for video candidates
        # STRICT FILTER: Exclude any file that has '.part' in its NAME, not just suffix
        video_candidates = [
            f for f in candidates
            if not f.suffix in [".json", ".srt", ".vtt", ".part", ".ytdl"]
            and ".part" not in f.name
            and ".audio." not in f.name # Exclude our explicit audio files
            and f.stat().st_size > 1024
        ]
        
        found_file = None
        actual_ext = None
        orphan_audio_file = None
        
        if video_candidates:
            # Largest non-audio file is the video
            found_file = max(video_candidates, key=lambda p: p.stat().st_size)
            actual_ext = found_file.suffix.lstrip(".")
            console.print(Panel(lang.get("main_file"), border_style="green"))

        # 2. Find the Explicit Audio File
        # Search for the specific pattern we defined: filename.audio.ext
        audio_candidates = list(self.download_path.glob(f"{filename_base}.audio.*"))
        
        valid_audio = [
            f for f in audio_candidates
             if not f.suffix in [".json", ".srt", ".vtt", ".part", ".ytdl"]
             and ".part" not in f.name # Strict check for partial files
             and f.stat().st_size > 1024
        ]
        
        if valid_audio:
            # Pick the largest if multiple match (unlikely, but safe)
            orphan_audio_file = max(valid_audio, key=lambda p: p.stat().st_size)

        # Fallback: If no explicit '.audio.' file, try the old size heuristic
        if not orphan_audio_file and found_file:
            # Check original candidates again
             valid_others = [
                f for f in candidates 
                if f != found_file
                and not f.suffix in [".json", ".srt", ".vtt", ".part", ".ytdl"]
                and ".part" not in f.name
                and f.stat().st_size > 1024
            ]
             if valid_others:
                 orphan_audio_file = max(valid_others, key=lambda p: p.stat().st_size)

        if orphan_audio_file:
            console.print(
                Panel(
                    lang.get("part_file_detected"),
                    title=lang.get(
                        "part_file_desc",
                        video=found_file.name if found_file else "None",
                        audio=orphan_audio_file.name,
                    ),
                    border_style="yellow",
                )
            )

        return found_file, actual_ext, orphan_audio_file