# BMT Voice Studio — Known Limitations v1.0.0

> Historical archive (v1.0.0). Current notes: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). Source: https://github.com/oneskareb-beep/BMTVoiceStudio-Source

1. **Edge TTS requires internet.** Online neural synthesis depends on Microsoft’s Edge TTS service availability and voice catalog.

2. **Piper voice packs require an initial download.** Offline models and the Piper engine are not shipped inside the EXE (size). Download them once via Voice Manager; afterward they work offline under `%LOCALAPPDATA%\BMTVoiceStudio\models\`.

3. **No MSI/setup installer in v1.0.** Distribution is a one-folder ZIP. Extract the full folder and run `BMTVoiceStudio.exe` (do not move the EXE alone).

4. **HLS protected / encrypted / expired streams** cannot be decoded. The app surfaces a clear FFmpeg error instead of crashing.

5. **Silence removal is intentionally mild.** It trims leading/trailing hush only, to protect devotionals with intentional pauses.

6. **Swahili DRC:** Piper catalog includes `sw_CD-lanfrica-medium`. The Edge preset uses available Swahili neural voices (`sw-TZ-*`) when Congo-specific Edge voices are unavailable.

7. **Health “Internet” probe** may report OFFLINE behind some corporate firewalls even when Edge TTS still works.
