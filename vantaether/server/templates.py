import re
from typing import Any
from pathlib import Path
from vantaether.utils.i18n import LanguageManager


_temp_lang = LanguageManager()


def get_tampermonkey_script() -> str:
    """Reads the JS file from assets."""
    path = Path(__file__).resolve().parent.parent / "assets" / "tampermonkey_script.js"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return _temp_lang.get("script_not_found")

def get_script_version() -> str:
    """Extracts the version number directly from the UserScript header.

    This function parses the script content using a regex designed to be tolerant
    of variable whitespace between the comment markers and the version tag.

    Returns:
        str: The extracted version number (e.g., '3.0') if found,
             otherwise returns '?.?'.
    """
    content: Optional[str] = get_tampermonkey_script()

    if not content:
        return "?.?"

    version_pattern: str = r"//\s*@version\s+([^\s]+)"

    rmatch: Optional[re.Match] = re.search(version_pattern, content)

    return rmatch.group(1) if rmatch else "?.?"

def render_html_page(lang_manager: Any) -> str:
    """Renders the HTML page with localized strings and injected script content.

    Args:
        lang_manager: An instance of LanguageManager containing translation logic.

    Returns:
        str: The complete, localized HTML document string.
    """
    # Helper lambda to shorten calls and improve readability within f-strings
    t = lang_manager.get
    
    # Get the dynamic version from the actual JS file
    script_ver: str = get_script_version()
    script_content: str = get_tampermonkey_script()

    # Format the title with the version
    raw_title_fmt = t('html_script_title')
    try:
        script_title = raw_title_fmt.format(version=script_ver)
    except (KeyError, ValueError):
        # Fallback if format placeholder {version} is missing in JSON or invalid
        script_title = f"{raw_title_fmt} (v{script_ver})"

    # HTML Template Construction
    return f"""
<!DOCTYPE html>
<html lang="{getattr(lang_manager, 'lang_code', 'en')}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{t('html_page_title')}</title>
    <style>
        body {{ background-color: #0d1117; color: #c9d1d9; font-family: 'Consolas', 'Monaco', monospace; padding: 20px; text-align: center; }}
        h1 {{ color: #00ff41; margin-bottom: 30px; letter-spacing: 1px; }}
        h3 {{ color: #79c0ff; }}
        .container {{ border: 1px solid #30363d; padding: 20px; background: #161b22; margin: 0 auto; max-width: 800px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
        textarea {{ width: 100%; height: 200px; background: #0d1117; color: #79c0ff; border: 1px solid #30363d; padding: 10px; border-radius: 4px; resize: none; font-family: inherit; font-size: 12px; }}
        
        .btn-group {{ display: flex; gap: 10px; margin-top: 15px; }}
        
        button {{ flex: 1; padding: 15px; border: none; cursor: pointer; font-weight: bold; font-size: 16px; border-radius: 4px; transition: all 0.2s; color: #fff; }}
        
        .btn-copy {{ background: #238636; border: 1px solid rgba(240,246,252,0.1); }}
        .btn-copy:hover {{ background: #2ea043; transform: translateY(-1px); }}
        
        .btn-install {{ background: #1f6feb; border: 1px solid rgba(240,246,252,0.1); }}
        .btn-install:hover {{ background: #388bfd; transform: translateY(-1px); }}
        
        .instructions {{ text-align: left; margin: 20px 0; line-height: 1.6; border-top: 1px solid #30363d; border-bottom: 1px solid #30363d; padding: 20px 0; }}
        .status-box {{ font-size: 1.2em; color: #e3b341; margin-top: 30px; padding: 15px; border: 1px dashed #30363d; background: #0d1117; border-radius: 6px; }}
        .step {{ font-weight: bold; color: #ffffff; margin-bottom: 4px; }}
        
        a.install-link {{ text-decoration: none; display: flex; flex: 1; }}
        
        /* Scrollbar styling for textarea */
        textarea::-webkit-scrollbar {{ width: 10px; }}
        textarea::-webkit-scrollbar-track {{ background: #0d1117; }}
        textarea::-webkit-scrollbar-thumb {{ background: #30363d; border-radius: 5px; }}
        textarea::-webkit-scrollbar-thumb:hover {{ background: #58a6ff; }}
    </style>
</head>
<body>
    <h1>{t('html_header')}</h1>
    
    <div class="container">
        <!-- Display Title with Version -->
        <h3>{script_title}</h3>
        
        <div class="instructions">
            <div class="step">{t('html_step1')}</div>
            {t('html_step1_desc')}<br><br>
            <div class="step">{t('html_step2')}</div>
            {t('html_step2_desc')}<br><br>
            <div class="step">{t('html_step3')}</div>
            {t('html_step3_desc')}<br><br>
            <div class="step">{t('html_step4')}</div>
            {t('html_step4_desc')}<br><br>
            <div class="step">{t('html_step5')}</div>
            {t('html_step5_desc')}
        </div>

        <h3>{script_title}</h3> 
        
        <textarea id="code" readonly>{script_content}</textarea>
        
        <div class="btn-group">
            <button class="btn-copy" onclick="copyToClipboard()">
                {t('html_copy_btn')}
            </button>
            <a href="/vantaether.user.js" class="install-link">
                <button class="btn-install">
                    {t('html_install_btn')}
                </button>
            </a>
        </div>
    </div>

    <div id="status" class="status-box">{t('html_status_waiting')}</div>
    
    <script>
        function copyToClipboard() {{
            const copyText = document.getElementById('code');
            copyText.select();
            copyText.setSelectionRange(0, 99999); // For mobile devices
            
            // Modern clipboard API usage
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(copyText.value)
                    .then(() => alert('{t('html_copied_alert')}'))
                    .catch(err => console.error('Failed to copy: ', err));
            }} else {{
                // Fallback for older browsers / non-secure contexts
                document.execCommand('copy');
                alert('{t('html_copied_alert')}');
            }}
        }}

        // Server-Sent Events (SSE) for Real-time Updates
        const evtSource = new EventSource("/stream");
        
        evtSource.onmessage = function(event) {{
            try {{
                const d = JSON.parse(event.data);
                const videoCount = d.video_count || 0;
                const subCount = d.sub_count || 0;
                
                if(videoCount > 0){{
                    let msg = "{t('html_js_videos_prefix')}" + videoCount + " {t('html_js_video_captured')}";
                    if(subCount > 0) msg += " | " + subCount + " {t('html_js_subtitle_captured')}";
                    
                    const el = document.getElementById('status');
                    el.innerText = msg;
                    el.style.color = "#00ff41";
                    el.style.borderColor = "#00ff41";
                    el.style.borderStyle = "solid";
                }}
            }} catch(e) {{
                console.error("Error parsing SSE data", e);
            }}
        }};
        
        evtSource.onerror = function() {{
            console.warn("{t('sse_connection_lost')}");
            // EventSource usually auto-reconnects, no manual logic needed unless complex handling required
        }};
    </script>
</body>
</html>
"""