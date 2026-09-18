from pathlib import Path

from video2md.errors import UsageError

SCENE_THRESHOLD = 0.30
MIN_SCENE_INTERVAL = 1.5
MAX_FRAMES = 500
HASH_THRESHOLD = 8
FRAME_EVERY = 5.0
OCR_CONFIDENCE = 0.30
OCR_MIN_CHARS = 12
FRAME_SCALE_MAX = 1920
DEFAULT_WHISPER_MODEL = "turbo"
OCR_FRAMEWORK = "vision"
OCR_LANGUAGES = ["ko-KR", "en-US"]

OCR_LANG = {
    "en": "en-US", "de": "de-DE", "fr": "fr-FR", "es": "es-ES",
    "ko": "ko-KR", "ja": "ja-JP", "zh": "zh-Hans",
    "it": "it-IT", "pt": "pt-BR",
}


def ocr_language_preference(language: str | None) -> list[str]:
    """BCP-47 list for ocrmac. Always a list; Vision rejects a bare string."""
    if language is not None and language in OCR_LANG:
        first = OCR_LANG[language]
        return [first, *[code for code in OCR_LANGUAGES if code != first]]
    return list(OCR_LANGUAGES)

WHISPER_ALIASES = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "turbo": "mlx-community/whisper-large-v3-turbo",
}

WHISPER_REVISIONS = {
    "mlx-community/whisper-tiny-mlx": "6caf9c55601caafbe6508a8b0d216bdf4783c4e8",
    "mlx-community/whisper-base-mlx": "1e3e249fb8d01c655324bd6841b1deadffd6d04c",
    "mlx-community/whisper-small-mlx": "45f3915923c7a79a5a5b5a7d909d39aeb0e5630e",
    "mlx-community/whisper-medium-mlx": "7fc08c4eac4c316526498f147dfdee6f6303f975",
    "mlx-community/whisper-large-v3-mlx": "49e6aa286ad60c14352c404340ded53710378a11",
    "mlx-community/whisper-large-v3-turbo": "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
}

_UNKNOWN_MODEL_MSG = (
    "unknown --whisper-model {value!r}; use an alias "
    "(tiny|base|small|medium|large|turbo) or an existing local directory"
)


def resolve_whisper_model(value: str) -> str:
    """Resolve a whisper model alias, local directory path, or reject raw Hub ids."""
    if value in WHISPER_ALIASES:
        return value
    if Path(value).is_dir():
        return value
    raise UsageError(_UNKNOWN_MODEL_MSG.format(value=value))
