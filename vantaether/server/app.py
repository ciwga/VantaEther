import sys
import logging
import threading
from rich.console import Console
from typing import Dict, List, Any
from vantaether.utils.i18n import LanguageManager
from .templates import render_html_page, get_tampermonkey_script
from flask import Flask, jsonify, render_template_string, request


log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

console = Console()
lag = LanguageManager()


# Global Thread-Safe Storage for captured streams
POOL: Dict[str, Any] = {
    "videos": [],
    "subs": [],
    "lock": threading.Lock()
}


class VantaServer:
    """
    Background Flask server to receive captured streams from the browser.
    """

    def __init__(self, port: int = 5005) -> None:
        """
        Initialize the VantaServer.

        Args:
            port (int): The port to run the server on.
        """
        self.app = Flask(__name__)
        self.port = port
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Configures Flask routes."""
        
        @self.app.route("/")
        def index():
            """
            Serves the main page with the Tampermonkey script code.
            Renders localized HTML based on the system language.
            """
            script_content = get_tampermonkey_script()
            html_content = render_html_page(lag)
            return render_template_string(html_content, script=script_content)

        @self.app.route("/status")
        def status():
            """Returns the current count of captured items."""
            with POOL["lock"]:
                return jsonify({
                    "video_count": len(POOL["videos"]),
                    "sub_count": len(POOL["subs"]),
                })

        @self.app.route("/snipe", methods=["POST"])
        def snipe():
            """Endpoint for Tampermonkey to POST captured data."""
            data = request.json
            if not data:
                return jsonify({"status": "error", "msg": "No data"}), 400

            typ = data.get("type")
            with POOL["lock"]:
                if typ == "video":
                    # Check for duplicates based on URL
                    if not any(v["url"] == data["url"] for v in POOL["videos"]):
                        POOL["videos"].append(data)
                elif typ == "sub":
                    if not any(s["url"] == data["url"] for s in POOL["subs"]):
                        POOL["subs"].append(data)

            return jsonify({"status": "received"})

    def run(self) -> None:
        """Starts the Flask server quietly."""
        try:
            # Hide banner
            cli = sys.modules.get("flask.cli")
            if cli:
                cli.show_server_banner = lambda *x: None
            
            self.app.run(
                host="0.0.0.0", 
                port=self.port, 
                debug=False, 
                use_reloader=False
            )
        except Exception as e:
            console.print(f"[red]{lag.get('flask_service_error', error=e)}[/]")


def get_pool() -> Dict[str, Any]:
    """Accessor for the shared pool."""
    return POOL