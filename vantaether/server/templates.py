from typing import Any
from pathlib import Path


def get_tampermonkey_script() -> str:
    """Reads the JS file from assets."""
    path = Path(__file__).resolve().parent.parent / "assets" / "tampermonkey_script.js"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "// Error: Script file not found."

def render_html_page(lang_manager: Any) -> str:
    """
    Renders the HTML page with localized strings based on the provided LanguageManager.
    
    Args:
        lang_manager: An instance of LanguageManager from i18n.py
        
    Returns:
        str: The complete HTML string with translations injected.
    """
    
    # Helper lambda to shorten calls
    t = lang_manager.get

    return f"""
<!DOCTYPE html>
<html lang="{lang_manager.lang_code}">
<head>
    <meta charset="UTF-8">
    <title>{t('html_page_title')}</title>
    <style>
        body {{ background-color: #0d1117; color: #c9d1d9; font-family: 'Consolas', 'Monaco', monospace; padding: 20px; text-align: center; }}
        h1 {{ color: #00ff41; margin-bottom: 30px; }}
        .container {{ border: 1px solid #30363d; padding: 20px; background: #161b22; margin: 0 auto; max-width: 800px; border-radius: 8px; }}
        textarea {{ width: 100%; height: 200px; background: #0d1117; color: #79c0ff; border: 1px solid #30363d; padding: 10px; border-radius: 4px; resize: none; }}
        
        .btn-group {{ display: flex; gap: 10px; margin-top: 15px; }}
        
        button {{ flex: 1; padding: 15px; border: none; cursor: pointer; font-weight: bold; font-size: 16px; border-radius: 4px; transition: background 0.2s; color: #fff; }}
        
        .btn-copy {{ background: #238636; }}
        .btn-copy:hover {{ background: #2ea043; }}
        
        .btn-install {{ background: #1f6feb; }}
        .btn-install:hover {{ background: #388bfd; }}
        
        .instructions {{ text-align: left; margin: 20px 0; line-height: 1.6; }}
        .status-box {{ font-size: 1.5em; color: #e3b341; margin-top: 30px; padding: 15px; border: 1px dashed #30363d; }}
        .step {{ font-weight: bold; color: #ffffff; }}
        
        a.install-link {{ text-decoration: none; display: flex; flex: 1; }}
    </style>
</head>
<body>
    <h1>{t('html_header')}</h1>
    
    <div class="container">
        <h3>{t('html_instructions_title')}</h3>
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

        <h3>{t('html_script_title')}</h3>
        <textarea id="code" readonly>{{{{ script }}}}</textarea>
        
        <div class="btn-group">
            <button class="btn-copy" onclick="navigator.clipboard.writeText(document.getElementById('code').value);alert('{t('html_copied_alert')}')">
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
        // Server-Sent Events (SSE) for Real-time Updates
        // Replaces inefficient polling (setInterval)
        const evtSource = new EventSource("/stream");
        
        evtSource.onmessage = function(event) {{
            const d = JSON.parse(event.data);
            const videoCount = d.video_count;
            const subCount = d.sub_count;
            
            if(videoCount > 0){{
                let msg = "{t('html_js_videos_prefix')}" + videoCount + " {t('html_js_video_captured')}";
                if(subCount > 0) msg += " | " + subCount + " {t('html_js_subtitle_captured')}";
                
                const el = document.getElementById('status');
                el.innerText = msg;
                el.style.color = "#00ff41";
                el.style.borderColor = "#00ff41";
            }}
        }};
        
        evtSource.onerror = function() {{
            console.log("SSE Connection lost, retrying...");
        }};
    </script>
</body>
</html>
"""