# VantaEther

![Version](https://img.shields.io/badge/version-2.1-blue)
![Python Version](https://img.shields.io/badge/python-3.8+-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

**VantaEther** is an advanced media stream sniffer, analyzer, and downloader written in Python. It bridges the gap between native `yt-dlp` support and complex, protected streaming scenarios by utilizing a local server-browser handshake workflow.

It features a modern TUI (Terminal User Interface) powered by `rich`, a modular service-based architecture, and a highly robust browser integration.

---

## 🚀 Features

* **Dual Mode Operation:**
    * **Native Mode:** Direct high-speed downloads for platforms supported natively (e.g., YouTube, Twitch) using `yt-dlp` internals.
    * **Sync Mode (Sniffer):** A local Flask server pairs with a custom UserScript to capture encrypted/protected streams (HLS/m3u8, MP4, API Endpoints) directly from the browser.

* **Smart Network Management (NEW):**
    * **Header Factory:** Implements automated header manipulation and spoofing (Referer/Origin) for strict platforms like Twitter/X.
    * **Universal Domain Spraying:** intelligently analyzes cookies and sprays them across valid subdomains to minimize "403 Forbidden" errors on strict CDNs.

* **Robust Browser Integration:**
    * **Memory Protection:** The agent now includes auto-pruning to prevent browser memory leaks during long sniffing sessions.
    * **Remote Logging:** Mirrors browser console logs (DEBUG) and DRM alerts directly to your terminal.
    * **Offline Queue:** Captured links are safely queued if the server is offline and automatically transmitted once the connection is restored.

* **Media Intelligence:**
    * Integrated `ffprobe` analyzer generates detailed technical JSON reports (Codec, Bitrate, FPS, Resolution) for every download via the `ReportGenerator` service.

* **Advanced Merging & Compatibility:**
    * Seamlessly merges video, audio, and subtitle streams.
    * Handles external subtitle synchronization and embedding (MKV/MP4).
    * **Android Support:** Enhanced directory resolution for Termux/Android environments.

---

## 🛠️ Prerequisites

### 1. Python
VantaEther requires **Python 3.8** or higher.

### 2. FFmpeg (Critical)
The application relies heavily on **FFmpeg** and **FFprobe** for stream merging, format conversion, and media analysis.
* **Windows:** Download a build, extract it, and add the `bin` folder to your System PATH.
* **Linux:** `sudo apt install ffmpeg`
* **macOS:** `brew install ffmpeg`

---

## 📥 Installation

It is recommended to use a virtual environment to maintain a clean workspace.

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
---

## 🖥️ Usage

You can run the application either as an installed command or directly from the source code.

**⚠️ Important Tip:** Always enclose URLs in **double quotes** (`""`). This prevents your terminal shell from misinterpreting special characters like `&` as commands.

### Option A: If Installed (Recommended)
If you installed the package via `pip install .` or directly from GitHub, you can simply use the `vantaether` command from anywhere in your terminal:

```bash
# General Usage
vantaether [URL] [OPTIONS]

# Example: Download a video
vantaether "https://www.youtube.com/watch?v=example"

# Open the Interactive Menu
vantaether
```

### Option B: Running from Source (Git Clone)
If you only cloned the repository and installed dependencies (pip install -r requirements.txt) without installing the package, you must run it as a module.

Note: Ensure you are in the root directory of the project (where pyproject.toml is located).
```bash
cd VantaEther
```
#### 1. Native Mode (CLI)
For supported sites (like YouTube playlists), you can pass the URL directly via the command line.

```bash
# Download a single video or a full playlist
python -m vantaether "https://www.youtube.com/watch?v=example&list=PL...&index=1"

# Audio Only Mode (use --audio or -a arguments):
python -m vantaether "https://www.youtube.com/watch?v=example" --audio
```

### 2. Interactive Mode
Running without arguments launches the interactive TUI, which guides you through mode selection.

```bash
python -m vantaether
```

## 🌐 Sync Mode (Browser Sniffing)

For sites that are not natively supported or require authentication/cookies, use the **Sync Mode**.

1.  **Start VantaEther:** Run `python -m vantaether` in your terminal.
2.  **Select Manual/Sync Mode:** The engine will start a background server on port `5005`.
3.  **Install the UserScript:**
    * Open your browser and navigate to `http://127.0.0.1:5005`.
    * Copy the generated UserScript for **Tampermonkey/Violentmonkey**.
    * Create a new script in your browser's Tampermonkey/Violentmonkey extension and paste the code.
4.  **Capture Streams:**
    * Navigate to the website containing the video you want to download.
    * Play the video. The script will intercept the network requests and queue them.
    * A notification in the browser will confirm the capture. If the server is offline, links are held; they will be sent automatically when the server is running.
5.  **Download:**
    * Return to your terminal. The captured streams will appear in a table as they are received.
    * Select the ID of the stream you wish to download.
---

## 📂 Output Structure

Downloads and reports are saved to the `Downloads/VantaEther` directory (automatically resolved based on your OS) by default.

* **Video Files:** Saved as `[Title].mp4` or `[Title].mkv`.
* **Technical Reports:** Saved as `[Title]_REPORT.json`. These contain:
    * Source URL and timestamp.
    * Detailed stream analysis (Bitrate, Codecs, Audio Channels).
    * Storage path.
---

## ⚖️ License & Disclaimer

**License:** MIT License.

**Disclaimer:** This tool is intended for educational purposes and personal archiving only. The authors do not condone piracy. Users are responsible for complying with the Terms of Service of the websites they interact with and their local copyright laws.