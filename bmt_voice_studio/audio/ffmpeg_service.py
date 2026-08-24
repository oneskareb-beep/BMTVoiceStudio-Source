"""FFmpeg discovery and process helpers."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    def __init__(self, message: str, *, technical: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.technical = technical or message


class FFmpegService:
    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self._explicit = ffmpeg_path
        self._cached: str | None = None
        self._resolution_source: str = ""

    def _imageio_ffmpeg(self) -> str | None:
        try:
            import imageio_ffmpeg

            path = imageio_ffmpeg.get_ffmpeg_exe()
            if path and Path(path).exists():
                return str(Path(path).resolve())
        except Exception as exc:
            logger.debug("imageio-ffmpeg lookup failed: %s", exc)
        return None

    def _bundled_near_exe(self) -> str | None:
        if not getattr(sys, "frozen", False):
            return None
        candidates: list[Path] = []
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        for root in (meipass, exe_dir, exe_dir / "_internal"):
            candidates.extend(
                [
                    root / "ffmpeg.exe",
                    root / "imageio_ffmpeg" / "binaries" / "ffmpeg.exe",
                ]
            )
            candidates.extend(root.glob("**/ffmpeg*.exe"))
        for path in candidates:
            try:
                if path.is_file():
                    return str(path.resolve())
            except Exception:
                continue
        return None

    def find(self) -> str:
        if self._cached:
            return self._cached
        if self._explicit and Path(self._explicit).exists():
            self._cached = str(Path(self._explicit).resolve())
            self._resolution_source = "explicit"
            return self._cached

        # Packaged EXE: prefer bundled imageio-ffmpeg over developer PATH.
        if getattr(sys, "frozen", False):
            bundled = self._bundled_near_exe() or self._imageio_ffmpeg()
            if bundled:
                self._cached = bundled
                self._resolution_source = "bundled"
                return self._cached

        which = shutil.which("ffmpeg")
        if which:
            self._cached = str(Path(which).resolve())
            self._resolution_source = "path"
            return self._cached

        imageio = self._imageio_ffmpeg()
        if imageio:
            self._cached = imageio
            self._resolution_source = "imageio_ffmpeg"
            return self._cached

        raise FFmpegError(
            "FFmpeg was not found. Reinstall BMT Voice Studio or place ffmpeg.exe on PATH."
        )

    def resolution_info(self) -> dict[str, str]:
        path = self.find()
        return {
            "path": path,
            "source": self._resolution_source or "unknown",
            "frozen": str(bool(getattr(sys, "frozen", False))),
        }

    def health_check(self) -> tuple[bool, str]:
        try:
            path = self.find()
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if result.returncode == 0:
                first = (result.stdout or "").splitlines()[0] if result.stdout else path
                return True, f"READY ({first}) via {self._resolution_source} @ {path}"
            return False, "ERROR (ffmpeg returned non-zero)"
        except Exception as exc:
            return False, f"ERROR ({exc})"


    def run(
        self,
        args: list[str],
        *,
        timeout: float | None = 600,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [self.find(), *args]
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=flags,
            )
        except subprocess.TimeoutExpired as exc:
            raise FFmpegError("FFmpeg timed out while processing audio.", technical=str(exc)) from exc
        except FileNotFoundError as exc:
            raise FFmpegError("FFmpeg executable is missing.", technical=str(exc)) from exc
        if check and result.returncode != 0:
            err = (result.stderr or result.stdout or "")[-800:]
            raise FFmpegError(
                "FFmpeg failed while processing audio.",
                technical=err,
            )
        return result

    def convert(
        self,
        src: Path,
        dest: Path,
        *,
        bitrate_kbps: int = 128,
        sample_rate: int = 44100,
    ) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.suffix.lower() == ".wav":
            self.run(
                [
                    "-y",
                    "-i",
                    str(src),
                    "-ac",
                    "1",
                    "-ar",
                    str(sample_rate),
                    str(dest),
                ]
            )
        else:
            self.run(
                [
                    "-y",
                    "-i",
                    str(src),
                    "-ac",
                    "1",
                    "-ar",
                    str(sample_rate),
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    f"{bitrate_kbps}k",
                    str(dest),
                ]
            )
        return dest

    def probe_is_audio(self, path: Path) -> bool:
        try:
            result = self.run(["-i", str(path)], check=False, timeout=30)
            combined = (result.stderr or "") + (result.stdout or "")
            return "Audio:" in combined
        except Exception:
            return False

    def generate_silence(self, dest: Path, duration_ms: int, sample_rate: int = 44100) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        seconds = max(0, duration_ms) / 1000.0
        self.run(
            [
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r={sample_rate}:cl=mono",
                "-t",
                f"{seconds:.3f}",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(dest),
            ]
        )
        return dest
