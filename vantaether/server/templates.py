import re
import json
from pathlib import Path
from typing import Any, Optional

import vantaether.config as config
from vantaether.utils.i18n import LanguageManager


_temp_lang = LanguageManager()


def get_tampermonkey_script() -> str:
    """
    Reads the raw UserScript from the assets directory and dynamically injects 
    the active server configuration (Host, Port, URL).
    
    Returns:
        str: The fully configured JavaScript code ready for installation.
    """
    try:
        # Resolve path relative to this file
        path = Path(__file__).resolve().parent.parent / "assets" / "tampermonkey_script.js"
        
        if path.exists():
            raw_content = path.read_text(encoding="utf-8")
            
            # Dynamic Injection
            injected_content = raw_content.replace("{{SERVER_HOST}}", config.SERVER_HOST)
            injected_content = injected_content.replace("{{SERVER_URL}}", config.SERVER_URL)
            injected_content = injected_content.replace("{{SERVER_PORT}}", str(config.SERVER_PORT))
            
            return injected_content
            
        return _temp_lang.get("script_file_error", path=path)
        
    except Exception as e:
        return _temp_lang.get("script_read_error", error=e)


def get_script_version() -> str:
    """
    Extracts the version number directly from the UserScript header metadata.
    
    Returns:
        str: The version string (e.g. '3.0') or '?.?' if parsing fails.
    """
    content: str = get_tampermonkey_script()

    # Regex to find @version tag with tolerance for whitespace
    version_pattern = r"//\s*@version\s+([^\s]+)"
    match = re.search(version_pattern, content)

    return match.group(1) if match else "?.?"


