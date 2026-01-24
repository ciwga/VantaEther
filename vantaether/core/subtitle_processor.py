import re
import os
from urllib.parse import urlparse
from typing import Any, Dict, List, Pattern, Set, Optional

from rich.console import Console
from vantaether.utils.i18n import LanguageManager


console = Console()
lang = LanguageManager()


class SubtitleProcessor:
    """
    Handles the processing of captured subtitle data and management of external sources.

    This class encapsulates the logic for detecting languages from URLs using Regex,
    validating file extensions, and mapping captured subtitle streams to the
    application's internal format, replacing standard logging with Rich UI output.
    
    Now supports truly universal language detection via ISO 639 standard mapping
    and neutral fallback logic.

    Attributes:
        capture_manager (Any): Manager instance providing snapshot data.
        _lang_pattern (Pattern): Pre-compiled regex for generic language code detection.
        _valid_languages (Set[str]): A set of valid ISO language codes to prevent false positives.
        _iso_map (Dict[str, str]): Mapping for common 3-letter codes to 2-letter ISO 639-1 codes.
    """

    def __init__(self, capture_manager: Any) -> None:
        """
        Initializes the SubtitleProcessor with capture management and detection patterns.

        Args:
            capture_manager (Any): Instance with a get_snapshot() method.
        """
        self.capture_manager = capture_manager

        # Pre-compile Regex pattern for performance optimizations.
        # Description: Searches for 2 or 3 letter alphabetic codes surrounded by delimiters.
        # Matches: file.tr.vtt, /en/subs, _fra_, -de-
        # The group (1) captures the candidate code.
        self._lang_pattern: Pattern = re.compile(
            r'(?:^|[./_-])([a-z]{2,3})(?:$|[./_-])', 
            re.IGNORECASE
        )

        # Mapping common ISO 639-2/B (3-letter) codes to ISO 639-1 (2-letter).
        # This ensures universal normalization (e.g., 'ger' -> 'de', 'tur' -> 'tr').
        self._iso_map: Dict[str, str] = {
            "tur": "tr", "eng": "en", "fre": "fr", "fra": "fr", 
            "ger": "de", "deu": "de", "spa": "es", "ita": "it",
            "por": "pt", "rus": "ru", "jpn": "ja", "kor": "ko",
            "chi": "zh", "zho": "zh", "ara": "ar", "dut": "nl", 
            "nld": "nl", "swe": "sv", "dan": "da", "nob": "no",
            "fin": "fi", "ell": "el", "gre": "el", "pol": "pl"
        }

        # Set of common ISO 639-1 and 639-2/B codes to validate regex matches.
        # This prevents matching non-language strings like "hd", "hq", "dolby", etc.
        self._valid_languages: Set[str] = frozenset({
            "aa", "ab", "af", "am", "ar", "as", "ay", "az", "ba", "be", "bg", "bh", "bi", 
            "bn", "bo", "br", "ca", "co", "cs", "cy", "da", "de", "dz", "el", "en", "eo", 
            "es", "et", "eu", "fa", "fi", "fj", "fo", "fr", "fy", "ga", "gd", "gl", "gn", 
            "gu", "ha", "he", "hi", "hr", "hu", "hy", "ia", "id", "ie", "ik", "in", "is", 
            "it", "iu", "iw", "ja", "ji", "jw", "ka", "kk", "kl", "km", "kn", "ko", "ks", 
            "ku", "ky", "la", "ln", "lo", "lt", "lv", "mg", "mi", "mk", "ml", "mn", "mo", 
            "mr", "ms", "mt", "my", "na", "ne", "nl", "no", "oc", "om", "or", "pa", "pl", 
            "ps", "pt", "qu", "rm", "rn", "ro", "ru", "rw", "sa", "sd", "sg", "sh", "si", 
            "sk", "sl", "sm", "sn", "so", "sq", "sr", "ss", "st", "su", "sv", "sw", "ta", 
            "te", "tg", "th", "ti", "tk", "tl", "tn", "to", "tr", "ts", "tt", "tur", "tw", 
            "uk", "ur", "uz", "vi", "vo", "wo", "xh", "yi", "yo", "za", "zh", "zu",
            "eng", "tur", "fra", "ger", "spa", "ita", "rus", "jpn", "kor", "chi", "ara"
        } | set(self._iso_map.keys()))

    def _detect_language(self, text_segment: str) -> Optional[str]:
        """
        Extracts and validates a language code from a given text segment (filename/path).

        Args:
            text_segment (str): The string to search (e.g., filename or path).

        Returns:
            Optional[str]: The detected ISO 639-1 code (e.g., 'tr', 'en') or None if not found.
        """
        # Find all candidate matches in the string
        matches: List[str] = self._lang_pattern.findall(text_segment)
        
        # Iterate matches in reverse order (usually the lang code is closer to the end/extension)
        for match in reversed(matches):
            candidate = match.lower()
            if candidate in self._valid_languages:
                # Universal Normalization: Map 3-letter codes to 2-letter if in map,
                # otherwise return the candidate as is.
                return self._iso_map.get(candidate, candidate)
        
        return None  # Return explicit None instead of default "en"

    def process_subtitles(self, subs_map: Dict[str, Any], start_idx: int) -> int:
        """
        Processes subtitle data from the snapshot pool and updates the provided map.

        This method retrieves the current snapshot of captured subtitles, iterates
        through them, and applies heuristic analysis to determine the language and
        file extension. It populates the 'subs_map' in-place.

        Args:
            subs_map (Dict[str, Any]): The dictionary to populate with processed subtitles.
            start_idx (int): The starting index for the subtitle ID counter.

        Returns:
            int: The updated index counter after adding new subtitles.
        """
        # Retrieve the data pool from the source
        pool: Dict[str, Any] = self.capture_manager.get_snapshot()
        
        # Safely get the list, defaulting to empty list if key is missing
        subs_list: List[Dict[str, Any]] = pool.get("subs", [])
        
        current_idx = start_idx

        for s_data in subs_list:
            try:
                url: str = s_data.get("url", "")
                
                if not url:
                    console.print(f"[dim yellow]{lang.get('sub_capture_warning', current_idx=current_idx)}[/]")
                    continue

                parsed_url = urlparse(url)
                path: str = parsed_url.path
                filename: str = os.path.basename(path).lower()
                
                s_lang: Optional[str] = self._detect_language(filename)
                
                # If filename yielded no results, fall back to checking the full path.
                if s_lang is None:
                     s_lang = self._detect_language(path)
                
                # If both checks failed, apply a universal default.
                if s_lang is None:
                    s_lang = "en"

                # 2. Extension Detection (Strict checking)
                # Checks the end of the filename explicitly rather than substring search
                ext_type: str = "vtt"
                if filename.endswith(".vtt"):
                    ext_type = "vtt"
                elif filename.endswith(".srt"):
                    ext_type = "srt"
                else:
                    if ".srt" in filename:
                        ext_type = "srt"

                # Map the processed data
                subs_map[str(current_idx)] = {
                    "type": "external",
                    "lang": f"{s_lang} (Ext)",
                    "url": url,
                    "ext": ext_type,
                }

                current_idx += 1

            except Exception as e:
                error_msg = lang.get("capture_add_error", error=str(e))
                console.print(f"[dim red]{error_msg}[/]")
                continue

        return current_idx