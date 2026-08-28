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
import tempfile
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


def android_storage_dir() -> Path | None:
    """
    Приватная папка приложения на Android.

    Android не даёт писать куда попало: `Path.home()` там указывает на `/data`,
    куда доступа нет вовсе. Обычная домашняя папка как запасной вариант
    не работает — именно на этом приложение падало при старте с
    `PermissionError: '/data/Downloader3000'`.

    Правильный источник — переменные окружения, которые Flet выставляет
    для приложения. Первая из них указывает на постоянное хранилище,
    остальные на кэш и временную папку: они переживают меньше, но писать
    в них тоже можно.
    """
    for name in ("FLET_APP_STORAGE_DATA", "FLET_APP_STORAGE_CACHE", "FLET_APP_STORAGE_TEMP"):
        value = os.environ.get(name)
        if value:
            return Path(value)
    return None


def android_native_lib_dir() -> Path | None:
    """
    Каталог нативных библиотек APK.

    Это единственное место на Android, откуда приложению разрешено
    запускать файлы: с Android 10 действует защита W^X, и запуск чего-либо
    из папки данных приложения блокируется. В каталог нативных библиотек
    файлы попадают при установке APK и получают право на исполнение.

    Путь туда выглядит примерно так:
        /data/app/~~<случайное>/<пакет>-<случайное>/lib/arm64

    Угадать его нельзя — в середине две случайные строки, которые меняются
    при каждой переустановке. Поэтому смотрим в `/proc/self/maps`: там
    перечислены все загруженные в процесс библиотеки вместе с полными
    путями. Достаточно найти любую из них и взять её папку.

    Способ надёжен потому, что к моменту вызова процесс уже загрузил
    свои библиотеки — иначе Python бы не работал.
    """
    if not IS_ANDROID:
        return None
    try:
        with open("/proc/self/maps", encoding="utf-8", errors="ignore") as maps:
            for line in maps:
                marker = line.find("/data/app/")
                if marker < 0 or not line.rstrip().endswith(".so"):
                    continue
                candidate = Path(line[marker:].strip()).parent
                if candidate.name.startswith("lib") or candidate.parent.name == "lib":
                    return candidate
                if candidate.is_dir():
                    return candidate
    except Exception:
        # Нет доступа к /proc или формат неожиданный — не беда,
        # просто останемся без вшитых бинарников.
        pass
    return None


def _first_writable(*candidates: Path, probe_suffix: str = ".txt") -> Path:
    """
    Возвращает первую папку из списка, куда реально получается писать.

    Проверяем не правами доступа, а делом: создаём папку, кладём пробный файл
    и сразу удаляем. Права в Windows и на Android врут слишком часто,
    чтобы им доверять.

    Про `probe_suffix` — это не мелочь, а следствие реальной ошибки.
    Раньше пробник назывался `.d3000_write_test`: скрытый файл без расширения.
    На Android общее хранилище идёт через MediaProvider, и он такие файлы
    просто не пускает, хотя обычные `.mp4` и `.mp3` принимает спокойно.
    В итоге пробник браковал папку `Download/Downloader3000`, в которую
    приложение отлично пишет, и скачанное уезжало в приватную папку,
    где пользователь его не найдёт.

    Поэтому пробуем тем же типом файла, какой будем писать на самом деле.

    Функция обязана вернуть путь и НИКОГДА не бросать исключение. Её зовут
    при старте, до появления интерфейса, поэтому любая ошибка здесь означает
    падение приложения без единого понятного слова на экране. Так и случилось
    на Android: запасной вариант вёл в `/data`, писать туда нельзя,
    и `mkdir` вылетал наружу.
    """
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / f"d3000_probe{probe_suffix}"
            probe.touch()
            probe.unlink()
            return path
        except Exception:
            continue

    # Ни один из предложенных вариантов не подошёл. Пробуем то,
    # что доступно всегда, в порядке убывания долговечности.
    for fallback in (
        android_storage_dir(),
        Path(tempfile.gettempdir()) / "Downloader3000",
    ):
        if fallback is None:
            continue
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
        except Exception:
            continue

    # Совсем безнадёжный случай: отдаём временную папку как есть.
    # Она точно существует, иначе не работал бы сам Python.
    return Path(tempfile.gettempdir())


