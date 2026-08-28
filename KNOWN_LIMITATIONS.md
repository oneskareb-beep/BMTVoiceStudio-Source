# BMT Voice Studio — Known Limitations (v1.3.38)

Current product notes. Older files `KNOWN_LIMITATIONS_V1.0.md` and `KNOWN_LIMITATIONS_V1.1.md` are historical.

## GitHub

- Source (clone this): https://github.com/oneskareb-beep/BMTVoiceStudio-Source
- Releases: https://github.com/oneskareb-beep/BMTVoiceStudio/releases/latest

## Synthesis

- Edge TTS requires internet. If Edge is unavailable, Daily Audio can fall back to Piper only when models are already installed. Quality differs from the approved neural Edge voices.
- Piper engine and voice packs are **not** shipped inside the EXE. They download on demand into `%LOCALAPPDATA%\BMTVoiceStudio\models\`.
- The old Voice Manager page is still in the source tree but is **not** on the main Audio/Video window. Use **Help → Troubleshooting** for health checks and regional voice setup.
- Piper is forbidden as the production voice for approved Daily languages when Edge is working.

## Languages

- English and French are the BMT default pair.
- Swahili and Portuguese are implemented. Release builds seed them as Ready from bundled production defaults. Congo-specific Edge voices may be unavailable; Swahili uses `sw-TZ-*` as the approved fallback. Portuguese Angola uses `pt-BR-*` as the approved fallback.
- HHR uses Swahili for speech, Kinyarwanda as the required on-screen transcript, and English as secondary captions. Kinyarwanda is not synthesized as its own TTS language.
- Changing validated BMT English/French voice IDs is not a user-facing setting.

## Video Maker

- Final video is blocked when a selected language is missing its real localized topic (`Topic` / `Thème` / `Mada` / `Tema`).
- Packaged default clips, meditation stills, and music pads must ship with the portable folder.

## Packaging and updates

- Distribution is a portable folder ZIP, not an MSI/setup installer. Do not move `BMTVoiceStudio.exe` out of its folder.
- Windowed EXE has no console. Use `--daily-batch` / `--production-batch` with a report path, or run from the Python entrypoint for stdout.
- In-app updates read **GitHub Latest** on the public repo. If download freezes, use **Open zip in browser**, then **Choose update zip**.

## Data

- Autosave, history, and exports stay on this PC (`Documents\BMT Voice Studio` by default). They are never uploaded.
- Interrupted productions resume from cached segment files. Join/master of a language re-runs if that language is retried.

## Not in this release

- Cloud sync or multi-user collaboration
- Automatic upload to radio / web CMS
- Single-file EXE or Windows Store installer
- Real-time conversational TTS (that is a different product)
