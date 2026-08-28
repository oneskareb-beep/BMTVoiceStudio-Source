# BMT Voice Studio

Windows desktop app for daily ministry audio and video. Current release: **1.3.38**.

**Daily Audio • Video Maker • BMT or HHR**

One tool, two ministries. Choose **BMT** (Believers Manna Today) or **HHR** (Hope & Healing Africa — Ruhuka Umutima) in the header before generating.

## GitHub

| What | URL |
|---|---|
| **Source code (this project)** | https://github.com/oneskareb-beep/BMTVoiceStudio-Source |
| **Portable releases / in-app updates (public)** | https://github.com/oneskareb-beep/BMTVoiceStudio |
| **Latest zip (Help → Check for Updates)** | https://github.com/oneskareb-beep/BMTVoiceStudio/releases/latest |

This PC copy (`Documents\BMTVoiceStudio`) tracks **BMTVoiceStudio-Source** on `master`. End-user installs download portable zips from **BMTVoiceStudio** via **Help → Check for Updates**.

## What the app does

Two workspaces: **Audio** and **Video**.

- **Audio** — paste curly-brace speaker scripts (`{female}` / male outside), generate mastered MP3/WAV by language and date.
- **Video** — turn that day’s audio into a branded video (captions, logo, meditation stills, music pads).
- **BMT** — English and French devotionals by default; Swahili and Portuguese are available with regional voice defaults (Congo/DRC Swahili, Angola Portuguese).
- **HHR** — Swahili voice, required Kinyarwanda transcript (large on-screen text), English captions, HHR logo and green Ruhuka Umutima look.

Online synthesis uses Edge neural TTS. Piper is an offline fallback (models are not inside the EXE). Data stays in `Documents\BMT Voice Studio` (or the folder chosen in Preferences).

## Languages

| Language | Default role |
|---|---|
| English | BMT ready (`en-NG`) |
| French | BMT ready (`fr-FR`) |
| Swahili | BMT optional + HHR spoken language (Congo/DRC target; `sw-TZ` neural fallback) |
| Portuguese | BMT optional (Angola target; `pt-BR` neural fallback) |
| Kinyarwanda | HHR transcript / large captions (not a separate TTS language) |

Change or re-approve regional voices from **Help → Troubleshooting → Regional Voice Setup**.

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

Output: `dist\BMTVoiceStudio\BMTVoiceStudio.exe`. Distribute the **whole folder**, not the EXE alone.

Publish a portable zip to the public repo so existing installs can update:

```powershell
.\tools\publish_github_release.ps1
```

Offline Piper models, when used, download into `%LOCALAPPDATA%\BMTVoiceStudio\models\`.

## Privacy

- No analytics, telemetry, ads, login, or cloud storage
- Text is sent to Edge TTS only when you generate with the online provider
- Piper synthesis never leaves the machine
- Autosave and history stay on this PC

## Current limitations

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). Historical v1.0 / v1.1 notes are kept as archives.

## License notices

See [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
