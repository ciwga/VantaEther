import sys
import time
import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator, Set

from flask import Flask, jsonify, render_template_string, request, Response

from rich.console import Console
from vantaether.utils.i18n import LanguageManager
from vantaether.server.templates import render_html_page, get_tampermonkey_script

# Initialize Logger specifically for Flask/Werkzeug to suppress generic output
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

console = Console()
lag = LanguageManager()


class CapturedItem:
    """
    Data model representing a captured media item.
    Ensures structural integrity of the data handled by the server.
    
    OPTIMIZATION:
    Implemented as a standard class with __slots__ instead of a dataclass to:
    1. Fix the 'ValueError' regarding default values conflicting with slots.
    2. Guarantee memory optimization (no __dict__ overhead) for thousands of items.
    3. Rename 'type' to 'media_type' to avoid shadowing Python built-ins.
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
        Initializes the captured item. 
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
            Dict[str, Any]: Serialized dictionary with ISO format timestamp.
        """
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


class CaptureManager:
    """
    Thread-safe manager for handling captured media streams.
    Implements event-driven notifications to avoid CPU-intensive polling.
    """

    def __init__(self) -> None:
        """
        Initializes the CaptureManager with thread-safe locks and storage lists.
        Defines the valid video types including API endpoints and manifests.
        """
        self._videos: List[CapturedItem] = []
        self._subs: List[CapturedItem] = []
        self._lock: threading.Lock = threading.Lock()
        self._event: threading.Event = threading.Event()

        # Limit the list size to prevent infinite growth during long sessions.
        self._MAX_ITEMS = 2000

        # Defines all types that should be treated as "Video" sources
        self.VIDEO_TYPES: Set[str] = {
            "video",
            "manifest_dash",  # .mpd
            "manifest_hls",   # .m3u8
            "stream_api",     # JSON API endpoints (/embed/, /q/1 etc.)
            "license"         # DRM License URLs
        }

    def _prune_list(self, target_list: List[Any]) -> None:
        """
        Internal helper: Removes the oldest items if the list exceeds the maximum size.
        This prevents memory leaks (unbounded growth) in long-running processes.
        """
        if len(target_list) > self._MAX_ITEMS:
            # Remove the oldest 10% of items to avoid frequent resizing
            del target_list[:int(self._MAX_ITEMS * 0.1)]

    def add_item(self, data: Dict[str, Any]) -> bool:
        """
        Adds a new item to the pool if it's not a duplicate.
        Triggers the notification event if an item is added.

        Args:
            data (Dict[str, Any]): The raw JSON data from the request.

        Returns:
            bool: True if added, False if duplicate or invalid.
        """
        try:
            if "url" not in data or "type" not in data:
                return False

            item = CapturedItem(
                url=data["url"],
                media_type=data["type"],
                source=data.get("source", "Unknown"),
                title=data.get("title"),
                page=data.get("page"),
                cookies=data.get("cookies"),
                agent=data.get("agent"),
                referrer=data.get("referrer")
            )

            with self._lock:
                added = False
                
                if item.media_type in self.VIDEO_TYPES:
                    if not any(v.url == item.url for v in self._videos):
                        self._videos.append(item)
                        self._prune_list(self._videos) # Enforce memory limit
                        added = True
                elif item.media_type == "sub":
                    if not any(s.url == item.url for s in self._subs):
                        self._subs.append(item)
                        self._prune_list(self._subs)
                        added = True
                
                # Trigger event if new data arrived to wake up consumers
                if added:
                    self._event.set()
                    return True
            return False
            
        except Exception as e:
            console.print(f"[red]{lag.get('capture_add_error', error=e)}[/]")
            return False

    def wait_for_item(self, timeout: Optional[float] = None) -> bool:
        """
        Blocks until a new item is added or timeout occurs.
        This allows consumers (like the Engine or SSE stream) to wait efficiently without busy loops.

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
        """
        Returns the current count of captured items safely.

        Returns:
            Dict[str, int]: A dictionary containing counts of videos and subs.
        """
        with self._lock:
            return {
                "video_count": len(self._videos),
                "sub_count": len(self._subs)
            }

    def get_snapshot(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns a thread-safe snapshot of current data.
        
        Note: This involves copying data. Frequent calls with large lists should be avoided.

        Returns:
            Dict[str, List[Dict[str, Any]]]: Complete lists of videos and subtitles.
        """
        with self._lock:
            return {
                "videos": [v.to_dict() for v in self._videos],
                "subs": [s.to_dict() for s in self._subs]
            }

    def clear_pool(self) -> None:
        """
        Clears all captured videos and subtitles from the memory.
        Resets the event state.
        """
        with self._lock:
            self._videos.clear()
            self._subs.clear()
            self._event.clear()


