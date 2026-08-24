# BMT Voice Studio — Release Notes v1.0.0

**Release date:** 2026-08-12  
**Product:** BMT Voice Studio  
**Organization:** BBNet — Believers Businessmen Network

## Highlights

- Desktop Windows app for daily devotionals: Neural TTS, Audio Builder, M3U Converter
- Edge TTS online neural voices with BMT English / French / Swahili presets
- Piper offline fallback + Voice Manager (models download on demand)
- Curly-brace male/female speaker scripting with smart segment cache regeneration
- FFmpeg join, loudness mastering (~−16 LUFS), MP3/WAV export
- M3U / URL list download & merge via Python httpx (no browser CORS)
- HLS/M3U8 detection with FFmpeg ingest
- Project save/load, settings persistence, BBNet branding
- One-folder Windows distributable — no Python install required for end users

## Bundled presets

| Preset | Male | Female | Rate | Pitch |
|--------|------|--------|------|-------|
| BMT ENGLISH | en-NG-AbeoNeural | en-NG-EzinneNeural | −10% | −3Hz |
| BMT FRENCH | fr-FR-RemyMultilingualNeural | fr-FR-VivienneMultilingualNeural | −8% | −1Hz |
| BMT SWAHILI (DRC) | sw-TZ-DaudiNeural | sw-TZ-RehemaNeural | −8% | −2Hz |

## Install

1. Unzip `BMTVoiceStudio-1.0.0.zip`
2. Run `BMTVoiceStudio.exe`
3. Optional: install Piper offline voices from Voice Manager

## Default export location

`Documents\BMT Voice Studio\Exports\`
