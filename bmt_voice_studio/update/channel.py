"""GitHub Releases is the shared update channel for every BMT Voice Studio install."""

from __future__ import annotations

# Public GitHub repo that holds portable zip releases (not a private folder on one PC).
# Format: owner/name  — filled after GitHub login / tools/connect_github.ps1
#
# Application source: https://github.com/oneskareb-beep/BMTVoiceStudio-Source
# Portable updates:   https://github.com/oneskareb-beep/BMTVoiceStudio
GITHUB_REPOSITORY = "oneskareb-beep/BMTVoiceStudio"

GITHUB_RELEASES_API = "https://api.github.com/repos/{repo}/releases/latest"


def default_feed_url() -> str:
    repo = (GITHUB_REPOSITORY or "").strip().strip("/")
    if not repo or "/" not in repo:
        return ""
    return GITHUB_RELEASES_API.format(repo=repo)
