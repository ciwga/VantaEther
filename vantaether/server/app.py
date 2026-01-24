import sys
import time
import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator, Set, Tuple

from flask import Flask, jsonify, render_template_string, request, Response
from werkzeug.serving import make_server
from rich.console import Console

import vantaether.config as config
from vantaether.utils.i18n import LanguageManager
from vantaether.server.templates import render_html_page, get_tampermonkey_script
from vantaether.exceptions import NetworkError


log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

console = Console()
lang = LanguageManager()


class CapturedItem:
    """
    Data model representing a captured media item.
    Ensures structural integrity and serialization of the data handled by the server.
    """
    __slots__ = (
        'url', 'media_type', 'source', 'title', 'page', 
        'cookies', 'agent', 'referrer', 'timestamp'
    )

    def __init__(
        self, 
        url: str, 
        media_type: str, 
        source: str, 
        title: Optional[str] = None, 
        page: Optional[str] = None, 
        cookies: Optional[str] = None, 
        agent: Optional[str] = None, 
        referrer: Optional[str] = None
    ) -> None:
        """
        Initializes the captured item with timestamp.
        """
        self.url = url
        self.media_type = media_type
        self.source = source
        self.title = title
        self.page = page
        self.cookies = cookies
        self.agent = agent
        self.referrer = referrer
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the object attributes to a dictionary for JSON serialization.
        
        Returns:
            Dict[str, Any]: Serialized data with ISO format timestamp.
        """
        try:
            return {
                'url': self.url,
                'media_type': self.media_type,
                'source': self.source,
                'title': self.title,
                'page': self.page,
                'cookies': self.cookies,
                'agent': self.agent,
                'referrer': self.referrer,
                'timestamp': self.timestamp.isoformat()
            }
        except Exception:
            return {'url': self.url, 'error': lang.get('serialization_failed')}


class CaptureManager:
    """
    Thread-safe manager for handling captured media streams.
    Implements event-driven notifications to avoid CPU-intensive polling.
    """

    def __init__(self) -> None:
        """
        Initializes the CaptureManager with thread-safe locks and storage lists.
        """
        self._videos: List[CapturedItem] = []
        self._subs: List[CapturedItem] = []
        
        # Lock for thread safety when modifying lists
        self._lock: threading.Lock = threading.Lock()
        
        # Event to notify consumers (Engine/SSE) of new items
        self._event: threading.Event = threading.Event()

        # Limit the list size to prevent infinite memory growth
        self._MAX_ITEMS = 2000

        # Defines all types that should be treated as "Video" sources
        # 'log' is included here so it enters the pipeline, but Engine filters it later.
        self.VIDEO_TYPES: Set[str] = {
            "video",
            "manifest_dash",  # .mpd
            "manifest_hls",   # .m3u8
            "stream_api",     # JSON API endpoints (/embed/, /q/1 etc.)
            "license",        # DRM License URLs
            "log"             # Remote browser logs
        }

    def _prune_list(self, target_list: List[Any]) -> None:
        """
        Internal helper: Removes the oldest items if the list exceeds the maximum size.
        This prevents memory leaks in long-running sessions.
        """
        if len(target_list) > self._MAX_ITEMS:
            # Remove the oldest 10% of items (FIFO)
            del target_list[:int(self._MAX_ITEMS * 0.1)]

    def add_item(self, data: Dict[str, Any]) -> bool:
        """
        Adds a new item to the pool if it's not a duplicate.
        Triggers the notification event if an item is successfully added.

        Args:
            data (Dict[str, Any]): The raw JSON data from the request.

        Returns:
            bool: True if added, False if duplicate or invalid.
        """
        try:
            # Basic Validation
            if "url" not in data or "type" not in data:
                return False

            item = CapturedItem(
                url=data["url"],
                media_type=data["type"],
                source=data.get("source", lang.get("unknown")),
                title=data.get("title"),
                page=data.get("page"),
                cookies=data.get("cookies"),
                agent=data.get("agent"),
                referrer=data.get("referrer")
            )

            added = False
            with self._lock:
                # Deduplication & Classification Logic
                if item.media_type in self.VIDEO_TYPES:
                    # Check if URL already exists in video list
                    if not any(v.url == item.url for v in self._videos):
                        self._videos.append(item)
                        self._prune_list(self._videos)
                        added = True
                        
                elif item.media_type == "sub":
                    # Check if URL already exists in sub list
                    if not any(s.url == item.url for s in self._subs):
                        self._subs.append(item)
                        self._prune_list(self._subs)
                        added = True

            if added:
                # Wake up any threads waiting for data
                self._event.set()
                return True
            
            return False
            
        except Exception as e:
            console.print(f"[red]{lang.get('capture_add_error', error=e)}[/]")
            return False

    def wait_for_item(self, timeout: Optional[float] = None) -> bool:
        """
        Blocks until a new item is added or timeout occurs.
        
        Args:
            timeout (Optional[float]): Time in seconds to wait. None for indefinite.

        Returns:
            bool: True if event was set (new item), False if timeout occurred.
        """
        flag = self._event.wait(timeout)
        if flag:
            self._event.clear()
        return flag

    def get_status(self) -> Dict[str, int]:
        """Returns the current count of captured items safely."""
        with self._lock:
            # Exclude logs from the visible video count
            real_vid_count = sum(1 for v in self._videos if v.media_type != "log")
            return {
                "video_count": real_vid_count,
                "sub_count": len(self._subs)
            }

    def get_snapshot(self) -> Dict[str, List[Dict[str, Any]]]:
        """Returns a thread-safe snapshot/copy of current data."""
        with self._lock:
            return {
                "videos": [v.to_dict() for v in self._videos],
                "subs": [s.to_dict() for s in self._subs]
            }

    def clear_pool(self) -> None:
        """Clears all captured videos and subtitles from memory."""
        with self._lock:
            self._videos.clear()
            self._subs.clear()
            self._event.clear()


class VantaServer:
    """
    Background Flask server to receive captured streams from the browser.
    
    Uses Werkzeug's make_server for robust thread control, avoiding the limitations
    of the standard app.run() development server.
    """

    def __init__(self, capture_manager: Optional[CaptureManager] = None, port: Optional[int] = None) -> None:
        """
        Initialize the VantaServer.
        
        Args:
            capture_manager: Injected manager instance. Creates new if None.
            port: Port to bind. Defaults to config.SERVER_PORT.
        """
        self.app = Flask(__name__)
        self.port = port if port is not None else config.SERVER_PORT
        self.capture_manager = capture_manager if capture_manager else CaptureManager()
        self.server = None 
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Configures Flask routes and endpoints."""
        
        @self.app.route("/")
        def index() -> str:
            """Serves the main page with instructions and the userscript."""
            try:
                script_content = get_tampermonkey_script()
                html_content = render_html_page(lang)
                return render_template_string(html_content, script=script_content)
            except Exception as e:
                return lang.get("template_error", error=e)

        @self.app.route("/vantaether.user.js")
        def install_script() -> Response:
            """Serves the raw userscript file for installation."""
            try:
                script_content = get_tampermonkey_script()
                return Response(script_content, mimetype="application/javascript")
            except Exception as e:
                return Response(lang.get("install_script_error", error=e), mimetype="application/javascript")

        @self.app.route("/status")
        def status() -> Response:
            """Returns the current capture counts."""
            return jsonify(self.capture_manager.get_status())
        
        @self.app.route("/clear", methods=["POST"])
        def clear_list() -> Response:
            """Clears the capture pool."""
            self.capture_manager.clear_pool()
            return jsonify({"status": "cleared"}), 200

        @self.app.route("/stream")
        def stream() -> Response:
            """
            Server-Sent Events (SSE) endpoint.
            Pushes updates to the browser UI in real-time.
            """
            def event_stream() -> Generator[str, None, None]:
                while True:
                    try:
                        # Block until data arrives or heartbeat timeout (20s)
                        self.capture_manager.wait_for_item(timeout=20.0)
                        
                        data = self.capture_manager.get_status()
                        json_str = json.dumps(data)
                        yield f"data: {json_str}\n\n"
                        
                        # Small buffer to prevent rapid-fire loop in edge cases
                        time.sleep(0.1)
                    except GeneratorExit:
                        # Client disconnected
                        break
                    except Exception:
                        time.sleep(1)
                        yield ": heartbeat\n\n"

            return Response(event_stream(), mimetype="text/event-stream")

        @self.app.route("/snipe", methods=["POST"])
        def snipe() -> Tuple[Response, int]:
            """
            Endpoint to receive captured data from the userscript.
            This is the main entry point for data coming from the browser.
            """
            try:
                data = request.json
                if not data:
                    return jsonify({"status": "error", "msg": lang.get("api_no_data")}), 400

                # This helps debugging connection issues immediately
                m_type = data.get("type", "unknown")
                m_url = data.get("url", "no_url")
                
                # Truncate long URLs for display
                disp_url = (m_url[:60] + '..') if len(m_url) > 60 else m_url
                
                if m_type == "log":
                    # Logs are handled differently in UI, but good to know they arrived
                    pass
                else:
                    # Visible feedback for valid media items
                    color = "green" if "manifest" in m_type else "yellow"
                    console.print(f"[dim]Recv:[/][{color}]{m_type}[/] -> {disp_url}")

                added = self.capture_manager.add_item(data)
                
                if added:
                    return jsonify({"status": "received"}), 200
                else:
                    # Duplicate or invalid
                    return jsonify({"status": "duplicate_or_invalid"}), 200
            
            except Exception as e:
                 console.print(f"[red]{lang.get('snipe_error', error=e)}[/]")
                 return jsonify({"status": "error", "msg": str(e)}), 500

    def run(self) -> None:
        """
        Starts the Flask server using werkzeug's make_server.
        
        This method is blocking and should typically be run in a separate thread.
        It handles port conflicts gracefully.
        
        Raises:
            NetworkError: If the server fails to bind to the port.
        """
        try:
            # Suppress Flask's startup banner
            cli = sys.modules.get("flask.cli")
            if cli:
                cli.show_server_banner = lambda *x: None # type: ignore
            
            # Create a robust WSGI server
            self.server = make_server(config.SERVER_HOST, self.port, self.app)
            self.server.serve_forever()
            
        except OSError as e:
            if e.errno == 98 or e.errno == 48: # Address already in use
                error_msg = lang.get("port_busy_error", port=self.port)
            else:
                error_msg = str(e)
            
            raise NetworkError(lang.get("server_startup_failed", error=error_msg))
            
        except Exception as e:
             raise NetworkError(lang.get("server_crash", error=e))