from typing import Dict, Optional

class HeaderFactory:
    """Centralizes the logic for generating HTTP headers suitable for specific domains.

    This class serves as a factory for creating robust HTTP headers, replacing
    scattered domain checks. It specifically handles 'Referer' and 'Origin'
    spoofing for strict domains like Twitter/X or Instagram.
    """

    # Domain-specific rules for Referer and Origin spoofing.
    # Key: Substring to match in the URL.
    # Value: The strictly required Referer/Origin URL.
    DOMAIN_RULES: Dict[str, str] = {
        "twimg.com": "https://twitter.com/",
        "twitter.com": "https://twitter.com/",
        "x.com": "https://x.com/",
        "instagram.com": "https://www.instagram.com/",
        # Add future domains here easily
    }

    @staticmethod
    def get_headers(
        target_url: str,
        page_url: Optional[str] = None,
        user_agent: str = "Mozilla/5.0"
    ) -> Dict[str, str]:
        """Generates a robust set of HTTP headers based on the target URL.

        Automatically applies domain-specific overrides for 'Referer' and 'Origin'
        headers by matching the target URL against known strict domains defined
        in DOMAIN_RULES.

        Args:
            target_url (str): The direct URL of the media stream or resource.
            page_url (Optional[str]): The webpage URL where the media was found.
                If None, 'target_url' is used as the default referer.
            user_agent (str): The User-Agent string to be sent with the request.
                Defaults to a standard "Mozilla/5.0".

        Returns:
            Dict[str, str]: A dictionary containing standard and spoofed HTTP headers
            suitable for requests (e.g., requests.get or aiohttp).
        """
        # Convert to lower case for case-insensitive matching against rules.
        target_url_lower = target_url.lower()

        # Default Logic: Use the page_url if provided, otherwise fallback to target.
        final_referer = page_url if page_url else target_url

        # Calculate Origin from the Referer (Protocol + Domain).
        # Logic: Split by '/' and take the first 3 parts to reconstruct the root.
        # Example: 'https://example.com/page/1' -> ['https:', '', 'example.com'] -> 'https://example.com'
        origin_parts = final_referer.split("/")[:3]
        final_origin = "/".join(origin_parts)

        # --- Rule-Based Override System ---
        # Scan the target URL against known strict domains in the configuration.
        for domain_key, fixed_root in HeaderFactory.DOMAIN_RULES.items():
            if domain_key in target_url_lower:
                # Override Referer with the strict domain root.
                final_referer = fixed_root
                # Override Origin (remove trailing slash for Origin header correctness).
                final_origin = fixed_root.rstrip("/")
                break

        # Construct the final headers dictionary with standard browser-like fields.
        headers: Dict[str, str] = {
            "User-Agent": user_agent,
            "Referer": final_referer,
            "Origin": final_origin,
            "Accept": "*/*",
            # Hardcoded language preference, likely for specific regional content bypassing.
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }

        return headers