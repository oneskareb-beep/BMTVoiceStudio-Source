# BMT Voice Studio — Release Notes v1.1.0

**Feature:** Daily BMT Production  
**Date:** 12 August 2026  
**Type:** Workflow + UX release (no TTS engine change)

## What’s new

Daily BMT is the recommended production screen. Paste English and French devotionals, pick the date, and click **GENERATE TODAY'S DEVOTIONAL**. The app validates both scripts, generates both languages, joins, masters, exports MP3 + WAV, and writes a production report.

## Workflow

1. Open BMT Voice Studio (starts on Daily BMT by default).
2. Select the devotional date (defaults to today).
3. Paste the English script and the French script.
4. Click **GENERATE TODAY'S DEVOTIONAL**.
5. Review the checklist, progress, and final validation.
6. Click **OPEN EXPORT FOLDER**.

## Output layout

```
Documents\BMT Voice Studio\Exports\Daily\YYYY\MM\BMT_YYYY_MM_DD\
  ENGLISH\  BMT_DD_MON_YYYY_ENGLISH_FINAL.mp3 / .wav  + segments\
  FRENCH\   BMT_DD_MON_YYYY_FRENCH_FINAL.mp3 / .wav   + segments\
  REPORTS\  PRODUCTION_REPORT.md  production.json
  SOURCE\   english_source.txt  french_source.txt
```

Example for 13 August 2026:

- Project: `BMT_2026_08_13`
- English: `BMT_13_AUG_2026_ENGLISH_FINAL.mp3`
- French: `BMT_13_AUG_2026_FRENCH_FINAL.mp3`

## Locked presets (unchanged from v1.0)

- **BMT ENGLISH** — en-NG-AbeoNeural / en-NG-EzinneNeural · −10% · −3Hz
- **BMT FRENCH** — fr-FR-RemyMultilingualNeural / fr-FR-VivienneMultilingualNeural · −8% · −1Hz
- Pause 450 ms · mastering ON · −16 LUFS · MP3 128 kbps · WAV ON

## Other Daily BMT features

- Side-by-side English/French editors (tabs on narrower windows)
- Local autosave and recovery of unsaved drafts
- Language failure isolation with Retry English / Retry French
- Smart regeneration (only changed segments; other language untouched)
- One-language mode (English only or French only)
- Cancel keeps completed segment files
- Daily production history with search/filter
- Use previous day as template (settings only unless you choose to copy text)
- First-run v1.1 welcome (shown once)
- Start-page preference: Daily BMT / TTS Studio / Last used page

## Unchanged from v1.0

TTS Studio, Audio Builder, Projects, Voice Manager, Settings, M3U/M3U8, Edge neural TTS, Piper fallback, existing projects and exports.

## Install

1. Unzip `BMTVoiceStudio-1.1.0.zip`
2. Run `BMTVoiceStudio.exe`
3. Keep the entire folder together (`_internal` must stay next to the EXE)
