import json
import locale
from pathlib import Path
from typing import Dict, Optional, Any


class LanguageManager:
    """Manages loading and retrieving localized strings."""

    def __init__(self, lang_code: Optional[str] = None):
        """
        Initialize the LanguageManager.

        Args:
            lang_code (str, optional): 'en' or 'tr'. Defaults to system locale.
        """
        self.base_path = Path(__file__).resolve().parent.parent / "locales"
        self.lang_code = lang_code or self._detect_system_lang()
        self.strings: Dict[str, str] = self._load_strings()

    def _detect_system_lang(self) -> str:
        """Detects system language, defaulting to 'en'."""
        try:
            sys_lang, _ = locale.getdefaultlocale()
            if sys_lang and sys_lang.lower().startswith("tr"):
                return "tr"
        except Exception:
            pass
        return "en"

    def _load_strings(self) -> Dict[str, str]:
        """Loads the JSON file for the current language."""
        file_path = self.base_path / f"{self.lang_code}.json"
        if not file_path.exists():
            # Fallback to English if file missing
            file_path = self.base_path / "en.json"
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Critical Error loading locales: {e}")
            return {}

    def get(self, key: str, **kwargs: Any) -> str:
        """
        Retrieve a string by key and format it with kwargs.

        Args:
            key (str): The key in the JSON file.
            **kwargs: Arguments for string formatting (e.g., {filename}).

        Returns:
            str: The formatted string or the key if not found.
        """
        val = self.strings.get(key, key)
        try:
            return val.format(**kwargs)
        except Exception:
            return val