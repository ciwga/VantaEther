import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict, Union, List

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
    """Handles logic for merging video, audio, and subtitle streams."""

    @staticmethod
    def _parse_time_str(time_str: str) -> float:
        """
        Parses FFmpeg time string (HH:MM:SS.ms) into total seconds.

        Args:
            time_str: Time string like '00:03:45.23'

        Returns:
            float: Total seconds.
        """
        try:
            h, m, s = time_str.split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
        except ValueError:
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
        Merges external subtitles AND/OR orphaned audio files using FFmpeg.
        
        Args:
            url: Subtitle URL (optional).
            fname: Base filename (Full absolute path without extension).
            mode: Embedding mode ('embed_mp4', 'embed_mkv', etc.).
            headers: HTTP headers for downloading subtitle.
            video_ext: The extension of the detected video part.
            audio_file: Path object or string path to the orphaned audio file (optional).
        """
        import requests

        if audio_file:
            audio_file = Path(audio_file)
            # Safety check: Do not attempt to merge partial files
            if ".part" in audio_file.name or not audio_file.exists():
                console.print(f"[bold red]{lang.get('invalid_audio_file', audio_file=audio_file)}[/]")
                audio_file = None

        if url:
            console.print(f"[cyan]{lang.get('download_external_sub')}[/]")
        elif audio_file:
            console.print(f"[cyan]{lang.get('manual_muxing')}[/]")

        final_sub: Optional[str] = None

        try:
            # Subtitle Download
            if url:
                r = requests.get(url, headers=headers, verify=False)
                if r.status_code == 200:
                    ext = "vtt" if ".vtt" in url else "srt"
                    raw = f"{fname}_ext.{ext}"
                    with open(raw, "wb") as f:
                        f.write(r.content)
                    final_sub = raw
                    if ext == "vtt":
                        srt_name = f"{fname}.srt"
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", raw, srt_name], capture_output=True
                        )
                        final_sub = srt_name
                        if Path(raw).exists():
                            Path(raw).unlink()

            # Setup Merge
            # Construct the theoretical video file path first
            video_file = Path(f"{fname}.{video_ext}")
            
            # Re-verify existence using pathlib glob
            if not video_file.exists():
                f_path = Path(fname)
                search_dir = f_path.parent
                stem_name = f_path.name

                candidates = []
                if search_dir.exists():
                    candidates = list(search_dir.glob(f"{stem_name}.*"))
                
                valid = [
                    f for f in candidates
                    if not f.suffix in [".json", ".srt", ".vtt", ".part", ".ytdl"]
                    and ".part" not in f.name
                    and ".audio." not in f.name # Exclude our explicit audio files from being detected as video
                ]
                if valid:
                    # Pick largest as video (safest assumption for video vs thumbnail/logs)
                    video_file = max(valid, key=lambda p: p.stat().st_size)

            target_output_ext = "mkv" if "mkv" in mode else "mp4"
            output_file = Path(f"{fname}_final.{target_output_ext}")

            cmd = ["ffmpeg", "-y", "-i", str(video_file)]

            # Input Audio (Input #1)
            if audio_file:
                cmd.extend(["-i", str(audio_file)])

            # Input Sub (Input #2 or #1)
            if final_sub:
                cmd.extend(["-i", final_sub])

            # --- MAPPING ---
            cmd.extend(["-map", "0:v"])  # Video from input 0

            if audio_file:
                # If the 'audio' file is actually a video without audio tracks (user error),
                # FFmpeg will ignore this map instead of crashing.
                cmd.extend(["-map", "1:a?"])  
            else:
                cmd.extend(["-map", "0:a?"]) # Audio from input 0 (if valid)

            if final_sub:
                sub_idx = "2" if audio_file else "1"
                cmd.extend(["-map", f"{sub_idx}:0"])

            # --- ENCODING ---
            if mode == "embed_mp4":
                cmd.extend(
                    [
                        "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k",
                        "-ac", "2",
                        "-c:s", "mov_text",
                    ]
                )
            elif mode == "embed_mkv":
                if audio_file:
                    cmd.extend(["-c:v", "copy", "-c:a", "aac", "-c:s", "srt"])
                else:
                    cmd.extend(["-c:v", "copy", "-c:a", "copy", "-c:s", "srt"])
            else:
                cmd.extend(["-c:v", "copy", "-c:a", "copy"])

            cmd.append(str(output_file))
            cmd.insert(1, "-strict")
            cmd.insert(2, "experimental")
            
            # Regex patterns for parsing FFmpeg output
            duration_pattern = re.compile(r"Duration:\s*(\d{2}:\d{2}:\d{2}\.\d+)")
            time_pattern = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d+)")

            # Use Popen to read stdout line by line for progress
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout for parsing
                universal_newlines=True,
                encoding='utf-8',
                errors='replace'
            )

            total_duration_secs: Optional[float] = None
            log_buffer: List[str] = [] # Keep last lines for error reporting

            with Progress(
                SpinnerColumn("dots", style="bold magenta"),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(
                    bar_width=None,
                    style="dim white",
                    complete_style="bold green",
                    finished_style="bold green"
                ),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                "•",
                TimeElapsedColumn(),
                "•",
                TimeRemainingColumn(),
                console=console
            ) as progress:
                
                # Start with indeterminate task (total=None)
                task_id = progress.add_task(f"[yellow]{lang.get('ffmpeg_processing')}[/]", total=None)

                if process.stdout:
                    for line in process.stdout:
                        log_buffer.append(line)
                        if len(log_buffer) > 50: # Keep only recent logs to save memory
                            log_buffer.pop(0)

                        line = line.strip()
                        
                        # 1. Attempt to find Total Duration
                        if total_duration_secs is None:
                            d_match = duration_pattern.search(line)
                            if d_match:
                                total_duration_secs = StreamMerger._parse_time_str(d_match.group(1))
                                if total_duration_secs > 0:
                                    progress.update(task_id, total=total_duration_secs)

                        # 2. Attempt to find Current Time
                        if total_duration_secs:
                            t_match = time_pattern.search(line)
                            if t_match:
                                current_secs = StreamMerger._parse_time_str(t_match.group(1))
                                progress.update(task_id, completed=current_secs)
            
            return_code = process.wait()

            if return_code == 0 and output_file.exists():
                # Only delete parts if merge was successful
                if video_file.exists() and video_file != output_file:
                    try:
                        video_file.unlink()
                    except OSError: pass
                if audio_file and audio_file.exists():
                    try:
                        audio_file.unlink()
                    except OSError: pass

                final_name = Path(f"{fname}.{target_output_ext}")
                if final_name.exists():
                    try:
                        final_name.unlink()
                    except OSError: pass
                
                output_file.rename(final_name)

                if final_sub and Path(final_sub).exists():
                    try:
                        Path(final_sub).unlink()
                    except OSError: pass

                console.print(f"[bold green]{lang.get('muxing_complete', filename=final_name)}[/]")
            else:
                error_log = "".join(log_buffer)
                console.print(f"[bold red]{lang.get('muxing_error')}[/]\n[dim]{error_log}[/]")

        except Exception as e:
            console.print(f"[red]{lang.get('merge_error', error=str(e))}[/]")