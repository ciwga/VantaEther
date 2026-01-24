import sys
import json
import locale
from pathlib import Path
from typing import Dict, Optional, Any, Union, List

from vantaether.exceptions import ConfigurationError


class LanguageManager:
    """
    Manages loading and retrieving localized strings for the application.
    
    This class handles JSON-based locale files, system language detection,
    and safe string formatting to prevent runtime crashes due to missing translations.
    """

    def __init__(self, lang_code: Optional[str] = None) -> None:
        """
        Initialize the LanguageManager.

        Args:
            lang_code (Optional[str]): Explicit language code ('en', 'tr'). 
                                       Defaults to system locale if None.
        """
        self.base_path: Path = Path(__file__).resolve().parent.parent / "locales"
        
        self.lang_code: str = lang_code or self._detect_system_lang()
        self.strings: Dict[str, Any] = self._load_strings()

    def _detect_system_lang(self) -> str:
        """
        Detects the system's default language safely.

        Returns:
            str: 'tr' if the system is Turkish, otherwise defaults to 'en'.
        """
        try:
            sys_lang_code, _ = locale.getdefaultlocale()
            
            if sys_lang_code and sys_lang_code.lower().startswith("tr"):
                return "tr"
        except Exception:
            pass
        return "en"

    def _load_strings(self) -> Dict[str, Any]:
        """
        Loads the JSON localization file for the current language.
        
        Implements a fallback mechanism:
        1. Try requested language (e.g., 'tr.json').
        2. If missing, fallback to 'en.json'.
        3. If both missing, return empty dict (prevent crash).

        Returns:
            Dict[str, Any]: The loaded dictionary of localized strings.
        """
        file_path = self.base_path / f"{self.lang_code}.json"
        
        if not file_path.exists():
            file_path = self.base_path / "en.json"
        
        if not file_path.exists():
            sys.stderr.write(f"[Critical] Locale files not found at: {self.base_path}\n")
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"[Error] Failed to parse locale JSON ({file_path.name}): {e}\n")
            return {}
        except Exception as e:
            sys.stderr.write(f"[Critical] Unexpected error loading locales: {e}\n")
            return {}

    def get(self, key: str, **kwargs: Any) -> str:
        """
        Retrieve a localized string by key and format it with provided arguments.

        Features:
        - Handles list values by joining them with newlines.
        - Safely handles missing formatting arguments (prevents KeyError).
        - Returns the key itself if the translation is missing.

        Args:
            key (str): The key identifier in the JSON file.
            **kwargs: Arguments for string interpolation (e.g., filename="video.mp4").

        Returns:
            str: The formatted localized string.
        """
        val = self.strings.get(key, key)
        
        if isinstance(val, list):
            val = "\n".join(val)
        
        val_str = str(val)

        if not kwargs:
            return val_str

        try:
            return val_str.format(**kwargs)
        except KeyError as e:
            return f"{val_str} (Missing param: {e})"
        except ValueError as e:
            return f"{val_str} (Format Error: {e})"
        except Exception:
            return val_str