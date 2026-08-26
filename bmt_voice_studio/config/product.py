"""Ministry product modes: BMT (existing) vs HHR / Ruhuka Umutima."""

from __future__ import annotations

from dataclasses import dataclass

PRODUCT_BMT = "bmt"
PRODUCT_HHR = "hhr"
HHR_LOGO_FILE = "hhr_logo.png"

# Dark forest green from the HHR banner, plus a softer sage for video pads.
HHR_GREEN_DEEP = (10, 46, 34, 255)
HHR_GREEN_SOFT = (46, 90, 72)
HHR_CREAM = (244, 247, 242, 255)
HHR_GOLD = (214, 186, 122, 255)


@dataclass(frozen=True)
class ProductProfile:
    id: str
    short_label: str
    title: str
    tagline: str
    generate_label: str
    audio_subtitle: str
    default_languages: tuple[str, ...]
    spoken_language: str
    caption_primary: str
    caption_secondary: str
    author: str
    kicker: str
    logo_file: str
    template_id: str


BMT_PRODUCT = ProductProfile(
    id=PRODUCT_BMT,
    short_label="BMT",
    title="BMT Voice Studio",
    tagline="Believers Manna Today",
    generate_label="Generate today's devotional",
    audio_subtitle="Date and languages, then the scripts — Generate when ready",
    default_languages=("en", "fr"),
    spoken_language="en",
    caption_primary="en",
    caption_secondary="",
    author="Apostle (Dr.) David A. Aderibigbe",
    kicker="DAILY DEVOTIONAL",
    logo_file="bbnet_logo.png",
    template_id="bmt_classic",
)

HHR_PRODUCT = ProductProfile(
    id=PRODUCT_HHR,
    short_label="HHR",
    title="Hope & Healing Africa",
    tagline="RUHUKA UMUTIMA",
    generate_label="Generate today's chaplaincy message",
    audio_subtitle="Swahili voice, Kinyarwanda transcript, English captions — then Generate",
    default_languages=("sw",),
    spoken_language="sw",
    caption_primary="rw",
    caption_secondary="en",
    author="Apostle (Dr.) David A. Aderibigbe",
    kicker="CHAPLAINCY MESSAGE FOR THE DAY",
    logo_file=HHR_LOGO_FILE,
    template_id="hhr_green",
)

_PRODUCTS = {PRODUCT_BMT: BMT_PRODUCT, PRODUCT_HHR: HHR_PRODUCT}


def normalize_product(value: str | None) -> str:
    raw = (value or PRODUCT_BMT).strip().lower()
    aliases = {
        "bmt": PRODUCT_BMT,
        "believers": PRODUCT_BMT,
        "manna": PRODUCT_BMT,
        "hhr": PRODUCT_HHR,
        "hha": PRODUCT_HHR,
        "ruhuka": PRODUCT_HHR,
        "ruhuka umutima": PRODUCT_HHR,
        "hope": PRODUCT_HHR,
        "hope and healing": PRODUCT_HHR,
        "hope & healing africa": PRODUCT_HHR,
    }
    return aliases.get(raw, PRODUCT_HHR if raw.startswith("hh") else PRODUCT_BMT)


def is_hhr(value: str | None) -> bool:
    return normalize_product(value) == PRODUCT_HHR


def get_product(value: str | None = None) -> ProductProfile:
    return _PRODUCTS[normalize_product(value)]
