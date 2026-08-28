# -*- coding: utf-8 -*-
"""
Подготовка релиза.

Берёт то, что собрал `flet build`, раскладывает в `Release/` с понятными
именами и считает контрольные суммы.

Зачем отдельный скрипт: сборщик кладёт результат в `build/<платформа>/`
безликими именами вроде `app-arm64-v8a-release.apk`. По такому файлу
через полгода невозможно понять ни версию, ни для чего он.

Схема имён:
    Downloader3000-<версия>-<платформа>-<архитектура>.<расширение>

Запуск:
    python tools/pack_release.py
    python tools/pack_release.py --version 2.1.0
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import re
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

# Скрипт печатает по-русски: на Windows консоль по умолчанию не в UTF-8,
# и print с кириллицей уронил бы процесс с UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "Release"
PYPROJECT = ROOT / "src" / "pyproject.toml"

PRODUCT = "Downloader3000"


def build_dir() -> Path | None:
    """
    Ищет папку с результатами сборки.

    `flet build <платформа> src` кладёт всё в `src/build/`, потому что
    считает от переданного пути приложения. Но если запустить сборку
    из корня без аргумента, папка окажется в корне. Проверяем оба места,
    иначе скрипт «ничего не находит» на ровном месте.
    """
    for candidate in (ROOT / "src" / "build", ROOT / "build"):
        if candidate.is_dir():
            return candidate
    return None


def read_version() -> str:
    """Версия берётся из pyproject.toml, чтобы не разъезжаться с приложением."""
    try:
        text = PYPROJECT.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "0.0.0"


def sha256(path: Path) -> str:
    """Считаем по кускам: файлы бывают по сто с лишним мегабайт."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def collect_apk(build: Path, version: str) -> list[Path]:
    """
    Забирает собранные APK.

    С флагом --split-per-abi сборщик делает отдельный файл на каждую
    архитектуру. Они втрое меньше универсального, поэтому для релиза
    предпочтительнее — телефон скачивает только своё.
    """
    out: list[Path] = []
    apk_dir = build / "apk"
    if not apk_dir.is_dir():
        return out

    for src in sorted(apk_dir.glob("*.apk")):
        # Из имён вида app-arm64-v8a-release.apk достаём архитектуру
        match = re.search(r"(arm64-v8a|armeabi-v7a|x86_64|x86)", src.name)
        arch = match.group(1) if match else "universal"
        dst = RELEASE / f"{PRODUCT}-{version}-android-{arch}.apk"
        shutil.copy2(src, dst)
        out.append(dst)
    return out


def collect_desktop(build: Path, version: str) -> list[Path]:
    """
    Упаковывает настольные сборки.

    Windows и macOS — в zip, Linux — в tar.gz: там важны права на исполнение,
    а zip их не сохраняет, и распакованный файл просто не запустится.
    """
    out: list[Path] = []
    targets = {
        "windows": ("windows-x64", "zip"),
        "macos": ("macos-universal", "zip"),
        "linux": ("linux-x64", "tar.gz"),
    }

    for folder, (suffix, kind) in targets.items():
        src = build / folder
        if not src.is_dir():
            continue

        # Windows собирается через PyInstaller и даёт один самодостаточный
        # .exe. Заворачивать его в архив незачем: пользователю приятнее
        # скачать файл и сразу запустить, чем сначала распаковывать.
        loose = [f for f in src.iterdir() if f.suffix == ".exe"]
        if folder == "windows" and len(loose) == 1:
            dst = RELEASE / f"{PRODUCT}-{version}-{suffix}.exe"
            shutil.copy2(loose[0], dst)
            out.append(dst)
            continue

        dst = RELEASE / f"{PRODUCT}-{version}-{suffix}.{kind}"
        if kind == "zip":
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in src.rglob("*"):
                    if item.is_file():
                        zf.write(item, item.relative_to(src))
        else:
            with tarfile.open(dst, "w:gz") as tf:
                tf.add(src, arcname=PRODUCT)
        out.append(dst)
    return out


def write_sums(files: list[Path]) -> Path:
    """Формат совместим с `sha256sum -c`."""
    target = RELEASE / "SHA256SUMS.txt"
    lines = [f"{sha256(f)}  {f.name}" for f in sorted(files, key=lambda p: p.name)]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Раскладывает сборки в Release/")
    parser.add_argument("--version", help="версия; по умолчанию из pyproject.toml")
    args = parser.parse_args()

    version = args.version or read_version()
    RELEASE.mkdir(exist_ok=True)

    build = build_dir()
    if build is None:
        print("Папки со сборками нет — сначала соберите приложение:")
        print("    flet build apk src --split-per-abi")
        return 1

    print(f"Версия: {version}")
    print(f"Сборки беру из: {build.relative_to(ROOT)}")
    print()

    files = collect_apk(build, version) + collect_desktop(build, version)
    if not files:
        print("В папке сборок нечего забирать.")
        return 1

    for f in files:
        print(f"  {f.name:<52} {human(f.stat().st_size)}")

    sums = write_sums(files)
    print(f"\nКонтрольные суммы: {sums.name}")
    print(f"Готово: {len(files)} файлов в {RELEASE.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