def default_video_dir() -> Path:
    """
    Куда сохранять видео по умолчанию.

    BUG-1: в старых батниках путь был прописан намертво как
    D:\\download video\\Saveged. У автора диск D существовал, у всех
    остальных — нет, и программа падала на ровном месте.
    Теперь путь вычисляется, а варианты перебираются по убыванию удобства.
    """
    if IS_ANDROID:
        # Сначала общая папка загрузок — оттуда файл видно любому
        # файловому менеджеру. Если разрешения на неё нет, уходим
        # в приватную папку приложения: она доступна всегда.
        base = android_storage_dir()
        return _first_writable(
            Path("/storage/emulated/0/Download/Downloader3000"),
            Path("/sdcard/Download/Downloader3000"),
            *( [base / "Видео"] if base else [] ),
            probe_suffix=".mp4",
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
        base = android_storage_dir()
        return _first_writable(
            Path("/storage/emulated/0/Music/Downloader3000"),
            Path("/storage/emulated/0/Download/Downloader3000"),
            *( [base / "Музыка"] if base else [] ),
            probe_suffix=".m4a",
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
    вместе с настройками. На Android рядом писать нельзя, поэтому берём
    приватную папку приложения.
    """
    if IS_ANDROID:
        # Path.home() на Android указывает на /data — туда писать нельзя.
        # Берём приватную папку приложения, которую выдаёт Flet.
        base = android_storage_dir()
        candidates = [base] if base else []
        candidates.append(Path(tempfile.gettempdir()) / "Downloader3000")
        return _first_writable(*candidates, probe_suffix=".json") / "settings.json"
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
    # На Android бинарник вшит в APK и лежит среди нативных библиотек
    # под именем libffmpeg.so — только оттуда его разрешено запускать.
    native = android_native_lib_dir()
    if native:
        bundled = native / "libffmpeg.so"
        if bundled.exists():
            return str(bundled)

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
    Путь возвращаем только когда движок наш; для системного достаточно имени,
    дальше yt-dlp разберётся сам.

    Замечание: у quickjs исполняемый файл называется `qjs`, а не `quickjs`.

    Где ищем, по убыванию приоритета:
      1. рядом с программой — пользователь положил движок вручную;
      2. в PATH — установлен в системе;
      3. встроенный QuickJS — он вшит в сборку и лежит в ресурсах.

    Встроенный проверяется последним нарочно: если у человека стоит Node
    или Deno, они быстрее решают JS-challenge, и правильнее взять их.
    """
    # На Android движок вшит в APK под именем libqjs.so и лежит среди
    # нативных библиотек. Проверяем его первым: ничего другого там нет.
    native = android_native_lib_dir()
    if native:
        bundled = native / "libqjs.so"
        if bundled.exists():
            return "quickjs", str(bundled)

    candidates = (("deno", "deno"), ("node", "node"), ("bun", "bun"), ("quickjs", "qjs"))
    for runtime, binary in candidates:
        name = binary + ".exe" if IS_WINDOWS else binary
        local = app_dir() / name
        if local.exists():
            return runtime, str(local)
        if shutil.which(binary):
            return runtime, None

    # Запасной вариант, который всегда с собой: QuickJS вшит в сборку.
    # Без него у пользователя без Node и Deno YouTube отдавал бы неполный
    # список форматов, а часть роликов помечал как недоступные.
    bundled = resource_dir() / "assets" / "runtimes" / ("qjs.exe" if IS_WINDOWS else "qjs")
    if bundled.exists():
        return "quickjs", str(bundled)
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
