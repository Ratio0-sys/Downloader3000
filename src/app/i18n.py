# -*- coding: utf-8 -*-
"""
ЛОКАЛИЗАЦИЯ
===========

Весь текст интерфейса лежит не в коде, а в JSON-файлах `assets/locales/`.
В коде остаются только ключи вида `btn.download`, а перевод достаётся
функцией `tr()`.

Зачем так, а не строками прямо в коде: добавить третий язык должно быть
можно, не притрагиваясь к логике — достаточно положить рядом новый файл.

Устойчивость важнее полноты
---------------------------
Отсутствующий файл, битый JSON или забытый ключ НЕ должны ронять программу.
Поэтому порядок поиска перевода такой:

    выбранный язык → русский → сам ключ

В худшем случае пользователь увидит `btn.download` вместо кнопки —
некрасиво, но работать программа не перестанет.
"""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

from . import platform_paths as pp

# Языки, между которыми можно переключаться. Ключ — код, значение — как
# язык называется на самом себе: так понятнее в списке выбора.
LANGUAGES: dict[str, str] = {
    "ru": "Русский",
    "en": "English",
}

DEFAULT_LANGUAGE = "ru"

_current: str = DEFAULT_LANGUAGE
_strings: dict[str, str] = {}
_fallback: dict[str, str] = {}


def _locales_dir() -> Path:
    """
    Где лежат файлы переводов.

    При разработке это `src/assets/locales`, в собранном приложении —
    та же папка рядом с исполняемым файлом. Проверяем оба варианта,
    потому что сборщик раскладывает ресурсы по-разному на разных платформах.
    """
    candidates = [
        pp.app_dir() / "assets" / "locales",
        Path(__file__).resolve().parent.parent / "assets" / "locales",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[-1]


def _load(code: str) -> dict[str, str]:
    """Читает один файл перевода. Ошибку не поднимает — вернёт пустой словарь."""
    try:
        path = _locales_dir() / f"{code}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception:
        # Битый JSON или нет прав на чтение. Молча уходим на запасной язык.
        pass
    return {}


def detect_system_language() -> str:
    """
    Угадывает язык системы при первом запуске.

    Смотрим переменные окружения, потом системную локаль. Если ничего
    не поняли или язык не поддерживается — берём русский.
    """
    raw = ""
    for name in ("LANG", "LANGUAGE", "LC_ALL"):
        raw = os.environ.get(name) or ""
        if raw:
            break
    if not raw:
        try:
            raw = locale.getlocale()[0] or ""
        except Exception:
            raw = ""

    code = raw.replace("-", "_").split("_")[0].lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def set_language(code: str) -> str:
    """
    Переключает язык и загружает словарь.

    Возвращает код языка, который реально применился: если попросили
    неизвестный, откатимся на язык по умолчанию.
    """
    global _current, _strings, _fallback
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE
    _strings = _load(_current)
    # Запасной словарь нужен, если в переводе забыли ключ.
    _fallback = _strings if _current == DEFAULT_LANGUAGE else _load(DEFAULT_LANGUAGE)
    return _current


def current_language() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    """
    Достаёт перевод по ключу.

    Подстановки передаются именованными аргументами и вставляются
    через обычный format: `tr("status.remaining", eta="2 мин")`.
    Если в шаблоне окажется лишняя или забытая подстановка —
    вернём шаблон как есть, но не упадём.
    """
    text = _strings.get(key) or _fallback.get(key) or key
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text


# Загружаем язык по умолчанию сразу, чтобы tr() работала
# даже если настройки ещё не прочитаны.
set_language(DEFAULT_LANGUAGE)
