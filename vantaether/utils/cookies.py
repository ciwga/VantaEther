import os
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Set

from rich.console import Console
from vantaether.utils.i18n import LanguageManager
from vantaether.utils.system import DirectoryResolver

# Initialize global instances
console = Console()
lang = LanguageManager()
resolver = DirectoryResolver()

# Constants for Netscape Cookie File format
NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"
NETSCAPE_WARNING = "# This is a generated file! Do not edit.\n\n"
MAX_EXPIRATION_DATE = 2147483647  # 2038-01-19 (32-bit signed integer max)


def _get_root_domain(hostname: str) -> str:
    """Extracts the root domain from a hostname using a naive heuristic.

    Used primarily to compare if two URLs share the same root scope (e.g.,
    'cdn.example.com' and 'www.example.com').

    Args:
        hostname (str): The hostname to parse (e.g., 'video.cdn.example.co.uk').

    Returns:
        str: The last two segments of the hostname (e.g., 'example.co.uk' or 'google.com').
        Returns the original hostname if it has fewer than 2 segments.
    """
    if not hostname:
        return ""
    
    parts = hostname.split('.')
    # Naive TLD extraction: assumes the last two parts constitute the root domain.
    # While not perfect for all TLDs (like .uk vs .co.uk), it suffices for
    # internal origin matching logic.
    if len(parts) > 2:
        return ".".join(parts[-2:])
    
    return hostname


def _generate_domain_variants(url: str) -> Set[str]:
    """Generates a set of valid cookie domain scopes for a given URL.

    This implements the 'Universal Spray' logic, ensuring that cookies are
    available to the host, its subdomains, and its parent domains, increasing
    the success rate of media downloads.

    Args:
        url (str): The target URL to parse.

    Returns:
        Set[str]: A set of domain strings suitable for Netscape cookie files.
    """
    domains: Set[str] = set()
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return domains

        # Handle Localhost, IPs, or non-standard hosts
        is_ip_or_local = (
            hostname == "localhost" or 
            hostname.replace(".", "").isdigit() or 
            ":" in hostname
        )
        if is_ip_or_local:
            domains.add(hostname)
            return domains

        # 1. Add exact hostname (e.g., "video.example.com")
        domains.add(hostname)
        # 2. Add dot-prefixed version (e.g., ".video.example.com")
        domains.add(f".{hostname}")

        # 3. Walk up the domain tree to broaden scope
        # If we have 'a.b.c.com', we want to also cover '.b.c.com' and '.c.com'
        parts = hostname.split('.')
        current_parts = parts

        # Keep strictly more than 2 parts to avoid stripping TLDs like '.com'
        while len(current_parts) > 2:
            current_parts = current_parts[1:]  # Remove the leading subdomain
            root = ".".join(current_parts)
            domains.add(f".{root}")
            
    except Exception:
        # If parsing fails entirely, return whatever domains were gathered (if any)
        pass
    
    return domains


def create_cookie_file(
    cookie_str: str, 
    url: str, 
    ref_url: Optional[str] = None
) -> str:
    """Creates a Netscape-formatted HTTP cookie file using 'Universal Domain Spraying'.

    This function parses a raw cookie string and registers it against multiple
    domain variants to ensure maximum compatibility with tools like yt-dlp or ffmpeg.
    It includes security checks to prevent Cross-Origin pollution.

    Args:
        cookie_str (str): The raw 'Cookie' header string from the browser.
        url (str): The direct URL of the media stream/file.
        ref_url (Optional[str]): The URL of the page where the media was found.
            Used to inject referer-based cookies if the domains match.

    Returns:
        str: The absolute path to the generated temporary cookie file. 
        Returns an empty string if generation fails or no valid domains are found.
    """
    app_dir: Path = resolver.resolve_download_directory()
    filename: Path = app_dir / f"cookies_{int(time.time())}.txt"
    
    target_domains: Set[str] = set()

    # 1. Generate variants for Video URL (Primary Target)
    target_domains.update(_generate_domain_variants(url))

    # 2. Generate variants for Referer URL (Conditional Target)
    # Prevent spraying cookies from a Referer to a totally different
    # Video domain (e.g., watching a Twitter video embedded on a blog).
    # Mismatched cookies can cause 403 Forbidden errors on strict CDNs.
    if ref_url:
        try:
            v_host = urlparse(url).hostname
            r_host = urlparse(ref_url).hostname
            
            if v_host and r_host:
                v_root = _get_root_domain(v_host)
                r_root = _get_root_domain(r_host)

                # Only mix domains if they share a common root (e.g., same organization)
                if v_root == r_root:
                    target_domains.update(_generate_domain_variants(ref_url))
                else:
                    # Log logic could go here; currently implicit skip for safety.
                    pass
        except Exception:
            # Fallback: If heuristic checks fail, ignore referer domains to be safe.
            pass

    if not target_domains:
        return ""

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(NETSCAPE_HEADER)
            f.write(NETSCAPE_WARNING)
            
            if cookie_str:
                for cookie in cookie_str.split(";"):
                    cookie = cookie.strip()
                    if not cookie or "=" not in cookie:
                        continue
                        
                    try:
                        name, value = cookie.split("=", 1)
                        
                        # Register this cookie for EVERY identified domain variant.
                        # This increases the likelihood that the download tool sends the cookie
                        # regardless of which subdomain it resolves to.
                        for domain in target_domains:
                            # 'TRUE' if domain starts with a dot (subdomain matching), else 'FALSE'
                            flag = "TRUE" if domain.startswith(".") else "FALSE"
                            
                            # Netscape Format:
                            # domain | flag | path | secure | expiration | name | value
                            # Secure is explicitly set to FALSE to allow mixed-content usage.
                            line = (
                                f"{domain}\t{flag}\t/\tFALSE\t"
                                f"{MAX_EXPIRATION_DATE}\t{name}\t{value}\n"
                            )
                            f.write(line)
                            
                    except ValueError:
                        # Skip malformed cookies that don't split correctly
                        continue
        
        # Set file permissions to Read/Write for owner only
        try:
            os.chmod(filename, 0o600)
        except OSError:
            # Ignore permission errors on systems that don't support chmod (e.g., some Windows filesystems)
            pass

        return str(filename)

    except IOError as e:
        console.print(f"[bold red]{lang.get('cookie_file_error', error=e)}[/]")
        return ""