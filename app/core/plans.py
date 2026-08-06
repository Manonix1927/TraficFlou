"""
Тарифні плани та реквізити ФОП.

ЦЕЙ ФАЙЛ — ЄДИНЕ МІСЦЕ, ДЕ ТРЕБА ПРАВИТИ ЦІНИ ТА РЕКВІЗИТИ.
Значення нижче — заготовка: постав свої суми та дані ФОП.
Реквізити можна також задати через змінні оточення (див. FOP_REQUISITES),
щоб не тримати їх у git.
"""

import os

CURRENCY = "UAH"
CURRENCY_SYMBOL = "₴"

# key — стабільний ідентифікатор, потрапляє в замовлення.
# credits — скільки кредитів нараховується (1 кредит = 1 хіт).
# price — вартість у CURRENCY.
PLANS = [
    {
        "key": "start",
        "name": {"uk": "Старт", "ru": "Старт", "en": "Start"},
        "credits": 50_000,
        "price": 490,
        "popular": False,
        "features": {
            "uk": ["До 50 000 хітів", "Гео та джерела на вибір", "Підтримка в чаті"],
            "ru": ["До 50 000 хитов", "Гео и источники на выбор", "Поддержка в чате"],
            "en": ["Up to 50,000 hits", "Custom geo & sources", "Chat support"],
        },
    },
    {
        "key": "business",
        "name": {"uk": "Бізнес", "ru": "Бизнес", "en": "Business"},
        "credits": 200_000,
        "price": 1690,
        "popular": True,
        "features": {
            "uk": ["До 200 000 хітів", "Всі джерела трафіку", "Пріоритетна підтримка"],
            "ru": ["До 200 000 хитов", "Все источники трафика", "Приоритетная поддержка"],
            "en": ["Up to 200,000 hits", "All traffic sources", "Priority support"],
        },
    },
    {
        "key": "pro",
        "name": {"uk": "Про", "ru": "Про", "en": "Pro"},
        "credits": 500_000,
        "price": 3690,
        "popular": False,
        "features": {
            "uk": ["До 500 000 хітів", "Всі джерела трафіку", "Персональний менеджер"],
            "ru": ["До 500 000 хитов", "Все источники трафика", "Персональный менеджер"],
            "en": ["Up to 500,000 hits", "All traffic sources", "Personal manager"],
        },
    },
    {
        "key": "max",
        "name": {"uk": "Максимум", "ru": "Максимум", "en": "Max"},
        "credits": 1_500_000,
        "price": 9900,
        "popular": False,
        "features": {
            "uk": ["До 1 500 000 хітів", "Всі джерела трафіку", "Індивідуальні налаштування"],
            "ru": ["До 1 500 000 хитов", "Все источники трафика", "Индивидуальные настройки"],
            "en": ["Up to 1,500,000 hits", "All traffic sources", "Custom setup"],
        },
    },
]

# Реквізити ФОП. Заповни або постав через змінні оточення на Railway.
FOP_REQUISITES = {
    "recipient": os.getenv("FOP_RECIPIENT", ""),
    "iban": os.getenv("FOP_IBAN", ""),
    "edrpou": os.getenv("FOP_EDRPOU", ""),
    "bank": os.getenv("FOP_BANK", ""),
}


def get_plan(key: str):
    """План за ключем або None."""
    for plan in PLANS:
        if plan["key"] == key:
            return plan
    return None


def plan_name(plan: dict, lang: str) -> str:
    names = plan.get("name", {})
    return names.get(lang) or names.get("uk") or plan["key"]


def plan_features(plan: dict, lang: str) -> list:
    features = plan.get("features", {})
    return features.get(lang) or features.get("uk") or []


def requisites_ready() -> bool:
    """Чи заповнені реквізити — інакше показуємо повідомлення про підтримку."""
    return bool(FOP_REQUISITES.get("recipient") and FOP_REQUISITES.get("iban"))
