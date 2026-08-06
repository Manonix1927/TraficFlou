"""
Нормалізація Project.pages — {шлях: вага%}.

Формат узгоджений з sources/geo/device: словник {ключ: відсоток},
який напряму йде в pick_weighted(). Тут лише чистимо вхід (порожні
шляхи, відсутній провідний "/", нечислові/нульові ваги).
"""


def normalize_pages(value) -> dict:
    if not isinstance(value, dict):
        return {}

    cleaned = {}
    for path, weight in value.items():
        if not isinstance(path, str):
            continue
        path = path.strip()
        if not path:
            continue
        if not path.startswith("/"):
            path = "/" + path
        try:
            w = int(weight)
        except (TypeError, ValueError):
            continue
        if w > 0:
            cleaned[path] = w
    return cleaned
