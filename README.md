# VantaEther

![Version](https://img.shields.io/badge/version-2.2.0-blue?style=flat-square)
![Python](https://img.shields.io/badge/python-3.8+-yellow?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20Android-lightgrey?style=flat-square)

**VantaEther** is a next-generation media toolkit for sniffing, analyzing, and downloading video streams. It's engineered to succeed where other tools fail, effortlessly capturing complex, protected, or obfuscated streams directly from your browser.

By combining a modern Terminal UI (`rich`), a modular Python backend, and a powerful browser-side agent, VantaEther provides a seamless workflow for even the most challenging streaming scenarios.



## 🚀 Key Features

### 1. Intelligent Stream Discovery Engine
VantaEther's core strength is its multi-layered detection system that goes far beyond simple URL matching.

*   **Header-Based Sniffing:** Automatically detects video manifests (HLS/DASH) by analyzing `Content-Type` headers, bypassing URL obfuscation used by many modern streaming sites.
*   **JSON API Parsing:** Proactively scans captured API endpoints, recursively searching through JSON data to discover direct video links and quality options before they even load in a player.
*   **Broad Manifest & Codec Support:** Captures everything from standard MP4s and WebMs to adaptive streaming manifests like M3U8 (HLS) and MPD (DASH).

### 2. Advanced Media Processing
Once a stream is captured, VantaEther provides powerful tools to download and assemble it exactly how you want.

*   **Multi-Track Merging (Audio & Subtitles):** Select and download multiple audio languages and subtitle tracks, which are then perfectly merged into a single MKV or MP4 file with correct language metadata tagging.
*   **Quality Selection:** For streams with multiple quality options, VantaEther presents a clean table for you to choose the desired resolution.
*   **Automated Merging:** Automatically handles the merging of separate video-only and audio-only streams, a common practice on sites like YouTube.
*   **Technical Reporting:** Generates a detailed JSON report for every download, containing codec info, resolution, bitrate, and source data via its integrated `ffprobe` analyzer.

### 3. Robust Browser & Network Integration
The connection between your browser and terminal is designed to be resilient and powerful.

*   **Dual Mode Operation:**
    *   **Native Mode:** For direct, high-speed downloads from `yt-dlp` supported platforms.
    *   **Sync Mode (Sniffer):** A local server pairs with a browser UserScript (Tampermonkey/Violentmonkey) to capture streams directly from any site as you browse.
*   **Smart Header & Cookie Management:** Intelligently spoofs `Referer`/`Origin` headers and sprays authentication cookies across subdomains to defeat CDN protections and minimize 403 errors.
*   **Resilient Capture:** The browser agent queues captured links offline and transmits them automatically when the server connection is restored. It also includes memory protection to prevent leaks during long sniffing sessions.


## 🛠️ Prerequisites

### 1. Python
VantaEther requires **Python 3.8** or higher.

### 2. FFmpeg (Critical)
The application relies heavily on **FFmpeg** and **FFprobe** for stream merging, format conversion, and media analysis.
* **Windows:** Download a build, extract it, and add the `bin` folder to your System PATH.
* **Linux:** `sudo apt install ffmpeg`
* **macOS:** `brew install ffmpeg`


## 📥 Installation

You can now easily install VantaEther directly from PyPI.

```bash
pip install VantaEther
```

After installation, you can run the app globally using the command: ```vantaether```

---

Alternatively, you can install from the source. It is recommended to use a virtual environment to maintain a clean workspace.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ciwga/VantaEther.git
    cd VantaEther
    ```

2.  **Create and activate a virtual environment:**
    * *Linux/macOS:*
        ```bash
        python3 -m venv .venv
        source .venv/bin/activate
        ```
    * *Windows:*
        ```bash
        python -m venv .venv
        .venv\Scripts\activate
        ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Alternatively, install as a package:**

    * *From source (Dev):*
        ```bash
        pip install .
        ```
    
    * *Directly from GitHub (git+https):*
        ```bash
        pip install git+https://github.com/ciwga/VantaEther.git
        ```

    **After installation, you can run the app globally using the command: ```vantaether```**

## 🖥️ Usage

You can run the application either as an installed command or directly from the source code.

**⚠️ Important Tip:** Always enclose URLs in **double quotes** (`""`). This prevents your terminal shell from misinterpreting special characters like `&` as commands.

### Option A: If Installed (Recommended)
If you installed the package via `pip install .` or directly from GitHub, you can simply use the `vantaether` command:

```bash
# General Usage
vantaether [URL] [OPTIONS]

# Example: Download a video
vantaether "https://www.youtube.com/watch?v=example"

# Open the Interactive Menu
vantaether
```

### Option B: Running from Source (Git Clone)
If you only cloned the repository and installed dependencies, you must run it as a module from the project's root directory.

```bash
# Download a single video or a full playlist
python -m vantaether "https://www.youtube.com/watch?v=example&list=PL...&index=1"

# Audio Only Mode (use --audio or -a arguments):
python -m vantaether "https://www.youtube.com/watch?v=example" --audio
```


## ⚙️ Configuration (Optional)

You can modify the server host/port or disable the startup animation using command-line flags.

This configuration applies whether running from source or as an installed package:
```bash
# Run on a different port and host
vantaether --host 0.0.0.0 --port 8080

# Skip the startup animation for a faster launch
vantaether --no-animation
```
## 🌐 Sync Mode (Browser Sniffing)

For sites that are not natively supported or require authentication, use the **Sync Mode**.

1.  **Start VantaEther:** Run `vantaether` in your terminal.
2.  **Select Manual/Sync Mode:** The engine will start a background server.
3.  **Install the UserScript:**
    * Navigate to the server address (default: `http://127.0.0.1:5005`) in your browser.
    * Install the VantaEther Sync Agent userscript (Requires Tampermonkey/Violentmonkey).
4.  **Capture Streams:**
    * Navigate to the website containing the video you want to download and play it.
    * The script will intercept network requests and send them to your terminal. A browser notification will confirm each capture.
5.  **Download:**
    * Return to your terminal. The captured streams will appear in a table.
    * Select the ID of the stream you wish to download and follow the prompts.


## 📂 Output Structure

Downloads and reports are saved to the `Downloads/VantaEther` directory by default.

* **Video Files:** Saved as `[Title].mp4` or `[Title].mkv`.
* **Technical Reports:** Saved as `[Title]_REPORT.json`. These contain:
    * Source URL and timestamp.
    * Detailed stream analysis (Bitrate, Codecs, Audio Channels).
    * Storage path.


## ⚖️ License & Disclaimer

**License:** MIT License.

**Disclaimer:** This tool is intended for educational purposes and for creating personal archives of legally owned content. The authors do not condone piracy. Users are solely responsible for complying with the Terms of Service of any website they use and all applicable local copyright laws.