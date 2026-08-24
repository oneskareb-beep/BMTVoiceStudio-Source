"""Piper offline neural TTS provider and voice manager helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import zipfile
from pathlib import Path
from typing import Any

import httpx

from bmt_voice_studio.config.paths import models_dir, temp_work_dir
from bmt_voice_studio.core.models import SynthRequest, SynthResult, VoiceInfo
from bmt_voice_studio.providers.base import (
    BaseTTSProvider,
    CancelCheck,
    ProgressCallback,
    TTSProviderError,
)

logger = logging.getLogger(__name__)

# Curated Piper voice catalog (rhasspy/piper voices). Models download on demand.
# Gender must be declared explicitly — never inferred from filenames alone.
PIPER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "en_US-lessac-medium",
        "name": "Lessac (US English, Medium)",
        "locale": "en_US",
        "language": "en",
        "gender": "female",
        "quality": "medium",
        "sample_rate": 22050,
        "license": "MIT — see MODEL_CARD",
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "card_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/MODEL_CARD",
    },
    {
        "id": "en_US-ryan-medium",
        "name": "Ryan (US English, Medium)",
        "locale": "en_US",
        "language": "en",
        "gender": "male",
        "quality": "medium",
        "sample_rate": 22050,
        "license": "MIT — see MODEL_CARD",
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json",
        "card_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/MODEL_CARD",
    },
    {
        "id": "en_GB-alan-medium",
        "name": "Alan (UK English, Medium)",
        "locale": "en_GB",
        "language": "en",
        "gender": "male",
        "quality": "medium",
        "sample_rate": 22050,
        "license": "MIT — see MODEL_CARD",
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json",
        "card_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/MODEL_CARD",
    },
    {
        "id": "fr_FR-siwis-medium",
        "name": "Siwis (French, Medium)",
        "locale": "fr_FR",
        "language": "fr",
        "gender": "female",
        "quality": "medium",
        "sample_rate": 22050,
        "license": "See MODEL_CARD",
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json",
        "card_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/MODEL_CARD",
    },
    {
        "id": "fr_FR-upmc-medium",
        "name": "UPMC (French, Medium)",
        "locale": "fr_FR",
        "language": "fr",
        "gender": "male",
        "quality": "medium",
        "sample_rate": 22050,
        "license": "See MODEL_CARD",
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx.json",
        "card_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/upmc/medium/MODEL_CARD",
    },
    {
        "id": "sw_CD-lanfrica-medium",
        "name": "Lanfrica (Congo Swahili / DRC, Medium)",
        "locale": "sw_CD",
        "language": "sw",
        "gender": "unknown",
        "quality": "medium",
        "sample_rate": 22050,
        "license": "See MODEL_CARD — verify before production use",
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/sw/sw_CD/lanfrica/medium/sw_CD-lanfrica-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/sw/sw_CD/lanfrica/medium/sw_CD-lanfrica-medium.onnx.json",
        "card_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/sw/sw_CD/lanfrica/medium/MODEL_CARD",
    },
]


def _piper_bin_dir() -> Path:
    return models_dir() / "piper_bin"


def _voice_dir(voice_id: str) -> Path:
    return models_dir() / "voices" / voice_id


def find_piper_executable() -> Path | None:
    env = os.environ.get("PIPER_PATH")
    if env and Path(env).exists():
        return Path(env)
    local = _piper_bin_dir() / ("piper.exe" if platform.system() == "Windows" else "piper")
    if local.exists():
        return local
    which = shutil.which("piper")
    if which:
        return Path(which)
    return None


class PiperVoiceManager:
    """Install, list, preview metadata, and delete Piper models."""

    USER_AGENT = "BMTVoiceStudio/1.0 (+local; piper-voice-manager)"

    def catalog(self) -> list[dict[str, Any]]:
        return list(PIPER_CATALOG)

    def installed_voices(self) -> list[VoiceInfo]:
        voices: list[VoiceInfo] = []
        root = models_dir() / "voices"
        if not root.exists():
            return voices
        catalog_by_id = {c["id"]: c for c in PIPER_CATALOG}
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            onnx = next(folder.glob("*.onnx"), None)
            if not onnx:
                continue
            meta_path = folder / "voice_meta.json"
            meta: dict[str, Any] = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            cat = catalog_by_id.get(folder.name, {})
            card = ""
            card_file = folder / "MODEL_CARD"
            if card_file.exists():
                try:
                    card = card_file.read_text(encoding="utf-8", errors="replace")[:2000]
                except Exception:
                    card = ""
            size = onnx.stat().st_size
            voices.append(
                VoiceInfo(
                    id=folder.name,
                    name=meta.get("name") or cat.get("name") or folder.name,
                    locale=meta.get("locale") or cat.get("locale") or "",
                    gender=meta.get("gender") or cat.get("gender") or "unknown",
                    provider="piper",
                    language=meta.get("language") or cat.get("language") or "",
                    sample_rate=meta.get("sample_rate") or cat.get("sample_rate"),
                    quality=meta.get("quality") or cat.get("quality") or "",
                    size_bytes=size,
                    license=meta.get("license") or cat.get("license") or "",
                    model_path=str(onnx),
                    installed=True,
                )
            )
            if card and not voices[-1].license:
                voices[-1].license = card.splitlines()[0][:200]
        return voices

    def get_model_card(self, voice_id: str) -> str:
        path = _voice_dir(voice_id) / "MODEL_CARD"
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return "No MODEL_CARD available for this voice."

    async def download_voice(
        self,
        voice_id: str,
        *,
        on_progress: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> VoiceInfo:
        entry = next((c for c in PIPER_CATALOG if c["id"] == voice_id), None)
        if not entry:
            raise TTSProviderError(f"Unknown Piper voice: {voice_id}")

        dest = _voice_dir(voice_id)
        dest.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=120.0,
            headers={"User-Agent": self.USER_AGENT},
        ) as client:
            for label, url, filename in (
                ("model", entry["onnx_url"], f"{voice_id}.onnx"),
                ("config", entry["json_url"], f"{voice_id}.onnx.json"),
                ("MODEL_CARD", entry.get("card_url"), "MODEL_CARD"),
            ):
                if not url:
                    continue
                if cancel_check and cancel_check():
                    raise TTSProviderError("Download cancelled.")
                if on_progress:
                    on_progress(f"Downloading {label} for {voice_id}…")
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    (dest / filename).write_bytes(resp.content)
                except Exception as exc:
                    if label == "MODEL_CARD":
                        logger.warning("MODEL_CARD download failed: %s", exc)
                        continue
                    raise TTSProviderError(
                        f"Failed to download Piper {label} for {voice_id}.",
                        technical=str(exc),
                    ) from exc

        meta = {
            "id": voice_id,
            "name": entry["name"],
            "locale": entry["locale"],
            "language": entry["language"],
            "gender": entry["gender"],
            "quality": entry["quality"],
            "sample_rate": entry["sample_rate"],
            "license": entry["license"],
        }
        (dest / "voice_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        installed = self.installed_voices()
        match = next((v for v in installed if v.id == voice_id), None)
        if not match:
            raise TTSProviderError("Voice downloaded but could not be verified.")
        return match

    def delete_voice(self, voice_id: str) -> None:
        path = _voice_dir(voice_id)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    async def ensure_piper_binary(
        self,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        existing = find_piper_executable()
        if existing:
            return existing

        if platform.system() != "Windows":
            raise TTSProviderError(
                "Piper binary not found. Install Piper and set PIPER_PATH."
            )

        # Official Windows release from rhasspy/piper
        url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
        dest_dir = _piper_bin_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        zip_path = temp_work_dir() / "piper_windows.zip"

        if on_progress:
            on_progress("Downloading Piper offline engine…")

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=180.0,
            headers={"User-Agent": self.USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            zip_path.write_bytes(resp.content)

        if on_progress:
            on_progress("Extracting Piper…")

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)

        # Find piper.exe in extracted tree
        exe = next(dest_dir.rglob("piper.exe"), None)
        if not exe:
            raise TTSProviderError("Piper archive downloaded but piper.exe was not found.")
        # Copy to bin root for easy discovery
        target = dest_dir / "piper.exe"
        if exe.resolve() != target.resolve():
            shutil.copy2(exe, target)
            # Also copy sibling DLLs / espeak-ng-data if present
            for sibling in exe.parent.iterdir():
                if sibling.is_file() and sibling.name != "piper.exe":
                    shutil.copy2(sibling, dest_dir / sibling.name)
                elif sibling.is_dir() and sibling.name in {"espeak-ng-data", "onnxruntime"}:
                    dest_sub = dest_dir / sibling.name
                    if dest_sub.exists():
                        shutil.rmtree(dest_sub, ignore_errors=True)
                    shutil.copytree(sibling, dest_sub)
        return target


class PiperProvider(BaseTTSProvider):
    id = "piper"
    display_name = "Piper TTS (Offline Neural)"
    requires_network = False

    def __init__(self) -> None:
        self.manager = PiperVoiceManager()

    async def list_voices(self) -> list[VoiceInfo]:
        return self.manager.installed_voices()

    async def health_check(self) -> tuple[bool, str]:
        exe = find_piper_executable()
        voices = self.manager.installed_voices()
        if not exe:
            return False, "MODEL NOT INSTALLED (piper binary missing)"
        if not voices:
            return False, "MODEL NOT INSTALLED"
        return True, f"READY ({len(voices)} voice(s))"

    def resolve_model(self, voice: str) -> Path:
        # voice may be voice id or path to onnx
        path = Path(voice)
        if path.suffix == ".onnx" and path.exists():
            return path
        candidate = _voice_dir(voice) / f"{voice}.onnx"
        if candidate.exists():
            return candidate
        # search installed
        for info in self.manager.installed_voices():
            if info.id == voice or info.name == voice:
                return Path(info.model_path)
        raise TTSProviderError(
            f"Piper model '{voice}' is not installed. Open Voice Manager to download it."
        )

    async def synthesize(
        self,
        request: SynthRequest,
        *,
        cancel_check: CancelCheck | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> SynthResult:
        from bmt_voice_studio.providers.provider_guard import assert_provider_voice_compatible

        try:
            assert_provider_voice_compatible(self.id, request.voice or "")
        except TTSProviderError as exc:
            return SynthResult(success=False, error=exc.message, provider=self.id)

        text = (request.text or "").strip()
        if not text:
            return SynthResult(success=False, error="Segment text is empty.", provider=self.id)
        if not request.output_path:
            return SynthResult(success=False, error="No output path provided.", provider=self.id)

        try:
            model = self.resolve_model(request.voice)
        except TTSProviderError as exc:
            return SynthResult(success=False, error=exc.message, provider=self.id)

        try:
            exe = await self.manager.ensure_piper_binary(on_progress=on_progress)
        except Exception as exc:
            return SynthResult(
                success=False,
                error=f"Piper engine unavailable: {exc}",
                provider=self.id,
            )

        if cancel_check and cancel_check():
            return SynthResult(success=False, cancelled=True, provider=self.id, error="Cancelled.")

        out = Path(request.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        # Piper outputs WAV; convert to requested extension via temp wav if needed
        wav_out = out if out.suffix.lower() == ".wav" else out.with_suffix(".wav")

        if on_progress:
            on_progress("Synthesizing with Piper (offline)…")

        try:
            proc = await asyncio.create_subprocess_exec(
                str(exe),
                "--model",
                str(model),
                "--output_file",
                str(wav_out),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(exe.parent),
            )
            stdout, stderr = await proc.communicate(input=text.encode("utf-8"))
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace")[:500]
                return SynthResult(
                    success=False,
                    error=f"Piper synthesis failed: {err or 'unknown error'}",
                    provider=self.id,
                )
            if not wav_out.exists() or wav_out.stat().st_size < 64:
                return SynthResult(success=False, error="Piper produced empty audio.", provider=self.id)

            if out.suffix.lower() == ".mp3":
                from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

                ff = FFmpegService()
                ff.convert(wav_out, out, bitrate_kbps=128)
                if wav_out != out and wav_out.exists():
                    wav_out.unlink(missing_ok=True)

            return SynthResult(success=True, output_path=str(out), provider=self.id)
        except Exception as exc:
            logger.exception("Piper synthesize error")
            return SynthResult(success=False, error=str(exc), provider=self.id)
