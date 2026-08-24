# BMT Voice Studio

Windows desktop app for Believers Manna Today daily devotional audio production.

**Neural TTS • Audio Builder • M3U Converter**

## Features

- Curly-brace speaker script (`{female}` / male outside)
- Edge TTS online neural voices (BMT English / BMT French / Swahili presets)
- Piper offline neural fallback + Voice Manager
- Smart segment regeneration (hash cache)
- FFmpeg join + loudness mastering
- M3U / M3U8 / pasted URL download & merge (Python `httpx`, no browser CORS)
- Project save/load, dark UI, health checks
- Packaged Windows EXE via PyInstaller

## Requirements (development)

- Windows 10/11
- Python 3.11 or 3.12

## Quick start (dev)

```powershell
cd $env:USERPROFILE\Documents\BMTVoiceStudio
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m bmt_voice_studio
```

## Tests

```powershell
pytest -q
```

## Windows build (end-user EXE)

```powershell
.\build_windows.ps1
```

Output: `dist\BMTVoiceStudio\BMTVoiceStudio.exe` (distribute the whole folder).

Offline Piper models download on demand into `%LOCALAPPDATA%\BMTVoiceStudio\models\`.

## Privacy

- No analytics, telemetry, ads, login, or cloud storage
- Text is sent to Edge TTS only when you generate with the online provider
- Piper synthesis never leaves the machine

## License notices

See [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
