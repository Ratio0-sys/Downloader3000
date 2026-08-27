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

import ast
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


def check_signatures(path: Path) -> list[tuple[int, str, str]]:
    """Цвет темы в значении аргумента по умолчанию."""
    found = []
    lines = path.read_text(encoding="utf-8").splitlines()
    inside_def = False
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith(("def ", "async def ")):
            inside_def = not stripped.endswith(":")
        elif inside_def:
            if stripped.endswith(":"):
                inside_def = False
        else:
            continue

        match = PATTERN.search(line)
        if match:
            found.append((number, match.group(1), stripped))
    return found


def check_class_attributes(path: Path) -> list[tuple[int, str, str]]:
    """
    Цвет темы в атрибуте класса.

    Такой же подвох, как со значением по умолчанию, и ровно так же
    незаметен: тело класса выполняется один раз при импорте модуля.
    Именно на этом попался словарь цветов лога — после смены оформления
    строки продолжали краситься по старой палитре.

    Разбираем через ast, а не регулярками: надо отличить присваивание
    в теле класса от такого же внутри метода.
    """
    found = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return found

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, (ast.Assign, ast.AnnAssign)):
                continue
            for sub in ast.walk(item):
                if (
                    isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "t"
                    and sub.attr in THEME_NAMES
                ):
                    found.append((item.lineno, sub.attr, f"class {node.name}: ..."))
    return found


def main() -> int:
    problems = 0
    for path in sorted(CODE_DIR.rglob("*.py")):
        rel = path.relative_to(ROOT)

        for number, name, context in check_signatures(path):
            problems += 1
            print(f"{rel}:{number}: цвет темы в значении по умолчанию — t.{name}")
            print(f"    {context}")
            print("    Замените на None и подставьте значение внутри функции.")

        for number, name, context in check_class_attributes(path):
            problems += 1
            print(f"{rel}:{number}: цвет темы в атрибуте класса — t.{name}")
            print(f"    {context}")
            print("    Вынесите в метод или свойство: тело класса выполняется")
            print("    один раз при импорте, и смена темы на него не подействует.")

    if problems:
        print(f"\nНайдено проблем: {problems}")
        return 1
    print("Цвета темы нигде не захвачены при импорте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
