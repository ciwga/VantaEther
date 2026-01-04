# VantaEther

**VantaEther** is an advanced media stream sniffer, analyzer, and downloader written in Python. It bridges the gap between native `yt-dlp` support and complex, protected streaming scenarios by utilizing a local server-browser handshake workflow.

It features a modern TUI (Terminal User Interface) powered by `rich`, detailed media analysis reports, and robust stream merging capabilities.

---

## 🚀 Features

* **Dual Mode Operation:**
    * **Native Mode:** Direct high-speed downloads for platforms supported natively (e.g., YouTube, Twitch) using `yt-dlp` internals.
    * **Sync Mode (Sniffer):** A local Flask server pairs with a custom Tampermonkey script to capture encrypted/protected streams (HLS/m3u8, MP4) directly from the browser network traffic.
* **Media Intelligence:**
    * Integrated `ffprobe` analyzer to generate detailed technical reports (Codec, Bitrate, FPS, Resolution) for every download.
    * Automatic stream quality sorting and selection.
* **Advanced Merging:**
    * Seamlessly merges video, audio, and subtitle streams.
    * Handles external subtitle synchronization and embedding (MKV/MP4/SRT).
* **Production Quality:**
    * Thread-safe architecture.
    * Cross-platform path resolution (Windows/Linux/macOS).
    * Rich, informative logging and progress visualization.

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
    *Alternatively, strictly using the setup file:*
    ```bash
    pip install .
    ```

---

## 🖥️ Usage

You can run the application directly as a module.

### 1. Native Mode (CLI)
For supported sites (like YouTube), you can pass the URL directly via the command line.

**⚠️ Important Tip:** Always enclose URLs in **double quotes** (`""`). This prevents your terminal shell from misinterpreting special characters like `&` (ampersand) or `?` as commands.

```bash
# Correct usage (Safe for all shells):
python -m vantaether "https://www.youtube.com/watch?v=example&t=120s"

# Audio Only Mode (converts to MP3, use --audio or -a arguments):
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
    * Copy the generated **Tampermonkey Script**.
    * Create a new script in the Tampermonkey extension and paste the code.
4.  **Capture Streams:**
    * Navigate to the website containing the video you want to download.
    * Play the video. The script will intercept the network requests.
    * A notification in the browser will confirm the capture ("Snipe sent").
5.  **Download:**
    * Return to your terminal.
    * The captured streams will appear in a table.
    * Select the ID of the stream you wish to download.

---

## 📂 Output Structure

Downloads and reports are saved to the `Downloads/VantaEther` directory (automatically resolved based on your OS).

* **Video Files:** Saved as `[Title].mp4` or `[Title].mkv`.
* **Technical Reports:** Saved as `[Title]_REPORT.json`. These contain:
    * Source URL and timestamp.
    * Detailed stream analysis (Bitrate, Codecs, Audio Channels).
    * Storage path.

---

## ⚖️ License & Disclaimer

**License:** MIT License.

**Disclaimer:** This tool is intended for educational purposes and personal archiving only. The authors do not condone piracy. Users are responsible for complying with the Terms of Service of the websites they interact with and their local copyright laws.