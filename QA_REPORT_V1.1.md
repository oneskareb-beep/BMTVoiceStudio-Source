# BMT Voice Studio — QA Report v1.1.0

**Decision target:** Version 1.1.0 Daily BMT  
**Date:** 12 August 2026  
**Feature:** Daily BMT Production (workflow + UX)

## Automated tests

```
38 passed in 3.38s
```

- Previous v1.0 suite: 27 tests — PASS
- New Daily BMT tests: 11 tests — PASS

New coverage:

- Daily project creation / date-based naming
- Dual-language validation
- Dual-language output structure
- One-language mode preflight
- Daily autosave / recovery
- Incomplete production marker
- Production history filter
- Language failure isolation status
- Daily smart regeneration isolation
- Production report generation
- Final status calculation

## Real August 13 Daily BMT production

Ran through Daily BMT pipeline (`--daily-batch`), not TTS Studio.

| Item | Result |
|---|---|
| English segments | 10 (M/F alternating) |
| French segments | 10 (M/F alternating) |
| English voices | en-NG-AbeoNeural / en-NG-EzinneNeural |
| French voices | fr-FR-RemyMultilingualNeural / fr-FR-VivienneMultilingualNeural |
| Rate / pitch EN | −10% / −3Hz |
| Rate / pitch FR | −8% / −1Hz |
| Provider | edge (0 retries, 0 fallback events) |
| English MP3 | 404.11 s · 128 kbps · 44100 Hz · mono · −16.05 LUFS · −1.24 dBTP |
| French MP3 | 357.38 s · 128 kbps · 44100 Hz · mono · −16.26 LUFS · −1.33 dBTP |
| WAV | both present, PCM s16le, matching duration |
| Status | COMPLETE |

Quality is equivalent to the approved v1.0 August 13 production (EN 404.11 s / −16.05 LUFS; FR 357.3 s / −16.26 LUFS).

Folder:

`Documents\BMT Voice Studio\Exports\Daily\2026\08\BMT_2026_08_13\`

Filenames:

- `BMT_13_AUG_2026_ENGLISH_FINAL.mp3` / `.wav`
- `BMT_13_AUG_2026_FRENCH_FINAL.mp3` / `.wav`

## Regression

TTS Studio, Audio Builder, Projects, Voice Manager, Settings, M3U, M3U8, Piper fallback, BMT English/French presets, existing projects/exports: unchanged architecture. Automated regression PASS.

## Packaged EXE smoke (`--release-smoke`)

16 / 16 checks PASS (logo, FFmpeg, brace parse, EN/FR synth, join/master, project save/restore, M3U).

## Smart regeneration

Re-run of the same August 13 Daily BMT job reused all cached segments:

- English: cached 10 / regenerated 0
- French: cached 10 / regenerated 0
- Final duration/LUFS unchanged

## Packaging

- EXE: `release\BMTVoiceStudio-1.1.0\BMTVoiceStudio.exe`
- ZIP: `release\BMTVoiceStudio-1.1.0.zip`
- SHA-256: `d6b45d1654ba0d47bedf988877f83a15f526026855bfec1995f68b361405c1a1`
- ZIP extract to `C:\Temp\BMT_ZIP_Extract_V1.1` — EXE launches, version 1.1.0, smoke 16/16 PASS

## Decision

**PRODUCTION READY**
