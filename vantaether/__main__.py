import sys
import argparse
import urllib3
from typing import Tuple, Optional

from rich.panel import Panel
from rich.console import Console
from rich.prompt import Prompt, Confirm
from yt_dlp.extractor import gen_extractors

import vantaether.config as config
from vantaether.core.engine import VantaEngine
from vantaether.utils.i18n import LanguageManager
from vantaether.core.downloader import DownloadManager
from vantaether.utils.ui import render_banner, show_startup_sequence

# Suppress SSL Warnings to ensure clean output
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

console = Console()
lang = LanguageManager()


def show_legal_disclaimer() -> bool:
    """
    Displays the mandatory legal disclaimer and terms of use.
    The user must explicitly accept these terms to proceed.
    
    Returns:
        bool: True if accepted, False otherwise.
    """
    console.clear()
    console.print(Panel(
        f"[bold white]{lang.get('disclaimer_text')}[/]",
        title=f"[bold red]{lang.get('disclaimer_title')}[/]",
        border_style="red",
        expand=False
    ))
    
    if Confirm.ask(f"\n[bold yellow]{lang.get('choice')}? [/]"):
        console.print(f"[green]{lang.get('disclaimer_accepted')}[/]\n")
        return True
    else:
        console.print(f"[red]{lang.get('disclaimer_rejected')}[/]")
        return False


def is_natively_supported(url: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if the given URL is natively supported by yt-dlp's internal extractors.
    
    Args:
        url (str): The URL to check.

    Returns:
        Tuple[bool, Optional[str]]: (Is Supported, Extractor Name)
    """
    with console.status(f"[bold cyan]{lang.get('scanning_platform_database')}[/]", spinner="earth"):
        extractors = gen_extractors()
        for ie in extractors:
            if ie.suitable(url) and ie.IE_NAME != 'generic':
                return True, ie.IE_NAME
    return False, None


def main() -> None:
    """
    Main entry point for VantaEther.
    Parses arguments, configures the server, handles UI initialization, 
    and routes to the appropriate downloader.
    """
    parser = argparse.ArgumentParser(
        description=lang.get("cli_desc"),
        epilog=lang.get("cli_epilog"),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "url", 
        nargs="?", 
        help=lang.get("cli_help_url")
    )
    
    parser.add_argument(
        "-a", "--audio", 
        action="store_true", 
        help=lang.get("cli_help_audio")
    )

    parser.add_argument(
        "-p", "--port",
        type=int,
        help=lang.get("cli_help_port"),
        default=None
    )

    parser.add_argument(
        "--host",
        type=str,
        help=lang.get("cli_help_host"),
        default=None
    )

    parser.add_argument(
        "--console",
        action="store_true",
        help=lang.get("cli_help_console")
    )

    args = parser.parse_args()

    if args.port or args.host:
        config.configure_server(host=args.host, port=args.port)

    # --- LEGAL CHECK ---
    # Display the legal disclaimer at the very start of the execution.
    if not show_legal_disclaimer():
        sys.exit(0)

    render_banner(console)

    url = args.url

    # Show startup sequence only if running purely interactively (no URL arg)
    if not url and not args.audio:
        show_startup_sequence(console, lang)
        
        # Display the selection menu
        console.print(Panel(
            f"[bold green]{lang.get('menu_option_url')}[/]\n"
            f"[bold cyan]{lang.get('menu_option_sync')}[/]",
            title=lang.get("menu_start_title"),
            border_style="blue",
            expand=False
        ))

        choice = Prompt.ask(
            f"[bold white]➤ {lang.get('menu_choice')}[/]", 
            choices=["1", "2"], 
            default="1"
        )

        # OPTION 2: Sync Mode (Direct VantaEngine)
        if choice == "2":
            console.print(Panel(
                lang.get("protected_desc"),
                title=lang.get("protected_site"),
                border_style="yellow",
                expand=False
            ))
            try:
                engine = VantaEngine(enable_console=args.console)
                engine.run()
            except Exception as e:
                console.print(f"[bold red]{lang.get('vanta_engine_error', error=e)}[/]")
            return
    
    # Determine URL: From CLI argument or Interactive Prompt (If Option 1 selected or args empty)
    if not url:
        url = Prompt.ask(f"[bold white]➤ {lang.get('target_url')}[/]", default="").strip()
    
    if not url:
        return

    # Basic URL sanitation
    if not url.startswith("http"):
        url = "https://" + url

    is_native, ie_name = is_natively_supported(url)

    if is_native:
        console.print(Panel(
            lang.get("native_desc", url=url),
            title=lang.get("native_platform", name=ie_name.upper() if ie_name else "UNKNOWN"),
            border_style="green",
            expand=False
        ))
        try:
            downloader = DownloadManager()
            downloader.native_download(url, audio_only=args.audio)
        except Exception as e:
            console.print(f"[bold red]{lang.get('native_mode_error', error=e)}[/]")
    else:
        # Fallback to Manual/Sync Mode (Engine) if native support fails
        console.print(Panel(
            lang.get("protected_desc"),
            title=lang.get("protected_site"),
            border_style="yellow",
            expand=False
        ))
        try:
            # Fallback mode: Pass console flag
            engine = VantaEngine(enable_console=args.console)
            engine.run() 
        except Exception as e:
            console.print(f"[bold red]{lang.get('vanta_engine_error', error=e)}[/]")


if __name__ == "__main__":
    main()