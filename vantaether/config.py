from typing import Final, Optional
from vantaether import __version__
from vantaether.utils.i18n import LanguageManager


lang = LanguageManager()
VERSION: Final[str] = __version__

# --- SERVER CONFIGURATION ---
SERVER_HOST: str = "127.0.0.1"
SERVER_PORT: int = 5005
SERVER_URL: str = f"http://{SERVER_HOST}:{SERVER_PORT}"

# --- UI CONFIGURATION ---
# Controls whether the fake startup loading bar is skipped.
SKIP_STARTUP_ANIMATION: bool = False

# --- DEBUGGING ---
DEBUG_MODE: bool = False

# --- UI ASSETS ---
BANNER: str = rf"""
[bold white]██╗   ██╗ █████╗ ███╗   ██╗████████╗ █████╗[/]
[bold white]██║   ██║██╔══██╗████╗  ██║╚══██╔══╝██╔══██╗[/]
[bold white]██║   ██║███████║██╔██╗ ██║   ██║   ███████║[/]
[bold white]╚██╗ ██╔╝██╔══██║██║╚██╗██║   ██║   ██╔══██║[/]
[bold white] ╚████╔╝ ██║  ██║██║ ╚████║   ██║   ██║  ██║[/]
[bold white]  ╚═══╝  ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝[/]
           [bold white on #007acc] V A N T A [/][bold black on white] E T H E R [/] [bold cyan]v{VERSION}[/]
       [dim]━━━ [italic]{lang.get('app_description')}[/] ━━━[/]
"""

def configure_server(host: Optional[str] = None, port: Optional[int] = None) -> None:
    """
    Updates the server configuration at runtime based on CLI arguments.
    
    This function must be called BEFORE initializing the Engine or Server classes.
    It recalculates dependent variables like SERVER_URL.

    Args:
        host (Optional[str]): The new host address (e.g., '0.0.0.0').
        port (Optional[int]): The new port number (e.g., 8080).
    """
    global SERVER_HOST, SERVER_PORT, SERVER_URL

    if host:
        SERVER_HOST = host
    
    if port:
        SERVER_PORT = port

    SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"


def configure_ui(skip_animation: bool = False) -> None:
    """
    Updates UI configuration settings at runtime.

    Args:
        skip_animation (bool): If True, the startup progress bar will be suppressed.
    """
    global SKIP_STARTUP_ANIMATION
    SKIP_STARTUP_ANIMATION = skip_animation