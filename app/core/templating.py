"""
Спільний Jinja2Templates: у кожен шаблон автоматично потрапляють
t() (переклад), lang (поточна мова) і languages (перемикач).
"""

from fastapi.templating import Jinja2Templates
from app.core.i18n import LANGUAGES, make_translator, resolve_lang


def _i18n_context(request) -> dict:
    lang = resolve_lang(request)
    return {
        "lang": lang,
        "t": make_translator(lang),
        "languages": LANGUAGES,
    }


templates = Jinja2Templates(
    directory="app/templates",
    context_processors=[_i18n_context],
)
