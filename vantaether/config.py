from typing import Final
from vantaether.utils.i18n import LanguageManager


lang = LanguageManager()


VERSION: Final[str] = "2.0"

BANNER: Final[str] = rf"""
[bold white]██╗   ██╗ █████╗ ███╗   ██╗████████╗ █████╗[/]
[bold white]██║   ██║██╔══██╗████╗  ██║╚══██╔══╝██╔══██╗[/]
[bold white]██║   ██║███████║██╔██╗ ██║   ██║   ███████║[/]
[bold white]╚██╗ ██╔╝██╔══██║██║╚██╗██║   ██║   ██╔══██║[/]
[bold white] ╚████╔╝ ██║  ██║██║ ╚████║   ██║   ██║  ██║[/]
[bold white]  ╚═══╝  ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝[/]
           [bold white on #007acc] V A N T A [/][bold black on white] E T H E R [/] [bold cyan]v{VERSION}[/]
       [dim]━━━ [italic]{lang.get('app_description')}[/] ━━━[/]
"""

# ███████╗████████╗██╗  ██╗███████╗██████╗ 
# ██╔════╝╚══██╔══╝██║  ██║██╔════╝██╔══██╗
# █████╗     ██║   ███████║█████╗  ██████╔╝
# ██╔══╝     ██║   ██╔══██║██╔══╝  ██╔══██╗
# ███████╗   ██║   ██║  ██║███████╗██║  ██║
# ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
