import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict, Union, List, Tuple

import requests
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TimeElapsedColumn
)

from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


class StreamMerger:
    """
    Handles complex logic for merging video, multiple audio, and multiple subtitle streams using FFmpeg.
    Ensures safe process execution and accurate progress tracking.
    """

    @staticmethod
    def _parse_time_str(time_str: str) -> float:
        """
        Parses FFmpeg time string (HH:MM:SS.ms) into total seconds.
        Handles variances in FFmpeg output formatting.

        Args:
            time_str: Time string like '00:03:45.23'

        Returns:
            float: Total seconds.
        """
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
        except (ValueError, TypeError):
            pass
        return 0.0

    @staticmethod
    def process_external_sub_sync(
        subtitle_urls: List[Dict[str, str]],  # List of {url, lang, type}
        fname: str,
        mode: str,
        headers: Dict[str, str],
        video_ext: str,
        audio_files: List[Tuple[str, str]] = [], # List of (filepath, lang_code)
        # Backwards compatibility arg (deprecated but kept for safety if called old way)
        url: Optional[str] = None, 
    ) -> None:
        """
        Orchestrates the merging of external subtitles and multiple audio tracks.
        
        Args:
            subtitle_urls: List of dicts containing 'url', 'lang', 'ext'.
            fname: Base absolute filename path without extension.
            mode: Muxing mode ('embed_mp4', 'embed_mkv', etc.).
            headers: HTTP headers for secure requests.
            video_ext: Extension of the main video file.
            audio_files: List of tuples (audio_file_path, language_code).
            url: Legacy single URL support (merged into subtitle_urls if provided).
        """
        # --- 1. Consolidate Inputs ---
        if url:
            subtitle_urls.append({"url": url, "lang": "und", "ext": "vtt"})

        # Validate Audio Files
        valid_audio_files = []
        for a_path, a_lang in audio_files:
            p = Path(a_path)
            if p.exists() and ".part" not in p.name:
                valid_audio_files.append((a_path, a_lang))
            else:
                 console.print(f"[bold red]{lang.get('invalid_audio_file', audio_file=a_path)}[/]")

        if not subtitle_urls and not valid_audio_files:
            return

        console.print(f"[cyan]{lang.get('merging_multistream', video_count=1, audio_count=len(valid_audio_files), sub_count=len(subtitle_urls))}[/]")

        temp_files_to_clean: List[str] = []

        try:
            # --- 2. Subtitle Download Phase ---
            processed_subs: List[Tuple[str, str]] = [] # (filepath, lang)

            for sub_info in subtitle_urls:
                s_url = sub_info.get("url")
                s_lang = sub_info.get("lang", "und")
                s_ext = sub_info.get("ext", "vtt")
                
                if not s_url: continue
                
                try:
                    r = requests.get(s_url, headers=headers, timeout=15)
                    r.raise_for_status()
                    
                    # Create a distinct filename for each sub
                    raw_sub_path = f"{fname}.{s_lang}.{len(processed_subs)}.{s_ext}"
                    with open(raw_sub_path, "wb") as f:
                        f.write(r.content)
                    
                    temp_files_to_clean.append(raw_sub_path)
                    
                    # Convert VTT to SRT if embedding (better compatibility)
                    final_sub_path = raw_sub_path
                    if s_ext == "vtt":
                        srt_name = f"{fname}.{s_lang}.{len(processed_subs)}.srt"
                        subprocess.run(
                            ["ffmpeg", "-y", "-v", "quiet", "-i", raw_sub_path, srt_name], 
                            check=False
                        )
                        final_sub_path = srt_name
                        temp_files_to_clean.append(final_sub_path)
                    
                    processed_subs.append((final_sub_path, s_lang))

                except Exception as e:
                    console.print(f"[red]{lang.get('subtitle_download_failed', error=e)}[/]")

            # --- 3. File Discovery Phase (Main Video) ---
            video_file = Path(f"{fname}.{video_ext}")
            
            if not video_file.exists():
                # Fallback discovery logic
                f_path = Path(fname)
                search_dir = f_path.parent
                stem_name = f_path.name

                if search_dir.exists():
                    candidates = list(search_dir.glob(f"{stem_name}.*"))
                    # Exclude our known temp files
                    valid = [
                        f for f in candidates
                        if f.suffix not in [".json", ".srt", ".vtt", ".part", ".ytdl"]
                        and ".part" not in f.name
                        and str(f) not in [a[0] for a in valid_audio_files]
                        and str(f) not in temp_files_to_clean
                    ]
                    if valid:
                        video_file = max(valid, key=lambda p: p.stat().st_size)

            if not video_file.exists():
                console.print(f"[bold red]{lang.get('merge_video_not_found', path=video_file)}[/]")
                return

            # --- 4. FFmpeg Command Construction ---
            target_output_ext = "mkv" if "mkv" in mode else "mp4"
            output_file = Path(f"{fname}_final.{target_output_ext}")

            cmd = ["ffmpeg", "-y", "-i", str(video_file)]

            # Inputs: Audio
            for a_path, _ in valid_audio_files:
                cmd.extend(["-i", a_path])

            # Inputs: Subs
            for s_path, _ in processed_subs:
                cmd.extend(["-i", s_path])

            # Maps & Metadata
            # Input 0 is video.
            cmd.extend(["-map", "0:v"])
            
            # Map Audio (Starts at Input 1)
            current_input_idx = 1
            for i, (_, a_lang) in enumerate(valid_audio_files):
                cmd.extend(["-map", f"{current_input_idx}:a"])
                # Set Metadata: output stream a:i
                cmd.extend([f"-metadata:s:a:{i}", f"language={a_lang}"])
                cmd.extend([f"-metadata:s:a:{i}", f"title={a_lang.upper()} Audio"])
                current_input_idx += 1
            
            # Map Subs (Starts after Audio)
            for i, (_, s_lang) in enumerate(processed_subs):
                cmd.extend(["-map", f"{current_input_idx}:0"])
                # Set Metadata: output stream s:i
                cmd.extend([f"-metadata:s:s:{i}", f"language={s_lang}"])
                cmd.extend([f"-metadata:s:s:{i}", f"title={s_lang.upper()}"])
                current_input_idx += 1

            # Codecs
            if mode == "embed_mp4":
                cmd.extend([
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ac", "2",
                    "-c:s", "mov_text"
                ])
            elif mode == "embed_mkv":
                cmd.extend(["-c:v", "copy"])
                # Copy audio streams if possible, else convert
                cmd.extend(["-c:a", "copy"]) 
                cmd.extend(["-c:s", "srt"])
            else:
                # Raw muxing
                cmd.extend(["-c:v", "copy", "-c:a", "copy", "-c:s", "copy"])

            cmd.append(str(output_file))
            
            # Compatibility flags
            cmd.insert(1, "-strict")
            cmd.insert(2, "experimental")
            cmd.insert(3, "-v")
            cmd.insert(4, "info") 

            # --- 5. Execution & Monitoring ---
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace'
            )

            # Regex for progress parsing
            duration_pattern = re.compile(r"Duration:\s*(\d{2}:\d{2}:\d{2}\.\d+)")
            time_pattern = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d+)")

            total_duration_secs: Optional[float] = None
            log_buffer: List[str] = []

            with Progress(
                SpinnerColumn("dots", style="bold magenta"),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(bar_width=None, style="dim white", complete_style="bold green"),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                "•", TimeElapsedColumn(), "•", TimeRemainingColumn(),
                console=console
            ) as progress:
                
                task_id = progress.add_task(f"[yellow]{lang.get('ffmpeg_processing')}[/]", total=None)

                if process.stdout:
                    for line in process.stdout:
                        log_buffer.append(line)
                        if len(log_buffer) > 20: 
                            log_buffer.pop(0)

                        line = line.strip()
                        if total_duration_secs is None:
                            d_match = duration_pattern.search(line)
                            if d_match:
                                total_duration_secs = StreamMerger._parse_time_str(d_match.group(1))
                                if total_duration_secs > 0:
                                    progress.update(task_id, total=total_duration_secs)

                        if total_duration_secs:
                            t_match = time_pattern.search(line)
                            if t_match:
                                current_secs = StreamMerger._parse_time_str(t_match.group(1))
                                progress.update(task_id, completed=current_secs)
            
            return_code = process.wait()

            # --- 6. Final Cleanup ---
            if return_code == 0 and output_file.exists() and output_file.stat().st_size > 0:
                StreamMerger._safe_unlink(video_file)
                # Cleanup all audio inputs
                for a_path, _ in valid_audio_files:
                    StreamMerger._safe_unlink(a_path)
                
                # Cleanup downloaded sub files
                for tmp_f in temp_files_to_clean:
                    StreamMerger._safe_unlink(tmp_f)
                
                final_path = Path(f"{fname}.{target_output_ext}")
                StreamMerger._safe_unlink(final_path)
                
                output_file.rename(final_path)
                console.print(f"[bold green]{lang.get('muxing_complete', filename=final_path.name)}[/]")
            else:
                console.print(f"[bold red]{lang.get('muxing_error')}[/]")
                if log_buffer:
                    console.print(f"[dim]{lang.get('last_log_label', log=log_buffer[-1])}[/]")

        except Exception as e:
            console.print(f"[red]{lang.get('merge_error', error=str(e))}[/]")

    @staticmethod
    def _safe_unlink(path: Union[Path, str, None]) -> None:
        """Helper to safely delete files suppressing errors."""
        if path:
            try:
                p = Path(path)
                if p.exists():
                    p.unlink()
            except OSError:
                pass