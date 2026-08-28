# -*- coding: utf-8 -*-
"""
Вкладывает ffmpeg и QuickJS в проект сборки Android.

Зачем нужен отдельный шаг
-------------------------
С Android 10 приложение не может запускать файлы из своей папки данных —
это защита W^X. Единственное разрешённое место, откуда запуск возможен, —
каталог нативных библиотек APK. Файлы туда попадают из папки `jniLibs`
и только под именами вида `lib*.so`.

У `flet build` своей опции для нативных библиотек нет: он умеет задавать
разрешения, иконки, метаданные и свойства Gradle, но не это. Поэтому
файлы кладём в сгенерированный проект напрямую.

Почему это работает
-------------------
Flet пересоздаёт проект Flutter только когда меняется шаблон, а не при
каждой сборке. Файлы, которых в шаблоне нет, при повторной сборке
остаются на месте. Отсюда порядок из двух проходов:

    flet build apk src            # первый проход создаёт проект
    python tools/inject_android_natives.py
    flet build apk src            # второй проход забирает библиотеки

Ключ `--clear-cache` удаляет проект целиком, после него вкладывать надо заново.

Запуск:
    python tools/inject_android_natives.py
"""
from __future__ import annotations

import argparse
import contextlib
import shutil
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "build_natives" / "android"

# Куда flet кладёт сгенерированный проект Flutter.
FLUTTER_PROJECT = ROOT / "src" / "build" / "flutter"
JNI_LIBS = FLUTTER_PROJECT / "android" / "app" / "src" / "main" / "jniLibs"


def human(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def main() -> int:
    parser = argparse.ArgumentParser(description="Вкладывает бинарники в проект Android")
    parser.add_argument("--project", help="путь к проекту Flutter, если он не на месте по умолчанию")
    args = parser.parse_args()

    jni_libs = Path(args.project).joinpath("android/app/src/main/jniLibs") if args.project else JNI_LIBS
    project_root = jni_libs.parents[3]

    if not SOURCE_DIR.is_dir():
        print("Нечего вкладывать: сначала выполните")
        print("    python tools/fetch_android_natives.py")
        return 1

    if not project_root.is_dir():
        print(f"Проекта Flutter нет: {project_root}")
        print("Сначала выполните первый проход сборки:")
        print("    flet build apk src")
        return 1

    copied = 0
    total = 0
    for abi_dir in sorted(SOURCE_DIR.iterdir()):
        if not abi_dir.is_dir():
            continue
        target = jni_libs / abi_dir.name
        target.mkdir(parents=True, exist_ok=True)
        print(f"\n{abi_dir.name}")
        for source in sorted(abi_dir.glob("lib*.so")):
            destination = target / source.name
            shutil.copy2(source, destination)
            size = destination.stat().st_size
            copied += 1
            total += size
            print(f"  {source.name:<16} {human(size)}")

    if not copied:
        print("В папке с бинарниками пусто.")
        return 1

    print(f"\nВложено файлов: {copied}, объём: {human(total)}")
    print(f"Каталог: {jni_libs.relative_to(ROOT)}")
    print("\nТеперь повторите сборку, чтобы библиотеки попали в APK:")
    print("    flet build apk src --split-per-abi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
