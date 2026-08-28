# -*- coding: utf-8 -*-
"""
Скачивает ffmpeg и QuickJS для вшивания в APK.

Зачем это отдельно от fetch_quickjs.py
--------------------------------------
Тот скрипт берёт бинарник под ТУ систему, на которой идёт сборка.
Здесь наоборот: нам нужны бинарники под Android, а собираем мы
на Windows или Linux. Поэтому архитектуры перечислены явно.

Почему обычные статические сборки для Linux подходят
----------------------------------------------------
Android использует libc под названием bionic, а не glibc, и обычно
программы для Linux там не запускаются. Но полностью статический
бинарник не зависит от libc системы вовсе — он несёт свою внутри.

Проверено на живом устройстве Infinix X6725D под Android 15:
и QuickJS, и ffmpeg запустились и отработали.

Куда потом попадают файлы
-------------------------
С Android 10 приложению запрещено запускать файлы из собственной папки
данных. Единственное разрешённое место — каталог нативных библиотек APK.
Файлы туда попадают только под именами вида `lib*.so`, поэтому здесь
они сразу так и называются, хотя это обычные исполняемые файлы,
а не библиотеки.

Раскладывает их по проекту сборки скрипт `inject_android_natives.py`.

Запуск:
    python tools/fetch_android_natives.py
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import io
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT / "build_natives" / "android"

QUICKJS_VERSION = "v0.16.2"
QUICKJS_URL = "https://github.com/quickjs-ng/quickjs/releases/download"

# Основной источник ffmpeg. Сборки там меньше, поэтому и APK выходит легче.
FFMPEG_URL = "https://johnvansickle.com/ffmpeg/releases"

# Запасной источник. Нужен не для красоты: основной — личный сайт одного
# человека, и он ограничивает частоту запросов по адресу. На своей машине
# всё качается, а сборка на GitHub падала через раз — соседние задания
# приходят с тех же адресов и исчерпывают лимит.
#
# Запасной лежит на самом GitHub, откуда сборка и запускается, поэтому
# упереться в лимит там нечему. Бинарник крупнее (49 МБ против 30),
# но это цена за то, что релиз вообще собирается.
FFMPEG_FALLBACK_URL = (
    "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1"
)

# Архитектуры Android, под которые собираем.
# Ключ — имя папки в APK, значения — что качать.
ABIS = {
    "arm64-v8a": {
        "qjs": "qjs-linux-aarch64",
        "ffmpeg": "ffmpeg-release-arm64-static.tar.xz",
        "ffmpeg_fallback": "ffmpeg-linux-arm64.gz",
    },
    "armeabi-v7a": {
        "qjs": "qjs-linux-armv7",
        "ffmpeg": "ffmpeg-release-armhf-static.tar.xz",
        "ffmpeg_fallback": "ffmpeg-linux-arm.gz",
    },
}

# Сколько раз пробовать один и тот же адрес, прежде чем сдаться.
ATTEMPTS = 3


def human(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def download(url: str, label: str, attempts: int = ATTEMPTS) -> bytes | None:
    """
    Качает по адресу, повторяя при неудаче.

    Повторы нужны, потому что чаще всего мешает не поломка, а временный
    отказ: сеть моргнула или сервер ограничил частоту запросов.
    Пауза между попытками растёт, чтобы не долбить сервер подряд.
    """
    for attempt in range(1, attempts + 1):
        data = _download_once(url, label if attempt == 1 else f"{label}, попытка {attempt}")
        if data is not None:
            return data
        if attempt < attempts:
            time.sleep(attempt * 5)
    return None


def _download_once(url: str, label: str) -> bytes | None:
    """Одна попытка. Качает в память: файлы до полусотни мегабайт, это допустимо."""
    request = urllib.request.Request(url, headers={"User-Agent": "Downloader3000-build"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            total = int(response.headers.get("Content-Length") or 0)
            chunks, done = [], 0
            while True:
                chunk = response.read(512 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {label}: {done * 100 // total}%", end="", flush=True)
        print(f"\r  {label}: готово ({human(done)})")
        return b"".join(chunks)
    except urllib.error.HTTPError as exc:
        print(f"\r  {label}: не скачалось — {exc.code} {exc.reason}")
    except Exception as exc:
        print(f"\r  {label}: не скачалось — {exc}")
    return None


def extract_ffmpeg(archive: bytes) -> bytes | None:
    """
    Достаёт единственный нужный файл из архива.

    Внутри лежит папка вида `ffmpeg-7.0.2-arm64-static` с документацией
    и вторым бинарником ffprobe. Нам нужен только ffmpeg — он и так
    весит полсотни мегабайт, тащить остальное в APK незачем.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:xz") as tf:
            for member in tf.getmembers():
                if member.isfile() and member.name.endswith("/ffmpeg"):
                    handle = tf.extractfile(member)
                    if handle:
                        return handle.read()
    except Exception as exc:
        print(f"  не удалось распаковать: {exc}")
    return None


def fetch_ffmpeg(assets: dict) -> bytes | None:
    """
    Достаёт ffmpeg: сперва с основного источника, при неудаче с запасного.

    Форматы у них разные — архив tar.xz с целой папкой внутри против
    одиночного файла под gzip, — поэтому и разбираются по-разному.
    """
    archive = download(f"{FFMPEG_URL}/{assets['ffmpeg']}", "ffmpeg")
    if archive is not None:
        binary = extract_ffmpeg(archive)
        if binary is not None:
            return binary
        print("  ffmpeg: в архиве не нашёлся исполняемый файл")

    print("  ffmpeg: основной источник не дался, беру запасной с GitHub")
    packed = download(f"{FFMPEG_FALLBACK_URL}/{assets['ffmpeg_fallback']}", "ffmpeg (запасной)")
    if packed is None:
        return None
    try:
        return gzip.decompress(packed)
    except Exception as exc:
        print(f"  не удалось распаковать запасной: {exc}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Скачивает бинарники под Android")
    parser.add_argument("--force", action="store_true", help="перекачать, даже если файлы есть")
    parser.add_argument("--abi", choices=list(ABIS), help="только одна архитектура")
    args = parser.parse_args()

    abis = {args.abi: ABIS[args.abi]} if args.abi else ABIS
    total_written = 0

    for abi, assets in abis.items():
        out_dir = TARGET_DIR / abi
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n{abi}")

        # --- QuickJS ---
        qjs_path = out_dir / "libqjs.so"
        if qjs_path.exists() and not args.force:
            print(f"  QuickJS: уже есть ({human(qjs_path.stat().st_size)})")
        else:
            data = download(f"{QUICKJS_URL}/{QUICKJS_VERSION}/{assets['qjs']}", "QuickJS")
            if data is None:
                return 1
            qjs_path.write_bytes(data)
            total_written += len(data)

        # --- ffmpeg ---
        ffmpeg_path = out_dir / "libffmpeg.so"
        if ffmpeg_path.exists() and not args.force:
            print(f"  ffmpeg: уже есть ({human(ffmpeg_path.stat().st_size)})")
        else:
            binary = fetch_ffmpeg(assets)
            if binary is None:
                return 1
            if not binary.startswith(b"ELF"):
                print("  ffmpeg: скачалось что-то не то — это не исполняемый файл")
                return 1
            ffmpeg_path.write_bytes(binary)
            total_written += len(binary)
            print(f"  ffmpeg: распакован ({human(len(binary))})")

    print(f"\nГотово. Файлы в {TARGET_DIR.relative_to(ROOT)}")
    if total_written:
        print(f"Скачано за этот раз: {human(total_written)}")
    print("Дальше: python tools/inject_android_natives.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
