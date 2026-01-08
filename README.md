# VantaEther

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python Version](https://img.shields.io/badge/python-3.8+-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

**VantaEther** is an advanced media stream sniffer, analyzer, and downloader written in Python. It bridges the gap between native `yt-dlp` support and complex, protected streaming scenarios by utilizing a local server-browser handshake workflow.

It features a modern TUI (Terminal User Interface) powered by `rich`, a modular service-based architecture, and a highly robust browser integration.

---

## 🚀 Features

* **Dual Mode Operation:**
    * **Native Mode:** Direct high-speed downloads for platforms supported natively (e.g., YouTube, Twitch) using `yt-dlp` internals, now with improved playlist handling.
    * **Sync Mode (Sniffer):** A local Flask server pairs with a custom UserScript to capture encrypted/protected streams (HLS/m3u8, MP4) directly from the browser.

* **Robust Browser Integration:**
    * The v2.0 UserScript (for Tampermonkey/Violentmonkey) features a **connection manager with a request queue and exponential backoff**.
    * If the VantaEther server is offline, captured links are safely queued in the browser. The script automatically detects when the server is back online and transmits the queue, **preventing any data loss**.

* **Modular Architecture:**
    * The core engine has been refactored into a service-oriented design (`DownloadManager`, `FileManager`, `PlaylistManager`, `FormatSelector`). This makes the system more maintainable, testable, and extensible.

* **Media Intelligence:**
    * Integrated `ffprobe` analyzer to generate detailed technical JSON reports (Codec, Bitrate, FPS, Resolution) for every download via a dedicated `ReportGenerator` service.

* **Advanced Merging:**
    * Seamlessly merges video, audio, and subtitle streams.
    * Handles external subtitle synchronization and embedding (MKV/MP4).

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

    *  *Standard Installation:*
        ```bash
        pip install .
        ```
        **After installation, you can run the app globally using the command: ```vantaether```**
---

## 🖥️ Usage

You can run the application directly as a module.

### 1. Native Mode (CLI)
For supported sites (like YouTube playlists), you can pass the URL directly via the command line.

**⚠️ Important Tip:** Always enclose URLs in **double quotes** (`""`). This prevents your terminal shell from misinterpreting special characters like `&` as commands.

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