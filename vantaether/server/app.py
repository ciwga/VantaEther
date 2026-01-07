import sys
import logging
import threading
import time
import json
from typing import Dict, List, Any, Optional, Generator
from dataclasses import dataclass, field, asdict
from datetime import datetime

from flask import Flask, jsonify, render_template_string, request, Response

from rich.console import Console
from vantaether.utils.i18n import LanguageManager
from vantaether.server.templates import render_html_page, get_tampermonkey_script

# Initialize Logger specifically for Flask/Werkzeug to suppress generic output
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

console = Console()
lag = LanguageManager()


@dataclass
class CapturedItem:
    """
    Data model representing a captured media item.
    Ensures structural integrity of the data handled by the server.
    """
    url: str
    type: str  # 'video' or 'sub'
    source: str
    title: Optional[str] = None
    page: Optional[str] = None
    cookies: Optional[str] = None
    agent: Optional[str] = None
    referrer: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the dataclass to a dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class CaptureManager:
    """
    Thread-safe manager for handling captured media streams.
    Implements event-driven notifications to avoid CPU-intensive polling.
    """
    def __init__(self) -> None:
        self._videos: List[CapturedItem] = []
        self._subs: List[CapturedItem] = []
        self._lock: threading.Lock = threading.Lock()
        # Event to notify waiters (Engine/SSE) that new data is available
        self._event: threading.Event = threading.Event()

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
            # Basic validation
            if "url" not in data or "type" not in data:
                return False

            item = CapturedItem(
                url=data["url"],
                type=data["type"],
                source=data.get("source", "Unknown"),
                title=data.get("title"),
                page=data.get("page"),
                cookies=data.get("cookies"),
                agent=data.get("agent"),
                referrer=data.get("referrer")
            )

            with self._lock:
                added = False
                if item.type == "video":
                    if not any(v.url == item.url for v in self._videos):
                        self._videos.append(item)
                        added = True
                elif item.type == "sub":
                    if not any(s.url == item.url for s in self._subs):
                        self._subs.append(item)
                        added = True
                
                if added:
                    # Notify any waiting threads/generators
                    self._event.set()
                    return True
            return False
            
        except Exception as e:
            console.print(f"[red]Error adding captured item: {e}[/]")
            return False

    def wait_for_item(self, timeout: Optional[float] = None) -> bool:
        """
        Blocks until a new item is added or timeout occurs.
        Efficient alternative to polling.
        """
        flag = self._event.wait(timeout)
        if flag:
            self._event.clear()
        return flag

    def get_status(self) -> Dict[str, int]:
        """Returns the current count of captured items safely."""
        with self._lock:
            return {
                "video_count": len(self._videos),
                "sub_count": len(self._subs)
            }

    def get_snapshot(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns a snapshot of current data for the Engine to process.
        Returns a thread-safe deep copy (list of dicts), so no external locking is needed.
        """
        with self._lock:
            return {
                "videos": [v.to_dict() for v in self._videos],
                "subs": [s.to_dict() for s in self._subs]
            }


# Singleton instance of the manager
capture_manager = CaptureManager()


class VantaServer:
    """
    Background Flask server to receive captured streams from the browser.
    
    Security Note:
        - Runs strictly on 127.0.0.1 to prevent external network access.
        - CORS handling is implicit via the browser extension context.
    """

    def __init__(self, port: int = 5005) -> None:
        """
        Initialize the VantaServer.

        Args:
            port (int): The port to run the server on. Defaults to 5005.
        """
        self.app = Flask(__name__)
        self.port = port
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Configures Flask routes and endpoints."""
        
        @self.app.route("/")
        def index() -> str:
            """
            Serves the main page with the Tampermonkey script code.
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
            """Returns the current count of captured items."""
            return jsonify(capture_manager.get_status())

        @self.app.route("/stream")
        def stream() -> Response:
            """
            Server-Sent Events (SSE) endpoint.
            Push updates to the browser when new media is captured,
            eliminating the need for polling from the frontend.
            """
            def event_stream() -> Generator[str, None, None]:
                while True:
                    # Wait for an event (max 20s to send keepalive)
                    capture_manager.wait_for_item(timeout=20.0)
                    
                    # Send current status
                    data = capture_manager.get_status()
                    
                    # Use json.dumps instead of jsonify to avoid application context errors
                    json_str = json.dumps(data)
                    yield f"data: {json_str}\n\n"
                    
                    # Small sleep to prevent tight loops if event isn't cleared fast enough
                    time.sleep(0.1)

            return Response(event_stream(), mimetype="text/event-stream")

        @self.app.route("/snipe", methods=["POST"])
        def snipe() -> tuple[Response, int]:
            """
            Endpoint for Tampermonkey to POST captured data.
            """
            data = request.json
            if not data:
                return jsonify({"status": "error", "msg": "No data"}), 400

            added = capture_manager.add_item(data)
            
            if added:
                return jsonify({"status": "received"}), 200
            else:
                return jsonify({"status": "duplicate_or_invalid"}), 200

    def run(self) -> None:
        """
        Starts the Flask server quietly.
        """
        try:
            # Suppress the default Flask banner
            cli = sys.modules.get("flask.cli")
            if cli:
                # Type ignore is used because we are monkey-patching a library function
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