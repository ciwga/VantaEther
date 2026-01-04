import os
import time
from pathlib import Path
from urllib.parse import urlparse
from rich.console import Console
from vantaether.utils.i18n import LanguageManager
from vantaether.utils.system import DirectoryResolver


console = Console()
lang = LanguageManager()
resolver = DirectoryResolver()


def create_cookie_file(cookie_str: str, url: str) -> str:
    """Creates a Netscape-formatted HTTP cookie file from a raw cookie string.

    This function parses a raw "key=value; key2=value2" string and writes it
    to a temporary file in the Netscape cookie format (tab-separated).
    The file is secured with restricted permissions (0o600) to prevent
    unauthorized access.

    Args:
        cookie_str (str): The raw cookie string (e.g., 'session_id=xyz; auth=1').
        url (str): The URL associated with the cookies, used to derive the domain.

    Returns:
        str: The absolute file path of the generated cookie file.
             Returns an empty string if an IOError occurs during creation.
    """
    app_dir: Path = resolver.resolve_download_directory()

    filename: Path = app_dir / f"cookies_{int(time.time())}.txt"
    
    parsed_url = urlparse(url)
    domain_name = parsed_url.hostname
    
    cookie_domain: str = (
        f".{domain_name}" 
        if domain_name and not domain_name.startswith(".") 
        else str(domain_name)
    )

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This is a generated file! Do not edit.\n\n")
            
            if cookie_str:
                for cookie in cookie_str.split("; "):
                    if "=" in cookie:
                        try:
                            name, value = cookie.split("=", 1)
                            
                            # Netscape format fields:
                            # domain, flag, path, secure, expiration, name, value
                            # Expiration is hardcoded to 2147483647 (Jan 2038) for longevity.
                            f.write(
                                f"{cookie_domain}\tTRUE\t/\tFALSE\t2147483647\t{name}\t{value}\n"
                            )
                        except ValueError:
                            continue
        
        try:
            os.chmod(filename, 0o600)
        except OSError:
            pass

        return str(filename)

    except IOError as e:
        console.print(f"[bold red]{lang.get('cookie_file_error', error=e)}[/]")
        return ""