# BMT Voice Studio v1.3.36 — Video Maker Reliability Fixes

## Fixed

- Localized daily topics are now accepted only from explicit per-language labels (`Topic`, `Thème`, `Mada`, `Tema`). The app no longer guesses a topic from an arbitrary first line.
- Final video generation is blocked when any selected language is missing its actual localized topic, preventing English or generic fallback titles from being published.
- MP3 locked-card artwork no longer falls back to the English source for French, Swahili, or Portuguese output.
- The intro card no longer fades in from black; frame 0 is immediately branded for better WhatsApp/social preview extraction.
- Meditation/paysage stills now receive subtle Ken Burns motion while preserving the fixed middle-half landscape band.
- When captions are enabled, voice-synchronised devotional school text now glides gently upward with a short fade while preserving the original sentence timing and safe margins.

## Build

- Runtime/package version: `1.3.36`.
- Added `BMTVoiceStudio-1.3.36.spec`.

## Regression coverage

Added targeted tests for topic isolation, missing-topic behavior, band-safe motion, no-black intro fade, and voice-timed caption motion.
