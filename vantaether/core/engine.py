import threading
import sys
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.align import Align

from vantaether.config import BANNER
from vantaether.utils.i18n import LanguageManager
from vantaether.core.analyzer import MediaAnalyzer
from vantaether.core.selector import FormatSelector
from vantaether.utils.file_manager import FileManager
from vantaether.core.downloader import DownloadManager
from vantaether.utils.cookies import create_cookie_file
from vantaether.server.app import VantaServer, CaptureManager
from vantaether.utils.report_generator import ReportGenerator
from vantaether.utils.system import check_systems, clear_screen


console = Console()
lang = LanguageManager()


class VantaEngine:
    """
    Main engine class for managing the UI, stream selection, cookie handling,
    and download execution.
    """

    def __init__(self) -> None:
        """
        Initialize the Engine, checking systems and setting up components.
        Establishes the Dependency Injection container behavior.
        """
        clear_screen()
        console.print(Align.center(BANNER), style="bold magenta")
        self.analyzer = MediaAnalyzer()
        
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
        Displays an interactive table of captured streams.
        Starts the Server in a daemon thread, injecting the CaptureManager.
        
        Returns:
            Optional[Dict[str, Any]]: The selected video target object or None.
        """
        console.print(
            Panel(
                f"[bold white]{lang.get('manual_step_1')}[/]\n"
                f"   [dim]{lang.get('manual_step_1_desc')}[/]\n\n"
                f"[bold white]{lang.get('manual_step_2')}[/]\n"
                f"   [dim]{lang.get('manual_step_2_desc')}[/]",
                title="MANUAL SYNC MODE",
                border_style="magenta",
                expand=False,
            )
        )

        # Inject capture_manager into the server explicitly
        server = VantaServer(capture_manager=self.capture_manager)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()

        selected_target = None

        try:
            while True:
                # Optimized waiting loop using threading.Event in CaptureManager
                with console.status(
                    f"[bold yellow]{lang.get('waiting_signal')}[/]",
                    spinner="earth",
                ):
                    while True:
                        current_status = self.capture_manager.get_status()
                        if current_status["video_count"] > 0:
                            break
                        # Efficient blocking wait
                        self.capture_manager.wait_for_item(timeout=1.0)

                clear_screen()
                console.print(Align.center(BANNER), style="bold magenta")

                table = Table(title=lang.get("captured_streams_title"), show_lines=True)
                table.add_column(lang.get("table_id"), style="cyan", justify="center")
                table.add_column(lang.get("source_type"), style="magenta")
                table.add_column(lang.get("url_short"), style="green")

                # Get thread-safe snapshot
                display_pool = self.capture_manager.get_snapshot()
                current_videos = list(display_pool["videos"])

                for idx, vid in enumerate(current_videos, 1):
                    u = vid["url"]
                    source = vid.get("source", lang.get("unknown"))

                    ftype = source
                    if "master" in u:
                        ftype += " [bold yellow](MASTER)[/]"
                    elif "m3u8" in u:
                        ftype += " (HLS)"
                    elif "mp4" in u:
                        ftype += " (MP4)"

                    display_url = u[:70] + "..." if len(u) > 70 else u
                    table.add_row(str(idx), ftype, display_url)

                console.print(table)
                console.print(
                    f"\n[dim]{lang.get('video_count', video_count=len(current_videos), sub_count=len(display_pool['subs']))}[/]"
                )
                console.print(f"[bold yellow]{lang.get('options')}[/]")
                console.print(f"  [bold white]{lang.get('enter_id')}[/]")
                console.print(f"  [bold white]{lang.get('refresh')}[/]")

                choice = Prompt.ask(f"\n[bold cyan]{lang.get('command_prompt')}[/]", default="r")

                if choice.lower() == "r":
                    continue

                if choice.isdigit():
                    idx = int(choice)
                    if 1 <= idx <= len(current_videos):
                        selected_target = current_videos[idx - 1]
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
        Analyzes target using yt-dlp and prompts user for quality, audio, and subtitle selection.

        Args:
            target: The target video dictionary containing URL and cookies.
            
        Returns:
            Tuple: (format, audio_id, subtitle, embed_mode, cookie_path, force_mode)
        """
        # Create a temporary Netscape cookie file for yt-dlp authentication
        c_file = create_cookie_file(target.get("cookies", ""), target["url"])

        headers = {
            "User-Agent": target.get("agent", "Mozilla/5.0"),
            "Referer": target.get("page", target["url"]),
            "Origin": "/".join(target.get("page", "").split("/")[:3]),
            "Accept": "*/*",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "X-Requested-With": "XMLHttpRequest",
        }

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
                if Path(c_file).exists():
                    try:
                        Path(c_file).unlink()
                    except OSError:
                        pass
                
                # Retry logic: Go back to list
                new_target = self.wait_for_target_interactive()
                if new_target:
                     return self.analyze_and_select(new_target)
                return None, None, None, "raw", "", False 

        # --- Quality Selection ---
        formats = info.get("formats", [])
        
        # Use the centralized FormatSelector instead of manual table logic
        selected_fmt = self.selector.select_video_format(formats)

        if not selected_fmt:
            console.print(
                Panel(
                    f"[yellow]{lang.get('auto_quality')}[/]", border_style="yellow"
                )
            )
            force_mode = True

        # --- Audio Selection ---
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
                # If video has audio but user might want to override
                if Confirm.ask(f"[cyan]{lang.get('select_audio')}[/]", default=False):
                    should_prompt = True
            
            if should_prompt:
                audio_fmt = self.selector.select_audio_format(formats)
                if audio_fmt:
                    selected_audio_id = audio_fmt["format_id"]

        # --- Subtitle Selection ---
        subs_map = {}
        sub_idx = 1
        
        # 1. Internal Subtitles (from yt-dlp info)
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

        # 2. External Subtitles (Captured via Browser)
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
        Coordinates the entire flow from selection to download and reporting.
        """
        c_file: Optional[str] = None
        
        try:
            target = self.wait_for_target_interactive()
            if target:
                fname = self.file_manager.get_user_filename(target.get("title", "video"))
                
                fmt, audio_id, sub, mode, c_file, force = self.analyze_and_select(
                    target
                )
                
                if fmt or force:
                    self.download_manager.download_stream(
                        target, fmt, audio_id, sub, mode, c_file, fname, force
                    )
                    
                    if Confirm.ask(f"{lang.get('create_technical_report')}", default=False):
                        self.report_generator.create_report(
                            fname, 
                            target["url"], 
                            format_info=fmt, 
                            subtitle_info=sub
                        )
                else:
                    console.print(f"[bold red]{lang.get('download_error', error='Init failed')}[/]")
            
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