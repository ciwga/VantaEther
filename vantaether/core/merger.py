import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict, Union, List

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
    Handles complex logic for merging video, audio, and subtitle streams using FFmpeg.
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
        url: Optional[str],
        fname: str,
        mode: str,
        headers: Dict[str, str],
        video_ext: str,
        audio_file: Optional[Union[Path, str]] = None,
    ) -> None:
        """
        Orchestrates the merging of external subtitles and/or orphaned audio files.
        
        Args:
            url: URL of the subtitle file (optional).
            fname: Base absolute filename path without extension.
            mode: Muxing mode ('embed_mp4', 'embed_mkv', etc.).
            headers: HTTP headers for secure requests.
            video_ext: Extension of the main video file.
            audio_file: Path to the separate audio file (optional).
        """
        if audio_file:
            audio_file = Path(audio_file)
            if ".part" in audio_file.name or not audio_file.exists():
                console.print(f"[bold red]{lang.get('invalid_audio_file', audio_file=audio_file)}[/]")
                audio_file = None

        if url:
            console.print(f"[cyan]{lang.get('download_external_sub')}[/]")
        elif audio_file:
            console.print(f"[cyan]{lang.get('manual_muxing')}[/]")

        final_sub: Optional[str] = None

        try:
            # 1. Subtitle Download Phase
            if url:
                try:
                    r = requests.get(url, headers=headers, timeout=15)
                    r.raise_for_status()
                    
                    ext = "vtt" if ".vtt" in url else "srt"
                    raw_sub_path = f"{fname}_ext.{ext}"
                    
                    with open(raw_sub_path, "wb") as f:
                        f.write(r.content)
                    
                    final_sub = raw_sub_path
                    
                    if ext == "vtt":
                        srt_name = f"{fname}.srt"
                        subprocess.run(
                            ["ffmpeg", "-y", "-v", "quiet", "-i", raw_sub_path, srt_name], 
                            check=False
                        )
                        final_sub = srt_name
                        StreamMerger._safe_unlink(raw_sub_path)
                        
                except Exception as e:
                    console.print(f"[red]{lang.get('subtitle_download_failed', error=e)}[/]")

            # 2. File Discovery Phase
            video_file = Path(f"{fname}.{video_ext}")
            
            # Fallback discovery if exact match fails
            if not video_file.exists():
                f_path = Path(fname)
                search_dir = f_path.parent
                stem_name = f_path.name

                if search_dir.exists():
                    candidates = list(search_dir.glob(f"{stem_name}.*"))
                    valid = [
                        f for f in candidates
                        if f.suffix not in [".json", ".srt", ".vtt", ".part", ".ytdl"]
                        and ".part" not in f.name
                        and ".audio." not in f.name 
                        and f != audio_file
                    ]
                    if valid:
                        video_file = max(valid, key=lambda p: p.stat().st_size)

            if not video_file.exists():
                console.print(f"[bold red]{lang.get('merge_video_not_found', path=video_file)}[/]")
                return

            # 3. FFmpeg Command Construction
            target_output_ext = "mkv" if "mkv" in mode else "mp4"
            output_file = Path(f"{fname}_final.{target_output_ext}")

            cmd = ["ffmpeg", "-y", "-i", str(video_file)]

            if audio_file:
                cmd.extend(["-i", str(audio_file)])

            if final_sub:
                cmd.extend(["-i", final_sub])

            # Stream Mapping
            cmd.extend(["-map", "0:v"])  # Always map video from first input

            if audio_file:
                cmd.extend(["-map", "1:a?"]) # Audio from second input
            else:
                cmd.extend(["-map", "0:a?"]) # Audio from first input

            if final_sub:
                sub_input_idx = "2" if audio_file else "1"
                cmd.extend(["-map", f"{sub_input_idx}:0"])

            # Encoding Options
            if mode == "embed_mp4":
                cmd.extend([
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ac", "2",
                    "-c:s", "mov_text"
                ])
            elif mode == "embed_mkv":
                cmd.extend(["-c:v", "copy"])
                # Re-encode audio to AAC if merging separate file, else copy
                if audio_file:
                    cmd.extend(["-c:a", "aac"]) 
                else:
                    cmd.extend(["-c:a", "copy"])
                cmd.extend(["-c:s", "srt"])
            else:
                cmd.extend(["-c:v", "copy", "-c:a", "copy"])

            cmd.append(str(output_file))
            
            # Compatibility flags
            cmd.insert(1, "-strict")
            cmd.insert(2, "experimental")
            cmd.insert(3, "-v")
            cmd.insert(4, "info") # Needed to parse progress

            # 4. Execution & Progress Monitoring
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
                        
                        # Capture Duration
                        if total_duration_secs is None:
                            d_match = duration_pattern.search(line)
                            if d_match:
                                total_duration_secs = StreamMerger._parse_time_str(d_match.group(1))
                                if total_duration_secs > 0:
                                    progress.update(task_id, total=total_duration_secs)

                        # Capture Progress
                        if total_duration_secs:
                            t_match = time_pattern.search(line)
                            if t_match:
                                current_secs = StreamMerger._parse_time_str(t_match.group(1))
                                progress.update(task_id, completed=current_secs)
            
            return_code = process.wait()

            # 5. Cleanup Phase
            if return_code == 0 and output_file.exists() and output_file.stat().st_size > 0:
                StreamMerger._safe_unlink(video_file)
                StreamMerger._safe_unlink(audio_file)
                
                final_path = Path(f"{fname}.{target_output_ext}")
                StreamMerger._safe_unlink(final_path)
                
                output_file.rename(final_path)
                StreamMerger._safe_unlink(final_sub)

                console.print(f"[bold green]{lang.get('muxing_complete', filename=final_path.name)}[/]")
            else:
                # Failure
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