def render_html_page(lang_manager: LanguageManager) -> str:
    """
    Generates the complete HTML dashboard for the user.
    
    Uses robust JSON serialization for injecting Python strings into JavaScript
    to prevent syntax errors caused by quotes or special characters in translations.

    Args:
        lang_manager: The language manager instance for localization.

    Returns:
        str: The rendered HTML document.
    """
    t = lang_manager.get
    
    script_ver = get_script_version()
    script_content = get_tampermonkey_script()

    # Safe Title Formatting
    raw_title_fmt = t('html_script_title')
    try:
        script_title = raw_title_fmt.format(version=script_ver)
    except (KeyError, ValueError):
        script_title = f"{raw_title_fmt} (v{script_ver})"

    # --- SAFE JAVASCRIPT VARS ---
    js_alert_copied = json.dumps(t('html_copied_alert'))
    js_prefix = json.dumps(t('html_js_videos_prefix'))
    js_vid_cap = json.dumps(t('html_js_video_captured'))
    js_sub_cap = json.dumps(t('html_js_subtitle_captured'))
    js_conn_lost = json.dumps(t('sse_connection_lost'))

    # --- HTML STRUCTURE ---
    html = f"""
<!DOCTYPE html>
<html lang="{getattr(lang_manager, 'lang_code', 'en')}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{t('html_page_title')}</title>
    <style>
        :root {{
            --bg-dark: #0d1117;
            --bg-panel: #161b22;
            --border: #30363d;
            --text-main: #c9d1d9;
            --text-accent: #58a6ff;
            --success: #238636;
            --success-hover: #2ea043;
            --primary: #1f6feb;
            --primary-hover: #388bfd;
        }}
        body {{ 
            background-color: var(--bg-dark); 
            color: var(--text-main); 
            font-family: 'Segoe UI', 'Roboto', monospace; 
            padding: 20px; 
            text-align: center; 
        }}
        h1 {{ color: #00ff41; margin-bottom: 20px; letter-spacing: 1px; font-family: monospace; }}
        h3 {{ color: var(--text-accent); margin-top: 0; }}
        
        .container {{ 
            border: 1px solid var(--border); 
            padding: 25px; 
            background: var(--bg-panel); 
            margin: 0 auto; 
            max-width: 800px; 
            border-radius: 8px; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.4); 
        }}
        
        textarea {{ 
            width: 100%; 
            height: 200px; 
            background: #090c10; 
            color: #79c0ff; 
            border: 1px solid var(--border); 
            padding: 12px; 
            border-radius: 6px; 
            resize: none; 
            font-family: 'Consolas', monospace; 
            font-size: 13px; 
            box-sizing: border-box;
        }}
        textarea:focus {{ outline: 1px solid var(--text-accent); }}
        
        .btn-group {{ display: flex; gap: 15px; margin-top: 20px; }}
        
        button {{ 
            flex: 1; 
            padding: 14px; 
            border: 1px solid rgba(240,246,252,0.1); 
            cursor: pointer; 
            font-weight: 600; 
            font-size: 15px; 
            border-radius: 6px; 
            transition: all 0.2s; 
            color: #fff; 
        }}
        
        .btn-copy {{ background: var(--success); }}
        .btn-copy:hover {{ background: var(--success-hover); transform: translateY(-1px); }}
        
        .btn-install {{ background: var(--primary); }}
        .btn-install:hover {{ background: var(--primary-hover); transform: translateY(-1px); }}
        
        .instructions {{ 
            text-align: left; 
            margin: 25px 0; 
            line-height: 1.6; 
            border-top: 1px solid var(--border); 
            border-bottom: 1px solid var(--border); 
            padding: 20px 5px;
            font-size: 15px;
        }}
        
        .step {{ font-weight: bold; color: #fff; margin-bottom: 2px; margin-top: 12px; }}
        .step:first-child {{ margin-top: 0; }}
        
        .status-box {{ 
            font-size: 1.1em; 
            color: #8b949e; 
            margin-top: 30px; 
            padding: 15px; 
            border: 1px dashed var(--border); 
            background: var(--bg-panel); 
            border-radius: 6px; 
            font-family: monospace;
            transition: all 0.3s ease;
        }}
        
        a.install-link {{ text-decoration: none; display: flex; flex: 1; }}
    </style>
</head>
<body>
    <h1>{t('html_header')}</h1>
    
    <div class="container">
        <h3>{script_title}</h3>
        
        <div class="instructions">
            <div class="step">1. {t('html_step1')}</div>
            <span style="color: #8b949e">{t('html_step1_desc')}</span>
            
            <div class="step">2. {t('html_step2')}</div>
            <span style="color: #8b949e">{t('html_step2_desc')}</span>
            
            <div class="step">3. {t('html_step3')}</div>
            <span style="color: #8b949e">{t('html_step3_desc')}</span>
            
            <div class="step">4. {t('html_step4')}</div>
            <span style="color: #8b949e">{t('html_step4_desc')}</span>
            
            <div class="step">5. {t('html_step5')}</div>
            <span style="color: #8b949e">{t('html_step5_desc')}</span>
        </div>
        
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
            copyText.setSelectionRange(0, 99999);
            
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(copyText.value)
                    .then(() => alert({js_alert_copied}))
                    .catch(err => console.error('Failed to copy: ', err));
            }} else {{
                document.execCommand('copy');
                alert({js_alert_copied});
            }}
        }}

        const evtSource = new EventSource("/stream");
        
        evtSource.onmessage = function(event) {{
            try {{
                const d = JSON.parse(event.data);
                const videoCount = d.video_count || 0;
                const subCount = d.sub_count || 0;
                
                if(videoCount > 0){{
                    let msg = {js_prefix} + " " + videoCount + " " + {js_vid_cap};
                    if(subCount > 0) msg += " | " + subCount + " " + {js_sub_cap};
                    
                    const el = document.getElementById('status');
                    el.innerText = msg;
                    el.style.color = "#00ff41";
                    el.style.borderColor = "#00ff41";
                    el.style.borderStyle = "solid";
                    el.style.backgroundColor = "rgba(0, 255, 65, 0.05)";
                }}
            }} catch(e) {{
                console.error("Error parsing SSE data", e);
            }}
        }};
        
        evtSource.onerror = function() {{
            console.warn({js_conn_lost});
        }};
    </script>
</body>
</html>
"""
    return html