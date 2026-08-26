# -*- coding: utf-8 -*-
"""
Ищет цвета темы, захваченные в значениях по умолчанию.

Зачем: Python вычисляет значения по умолчанию ОДИН РАЗ при импорте модуля.
Если написать `def __init__(self, tint: str = t.GOLD)`, кнопка навсегда
запомнит цвет той темы, что была активна при импорте, и смена оформления
на неё не подействует.

Так уже случилось на светлой теме: кнопки остались с ярко-жёлтым текстом
на белом фоне и стали нечитаемыми.

Запуск:
    python tools/check_theme_defaults.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = ROOT / "src" / "app"

# Имена из theme.py, которые меняются при смене оформления.
THEME_NAMES = (
    "GOLD", "GOLD_A", "GOLD_B", "GOLD_DIM", "GOLD_EDGE", "INK",
    "TEXT", "MUTED", "FAINT", "WARM", "CODE",
    "DANGER", "SUCCESS", "GLASS", "GLASS_HOVER", "STROKE", "PRE_BG",
    "BG_1", "BG_2", "BG_3",
    "FS_H1", "FS_H2", "FS_LABEL", "FS_BODY", "FS_SMALL", "FS_TINY", "FS_MONO",
)

# что-нибудь вида `= t.GOLD,` или `= t.FS_BODY)` внутри строки с def
PATTERN = re.compile(r"=\s*t\.(" + "|".join(THEME_NAMES) + r")\b")


def main() -> int:
    problems = 0
    for path in sorted(CODE_DIR.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        inside_def = False
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                inside_def = not stripped.endswith(":")
                target = line
            elif inside_def:
                target = line
                if stripped.endswith(":"):
                    inside_def = False
            else:
                continue

            match = PATTERN.search(target)
            if match:
                problems += 1
                rel = path.relative_to(ROOT)
                print(f"{rel}:{number}: цвет темы в значении по умолчанию — t.{match.group(1)}")
                print(f"    {stripped}")
                print("    Замените на None и подставьте значение внутри функции.")

    if problems:
        print(f"\nНайдено проблем: {problems}")
        return 1
    print("Цвета темы нигде не захвачены в значениях по умолчанию.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