class VantaServer:
    """
    Background Flask server to receive captured streams from the browser.
    
    Uses Dependency Injection for CaptureManager to ensure testability and isolation.
    """

    def __init__(self, capture_manager: CaptureManager, port: int = 5005) -> None:
        """
        Initialize the VantaServer.

        Args:
            capture_manager (CaptureManager): The injected dependency for state management.
            port (int): The port to run the server on. Defaults to 5005.
        """
        self.app = Flask(__name__)
        self.port = port
        self.capture_manager = capture_manager
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Configures Flask routes and endpoints."""
        
        @self.app.route("/")
        def index() -> str:
            """
            Serves the main page with the Tampermonkey/Violentmonkey script code.
            Renders localized HTML based on the system language.
            """
            script_content = get_tampermonkey_script()
            html_content = render_html_page(lag)
            return render_template_string(html_content, script=script_content)

        @self.app.route("/vantaether.user.js")
        def install_script() -> Response:
            """
            Serves the script with the correct MIME type to trigger 
            Tampermonkey/Violentmonkey installation dialog automatically.
            """
            script_content = get_tampermonkey_script()
            return Response(script_content, mimetype="application/javascript")

        @self.app.route("/status")
        def status() -> Response:
            """
            Returns the current count of captured items.
            Used for polling if SSE is not active.
            """
            return jsonify(self.capture_manager.get_status())
        
        @self.app.route("/clear", methods=["POST"])
        def clear_list() -> Response:
            """
            Clears the capture pool.
            Called by the engine when the user requests a reset.
            """
            self.capture_manager.clear_pool()
            return jsonify({"status": "cleared"}), 200

        @self.app.route("/stream")
        def stream() -> Response:
            """
            Server-Sent Events (SSE) endpoint.
            Push updates to the browser when new media is captured,
            eliminating the need for polling from the frontend.
            """
            def event_stream() -> Generator[str, None, None]:
                while True:
                    self.capture_manager.wait_for_item(timeout=20.0)
                    
                    data = self.capture_manager.get_status()
                    json_str = json.dumps(data)
                    yield f"data: {json_str}\n\n"
                    
                    # Small sleep to prevent rapid-fire events in edge cases
                    time.sleep(0.1)

            return Response(event_stream(), mimetype="text/event-stream")

        @self.app.route("/snipe", methods=["POST"])
        def snipe() -> tuple[Response, int]:
            """
            Endpoint for Tampermonkey/Violentmonkey to POST captured data.
            Receives JSON payload and delegates to CaptureManager.
            """
            data = request.json
            if not data:
                return jsonify({"status": "error", "msg": "No data"}), 400

            added = self.capture_manager.add_item(data)
            
            if added:
                return jsonify({"status": "received"}), 200
            else:
                return jsonify({"status": "duplicate_or_invalid"}), 200

    def run(self) -> None:
        """Starts the Flask server quietly."""
        try:
            cli = sys.modules.get("flask.cli")
            if cli:
                cli.show_server_banner = lambda *x: None # type: ignore
            
            self.app.run(
                host="127.0.0.1",
                port=self.port, 
                debug=False, 
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            console.print(f"[red]{lag.get('flask_service_error', error=e)}[/]")