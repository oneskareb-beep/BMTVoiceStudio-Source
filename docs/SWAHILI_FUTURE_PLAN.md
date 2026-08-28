# Language status — Swahili, Portuguese, HHR

**Status (v1.3.39):** Swahili **is implemented** with East African Kenya neural voices.

Source: https://github.com/oneskareb-beep/BMTVoiceStudio-Source

## What shipped

- Daily Audio can generate **English, French, Swahili, and Portuguese**.
- Swahili and Portuguese use `LanguageProductionConfig` plus regional approval (`Help → Troubleshooting → Regional Voice Setup`).
- Release builds seed SW/PT as production-ready from `bmt_voice_studio/config/production_defaults.json`.
- **HHR** (Hope & Healing Africa — Ruhuka Umutima) speaks Swahili, shows a required Kinyarwanda transcript (large captions), and English captions (medium).

## Voice defaults (do not treat these as Congo/Angola-native Edge catalogs)

| Language | Target | Spoken Edge voices (approved fallback) |
|---|---|---|
| Swahili | Congo/DRC (`sw-CD`) | `sw-KE-RafikiNeural` / `sw-KE-ZuriNeural` (East Africa) |
| Portuguese | Angola (`pt-AO`) | `pt-BR-AntonioNeural` / `pt-BR-FranciscaNeural` |

Congo-specific and West African Swahili neural voices do not exist on Edge TTS. Production uses Kenya (East Africa). Tanzania voices are remapped to Kenya on upgrade.

## Remaining work (not a rewrite)

1. Ministry listen-through of Swahili (BMT + HHR) and Portuguese on real scripts: Bible references, names, phone numbers, dates, ordinals, religious terms.
2. If a better Edge or Piper pair is approved, record it in Regional Voice Setup — do not silently change English/French presets.
3. HHR-only polish: Kinyarwanda transcript layout, caption size, and branding on real chaplaincy messages.
4. Optional: restore a reachable Voice Manager so Piper packs are easier to install when Edge is down.

## Architecture (already in place)

- `LanguageProductionConfig` binds display labels to a voice preset / pipeline.
- `DailyLanguagePanel` is the reusable script + validate panel.
- Generation orchestration already covers EN + FR + SW + PT and the HHR product profile.
