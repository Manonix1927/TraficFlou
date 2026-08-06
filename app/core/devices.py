"""
Нормализация поля Project.device к виду {device: %}.

Колонка device исторически создавалась как VARCHAR ('desktop' / 'mobile' /
'mixed'), затем модель переехала на JSON. На базах, где ALTER COLUMN ... TYPE
JSONB не отработал, значение возвращается строкой — либо legacy-названием
устройства, либо JSON-текстом вида '{"desktop":84,...}'. Всё это приводим
к словарю, иначе isinstance(..., dict) молча падает на 100% desktop.
"""

import json

VALID_DEVICES = ("desktop", "mobile", "tablet")
DEFAULT_DEVICE = {"desktop": 100}


def normalize_device(value) -> dict:
    """Приводит любое представление device к {device: вес}."""
    if isinstance(value, dict):
        cleaned = {
            k: int(v)
            for k, v in value.items()
            if k in VALID_DEVICES and _as_int(v) > 0
        }
        return cleaned or dict(DEFAULT_DEVICE)

    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{"):
            try:
                return normalize_device(json.loads(text))
            except (ValueError, TypeError):
                return dict(DEFAULT_DEVICE)
        # legacy-форматы
        if text == "mixed":
            return {"desktop": 34, "mobile": 33, "tablet": 33}
        if text in VALID_DEVICES:
            return {text: 100}

    return dict(DEFAULT_DEVICE)


def _as_int(v) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0
