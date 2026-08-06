"""
Тарифні плани та реквізити ФОП.

ЦЕЙ ФАЙЛ — ЄДИНЕ МІСЦЕ, ДЕ ТРЕБА ПРАВИТИ ЦІНИ ТА РЕКВІЗИТИ.
Реквізити можна також задати через змінні оточення (див. FOP_REQUISITES),
щоб не тримати їх у git.
"""

import os

CURRENCY = "UAH"
CURRENCY_SYMBOL = "₴"

# Базова ціна за 1 клік (до знижки). Звідси рахується base_price кожного
# плану: credits * CLICK_PRICE. Зміниш тут — перерахується все автоматично.
CLICK_PRICE = 0.0058

# key — стабільний ідентифікатор, потрапляє в замовлення.
# credits — скільки кредитів нараховується (1 кредит = 1 хіт/клік).
# discount_percent — знижка від base_price саме для цього плану (0, якщо
# немає); показується плашкою "-N%" тільки на планах, де вона задана.
PLANS = [
    {
        "key": "start",
        "name": {"uk": "Старт", "ru": "Старт", "en": "Start"},
        "credits": 50_000,
        "popular": False,
        "discount_percent": 0,
    },
    {
        "key": "business",
        "name": {"uk": "Бізнес", "ru": "Бизнес", "en": "Business"},
        "credits": 500_000,
        "popular": True,
        "discount_percent": 0,
    },
    {
        "key": "max",
        "name": {"uk": "Максимум", "ru": "Максимум", "en": "Max"},
        "credits": 2_000_000,
        "popular": False,
        "discount_percent": 15,
    },
]

# Реквізити ФОП. За замовчуванням — фактичні дані нижче; на Railway можна
# перекрити змінними оточення (FOP_RECIPIENT / FOP_IBAN / FOP_EDRPOU /
# FOP_BANK), якщо реквізити зміняться і не хочеться чіпати код.
FOP_REQUISITES = {
    "recipient": os.getenv("FOP_RECIPIENT", "ФОП Волкова Анастасія Сергіївна"),
    "iban": os.getenv("FOP_IBAN", "UA813348510000000026008363839"),
    "edrpou": os.getenv("FOP_EDRPOU", "3587302862"),
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


def base_price(plan: dict) -> float:
    """Ціна до знижки: кредити × ціна за клік."""
    return round(plan["credits"] * CLICK_PRICE, 2)


def final_price(plan: dict) -> float:
    """Ціна після знижки цього плану — те, що реально платить клієнт."""
    discount = plan.get("discount_percent", 0)
    return round(base_price(plan) * (1 - discount / 100), 2)


def requisites_ready() -> bool:
    """Чи заповнені реквізити — інакше показуємо повідомлення про підтримку."""
    return bool(FOP_REQUISITES.get("recipient") and FOP_REQUISITES.get("iban"))
