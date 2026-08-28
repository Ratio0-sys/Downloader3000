# -*- coding: utf-8 -*-
"""
Скачивает QuickJS — движок JavaScript, который вшивается в сборку.

Зачем он нужен
--------------
YouTube требует решать JS-challenge, иначе отдаёт неполный список форматов,
а часть роликов помечает как недоступные. Решать challenge умеет только
настоящий движок JavaScript, и yt-dlp ищет его в системе: deno, node, bun
или quickjs.

Проблема в том, что у обычного пользователя ничего из этого не стоит.
Deno и Node весят десятки мегабайт и требуют установки, а QuickJS — это
один файл на два мегабайта, который просто лежит рядом. Поэтому в сборку
кладём именно его.

Берём официальные бинарники quickjs-ng с GitHub. Лицензия MIT,
распространять в составе программы можно.

В репозиторий бинарник НЕ коммитится: он качается при сборке.
Так репозиторий остаётся лёгким, а обновить движок можно, поменяв версию здесь.

Запуск:
    python tools/fetch_quickjs.py
    python tools/fetch_quickjs.py --version v0.16.2
"""
from __future__ import annotations

import argparse
import contextlib
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Скрипт печатает по-русски, а на Windows консоль по умолчанию не в UTF-8.
# Без этой строчки первый же print роняет процесс с UnicodeEncodeError,
# и в CI это выглядит как «сборка упала» — хотя не собралось ничего,
# потому что скрипт умер на приветствии. Именно так и случилось однажды.
for stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT / "src" / "assets" / "runtimes"

DEFAULT_VERSION = "v0.16.2"
BASE_URL = "https://github.com/quickjs-ng/quickjs/releases/download"

# Какой файл релиза брать для каждой связки система + архитектура.
# Имя, под которым сохраняем, всегда `qjs` — именно его ищет yt-dlp.
ASSETS = {
    ("Windows", "AMD64"): "qjs-windows-x86_64.exe",
    ("Windows", "x86"): "qjs-windows-x86.exe",
    ("Linux", "x86_64"): "qjs-linux-x86_64",
    ("Linux", "aarch64"): "qjs-linux-aarch64",
    ("Darwin", "x86_64"): "qjs-darwin-x86_64",
    ("Darwin", "arm64"): "qjs-darwin-arm64",
}


def target_name() -> str:
    """Имя файла назначения. На Windows нужно расширение, иначе не запустится."""
    return "qjs.exe" if platform.system() == "Windows" else "qjs"


def pick_asset() -> str | None:
    system = platform.system()
    machine = platform.machine()
    asset = ASSETS.get((system, machine))
    if asset:
        return asset
    # macOS на Apple Silicon иногда представляется по-разному
    if system == "Darwin":
        return ASSETS[("Darwin", "arm64")]
    return None


def download(url: str, target: Path) -> None:
    """Качаем во временный файл и переименовываем — чтобы не оставить огрызок."""
    temp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "Downloader3000-build"})
    with urllib.request.urlopen(request, timeout=120) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with temp.open("wb") as fh:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  скачано {done * 100 // total}%", end="", flush=True)
    print()
    temp.replace(target)


def verify(path: Path) -> str | None:
    """
    Проверяем, что скачался работающий движок.

    У QuickJS нет ключа --version, а --help возвращает ненулевой код возврата —
    поэтому и yt-dlp, и мы смотрим именно на текст вывода.
    """
    try:
        result = subprocess.run(
            [str(path), "--help"], capture_output=True, text=True, timeout=20,
        )
    except Exception as exc:
        return f"не удалось запустить: {exc}"

    output = (result.stdout or "") + (result.stderr or "")
    if "QuickJS" not in output:
        return "это не QuickJS: в выводе --help нет опознавательных знаков"
    first = output.strip().splitlines()[0] if output.strip() else "?"
    print(f"  движок отвечает: {first}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Скачивает QuickJS для вшивания в сборку")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="тег релиза quickjs-ng")
    parser.add_argument("--force", action="store_true", help="перекачать, даже если файл есть")
    args = parser.parse_args()

    asset = pick_asset()
    if asset is None:
        print(f"Нет готового бинарника для {platform.system()} / {platform.machine()}.")
        print("Поставьте Node.js или Deno — программа их тоже поддерживает.")
        return 1

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    target = TARGET_DIR / target_name()

    if target.exists() and not args.force:
        print(f"Уже на месте: {target.relative_to(ROOT)}")
        problem = verify(target)
        if problem is None:
            return 0
        print(f"  но с ним что-то не так — {problem}")
        print("  перекачиваю")

    url = f"{BASE_URL}/{args.version}/{asset}"
    print(f"Качаю {asset} ({args.version})")
    try:
        download(url, target)
    except urllib.error.HTTPError as exc:
        print(f"Не удалось скачать: {exc.code} {exc.reason}")
        print(f"Проверьте, что релиз {args.version} существует.")
        return 1
    except Exception as exc:
        print(f"Не удалось скачать: {exc}")
        return 1

    if platform.system() != "Windows":
        target.chmod(0o755)

    problem = verify(target)
    if problem is not None:
        print(f"Скачанный файл не прошёл проверку: {problem}")
        return 1

    size = target.stat().st_size / 1024 / 1024
    print(f"Готово: {target.relative_to(ROOT)} ({size:.1f} МБ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
