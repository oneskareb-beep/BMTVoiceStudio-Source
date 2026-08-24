"""Provider registry — Edge, Piper, and future backends."""

from __future__ import annotations

from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.providers.base import BaseTTSProvider, TTSProviderError
from bmt_voice_studio.providers.edge_tts import EdgeTTSProvider
from bmt_voice_studio.providers.piper import PiperProvider

_REGISTRY: dict[str, BaseTTSProvider] = {}


def _build_defaults() -> dict[str, BaseTTSProvider]:
    settings = get_settings()
    return {
        "edge": EdgeTTSProvider(
            timeout=settings.network_timeout,
            retry_count=settings.retry_count,
        ),
        "piper": PiperProvider(),
        # Future: "kokoro": KokoroProvider(), "azure": AzureProvider(), ...
    }


def get_registry() -> dict[str, BaseTTSProvider]:
    global _REGISTRY
    if not _REGISTRY:
        _REGISTRY = _build_defaults()
    return _REGISTRY


def reset_registry() -> None:
    global _REGISTRY
    _REGISTRY = {}


def get_provider(provider_id: str) -> BaseTTSProvider:
    registry = get_registry()
    if provider_id not in registry:
        raise TTSProviderError(f"Unknown TTS provider: {provider_id}")
    return registry[provider_id]


def list_providers() -> list[BaseTTSProvider]:
    return list(get_registry().values())


def register_provider(provider: BaseTTSProvider) -> None:
    get_registry()[provider.id] = provider
