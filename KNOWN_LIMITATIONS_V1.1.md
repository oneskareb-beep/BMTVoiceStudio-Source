# BMT Voice Studio — Known Limitations v1.1.0

All v1.0 limitations still apply. Daily BMT adds the following notes.

## Daily BMT

- Daily BMT is a workflow layer over the existing v1.0 engines. It does not add new voices or change BMT English/French presets.
- Edge TTS requires internet. If Edge is unavailable and Piper models are installed, Daily BMT can fall back to Piper (quality will differ from neural Edge voices).
- Autosave and production history are stored only in `%LOCALAPPDATA%\BMTVoiceStudio\daily\`. They are never uploaded.
- Interrupted productions resume from cached segment files. Join/master of a language re-runs if that language is retried.
- One-language mode still creates the full Daily folder layout (ENGLISH/FRENCH/REPORTS/SOURCE) so a later retry can fill the missing language.
- “Use previous day as template” copies production settings. Devotional text is copied only if you confirm.
- The v1.1 welcome dialog appears once. After that, the start-page setting controls the first screen.
- Narrow-window tab mode hides one language editor at a time; content is not lost.

## Packaging

- Distribute the whole `BMTVoiceStudio` folder. The EXE is not a single-file build.
- Windowed EXE has no console. Use `--daily-batch` / `--production-batch` with a report path, or run from the Python entrypoint for stdout.

## Not in this release

- Swahili / additional language presets
- Cloud sync or multi-user collaboration
- Automatic upload to radio / web CMS
- Changing validated BMT voice presets
