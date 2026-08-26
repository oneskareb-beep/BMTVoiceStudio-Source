"""Language production configuration — EN / FR / SW / PT for Daily BMT."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from bmt_voice_studio.config.presets import (
    BMT_ENGLISH,
    BMT_FRENCH,
    BMT_PORTUGUESE,
    BMT_SWAHILI,
    VoicePreset,
)
from bmt_voice_studio.config.production_defaults import language_defaults
from bmt_voice_studio.daily.regional_approval import (
    approved_voices_for,
    get_regional_entry,
    is_language_production_approved,
    readiness_label,
)


@dataclass(frozen=True)
class LanguageProductionConfig:
    """Canonical display + pipeline binding for one Daily BMT language."""

    language_id: str
    display_name: str
    display_name_local: str
    script_placeholder: str
    male_label: str
    female_label: str
    service_label: str
    preset: VoicePreset
    enabled: bool = True
    requires_regional_approval: bool = False
    target_region: str = ""
    folder_name: str = ""
    short_code: str = ""
    # Real PNG flag icon key (resources/flags). Not emoji — Windows shows emoji as letter codes.
    flag_icon: str = ""

    @property
    def production_approved(self) -> bool:
        if not self.requires_regional_approval:
            return True
        return is_language_production_approved(self.language_id)

    @property
    def male_voice(self) -> str:
        return self.resolved_preset().male_voice

    @property
    def female_voice(self) -> str:
        return self.resolved_preset().female_voice

    @property
    def rate(self) -> str:
        return self.preset.rate

    @property
    def pitch(self) -> str:
        return self.preset.pitch

    @property
    def volume(self) -> str:
        return self.preset.volume

    @property
    def pause_ms(self) -> int:
        return self.preset.pipeline.pause_ms

    @property
    def output_folder(self) -> str:
        return self.folder_name or self.display_name.upper()

    @property
    def target_locale(self) -> str:
        defaults = language_defaults(self.language_id)
        if defaults.get("target_locale"):
            return str(defaults["target_locale"])
        entry = get_regional_entry(self.language_id) if self.requires_regional_approval else {}
        if entry.get("target_locale"):
            return str(entry["target_locale"])
        return self.preset.language

    @property
    def fallback_locale(self) -> str:
        defaults = language_defaults(self.language_id)
        if defaults.get("fallback_locale"):
            return str(defaults["fallback_locale"])
        entry = get_regional_entry(self.language_id) if self.requires_regional_approval else {}
        return str(entry.get("fallback_locale") or "")

    def readiness_state(self) -> str:
        if self.production_approved:
            return "Ready"
        if self.requires_regional_approval:
            return readiness_label(self.language_id)
        return "Ready"

    def resolved_preset(self) -> VoicePreset:
        """Preset with approved / release-default voices applied."""
        if not self.requires_regional_approval:
            return self.preset
        male, female = approved_voices_for(self.language_id)
        if male and female:
            return replace(self.preset, male_voice=male, female_voice=female)
        return self.preset


def _region_for(language_id: str, fallback: str = "") -> str:
    defaults = language_defaults(language_id)
    return str(defaults.get("target_region") or fallback)


DAILY_LANGUAGES: tuple[LanguageProductionConfig, ...] = (
    LanguageProductionConfig(
        language_id="en",
        display_name="English",
        display_name_local="English Devotional",
        script_placeholder="Paste the ENGLISH devotional. Outside braces = Male. {Inside} = Female.",
        male_label="BMT English Male",
        female_label="BMT English Female",
        service_label="Online Neural TTS",
        preset=BMT_ENGLISH,
        enabled=True,
        requires_regional_approval=False,
        folder_name="ENGLISH",
        short_code="EN",
        flag_icon="flag_en.png",
    ),
    LanguageProductionConfig(
        language_id="fr",
        display_name="French",
        display_name_local="French Devotional",
        script_placeholder="Collez le dévotionnel FRANÇAIS. Hors accolades = Homme. {Dedans} = Femme.",
        male_label="BMT French Male",
        female_label="BMT French Female",
        service_label="Online Neural TTS",
        preset=BMT_FRENCH,
        enabled=True,
        requires_regional_approval=False,
        folder_name="FRENCH",
        short_code="FR",
        flag_icon="flag_fr.png",
    ),
    LanguageProductionConfig(
        language_id="sw",
        display_name="Swahili",
        display_name_local="Swahili Devotional",
        script_placeholder="Paste the SWAHILI devotional. Outside braces = Male. {Inside} = Female.",
        male_label="BMT Swahili Male",
        female_label="BMT Swahili Female",
        service_label="Online Neural TTS",
        preset=BMT_SWAHILI,
        enabled=True,
        requires_regional_approval=True,
        target_region=_region_for("sw", "Congo/DRC"),
        folder_name="SWAHILI",
        short_code="SW",
        flag_icon="flag_sw.png",
    ),
    LanguageProductionConfig(
        language_id="pt",
        display_name="Portuguese",
        display_name_local="Portuguese Devotional",
        script_placeholder=(
            "Cole o devocional em PORTUGUÊS.\n"
            "Fora das chaves = Homem.\n"
            "{Dentro} = Mulher."
        ),
        male_label="BMT Portuguese Male",
        female_label="BMT Portuguese Female",
        service_label="Online Neural TTS",
        preset=BMT_PORTUGUESE,
        enabled=True,
        requires_regional_approval=True,
        target_region=_region_for("pt", "Angola"),
        folder_name="PORTUGUESE",
        short_code="PT",
        flag_icon="flag_pt.png",
    ),
)


def selectable_daily_languages() -> list[LanguageProductionConfig]:
    return [cfg for cfg in DAILY_LANGUAGES if cfg.enabled]


def enabled_daily_languages() -> list[LanguageProductionConfig]:
    return selectable_daily_languages()


def production_ready_languages() -> list[LanguageProductionConfig]:
    return [cfg for cfg in selectable_daily_languages() if cfg.production_approved]


def get_language_config(language_id: str) -> LanguageProductionConfig | None:
    for cfg in DAILY_LANGUAGES:
        if cfg.language_id == language_id:
            return cfg
    return None


def default_selected_language_ids() -> list[str]:
    return ["en", "fr"]


def normalize_selected_language_ids(
    ids: Iterable[str] | None,
    *,
    fallback: list[str] | None = None,
) -> list[str]:
    allowed = {cfg.language_id for cfg in selectable_daily_languages()}
    order = [cfg.language_id for cfg in selectable_daily_languages()]
    chosen = []
    for lang_id in ids or []:
        lid = str(lang_id).strip().lower()
        if lid in allowed and lid not in chosen:
            chosen.append(lid)
    if not chosen:
        return list(fallback or default_selected_language_ids())
    return [lid for lid in order if lid in chosen]


def production_details_text(languages: Iterable[LanguageProductionConfig] | None = None) -> str:
    """Friendly Daily summary — no Edge voice IDs, locales, or fallback tech details."""
    langs = list(languages) if languages is not None else selectable_daily_languages()
    blocks: list[str] = []
    for cfg in langs:
        status = "Ready" if cfg.production_approved else cfg.readiness_state()
        blocks.append(
            f"{cfg.display_name.upper()}\n"
            f"Service: {cfg.service_label}\n"
            f"Male voice: {cfg.male_label}\n"
            f"Female voice: {cfg.female_label}\n"
            f"Status: {status}"
        )
    return "\n\n".join(blocks)


def regional_technical_details_text() -> str:
    """Troubleshooting-only technical voice configuration."""
    blocks: list[str] = []
    for cfg in selectable_daily_languages():
        defaults = language_defaults(cfg.language_id)
        preset = cfg.resolved_preset()
        lines = [
            f"{cfg.display_name.upper()}",
            f"target_language: {defaults.get('target_language') or cfg.display_name}",
            f"target_locale: {cfg.target_locale}",
            f"voice_locale: {defaults.get('locale') or preset.language}",
            f"male_voice: {preset.male_voice}",
            f"female_voice: {preset.female_voice}",
            f"rate: {cfg.rate}",
            f"pitch: {cfg.pitch}",
            f"volume: {cfg.volume}",
            f"pause_ms: {cfg.pause_ms}",
            f"production_approved: {cfg.production_approved}",
        ]
        if cfg.target_region:
            lines.insert(2, f"target_region: {cfg.target_region}")
        if cfg.fallback_locale:
            lines.append(f"fallback_locale: {cfg.fallback_locale}")
            lines.append(f"approved_fallback: {bool(defaults.get('approved_fallback'))}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def not_selected_language_block(language_id: str) -> dict:
    cfg = get_language_config(language_id)
    return {
        "selected": False,
        "status": "NOT_SELECTED",
        "ok": None,
        "language": language_id,
        "display_name": cfg.display_name if cfg else language_id,
        "target_locale": cfg.target_locale if cfg else "",
        "provider": "",
        "configured_voice": "",
        "actual_voice": "",
        "segment_count": 0,
        "segments": 0,
        "duration": "",
        "spoken_list_markers_removed": 0,
        "output_files": {},
        "piper_invocations": 0,
        "errors": [],
        "final_mp3": "",
        "final_wav": "",
    }


def unapproved_setup_message(language_id: str) -> str:
    if language_id == "sw":
        return "Swahili requires regional voice verification before first production."
    if language_id == "pt":
        return "Portuguese requires Angola voice verification before first production."
    cfg = get_language_config(language_id)
    name = cfg.display_name if cfg else language_id
    return f"{name} requires voice verification before first production."
