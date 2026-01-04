import sys
import time
import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


class MediaAnalyzer:
    """
    Handles comprehensive media file analysis with advanced parsing logic.
    """

    def _find_ffprobe(self) -> Optional[str]:
        """
        Locates the ffprobe executable on the system (Cross-Platform).
        
        Returns:
            Optional[str]: Path to ffprobe executable or None.
        """
        if shutil.which("ffprobe"):
            return "ffprobe"
            
        paths = []
        
        if sys.platform == "win32":
            # Common Windows paths
            paths = [
                r"C:\ffmpeg\bin\ffprobe.exe",
                r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
                r"C:\Program Files (x86)\ffmpeg\bin\ffprobe.exe",
                # Current directory fallback
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

        for p in paths:
            path_obj = Path(p)
            if path_obj.exists() and path_obj.is_file():
                return str(path_obj)
                
        return None

    def _calculate_frame_rate(self, r_frame_rate: str) -> float:
        """Converts ffprobe fraction string to float."""
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
        """Parses raw stream data into a clean format."""
        processed_streams = []
        
        for stream in streams:
            codec_type = stream.get('codec_type', 'unknown')
            codec_name = stream.get('codec_name', 'unknown')
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
                details = tags.get('title', 'Subtitle')
            
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

        Args:
            base_filename (str): The file path/name.

        Returns:
            Dict[str, Any]: A dictionary containing processed metadata.
        """
        time.sleep(1) # Buffer
        
        ffprobe = self._find_ffprobe()
        if not ffprobe:
            console.print(Panel(lang.get("ffprobe_not_found"), style="bold red"))
            return {"error": "FFprobe not found."}
        
        target: Optional[Path] = None
        supported_extensions: List[str] = [".mp4", ".mkv", ".webm", ".avi", ".mov"]

        base_path = Path(base_filename)
        if base_path.exists():
            target = base_path
        else:
            for ext in supported_extensions:
                # Avoid double extension
                if base_filename.lower().endswith(ext): 
                    continue
                
                f = base_path.with_suffix(ext)
                if f.exists(): 
                    target = f
                    break
        
        if not target:
            console.print(Panel(lang.get("file_not_found", filename=base_filename), style="bold red"))
            return {"error": "File not found."}

        try:
            cmd = [
                ffprobe, "-v", "quiet", "-print_format", "json", 
                "-show_format", "-show_streams", str(target)
            ]
            
            with console.status(lang.get("processing", filename=target.name)):
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=20)
            
            data = json.loads(result.stdout)
            fmt = data.get('format', {})
            raw_streams = data.get('streams', [])

            video_stream = next((s for s in raw_streams if s.get('codec_type') == 'video'), None)
            
            size_bytes = float(fmt.get('size', 0))
            size_mb = f"{size_bytes / (1024 * 1024):.2f} MB"

            fps_val = 0.0
            if video_stream:
                fps_val = self._calculate_frame_rate(video_stream.get('r_frame_rate', '0/0'))
            
            clean_streams = self._process_stream_details(raw_streams)

            resolution = "Unknown"
            codec_name = "Unknown"
            if video_stream:
                resolution = f"{video_stream.get('width')}x{video_stream.get('height')}"
                codec_name = video_stream.get('codec_name', 'Unknown')

            info_data = {
                "filename": target.name,
                "size_mb": size_mb,
                "duration": fmt.get('duration', '0'),
                "bit_rate": f"{int(fmt.get('bit_rate', 0)) // 1000} kbps",
                "format": fmt.get('format_name', 'Unknown'),
                "codec": codec_name,
                "resolution": resolution,
                "fps": fps_val,
                "stream_count": len(raw_streams),
                "streams": clean_streams
            }
            
            self._display_table(info_data, clean_streams)
            return info_data

        except subprocess.CalledProcessError as e:
            console.print(Panel(lang.get("ffprobe_error", error=e.stderr), style="bold red"))
            return {"error": f"FFprobe error: {e.stderr}"}
        except Exception as e:
            console.print(Panel(f"Error: {str(e)}", style="bold red"))
            return {"error": str(e)}

    def _display_table(self, info: Dict[str, Any], streams: List[Dict[str, Any]]) -> None:
        """Visualizes the analysis results."""
        main_table = Table(title=lang.get("media_analysis_title", filename=info['filename']), border_style="blue")
        main_table.add_column(lang.get("parameter"), style="cyan")
        main_table.add_column(lang.get("value"), style="green")
        
        main_table.add_row(lang.get("resolution"), info['resolution'])
        main_table.add_row(lang.get("fps"), str(info['fps']))
        main_table.add_row(lang.get("codec"), info['codec'])
        main_table.add_row(lang.get("size"), info['size_mb'])
        main_table.add_row(lang.get("duration"), f"{float(info['duration']):.1f} sn")
        
        console.print(main_table)

        stream_table = Table(title=lang.get("stream_details_title"), border_style="green")
        stream_table.add_column("ID", style="dim")
        stream_table.add_column(lang.get("type"), style="bold magenta")
        stream_table.add_column(lang.get("codec"), style="yellow")
        stream_table.add_column(lang.get("language"), style="cyan")
        stream_table.add_column(lang.get("details"), style="white")

        for s in streams:
            stream_table.add_row(
                str(s['index']), 
                s['type'].upper(), 
                s['codec'], 
                s['language'], 
                s['details']
            )
        
        console.print(stream_table)