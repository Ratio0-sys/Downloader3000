# -*- coding: utf-8 -*-
"""
ПЛАТФОРМЕННЫЕ РАЗЛИЧИЯ
======================

Единственный модуль, который знает, что Windows, Linux, macOS и Android —
разные штуки. Всё остальное приложение написано так, будто платформа одна.

Здесь решаются три вопроса:
  1. Где лежит сама программа и куда складывать скачанное.
  2. Где искать ffmpeg.
  3. Где искать движок JavaScript (он нужен YouTube).

Если когда-нибудь понадобится новая платформа — править надо только этот файл.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# ------------------------------------------------------------- ОПОЗНАНИЕ ОС
# Android определяем по переменным окружения: там нет привычных домашних
# каталогов, а писать можно только в специально отведённые папки.
# sys.platform на Android возвращает "linux", поэтому одного его недостаточно.
IS_ANDROID = bool(os.environ.get("ANDROID_ROOT") or os.environ.get("ANDROID_DATA"))
IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux") and not IS_ANDROID


def app_dir() -> Path:
    """
    Папка, РЯДОМ С КОТОРОЙ живёт программа.

    Сюда пишутся настройки и сюда же по умолчанию складываются скачанные
    файлы, поэтому путь обязан пережить перезапуск.

    Две ситуации:
      - собранное приложение: sys.frozen выставлен, берём папку exe;
      - запуск из исходников: поднимаемся на уровень выше от этого файла,
        то есть в src/.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """
    Папка, ОТКУДА читаются встроенные ресурсы: иконка и файлы локализации.

    Это НЕ то же самое, что app_dir(), и путать их нельзя.

    PyInstaller в режиме одного файла распаковывает всё содержимое
    во временную папку и кладёт её путь в `sys._MEIPASS`. После выхода
    из программы эта папка удаляется. То есть читать ресурсы оттуда можно,
    а писать настройки — категорически нельзя: они исчезнут.

    Порядок проверки:
      1. `sys._MEIPASS` — сборка PyInstaller;
      2. папка рядом с exe — сборка `flet build`, там ресурсы лежат рядом;
      3. папка исходников — обычный запуск при разработке.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _first_writable(*candidates: Path) -> Path:
    """
    Возвращает первую папку из списка, куда реально получается писать.

    Проверяем не правами доступа, а делом: создаём папку, кладём пробный файл
    и сразу удаляем. Права в Windows и на Android врут слишком часто,
    чтобы им доверять.
    """
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".d3000_write_test"
            probe.touch()
            probe.unlink()
            return path
        except Exception:
            continue

    # Совсем некуда писать — уходим в домашнюю папку, лишь бы не падать.
    fallback = Path.home() / "Downloader3000"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def default_video_dir() -> Path:
    """
    Куда сохранять видео по умолчанию.

    BUG-1: в старых батниках путь был прописан намертво как
    D:\\download video\\Saveged. У автора диск D существовал, у всех
    остальных — нет, и программа падала на ровном месте.
    Теперь путь вычисляется, а варианты перебираются по убыванию удобства.
    """
    if IS_ANDROID:
        return _first_writable(
            Path("/storage/emulated/0/Download/Downloader3000"),
            Path("/sdcard/Download/Downloader3000"),
            app_dir() / "Saveged",
        )
    # На десктопе сначала пробуем папку рядом с программой — так она портабельная.
    return _first_writable(
        app_dir() / "Saveged",
        Path.home() / "Videos" / "Downloader3000",
        Path.home() / "Downloads" / "Downloader3000",
    )


def default_audio_dir() -> Path:
    """Куда сохранять музыку. Логика та же, но целимся в музыкальные папки."""
    if IS_ANDROID:
        return _first_writable(
            Path("/storage/emulated/0/Music/Downloader3000"),
            Path("/storage/emulated/0/Download/Downloader3000"),
            app_dir() / "Sounds",
        )
    return _first_writable(
        app_dir() / "Sounds",
        Path.home() / "Music" / "Downloader3000",
        Path.home() / "Downloads" / "Downloader3000",
    )


def config_path() -> Path:
    """
    Файл настроек.

    На десктопе кладём рядом с программой — тогда её можно носить на флешке
    вместе с настройками. На Android рядом писать нельзя, уходим в домашнюю папку.
    """
    if IS_ANDROID:
        return _first_writable(Path.home() / ".downloader3000") / "settings.json"
    return app_dir() / "settings.json"


def find_ffmpeg() -> str | None:
    """
    Ищет ffmpeg. Возвращает ПОЛНЫЙ ПУТЬ к бинарнику или None.

    BUG-4: раньше наличие ffmpeg вообще не проверялось, и человек получал
    невнятную ошибку постпроцессинга уже после скачивания.

    Важно понимать: для видео с YouTube ffmpeg не «желателен», а обязателен.
    Совмещённых форматов (видео и звук одним файлом) там больше нет —
    проверено на живом ролике: 32 потока без звука, 11 без картинки,
    ни одного цельного. Всё требует склейки.

    Порядок поиска — от самого явного к самому неочевидному:
      1. рядом с программой (пользователь положил вручную);
      2. в PATH (установлен в системе);
      3. внутри пакета imageio-ffmpeg (приезжает вместе с зависимостями).

    Почему возвращаем путь к файлу, а не папку: у бандла imageio имя вида
    `ffmpeg-win-x86_64-v7.1.exe`, и по имени папки yt-dlp его не опознаёт.
    Проверено напрямую: location=папка → not available, location=файл → available.
    """
    names = ("ffmpeg.exe", "ffmpeg") if IS_WINDOWS else ("ffmpeg",)
    for name in names:
        local = app_dir() / name
        if local.exists():
            return str(local)

    found = shutil.which("ffmpeg")
    if found:
        return str(found)

    # Колесо imageio-ffmpeg привозит настоящий ffmpeg внутри пакета —
    # благодаря этому на десктопе всё работает без ручной установки.
    try:
        import imageio_ffmpeg

        exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if exe.exists():
            return str(exe)
    except Exception:
        # Пакета нет или он сломан — не беда, просто вернём None.
        pass
    return None


def find_js_runtime() -> tuple[str, str | None] | None:
    """
    Ищет движок JavaScript. Возвращает (имя, путь) или None.

    BUG-3: в батниках было жёстко прописано `--js-runtimes deno`, хотя deno
    в системе не стоял. yt-dlp это молча проглатывал и терял часть форматов
    YouTube — тот требует исполнения JS, чтобы отдать полный список.

    Порядок совпадает с приоритетом самого yt-dlp: deno, node, bun, quickjs.
    Путь возвращаем только для найденного рядом с программой; для системного
    достаточно имени, дальше yt-dlp разберётся сам.

    Замечание: у quickjs исполняемый файл называется `qjs`, а не `quickjs`.
    """
    candidates = (("deno", "deno"), ("node", "node"), ("bun", "bun"), ("quickjs", "qjs"))
    for runtime, binary in candidates:
        local = app_dir() / (binary + ".exe" if IS_WINDOWS else binary)
        if local.exists():
            return runtime, str(local)
        if shutil.which(binary):
            return runtime, None
    return None


def platform_name() -> str:
    """Название платформы для показа в интерфейсе."""
    if IS_ANDROID:
        return "Android"
    if IS_WINDOWS:
        return "Windows"
    if IS_MACOS:
        return "macOS"
    if IS_LINUX:
        return "Linux"
    return sys.platform
