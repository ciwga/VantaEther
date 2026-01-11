import sys
import time
import requests
import threading
import traceback
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, Any, Tuple, List, Set

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
from vantaether.utils.file_manager import FileManager
from vantaether.core.downloader import DownloadManager
from vantaether.utils.cookies import create_cookie_file
from vantaether.utils.header_factory import HeaderFactory
from vantaether.server.app import VantaServer, CaptureManager
from vantaether.utils.report_generator import ReportGenerator
from vantaether.utils.system import check_systems, clear_screen


console = Console()
lang = LanguageManager()


class VantaEngine:
    """
    Main engine class for managing the UI, stream selection, cookie handling,
    and download execution.

    Orchestrates the interaction between the Flask Server (CaptureManager),
    the User Interface (Rich), and the Downloader (yt-dlp).
    """

    def __init__(self, enable_console: bool = False) -> None:
        """
        Initialize the Engine, checking systems and setting up components.
        Establishes the Dependency Injection container behavior.
        """
        clear_screen()
        console.print(Align.center(config.BANNER), style="bold magenta")
        self.analyzer = MediaAnalyzer()
        
        self.enable_console = enable_console
        
        try:
            check_systems()
        except Exception:
            console.print(Panel(lang.get("ffmpeg_not_found"), style="bold red"))

        self.download_manager = DownloadManager()
        self.file_manager = self.download_manager.file_manager
        self.report_generator = self.download_manager.report_generator
        self.selector = FormatSelector()
        self.capture_manager = CaptureManager()

    def wait_for_target_interactive(self) -> Optional[Dict[str, Any]]:
        """
        Displays an interactive table of captured streams and handles user input.
        Starts the Server in a daemon thread, injecting the CaptureManager.

        Returns:
            Optional[Dict[str, Any]]: The selected target video object or None.
        """
        
        step1_desc = lang.get('manual_step_1_desc', url=config.SERVER_URL)
        # Indent subsequent lines by 3 spaces to match the f-string padding
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

        # Inject capture_manager into the server explicitly
        server = VantaServer(capture_manager=self.capture_manager)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        
        if not self.enable_console:
            if Confirm.ask(f"[bold yellow]{lang.get('ask_enable_console')}[/]", default=False):
                self.enable_console = True
                console.print(f"[green]✔ {lang.get('listen_console')}[/]")
            else:
                console.print(f"[dim]{lang.get('console_disabled')}[/]")

        selected_target: Optional[Dict[str, Any]] = None
        seen_logs: Set[str] = set()
        
        last_item_count = -1

        try:
            while True:
                with console.status(
                    f"[bold yellow]{lang.get('waiting_signal')}[/] [dim]({lang.get('listen_console') if self.enable_console else lang.get('silent_mode')})[/]",
                    spinner="earth",
                ) as status:
                    while True:
                        has_new_data = self.capture_manager.wait_for_item(timeout=1.0)
                        
                        if has_new_data or self.enable_console:
                            snapshot = self.capture_manager.get_snapshot()
                            raw_videos = snapshot.get("videos", [])
                            
                            real_videos = []
                            new_logs = []
                            
                            for v in raw_videos:
                                if v.get("source") == "REMOTE_LOG":
                                    if self.enable_console:
                                        msg_id = f"{v.get('title')}:{v.get('url')}"
                                        if msg_id not in seen_logs:
                                            new_logs.append(v)
                                            seen_logs.add(msg_id)
                                else:
                                    real_videos.append(v)
                            
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

                            current_count = len(real_videos)
                            if current_count > 0 and current_count > last_item_count:
                                break

                clear_screen()
                console.print(Align.center(config.BANNER), style="bold magenta")

                table = Table(title=lang.get("captured_streams_title"), show_lines=True)
                table.add_column(lang.get("table_id"), style="cyan", justify="center")
                table.add_column(lang.get("source_type"), style="magenta")
                table.add_column(lang.get("url_short"), style="green")

                display_pool = self.capture_manager.get_snapshot()
                all_items = display_pool["videos"]
                
                valid_videos = [v for v in all_items if v.get("source") != "REMOTE_LOG"]
                
                last_item_count = len(valid_videos)

                for idx, vid in enumerate(valid_videos, 1):
                    u = vid["url"]
                    source = vid.get("source", lang.get("unknown"))
                    
                    t_type = vid.get("media_type", "")

                    ftype = source
                    if "master" in u:
                        ftype += f" [bold yellow]{lang.get('master_suffix')}[/]"
                    elif "manifest" in t_type or "m3u8" in u:
                        ftype += lang.get("stream_suffix")
                    elif "api" in t_type or "embed" in u:
                        ftype += f" [bold yellow]{lang.get('api_embed_suffix')}[/]"
                    elif "mp4" in u:
                        ftype += lang.get("mp4_suffix")

                    # Smart URL Display Logic: Show last 2 path segments instead of beginning
                    # This provides better context (e.g., filename/folder) than the domain.
                    display_url: str = u
                    try:
                        parsed_url = urlparse(u)
                        # Filter out empty strings from split (e.g., from leading/trailing slashes)
                        path_segments: List[str] = [p for p in parsed_url.path.split('/') if p]
                        
                        if len(path_segments) >= 2:
                            # Join the last two segments (e.g. folder/filename.ext)
                            display_url = f".../{'/'.join(path_segments[-2:])}"
                        elif len(path_segments) == 1:
                            display_url = f".../{path_segments[0]}"
                        else:
                            # Fallback if no path segments found (e.g. root domain)
                            display_url = u[:70] + "..." if len(u) > 70 else u
                    except Exception:
                        # Fallback to original truncation on parsing error
                        display_url = u[:70] + "..." if len(u) > 70 else u

                    table.add_row(str(idx), ftype, display_url)

                console.print(table)
                console.print(
                    f"\n[dim]{lang.get('video_count', video_count=len(valid_videos), sub_count=len(display_pool['subs']))}[/]"
                )
                console.print(f"[bold yellow]{lang.get('options')}[/]")
                console.print(f"  [bold white]<ID>[/] : {lang.get('enter_id')}")
                console.print(f"  [bold white]r[/]    : {lang.get('refresh')}")
                console.print(f"  [bold red]c[/]    : {lang.get('clear_list')}")
                if self.enable_console:
                    console.print(f"  [dim white]{lang.get('logs_background_hint')}[/]")

                choice = Prompt.ask(f"\n[bold cyan]{lang.get('command_prompt')}[/]", default="r")

                if choice.lower() == "r":
                    last_item_count = -1
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
                        time.sleep(2)
                    continue

                if choice.isdigit():
                    idx = int(choice)
                    if 1 <= idx <= len(valid_videos):
                        selected_target = valid_videos[idx - 1]
                        console.print(lang.get("selected", url=selected_target['url']))
                        break
                    else:
                        console.print(f"[bold red]{lang.get('invalid_id')}[/]")
                        time.sleep(1)
        except KeyboardInterrupt:
            console.print(f"\n[red]{lang.get('cancelled')}[/]")
            sys.exit(0)

        return selected_target

    def analyze_and_select(
        self, target: Dict[str, Any]
    ) -> Tuple[Any, Optional[str], Any, str, str, bool]:
        """
        Analyzes target using yt-dlp and prompts user for quality.
        
        Returns:
            Tuple: (format, audio_id, subtitle, embed_mode, cookie_path, force_mode)
        """
        c_file = create_cookie_file(
            target.get("cookies", ""), 
            target["url"],
            ref_url=target.get("page")
        )

        # Use centralized factory for consistency
        headers = HeaderFactory.get_headers(
            target_url=target["url"],
            page_url=target.get("page", target["url"]),
            user_agent=target.get("agent", "Mozilla/5.0")
        )

        console.print(f"\n[magenta]{lang.get('analyzing')}[/]")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "http_headers": headers,
            "cookiefile": c_file,
            "listsubtitles": True,
            "socket_timeout": 30,
            "allow_unplayable_formats": True, 
            "logger": None,
        }

        info = None
        force_mode = False

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target["url"], download=False)
        except Exception as e:
            console.print(f"[bold red]{lang.get('analysis_failed')}[/]\n[dim]{str(e)[:150]}...[/]")
            
            if Confirm.ask(
                f"[bold yellow]{lang.get('try_raw')}[/]",
                default=True,
            ):
                return None, None, None, "raw", c_file, True
            else:
                # Cleanup and signal cancellation
                if c_file and Path(c_file).exists():
                    try:
                        Path(c_file).unlink()
                    except OSError:
                        pass
                
                return None, None, None, "cancel", "", False 

        if target.get("media_type") in ["stream_api", "embed"] or "embed" in target["url"]:
             console.print(
                 Panel(
                     f"[yellow]{lang.get('api_stream_warning_body')}[/]", 
                     border_style="yellow",
                     title=lang.get("api_stream_warning_title")
                 )
             )

        formats = info.get("formats", [])
        selected_fmt = self.selector.select_video_format(formats)

        if not selected_fmt:
            console.print(
                Panel(
                    f"[yellow]{lang.get('auto_quality')}[/]", border_style="yellow"
                )
            )
            force_mode = True

        selected_audio_id = None
        if selected_fmt:
            acodec = selected_fmt.get("acodec")
            needs_audio = acodec is None or acodec == "none"
            
            has_audio_options = any(
                f.get("vcodec") == "none" and f.get("acodec") != "none" 
                for f in formats
            )

            should_prompt = False
            if needs_audio and has_audio_options:
                should_prompt = True
            elif has_audio_options:
                if Confirm.ask(f"[cyan]{lang.get('select_audio')}[/]", default=False):
                    should_prompt = True
            
            if should_prompt:
                audio_fmt = self.selector.select_audio_format(formats)
                if audio_fmt:
                    selected_audio_id = audio_fmt["format_id"]

        subs_map = {}
        sub_idx = 1
        
        if "subtitles" in info and info["subtitles"]:
            for curr_lang, sub_list in info["subtitles"].items():
                for s in sub_list:
                    subs_map[str(sub_idx)] = {
                        "type": "internal",
                        "lang": curr_lang,
                        "url": s["url"],
                        "ext": s["ext"],
                    }
                    sub_idx += 1

        pool = self.capture_manager.get_snapshot()
        for s_data in pool["subs"]:
            url = s_data["url"]
            s_lang = "tr" if "tr" in url or "tur" in url else "en"
            subs_map[str(sub_idx)] = {
                "type": "external",
                "lang": f"{s_lang} (Ext)",
                "url": url,
                "ext": "vtt" if "vtt" in url else "srt",
            }
            sub_idx += 1

        selected_sub = None
        embed_mode = "none"

        if subs_map:
            table = Table(title=lang.get("subtitles_title"), header_style="bold cyan")
            table.add_column(lang.get("table_id"), justify="center")
            table.add_column(lang.get("language"))
            table.add_column(lang.get("type"))
            
            for k, v in subs_map.items():
                table.add_row(k, v["lang"], v["ext"])
            console.print(table)

            if Confirm.ask(lang.get("download_subs"), default=True):
                s_choice = Prompt.ask(lang.get("choice"), choices=list(subs_map.keys()))
                selected_sub = subs_map[s_choice]

                console.print(lang.get("embed_mode_prompt"))
                m = Prompt.ask(lang.get("embed_mode_choice"), choices=["1", "2", "3", "4"], default="3")
                embed_mode = {
                    "1": "convert_srt",
                    "2": "embed_mp4",
                    "3": "embed_mkv",
                    "4": "raw",
                }[m]

        return selected_fmt, selected_audio_id, selected_sub, embed_mode, c_file, force_mode

    def run(self) -> None:
        """
        Main execution loop for Manual/Sync Mode.
        """
        c_file: Optional[str] = None
        
        try:
            target = self.wait_for_target_interactive()
            if target:
                fname = self.file_manager.get_user_filename(target.get("title", lang.get("default_filename_base")))
                
                fmt, audio_id, sub, mode, c_file, force = self.analyze_and_select(
                    target
                )
                
                if mode == "cancel":
                    console.print(f"[yellow]{lang.get('cancelled')}[/]")
                    return

                if fmt or force:
                    success = self.download_manager.download_stream(
                        target, fmt, audio_id, sub, mode, c_file, fname, force
                    )
                    
                    if success:
                         if Confirm.ask(f"{lang.get('create_technical_report')}", default=True):
                            self.report_generator.create_report(
                                fname, 
                                target["url"], 
                                format_info=fmt, 
                                subtitle_info=sub
                            )
                else:
                    console.print(f"[bold red]{lang.get('download_error', error=lang.get('init_failed'))}[/]")
            
        except Exception as e:
            console.print(f"\n[bold red]{lang.get('critical_error')}[/]\n{e}")
            traceback.print_exc()
        finally:
            if c_file and Path(c_file).exists():
                try:
                    Path(c_file).unlink()
                    console.print(f"[dim]{lang.get('cookies_deleted')}[/]")
                except OSError:
                    pass