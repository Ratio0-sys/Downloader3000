# -*- coding: utf-8 -*-
"""
Проверка словарей локализации.

Ловит три беды, которые иначе видно только глазами в запущенной программе:
  1. ключ используется в коде через tr(), но его нет в словаре;
  2. ключ есть в словаре, но нигде не используется;
  3. языки разошлись — в одном ключ есть, в другом нет.

Отдельно проверяются ключи режимов: они собираются динамически
как `mode.{значение}.name`, и обычным поиском по коду их не найти.
Именно на этом уже один раз попались — значения enum `1080p` и `720p`
не совпали с ключами `mode.1080` и `mode.720`.

Запуск:
    python tools/check_locales.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = ROOT / "src" / "app"
LOCALES_DIR = ROOT / "src" / "assets" / "locales"

# tr("ключ") и tr('ключ') — динамические вызовы вида tr(f"...") обрабатываются отдельно
KEY_CALL = re.compile(r"""tr\(\s*["']([a-z0-9_.]+)["']""", re.IGNORECASE)

# Ключи, которые собираются во время работы и в коде буквально не встречаются.
DYNAMIC_KEYS = {
    f"mode.{mode}.{part}"
    for mode in ("best", "1080p", "720p", "mp3")
    for part in ("name", "desc", "title")
} | {
    # Стадии постобработки: в engine.py лежит словарь
    # {имя_постпроцессора_yt_dlp: ключ_локализации}, и ключ уходит в tr()
    # переменной, поэтому поиском по коду его не видно.
    "stage.downloaded", "stage.merging", "stage.remux",
    "stage.mp3", "stage.thumbnail", "stage.metadata", "stage.moving",
} | {
    # Названия тем: ключ собирается как `theme.{код}` из t.THEMES.
    "theme.original", "theme.dark", "theme.light",
} | {
    "settings.title",
}


def used_keys() -> set[str]:
    found: set[str] = set(DYNAMIC_KEYS)
    for path in CODE_DIR.rglob("*.py"):
        found |= set(KEY_CALL.findall(path.read_text(encoding="utf-8")))
    return found


def load_locales() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(LOCALES_DIR.glob("*.json")):
        try:
            out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[ОШИБКА] {path.name}: битый JSON — {exc}")
            out[path.stem] = {}
    return out


def main() -> int:
    used = used_keys()
    locales = load_locales()
    if not locales:
        print("[ОШИБКА] не найдено ни одного файла локализации")
        return 1

    problems = 0
    print(f"Языков: {len(locales)}  ·  ключей в коде: {len(used)}\n")

    for code, data in locales.items():
        missing = sorted(used - set(data))
        if missing:
            problems += len(missing)
            print(f"[{code}] нет перевода для {len(missing)} ключей:")
            for key in missing:
                print(f"    {key}")

    # Ключи, которые есть в словаре, но нигде не используются
    for code, data in locales.items():
        extra = sorted(set(data) - used)
        if extra:
            print(f"[{code}] лишние ключи ({len(extra)}), нигде не используются:")
            for key in extra:
                print(f"    {key}")

    # Расхождение между языками
    all_keys = set().union(*(set(d) for d in locales.values()))
    for code, data in locales.items():
        diff = sorted(all_keys - set(data))
        if diff:
            problems += len(diff)
            print(f"[{code}] отстаёт от других языков на {len(diff)} ключей:")
            for key in diff:
                print(f"    {key}")

    if problems:
        print(f"\nНайдено проблем: {problems}")
        return 1

    print("Все словари согласованы.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
