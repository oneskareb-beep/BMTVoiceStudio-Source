"""French dedicated Neural voices + Edge SSML language lock."""

from __future__ import annotations

from dataclasses import dataclass

from bmt_voice_studio.config.french_tts import (
    FRENCH_FEMALE_VOICE,
    FRENCH_MALE_VOICE,
    remap_french_preset,
    remap_french_voice,
)
from bmt_voice_studio.config.presets import BMT_FRENCH
from bmt_voice_studio.providers.edge_ssml import (
    patch_edge_tts_ssml_lang,
    rewrite_ssml_lang,
    voice_ssml_lang,
)


def test_french_preset_is_dedicated_neural_not_multilingual():
    assert BMT_FRENCH.male_voice == FRENCH_MALE_VOICE
    assert BMT_FRENCH.female_voice == FRENCH_FEMALE_VOICE
    assert "Multilingual" not in BMT_FRENCH.male_voice
    assert "Multilingual" not in BMT_FRENCH.female_voice


def test_remap_replaces_legacy_multilingual_pair():
    assert remap_french_voice("fr-FR-RemyMultilingualNeural") == "fr-FR-HenriNeural"
    assert remap_french_voice("fr-FR-VivienneMultilingualNeural") == "fr-FR-DeniseNeural"
    assert remap_french_voice("fr-FR-HenriNeural") == "fr-FR-HenriNeural"


def test_remap_preset_rewrites_stale_multilingual():
    @dataclass
    class FakePreset:
        language: str
        male_voice: str
        female_voice: str

    stale = FakePreset(
        language="fr-FR",
        male_voice="fr-FR-RemyMultilingualNeural",
        female_voice="fr-FR-VivienneMultilingualNeural",
    )
    fixed = remap_french_preset(stale)  # type: ignore[arg-type]
    assert fixed.male_voice == "fr-FR-HenriNeural"
    assert fixed.female_voice == "fr-FR-DeniseNeural"


def test_voice_ssml_lang_from_shortname():
    assert voice_ssml_lang("fr-FR-HenriNeural") == "fr-FR"
    assert voice_ssml_lang("en-NG-AbeoNeural") == "en-NG"
    assert voice_ssml_lang("sw-TZ-DaudiNeural") == "sw-TZ"
    assert voice_ssml_lang("pt-BR-FranciscaNeural") == "pt-BR"
    assert (
        voice_ssml_lang("Microsoft Server Speech Text to Speech Voice (fr-FR, HenriNeural)")
        == "fr-FR"
    )


def test_rewrite_ssml_locks_french():
    raw = (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
        "<voice name='fr-FR-HenriNeural'>"
        "<prosody pitch='-1Hz' rate='-8%' volume='+5%'>Bonjour</prosody>"
        "</voice></speak>"
    )
    out = rewrite_ssml_lang(raw, "fr-FR")
    assert "xml:lang='fr-FR'" in out
    assert "<lang xml:lang=" not in out
    assert "xml:lang='en-US'" not in out


def test_edge_tts_mkssml_uses_voice_locale():
    patch_edge_tts_ssml_lang()
    from edge_tts.communicate import TTSConfig, mkssml

    tc = TTSConfig("fr-FR-HenriNeural", "-8%", "+5%", "-1Hz", "SentenceBoundary")
    ssml = mkssml(tc, "Bonjour les amis")
    assert "xml:lang='fr-FR'" in ssml
    assert "<lang xml:lang=" not in ssml
    assert "en-US" not in ssml
