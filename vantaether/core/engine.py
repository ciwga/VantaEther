import re
import sys
import time
import json
import threading
import traceback
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, Any, Tuple, List, Set, Union

import requests
import yt_dlp
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.console import Console
from rich.prompt import Prompt, Confirm

import vantaether.config as config
from vantaether.utils.i18n import LanguageManager
from vantaether.core.analyzer import MediaAnalyzer
from vantaether.core.selector import FormatSelector
from vantaether.core.downloader import DownloadManager
from vantaether.core.subtitle_processor import SubtitleProcessor
from vantaether.utils.cookies import create_cookie_file
from vantaether.utils.header_factory import HeaderFactory
from vantaether.server.app import VantaServer, CaptureManager
from vantaether.utils.system import check_systems, clear_screen
from vantaether.exceptions import VantaError


console = Console()
lang = LanguageManager()


class VantaEngine:
    """
    Main engine class for managing the UI, stream selection, cookie handling,
    and download execution in Sync Mode (Browser Interception).

    Orchestrates:
    1. The Flask Server (CaptureManager) -> Captures URLs
    2. The User Interface (Rich) -> Interactions
    3. The Downloader (yt-dlp) -> Processing
    """

    def __init__(self, enable_console: bool = False) -> None:
        """
        Initialize the Engine, checking systems and setting up components.
        
        Args:
            enable_console (bool): If True, browser console logs are mirrored to TUI.
        """
        try:
            clear_screen()
            console.print(Align.center(config.BANNER), style="bold magenta")
            
            self.analyzer = MediaAnalyzer()
            self.enable_console = enable_console
            
            check_systems()

            self.download_manager = DownloadManager()
            self.file_manager = self.download_manager.file_manager
            self.report_generator = self.download_manager.report_generator
            self.selector = FormatSelector()
            self.capture_manager = CaptureManager()
            
            # Initialize the dedicated subtitle processor
            self.subtitle_processor = SubtitleProcessor(self.capture_manager)
            
        except Exception:
            console.print(Panel(lang.get("ffmpeg_not_found"), style="bold red"))
            console.print(f"[dim]{traceback.format_exc()}[/]")
            sys.exit(1)
    
    def format_smart_display_url(self, url: str, max_length: int = 70) -> str:
        """
        Formats a URL to be human-readable by keeping domain, start, and end.
        
        Args:
            url (str): The original full URL string.
            max_length (int): The maximum allowed length.

        Returns:
            str: The formatted display string.
        """
        display_url: str = url

        try:
            parsed_url = urlparse(url)
            path_segments: List[str] = [p for p in parsed_url.path.split('/') if p]
            
            if len(path_segments) >= 2:
                base_url: str = f"{parsed_url.scheme}://{parsed_url.netloc}"
                first_segment: str = path_segments[0]
                last_segment: str = path_segments[-1]
                display_url = f"{base_url}/{first_segment}/.../{last_segment}"
            elif len(path_segments) == 1:
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                display_url = f"{base_url}/{path_segments[0]}"
            else:
                display_url = url[:max_length] + "..." if len(url) > max_length else url

        except Exception:
            display_url = url[:max_length] + "..." if len(url) > max_length else url

        return display_url

    def _render_capture_instructions(self) -> None:
        """Renders the initial instructions panel."""
        step1_desc = lang.get('manual_step_1_desc', url=config.SERVER_URL)
        step1_desc = step1_desc.replace("\n", "\n   ")
        
        step2_desc = lang.get('manual_step_2_desc')
        step2_desc = step2_desc.replace("\n", "\n   ")

        console.print(
            Panel(
                f"[bold white]{lang.get('manual_step_1')}[/]\n"
                f"   [dim]{step1_desc}[/]\n\n"
                f"[bold white]{lang.get('manual_step_2')}[/]\n"
                f"   [dim]{step2_desc}[/]",
                title=lang.get("manual_sync_title"),
                border_style="magenta",
                expand=False,
            )
        )

    def _poll_for_items(self, seen_logs: Set[str], last_item_count: int) -> int:
        """
        Polls the capture manager for new items or logs.
        Blocks (via wait_for_item) until data arrives or timeout.
        
        Args:
            seen_logs (Set[str]): Set of log IDs already displayed.
            last_item_count (int): Previous count of video items.
            
        Returns:
            int: The new item count if updated, otherwise -1.
        """
        with console.status(
            f"[bold yellow]{lang.get('waiting_signal')}[/] "
            f"[dim]({lang.get('listen_console') if self.enable_console else lang.get('silent_mode')})[/]",
            spinner="earth",
        ) as status:
            while True:
                try:
                    has_new_data = self.capture_manager.wait_for_item(timeout=1.0)
                    
                    if has_new_data or self.enable_console:
                        snapshot = self.capture_manager.get_snapshot()
                        raw_videos = snapshot.get("videos", [])
                        
                        real_videos = []
                        new_logs = []
                        
                        # Separate logs from actionable video streams
                        for v in raw_videos:
                            v_type = v.get("media_type", "")
                            v_source = v.get("source", "")
                            
                            if v_type == "log" or v_source == "REMOTE_LOG":
                                if self.enable_console:
                                    msg_id = f"{v.get('title')}:{v.get('url')}"
                                    if msg_id not in seen_logs:
                                        new_logs.append(v)
                                        seen_logs.add(msg_id)
                            else:
                                real_videos.append(v)
                        
                        # Print new logs
                        for log_item in new_logs:
                            level = log_item.get("title", "INFO")
                            msg = log_item.get("url", "").replace("LOG: ", "")
                            
                            style = "dim white"
                            prefix = lang.get("browser_log_prefix")
                            
                            if level == "DRM_ALERT":
                                style = "bold white on red"
                                prefix = lang.get("drm_detected_prefix")
                            elif level == "SUCCESS":
                                style = "bold green"
                                prefix = lang.get("capture_prefix")
                            
                            console.print(f"{prefix} {msg}", style=style)

                        # Check if video count increased
                        current_count = len(real_videos)
                        if current_count > 0 and current_count > last_item_count:
                            return current_count
                except Exception as inner_e:
                    console.print(f"[dim red]{lang.get('polling_error', error=inner_e)}[/]")
                    time.sleep(1)
        return -1

    def _render_capture_table(self, valid_videos: List[Dict], pool: Dict) -> None:
        """Renders the table of captured media streams."""
        clear_screen()
        console.print(Align.center(config.BANNER), style="bold magenta")

        table = Table(title=lang.get("captured_streams_title"), show_lines=True)
        table.add_column(lang.get("table_id"), style="cyan", justify="center")
        table.add_column(lang.get("source_type"), style="magenta")
        table.add_column(lang.get("url_short"), style="green")

        for idx, vid in enumerate(valid_videos, 1):
            u = vid.get("url", "")
            source = vid.get("source", lang.get("unknown"))
            t_type = vid.get("media_type", "")

            # Determine formatted type label
            ftype = source
            if "master" in u:
                ftype += f" [bold yellow]{lang.get('master_suffix')}[/]"
            elif "manifest" in t_type or "m3u8" in u:
                ftype += lang.get("stream_suffix")
            elif "api" in t_type or "embed" in u:
                ftype += f" [bold yellow]{lang.get('api_embed_suffix')}[/]"
            elif "mp4" in u:
                ftype += lang.get("mp4_suffix")

            display_url = self.format_smart_display_url(u)
            table.add_row(str(idx), ftype, display_url)

        console.print(table)
        console.print(
            f"\n[dim]{lang.get('video_count', video_count=len(valid_videos), sub_count=len(pool.get('subs', [])))}[/]"
        )
        console.print(f"[bold yellow]{lang.get('options')}[/]")
        console.print(f"  [bold white]<ID>[/] : {lang.get('enter_id')}")
        console.print(f"  [bold white]r[/]    : {lang.get('refresh')}")
        console.print(f"  [bold red]c[/]    : {lang.get('clear_list')}")
        if self.enable_console:
            console.print(f"  [dim white]{lang.get('logs_background_hint')}[/]")

    def wait_for_target_interactive(self) -> Optional[Dict[str, Any]]:
        """
        Main loop for the TUI.
        Starts server, polls for items, and handles user selection.

        Returns:
            Optional[Dict[str, Any]]: Selected target or None.
        """
        try:
            self._render_capture_instructions()

            # Start server
            server = VantaServer(capture_manager=self.capture_manager)
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()
            
            if not self.enable_console:
                if Confirm.ask(f"[bold yellow]{lang.get('ask_enable_console')}[/]", default=False):
                    self.enable_console = True
                    console.print(f"[green]✔ {lang.get('listen_console')}[/]")
                else:
                    console.print(f"[dim]{lang.get('console_disabled')}[/]")

            seen_logs: Set[str] = set()
            last_item_count: int = -1

            while True:
                # 1. Polling
                new_count = self._poll_for_items(seen_logs, last_item_count)
                if new_count != -1:
                    last_item_count = new_count

                # 2. Display & Input
                display_pool = self.capture_manager.get_snapshot()
                all_items = display_pool.get("videos", [])
                valid_videos = [
                    v for v in all_items 
                    if v.get("media_type") != "log" and v.get("source") != "REMOTE_LOG"
                ]

                self._render_capture_table(valid_videos, display_pool)
                last_item_count = len(valid_videos) # Sync count

                choice = Prompt.ask(f"\n[bold cyan]{lang.get('command_prompt')}[/]", default="r")

                # Handle Commands
                if choice.lower() == "r":
                    last_item_count = -1 # Force re-poll
                    continue
                
                if choice.lower() == "c":
                    try:
                        requests.post(f"{config.SERVER_URL}/clear", timeout=2)
                        seen_logs.clear()
                        last_item_count = -1
                        console.print(f"[green]{lang.get('list_cleared_success')}[/]")
                        time.sleep(1)
                    except Exception as e:
                        console.print(f"[bold red]{lang.get('clear_failed', error=e)}[/]")
                    continue

                if choice.isdigit():
                    idx = int(choice)
                    if 1 <= idx <= len(valid_videos):
                        selected_target = valid_videos[idx - 1]
                        console.print(lang.get("selected", url=selected_target['url']))
                        return selected_target
                    else:
                        console.print(f"[bold red]{lang.get('invalid_id')}[/]")
                        time.sleep(1)

        except KeyboardInterrupt:
            console.print(f"\n[red]{lang.get('cancelled')}[/]")
            sys.exit(0)
        except Exception as e:
            console.print(f"[bold red]{lang.get('critical_error')}[/] {lang.get('unhandled_ui_exception')} {e}")
            return None

    def _recursive_find_videos(self, data: Union[Dict, List, Any], found_videos: List[Dict]) -> None:
        """
        Recursively searches for video-like objects in a JSON structure.
        Look for keys like 'url', 'file', 'src' and associated metadata.

        Args:
            data: The JSON data to search.
            found_videos: List to append found formats to.
        """
        if isinstance(data, dict):
            # Check if this dict looks like a video object
            url_candidate = data.get("url") or data.get("file") or data.get("src")
            if url_candidate and isinstance(url_candidate, str):
                # Simple check for common video extensions or keywords
                if re.search(r'\.(mp4|mkv|webm|m3u8)|/video/', url_candidate):
                    
                    label = data.get("label") or data.get("quality") or data.get("res") or "unknown"
                    size = data.get("size") or data.get("filesize") or 0
                    
                    # Try to extract height from label (e.g., "1080p" -> 1080)
                    height = 0
                    if label != "unknown":
                        match = re.search(r'(\d{3,4})', str(label))
                        if match:
                            height = int(match.group(1))

                    found_videos.append({
                        "format_id": f"json_{label}_{len(found_videos)}",
                        "url": url_candidate,
                        "ext": "mp4",
                        "vcodec": "unknown",
                        "acodec": "unknown",
                        "height": height,
                        "filesize": size if isinstance(size, int) else 0,
                        "tbr": 0, # Usually unknown in simple JSON APIs
                        "format_note": str(label)
                    })
            
            # Recurse into values
            for v in data.values():
                self._recursive_find_videos(v, found_videos)
        
        elif isinstance(data, list):
            for item in data:
                self._recursive_find_videos(item, found_videos)

    def _process_json_api(self, target: Dict[str, Any], headers: Dict) -> Optional[List[Dict]]:
        """
        Attempts to fetch and parse the target URL as a JSON API to find video links.

        Args:
            target: The captured target metadata.
            headers: Headers for the request.

        Returns:
            Optional[List[Dict]]: A list of yt-dlp compatible formats if found, else None.
        """
        try:
            console.print(f"[cyan]{lang.get('json_api_scan_start')}[/]")
            resp = requests.get(target["url"], headers=headers, timeout=10)
            
            try:
                data = resp.json()
            except json.JSONDecodeError:
                return None

            found_formats = []
            self._recursive_find_videos(data, found_formats)

            if found_formats:
                console.print(f"[green]{lang.get('json_api_scan_success', count=len(found_formats))}[/]")
                return found_formats
            
            return None

        except Exception as e:
            console.print(f"[dim red]{lang.get('json_api_scan_failed', error=e)}[/]")
            return None

    def analyze_and_select(
        self, target: Dict[str, Any]
    ) -> Tuple[Optional[Dict], Optional[str], Optional[Dict], str, str, bool]:
        """
        Analyzes the target stream using yt-dlp and handles format/subtitle selection.

        Args:
            target: The captured item.

        Returns:
            Tuple of selection data (format, audio_id, sub, embed_mode, cookie_file, force_mode).
        """
        # Cookie & Header generation
        c_file = ""
        try:
            c_file = create_cookie_file(
                target.get("cookies", ""), 
                target["url"],
                ref_url=target.get("page")
            )
        except Exception as e:
            console.print(f"[red]{lang.get('cookie_file_error', error=str(e))}[/]")

        headers = HeaderFactory.get_headers(
            target_url=target["url"],
            page_url=target.get("page", target["url"]),
            user_agent=target.get("agent", "Mozilla/5.0")
        )

        console.print(f"\n[magenta]{lang.get('analyzing')}[/]")

        # If it looks like an API, try to parse JSON directly first
        is_api = "api" in target.get("media_type", "") or "/api/" in target["url"]
        
        if is_api:
            json_formats = self._process_json_api(target, headers)
            if json_formats:
                # Bypass yt-dlp extraction and go straight to selection
                selected_fmt = self.selector.select_video_format(json_formats)
                
                if selected_fmt:
                    target["url"] = selected_fmt["url"]
                    # FORCE MODE = TRUE (Since we have a direct file URL now, we skip yt-dlp format selection)
                    return selected_fmt, None, None, "raw", c_file, True
                else:
                    return None, None, None, "cancel", "", False

        # --- STANDARD YT-DLP EXTRACTION ---
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "http_headers": headers,
            "cookiefile": c_file if c_file else None,
            "listsubtitles": True,
            "socket_timeout": 30,
            "allow_unplayable_formats": False, 
            "logger": None,
        }

        info = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target["url"], download=False)
        except Exception as e:
            console.print(f"[bold red]{lang.get('analysis_failed')}[/]: {e}")
            if Confirm.ask(f"[bold yellow]{lang.get('try_raw')}[/]", default=True):
                return None, None, None, "raw", c_file, True
            else:
                self._safe_delete(c_file)
                return None, None, None, "cancel", "", False

        if target.get("media_type") in ["stream_api", "embed"] or "embed" in target["url"]:
             console.print(Panel(
                 f"[yellow]{lang.get('api_stream_warning_body')}[/]", 
                 border_style="yellow",
                 title=lang.get("api_stream_warning_title")
             ))

        # Format Selection
        formats = info.get("formats", []) if info else []
        selected_fmt = self.selector.select_video_format(formats)
        force_mode = False
        if not selected_fmt:
            console.print(Panel(f"[yellow]{lang.get('auto_quality')}[/]", border_style="yellow"))
            force_mode = True

        # Audio Selection Logic
        selected_audio_id = None
        if selected_fmt:
            acodec = selected_fmt.get("acodec")
            # Check if video has no audio but other audio streams exist
            has_audio_options = any(
                f.get("vcodec") == "none" and f.get("acodec") != "none" for f in formats
            )
            should_prompt = (acodec == "none" and has_audio_options) or (
                has_audio_options and Confirm.ask(f"[cyan]{lang.get('select_audio')}[/]", default=False)
            )

            if should_prompt:
                audio_fmt = self.selector.select_audio_format(formats)
                if audio_fmt:
                    selected_audio_id = audio_fmt["format_id"]

        # Subtitle Logic
        subs_map = {}
        sub_idx = 1
        
        # 1. Internal Subtitles (from yt-dlp)
        if info and info.get("subtitles"):
            for curr_lang, sub_list in info["subtitles"].items():
                for s in sub_list:
                    subs_map[str(sub_idx)] = {
                        "type": "internal",
                        "lang": curr_lang,
                        "url": s["url"],
                        "ext": s["ext"],
                    }
                    sub_idx += 1

        # 2. External Subtitles
        sub_idx = self.subtitle_processor.process_subtitles(subs_map, sub_idx)

        selected_sub = None
        embed_mode = "none"

        if subs_map:
            self._render_subtitle_table(subs_map)
            if Confirm.ask(lang.get("download_subs"), default=True):
                s_choice = Prompt.ask(lang.get("choice"), choices=list(subs_map.keys()))
                selected_sub = subs_map[s_choice]
                
                console.print(lang.get("embed_mode_prompt"))
                m = Prompt.ask(lang.get("embed_mode_choice"), choices=["1", "2", "3", "4"], default="3")
                embed_mode = {
                    "1": "convert_srt", "2": "embed_mp4", "3": "embed_mkv", "4": "raw"
                }[m]

        return selected_fmt, selected_audio_id, selected_sub, embed_mode, c_file, force_mode

    def _render_subtitle_table(self, subs_map: Dict[str, Dict]) -> None:
        """Helper to render subtitles."""
        table = Table(title=lang.get("subtitles_title"), header_style="bold cyan")
        table.add_column(lang.get("table_id"), justify="center")
        table.add_column(lang.get("language"))
        table.add_column(lang.get("type"))
        
        for k, v in subs_map.items():
            table.add_row(k, v["lang"], v["ext"])
        console.print(table)

    def _safe_delete(self, filepath: Optional[str]) -> None:
        """Safely deletes a file."""
        if filepath and Path(filepath).exists():
            try:
                Path(filepath).unlink()
            except OSError:
                pass

    def run(self) -> None:
        """Main execution loop for Manual/Sync Mode."""
        c_file: Optional[str] = None
        try:
            target = self.wait_for_target_interactive()
            if target:
                default_title = target.get("title") or lang.get("default_filename_base")
                fname = self.file_manager.get_user_filename(default_title)
                
                fmt, audio_id, sub, mode, c_file, force = self.analyze_and_select(target)
                
                if mode == "cancel":
                    console.print(f"[yellow]{lang.get('cancelled')}[/]")
                    return

                if fmt or force:
                    success = self.download_manager.download_stream(
                        target, fmt, audio_id, sub, mode, c_file, fname, force
                    )
                    if success and Confirm.ask(f"{lang.get('create_technical_report')}", default=True):
                        self.report_generator.create_report(
                            fname, target["url"], format_info=fmt, subtitle_info=sub
                        )
                else:
                    console.print(f"[bold red]{lang.get('download_error', error=lang.get('init_failed'))}[/]")
            
        except KeyboardInterrupt:
            console.print(f"\n[red]{lang.get('cancelled')}[/]")
        except VantaError as ve:
             console.print(f"[bold red]{ve.message}[/]")
        except Exception as e:
            console.print(f"\n[bold red]{lang.get('critical_error')}[/]\n{e}")
            console.print(f"[dim]{traceback.format_exc()}[/]")
        finally:
            if c_file:
                self._safe_delete(c_file)
                console.print(f"[dim]{lang.get('cookies_deleted')}[/]")