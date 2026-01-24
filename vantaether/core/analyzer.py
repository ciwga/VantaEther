import sys
import time
import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vantaether.utils.i18n import LanguageManager
from vantaether.exceptions import AnalysisError


console = Console()
lang = LanguageManager()


class MediaAnalyzer:
    """
    Handles comprehensive media file analysis using FFprobe.
    
    This class is responsible for extracting technical metadata (codec, resolution,
    bitrate, etc.) from media files safely and displaying them in a rich format.
    """

    def _find_ffprobe(self) -> Optional[str]:
        """
        Locates the ffprobe executable on the system (Cross-Platform).
        
        Checks system PATH first, then falls back to common installation directories
        on Windows, Linux, and MacOS/Termux.

        Returns:
            Optional[str]: Absolute path to ffprobe executable or None if not found.
        """
        # 1. Check system PATH first (Most reliable)
        if shutil.which("ffprobe"):
            return "ffprobe"
            
        paths = []
        
        # 2. Add OS-specific fallback paths
        if sys.platform == "win32":
            paths = [
                r"C:\ffmpeg\bin\ffprobe.exe",
                r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
                r"C:\Program Files (x86)\ffmpeg\bin\ffprobe.exe",
                str(Path.cwd() / "ffprobe.exe"),
                str(Path.cwd() / "bin" / "ffprobe.exe")
            ]
        else:
            # Common Linux/Termux/macOS paths
            paths = [
                "/data/data/com.termux/files/usr/bin/ffprobe",
                "/usr/bin/ffprobe", 
                "/usr/local/bin/ffprobe",
                "/opt/homebrew/bin/ffprobe"
            ]

        # 3. Verify existence
        for p in paths:
            path_obj = Path(p)
            if path_obj.exists() and path_obj.is_file():
                return str(path_obj)
                
        return None

    def _calculate_frame_rate(self, r_frame_rate: str) -> float:
        """
        Converts ffprobe fraction string (e.g., '30000/1001') to float.
        
        Args:
            r_frame_rate (str): The frame rate string from ffprobe.

        Returns:
            float: Calculated fps or 0.0 on error.
        """
        try:
            if not r_frame_rate or r_frame_rate == "0/0":
                return 0.0
            
            if '/' in r_frame_rate:
                num, den = r_frame_rate.split('/')
                if float(den) == 0:
                    return 0.0
                return round(float(num) / float(den), 2)
            
            return float(r_frame_rate)
        except (ValueError, TypeError, ZeroDivisionError):
            return 0.0

    def _process_stream_details(self, streams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parses raw FFprobe stream data into a clean, UI-friendly format.
        
        Args:
            streams (List[Dict]): Raw stream dictionaries from JSON output.

        Returns:
            List[Dict]: Processed list of streams with readable details.
        """
        processed_streams = []
        
        for stream in streams:
            codec_type = stream.get('codec_type', lang.get("unknown_short").lower())
            codec_name = stream.get('codec_name', lang.get("unknown_short").lower())
            index = stream.get('index', -1)
            
            tags = stream.get('tags', {})
            language = tags.get('language', 'und')

            details = ""
            if codec_type == 'video':
                w = stream.get('width', 0)
                h = stream.get('height', 0)
                details = f"{w}x{h}"
            elif codec_type == 'audio':
                hz = stream.get('sample_rate', '0')
                channels = stream.get('channels', 0)
                details = f"{hz}Hz, {channels}ch"
            elif codec_type == 'subtitle':
                details = tags.get('title', lang.get("subtitle_label"))
            
            processed_streams.append({
                "index": index,
                "type": codec_type,
                "codec": codec_name,
                "language": language,
                "details": details
            })
            
        return processed_streams

    def get_media_info(self, base_filename: str) -> Dict[str, Any]:
        """
        Extracts and processes technical details from a media file.
        
        Automatically attempts to find the file with supported extensions if
        the exact filename is not found.

        Args:
            base_filename (str): The file path/name.

        Returns:
            Dict[str, Any]: A dictionary containing processed metadata.
        """
        time.sleep(1) # Small UX buffer
        
        ffprobe = self._find_ffprobe()
        if not ffprobe:
            console.print(Panel(lang.get("ffprobe_not_found"), style="bold red"))
            return {"error": lang.get("ffprobe_not_found")}
        
        target: Optional[Path] = None
        supported_extensions: List[str] = [".mp4", ".mkv", ".webm", ".avi", ".mov", ".mp3", ".m4a"]

        try:
            base_path = Path(base_filename)
            if base_path.exists() and base_path.is_file():
                target = base_path
            else:
                for ext in supported_extensions:
                    if base_filename.lower().endswith(ext): 
                        continue
                    
                    candidate = base_path.with_suffix(ext)
                    if candidate.exists() and candidate.is_file(): 
                        target = candidate
                        break
        except OSError as e:
            return {"error": f"{lang.get('filename_error', error=e)}"}
        
        if not target:
            console.print(Panel(lang.get("file_not_found", filename=base_filename), style="bold red"))
            return {"error": lang.get("file_not_found", filename=base_filename)}

        try:
            # -v quiet: Suppress logs
            # -print_format json: Output JSON
            # -show_format -show_streams: Get all info
            cmd = [
                ffprobe, "-v", "quiet", "-print_format", "json", 
                "-show_format", "-show_streams", str(target)
            ]
            
            with console.status(lang.get("processing", filename=target.name), spinner="dots"):
                # Run with timeout to prevent hangs on corrupted files
                # Use errors='replace' to handle non-utf8 metadata safely
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    check=True, 
                    timeout=20,
                    encoding='utf-8',
                    errors='replace'
                )
            
            if not result.stdout:
                raise AnalysisError(lang.get("ffprobe_empty_output"))

            data = json.loads(result.stdout)
            fmt = data.get('format', {})
            raw_streams = data.get('streams', [])

            video_stream = next((s for s in raw_streams if s.get('codec_type') == 'video'), None)
            
            try:
                size_bytes = float(fmt.get('size', 0))
                size_mb = f"{size_bytes / (1024 * 1024):.2f} MB"
            except (ValueError, TypeError):
                size_mb = lang.get("unknown_value")

            fps_val = 0.0
            if video_stream:
                fps_val = self._calculate_frame_rate(video_stream.get('r_frame_rate', '0/0'))
            
            clean_streams = self._process_stream_details(raw_streams)

            resolution = lang.get("unknown_value")
            codec_name = lang.get("unknown_value")
            if video_stream:
                resolution = f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}"
                codec_name = video_stream.get('codec_name', lang.get("unknown_value"))

            info_data = {
                "filename": target.name,
                "size_mb": size_mb,
                "duration": fmt.get('duration', '0'),
                "bit_rate": f"{int(fmt.get('bit_rate', 0)) // 1000} kbps" if fmt.get('bit_rate') else lang.get("unknown_value"),
                "format": fmt.get('format_name', lang.get("unknown_value")),
                "codec": codec_name,
                "resolution": resolution,
                "fps": fps_val,
                "stream_count": len(raw_streams),
                "streams": clean_streams
            }
            
            self._display_table(info_data, clean_streams)
            return info_data

        except subprocess.TimeoutExpired:
            console.print(Panel(lang.get("ffprobe_timeout"), style="bold red"))
            return {"error": "Timeout"}
        except subprocess.CalledProcessError as e:
            err_out = e.stderr if e.stderr else lang.get("unknown_process_error")
            console.print(Panel(lang.get("ffprobe_error", error=err_out), style="bold red"))
            return {"error": f"FFprobe Error: {err_out}"}
        except json.JSONDecodeError as je:
             console.print(Panel(lang.get("ffprobe_json_error", error=je), style="bold red"))
             return {"error": "JSON Error"}
        except Exception as e:
            console.print(Panel(lang.get("analysis_unexpected_error", error=str(e)), style="bold red"))
            return {"error": str(e)}

    def _display_table(self, info: Dict[str, Any], streams: List[Dict[str, Any]]) -> None:
        """
        Visualizes the analysis results in a formatted Rich table.
        
        Args:
            info (Dict): General file info.
            streams (List[Dict]): Detailed stream info.
        """
        try:
            filename = info.get('filename', lang.get("unknown_filename"))
            main_table = Table(
                title=lang.get("media_analysis_title", filename=filename), 
                border_style="blue",
                show_header=True
            )
            main_table.add_column(lang.get("parameter"), style="cyan", justify="right")
            main_table.add_column(lang.get("value"), style="green")
            
            main_table.add_row(lang.get("resolution"), str(info.get('resolution', 'N/A')))
            main_table.add_row(lang.get("fps"), str(info.get('fps', 0)))
            main_table.add_row(lang.get("codec"), str(info.get('codec', 'N/A')))
            main_table.add_row(lang.get("size"), str(info.get('size_mb', 'N/A')))
            
            duration = info.get('duration')
            try:
                dur_str = f"{float(duration):.1f} sn" if duration else lang.get("unknown_value")
            except (ValueError, TypeError):
                dur_str = lang.get("unknown_value")
            main_table.add_row(lang.get("duration"), dur_str)
            
            console.print(main_table)

            if streams:
                stream_table = Table(title=lang.get("stream_details_title"), border_style="green")
                stream_table.add_column("ID", style="dim")
                stream_table.add_column(lang.get("type"), style="bold magenta")
                stream_table.add_column(lang.get("codec"), style="yellow")
                stream_table.add_column(lang.get("language"), style="cyan")
                stream_table.add_column(lang.get("details"), style="white")

                for s in streams:
                    stream_table.add_row(
                        str(s.get('index', '?')), 
                        str(s.get('type', 'unk')).upper(), 
                        str(s.get('codec', 'unk')), 
                        str(s.get('language', 'unk')), 
                        str(s.get('details', ''))
                    )
                
                console.print(stream_table)
            else:
                console.print(f"[yellow]{lang.get('no_streams_found')}[/]")
                
        except Exception as e:
            console.print(f"[dim red]{lang.get('unhandled_ui_exception')} {e}[/]")