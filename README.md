# vlc-ai-subs

VLC media player plugin that generates subtitles using OpenAI Whisper — works with any video, any language.

## Features

- **Two modes** — Real-time OSD (subtitles appear as they're generated) or Generate & Load SRT (synced to playback)
- **Any language** — Auto-detection or specify a language code
- **Translation** — Translate any language to English subtitles
- **5 model sizes** — From `tiny` (fastest) to `large` (most accurate)
- **Quiet voice detection** — Tuned to catch whispers, husky voices, and low speech
- **VLC 3.x & 4.x** — Compatible with both versions
- **Cross-platform** — Windows, macOS, and Linux (native, snap, flatpak)

## Quick Start

### Linux / macOS

```bash
git clone https://github.com/voidrlm/vlc-ai-subs.git
cd vlc-ai-subs
./setup.sh
```

### Windows

```
git clone https://github.com/voidrlm/vlc-ai-subs.git
cd vlc-ai-subs
setup.bat
```

Then:

1. **Restart VLC**
2. Open a video
3. **View → AI Subs Generator**
4. Click **Generate**

## Requirements

- Python 3.8+
- VLC 3.x or 4.x
- ~150 MB disk space for the `base` model (downloaded on first use)

## How It Works

| Mode | Description |
|------|-------------|
| **Real-time OSD** | Subtitles appear on screen as Whisper transcribes. Great for first-time viewing. |
| **Generate & Load SRT** | Full transcription runs first, then the `.srt` file is loaded as a proper subtitle track. Perfect sync on replay. |

## Models

| Model | Speed | Accuracy | RAM | Download |
|-------|-------|----------|-----|----------|
| `tiny` | Fastest | Basic | ~1 GB | ~75 MB |
| `base` | Fast | Good | ~1 GB | ~140 MB |
| `small` | Moderate | Better | ~2 GB | ~460 MB |
| `medium` | Slow | Great | ~5 GB | ~1.5 GB |
| `large` | Slowest | Best | ~10 GB | ~3 GB |

## Options

- **Language** — `auto` for detection, or a code like `en`, `es`, `fr`, `hi`, `ja`, `zh`, etc.
- **Task** — `Transcribe` (same language) or `Translate to English`

## Files

```
vlc-ai-subs/
├── aisubs.lua           # VLC Lua extension (the UI)
├── aisubs_whisper.py    # Python Whisper backend
├── setup.sh             # Setup & install (Linux / macOS)
├── setup.bat            # Setup & install (Windows)
├── LICENSE
└── README.md
```

## Manual Installation

If the setup script doesn't work for your system:

1. Install faster-whisper:
   ```bash
   python3 -m venv venv
   venv/bin/pip install faster-whisper        # Linux/macOS
   venv\Scripts\pip.exe install faster-whisper # Windows
   ```

2. Copy `aisubs.lua` to your VLC extensions folder:
   - **Linux**: `~/.local/share/vlc/lua/extensions/`
   - **macOS**: `~/Library/Application Support/org.videolan.vlc/lua/extensions/`
   - **Windows**: `%APPDATA%\vlc\lua\extensions\`

3. Restart VLC.

To update just the VLC extension without reinstalling Python deps:
```bash
./setup.sh --install        # Linux/macOS
setup.bat --install         # Windows
```

## License

MIT
