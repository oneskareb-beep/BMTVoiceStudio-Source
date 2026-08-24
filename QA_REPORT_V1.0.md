# BMT Voice Studio — QA Report v1.0.0 (FINAL GATE)

**QA date:** 2026-08-12  
**Decision target:** Version 1.0.0 FINAL  
**Build:** `release\BMTVoiceStudio-1.0.0\BMTVoiceStudio.exe`

## Automated tests (final)

| TOTAL | PASSED | FAILED | SKIPPED |
|-------|--------|--------|---------|
| 27 | 27 | 0 | 0 |

Includes regression: `test_piper_fallback.py` (requires installed Piper model).

---

## Piper Offline Fallback Test

**Model used:** `en_US-lessac-medium` (Voice Manager catalog download)  
**Binary:** `%LOCALAPPDATA%\BMTVoiceStudio\models\piper_bin\piper.exe`  
**Model path:** `%LOCALAPPDATA%\BMTVoiceStudio\models\voices\en_US-lessac-medium\`

| Check | Result |
|-------|--------|
| Download via Voice Manager API | PASS |
| Stored under models dir | PASS |
| Metadata + MODEL_CARD | PASS |
| Preview / audition | PASS (2.52s) |
| Assign male/female fallback | PASS |
| Piper-only generation (Edge not called) | PASS |
| Output | `%LOCALAPPDATA%\BMTVoiceStudio\temp\gate1_piper_paragraph.mp3` |
| Duration | **5.77s** |
| Simulate Edge failure | PASS (human-readable error) |
| Automatic Piper fallback | PASS |
| Auto-fallback output | `gate1_auto_fallback.mp3` (**3.58s**) |
| Return to Edge TTS afterward | PASS |

Gate 1 summary: **19/19 PASS**

---

## Clean Windows Test

Windows Sandbox was **not available** on the QA host (feature not present / requires elevation).

**Equivalent clean-machine simulation performed:**

- PATH restricted to `C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem`
- Confirmed `python`, `ffmpeg`, and `git` were **not** on PATH
- Ran packaged `release\BMTVoiceStudio-1.0.0\BMTVoiceStudio.exe` only

| Check | Result |
|-------|--------|
| GUI launch | PASS |
| BBNet logo/resources | PASS (from `_internal\bmt_voice_studio\resources\`) |
| Missing DLL / Python errors | PASS (none) |
| Packaged FFmpeg | PASS (`_internal\imageio_ffmpeg\binaries\...`) |
| Edge EN sample + braces | PASS |
| Edge FR sample + accents | PASS |
| Final MP3 / WAV | PASS |
| M3U → MP3 | PASS |
| Project save/restore | PASS |
| Close/reopen capability | PASS (GUI launched twice in gates) |

Packaged `--release-smoke`: **16/16 PASS**, exit code 0

---

## Final ZIP Extraction Test

1. Built `release\BMTVoiceStudio-1.0.0.zip`
2. Extracted to `C:\Temp\BMT_ZIP_Extract_Final\`
3. Ran `BMTVoiceStudio.exe` from the extracted copy with cleaned PATH
4. GUI launch: PASS
5. `--release-smoke`: **16/16 PASS**, exit code 0

---

## Release Integrity Check

| Check | Result |
|-------|--------|
| No `__pycache__` / pytest cache in release | PASS |
| No QA temp projects inside release folder | PASS |
| Hard-coded `C:\Users\aganz` in release runtime/docs scan | **0 hits** |
| Runtime paths resolve dynamically | PASS |

---

## SHA-256

```
BMTVoiceStudio-1.0.0.zip  a82226a5cbf47fc339126cde1a8b8092b626142ac4dcb47762a88217928d31e5
```

File: `release\SHA256SUMS.txt`  
ZIP size: **93466557** bytes (~89.1 MB)

---

## Bugs fixed during FINAL gates

1. Mastering same-path read/write crash (FFmpeg) — temp file then replace.
2. Packaged `--release-smoke` requires QApplication — offscreen Qt init added.
3. Piper offline path validated end-to-end with real model download.

---

## FINAL DECISION

**PRODUCTION READY** — see scorecard in release notes / chat handoff.
