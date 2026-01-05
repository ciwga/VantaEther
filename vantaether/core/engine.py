import re
import os
import sys
import time
import json
import threading
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.align import Align

from vantaether.config import BANNER
from vantaether.utils.i18n import LanguageManager
from vantaether.core.downloader import Downloader
from vantaether.core.analyzer import MediaAnalyzer
from vantaether.utils.cookies import create_cookie_file
from vantaether.server.app import VantaServer, get_pool
from vantaether.utils.system import check_systems, clear_screen


console = Console()
lang = LanguageManager()


class VantaEngine:
    """
    Main engine class for managing the UI, stream selection, cookie handling,
    and download execution.
    """

    def __init__(self) -> None:
        clear_screen()
        console.print(Align.center(BANNER), style="bold magenta")
        self.analyzer = MediaAnalyzer()
        try:
            check_systems()
        except Exception:
            console.print(Panel(lang.get("ffmpeg_not_found"), style="bold red"))

        self.downloader = Downloader()
        self.download_path = self.downloader.download_path
        
    def wait_for_target_interactive(self) -> Optional[Dict[str, Any]]:
        """
        Displays an interactive table of captured streams.
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

        server = VantaServer()
        t = threading.Thread(target=server.run, daemon=True)
        t.start()

        pool = get_pool()
        selected_target = None

        try:
            while True:
                with console.status(
                    f"[bold yellow]{lang.get('waiting_signal')}[/]",
                    spinner="earth",
                ):
                    while True:
                        with pool["lock"]:
                            if len(pool["videos"]) > 0:
                                break
                        time.sleep(0.5)

                clear_screen()
                console.print(Align.center(BANNER), style="bold magenta")

                table = Table(title=lang.get("captured_streams_title"), show_lines=True)
                table.add_column("ID", style="cyan", justify="center")
                table.add_column(lang.get("source_type"), style="magenta")
                table.add_column(lang.get("url_short"), style="green")

                current_videos = []
                with pool["lock"]:
                    current_videos = list(pool["videos"])

                for idx, vid in enumerate(current_videos, 1):
                    u = vid["url"]
                    source = vid.get("source", "Unknown")

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
                    f"\n[dim]{lang.get('video_count', video_count=len(current_videos), sub_count=len(pool['subs']))}[/]"
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
        """Analyzes target and prompts user for quality selection."""
        c_file = create_cookie_file(target["cookies"], target["url"])

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
                    Path(c_file).unlink()
                return self.analyze_and_select(self.wait_for_target_interactive())

        # Quality Selection
        formats = info.get("formats", [])
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

        selected_fmt = None

        if unique_fmts:
            table = Table(title=lang.get("quality_options"), header_style="bold magenta")
            
            # Using no_wrap=True for critical columns
            table.add_column("ID", justify="center", no_wrap=True)
            table.add_column(lang.get("resolution"), no_wrap=True)
            table.add_column("Bitrate", no_wrap=True)
            # Codec with overflow protection
            table.add_column(lang.get("codec"), no_wrap=True, overflow="ellipsis", max_width=10)
            table.add_column(lang.get("audio_status"), style="cyan")

            for idx, f in enumerate(unique_fmts, 1):
                audio_status = (
                    lang.get("exists")
                    if f.get("acodec") != "none" and f.get("acodec") is not None
                    else lang.get("video_only")
                )
                # Extract codec
                vcodec = f.get("vcodec", "unknown")
                if vcodec == "none":
                    vcodec = "images"

                table.add_row(
                    str(idx),
                    f"{f.get('height')}p",
                    f"{int(f.get('tbr', 0) or 0)}k",
                    vcodec,
                    audio_status,
                )
            console.print(table)
            choice = Prompt.ask(
                lang.get("choice"),
                choices=[str(i) for i in range(1, len(unique_fmts) + 1)],
                default="1",
            )
            selected_fmt = unique_fmts[int(choice) - 1]
        else:
            console.print(
                Panel(
                    f"[yellow]{lang.get('auto_quality')}[/]", border_style="yellow"
                )
            )
            force_mode = True

        # Audio Selection
        selected_audio_id = None
        selected_is_silent = False

        if selected_fmt:
            acodec = selected_fmt.get("acodec")
            selected_is_silent = acodec is None or acodec == "none"

        audio_formats = [
            f
            for f in formats
            if (f.get("vcodec") == "none" or f.get("vcodec") is None)
            and f.get("acodec") != "none"
        ]

        if len(audio_formats) > 0:
            should_show_table = False
            if selected_is_silent:
                should_show_table = True
            elif len(audio_formats) > 1:
                should_show_table = Confirm.ask(
                    f"[cyan]{lang.get('select_audio')}[/]",
                    default=False,
                )

            if should_show_table:
                unique_audios = []
                seen_audio = set()
                for af in audio_formats:
                    aud_id = af.get("format_id")
                    if aud_id not in seen_audio:
                        unique_audios.append(af)
                        seen_audio.add(aud_id)

                if unique_audios:
                    table = Table(title=lang.get("audio_sources"), header_style="bold yellow")
                    table.add_column("ID", justify="center", no_wrap=True)
                    table.add_column("Format ID", no_wrap=True)
                    # Audio Codec with overflow protection
                    table.add_column(lang.get("codec"), no_wrap=True, overflow="ellipsis", max_width=10)
                    table.add_column(lang.get("language") + " / Note")
                    table.add_column("Bitrate", no_wrap=True)

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
                    choice = Prompt.ask(
                        lang.get("audio_choice"),
                        choices=[str(i) for i in range(1, len(unique_audios) + 1)],
                        default="1",
                    )
                    selected_audio_id = unique_audios[int(choice) - 1]["format_id"]

        # Subtitle Selection
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

        pool = get_pool()
        with pool["lock"]:
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
            table.add_column("ID")
            table.add_column(lang.get("language"))
            table.add_column("Type")
            for k, v in subs_map.items():
                table.add_row(k, v["lang"], v["ext"])
            console.print(table)

            if Confirm.ask(lang.get("download_subs"), default=True):
                s_choice = Prompt.ask("Selection", choices=list(subs_map.keys()))
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

    def get_filename(self, target: Dict[str, Any]) -> str:
        """Determines the output filename (without path)."""
        default_name = re.sub(
            r'[<>:"/\\|?*]', "", target.get("title", "video")
        ).strip()[:50]
        if not default_name or default_name == "cyber_media":
            default_name = "video_download"

        console.print(f"\n[dim]{lang.get('filename_detected', name=default_name)}[/]")
        user_name = Prompt.ask(
            lang.get("filename_prompt"), default=default_name
        )
        return user_name.strip()

    def create_pro_log(self, filename_base: str, fmt: Any, sub: Any, url: str) -> None:
        """
        Generates a JSON report in the universal download directory.
        
        Args:
            filename_base (str): The filename chosen by user (no path).
            fmt (Any): The format object.
            sub (Any): The subtitle object.
            url (str): Source URL.
        """
        try:
            media_info = {}
            target_path = None
            
            # Check for file existence in the correct directory
            possible_exts = [".mp4", ".mkv", ".webm"]
            for ext in possible_exts:
                candidate = self.download_path / f"{filename_base}{ext}"
                if candidate.exists():
                    target_path = candidate
                    break
            
            if target_path and self.analyzer:
                media_info = self.analyzer.get_media_info(str(target_path))

            log_data = {
                "timestamp": str(datetime.now()),
                "source": url,
                "storage_path": str(self.download_path),
                "media_info": media_info,
                "options": {
                    "quality": fmt.get("format_id") if fmt else "Raw",
                    "subtitle": sub,
                },
            }
            
            report_file = self.download_path / f"{filename_base}_REPORT.json"
            
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=4)
            console.print(f"[green]{lang.get('report_created', path=str(report_file))}[/]")
        except Exception as e:
            console.print(f"[red]{lang.get('report_failed', error=str(e))}[/]")

    def run(self) -> None:
        """Main execution loop for Manual/Sync Mode."""
        try:
            target = self.wait_for_target_interactive()
            if target:
                fname = self.get_filename(target)
                fmt, audio_id, sub, mode, c_file, force = self.analyze_and_select(
                    target
                )
                if fmt or force:
                    # Pass the filename (not path) to downloader, it handles the path now
                    self.downloader.download_stream(
                        target, fmt, audio_id, sub, mode, c_file, fname, force
                    )
                    
                    if Confirm.ask("Create technical report?", default=False):
                        self.create_pro_log(fname, fmt, sub, target["url"])
                else:
                    console.print(f"[bold red]{lang.get('download_error', error='Init failed')}[/]")
            
            if c_file and Path(c_file).exists():
                Path(c_file).unlink()

        except Exception as e:
            console.print(f"\n[bold red]{lang.get('critical_error')}[/]\n{e}")
            traceback.print_exc()