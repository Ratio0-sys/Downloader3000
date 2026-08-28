# -*- coding: utf-8 -*-
"""
ДВИЖОК СКАЧИВАНИЯ
=================

Обёртка над библиотекой yt-dlp. Здесь происходит вся настоящая работа,
а интерфейс только показывает результат.

Главное отличие от старых батников
----------------------------------
Раньше батник запускал внешний `yt-dlp.exe` и передавал ему аргументы строкой.
Отсюда росли сразу несколько багов: ссылка с символом `&` рвала команду,
путь к программе искали не там, а экранирование кавычек было лотереей.

Теперь yt-dlp — это импортированный Python-пакет. Мы не строим командную
строку вообще: настройки передаются обычным словарём. Как бонус,
это единственный способ заставить yt-dlp работать на Android,
потому что там нельзя просто запустить посторонний .exe.

Как это работает по шагам
-------------------------
1. `detect()` осматривает систему: есть ли ffmpeg, есть ли JS-движок.
2. `format_selector()` по выбранному режиму собирает строку формата
   в синтаксисе yt-dlp — что именно качать.
3. `build_opts()` складывает все настройки в словарь.
4. `download()` создаёт YoutubeDL с этим словарём и запускает скачивание.
5. По ходу дела yt-dlp дёргает наши хуки, а те пересылают прогресс в интерфейс.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from . import platform_paths as pp
from .i18n import tr

# Компоненты, которые yt-dlp разрешено догружать во время работы.
#
# Зачем это нужно. YouTube требует решать JS-challenge, и без решателя
# часть роликов отдаётся как «This video is not available» — проверено
# на живом плейлисте. Сам решатель внутрь yt-dlp не входит: он скачивается
# по требованию, и по умолчанию это ЗАПРЕЩЕНО.
#
# Говорю прямо, потому что это не мелочь: во время работы yt-dlp скачивает
# JS-код и исполняет его найденным движком (node/deno/bun). Берём источником
# официальный репозиторий проекта yt-dlp-ejs, а не npm — там код подписан
# самими разработчиками yt-dlp.
REMOTE_COMPONENTS = ["ejs:github"]


class Mode(str, Enum):
    """
    Режимы скачивания — те же четыре, что были отдельными батниками.

    Наследуемся от str, чтобы значение можно было без плясок писать
    в JSON-настройки и читать обратно.
    """

    BEST = "best"
    P1080 = "1080p"
    P720 = "720p"
    MP3 = "mp3"

    @property
    def title(self) -> str:
        """
        Человеческое название для интерфейса.

        Берётся из словаря локализации, а не из кода: ключ строится
        из значения режима, например `mode.720.title`.
        """
        return tr(f"mode.{self.value}.title")

    @property
    def is_audio(self) -> bool:
        """Аудио-режим ведёт себя иначе: другая папка и другой постпроцессинг."""
        return self is Mode.MP3


@dataclass
class Progress:
    """
    Снимок состояния для интерфейса.

    percent = None означает «работа идёт, но проценты неизвестны».
    Так бывает на склейке и конвертации: ffmpeg не сообщает прогресс,
    поэтому в эти моменты полоска переключается в бесконечный режим.
    """

    percent: float | None = None
    speed: str = ""        # уже отформатированная строка, например «12.4 МБ/с»
    eta: str = ""          # «2 мин 15 с»
    stage: str = ""        # название текущей стадии постобработки
    filename: str = ""
    item_index: int = 0    # какой по счёту ролик качается (для плейлиста)
    item_total: int = 0    # сколько всего роликов в задании


@dataclass
class PlaylistItem:
    """Одна позиция плейлиста в списке выбора."""

    index: int             # порядковый номер, начиная с 1 — его понимает yt-dlp
    title: str
    duration: int | None   # в секундах, у стримов бывает None
    video_id: str = ""
    selected: bool = True  # по умолчанию отмечены все

    @property
    def duration_text(self) -> str:
        """Длительность в виде «7:12» или «1:02:33»."""
        if not self.duration:
            return "—"
        total = int(self.duration)
        h, rest = divmod(total, 3600)
        m, s = divmod(rest, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class PlaylistInfo:
    """Результат сканирования плейлиста."""

    title: str
    items: list[PlaylistItem]

    @property
    def total_duration(self) -> int:
        return sum(i.duration or 0 for i in self.items if i.selected)


@dataclass
class Environment:
    """
    Что нашлось в системе.

    Показываем пользователю честно: если чего-то нет, лучше сказать заранее,
    чем уронить скачивание на середине непонятной ошибкой.
    """

    ffmpeg_path: str | None = None
    js_runtime: tuple[str, str | None] | None = None   # (имя, путь или None)
    platform: str = ""
    ytdlp_version: str = ""

    @property
    def has_ffmpeg(self) -> bool:
        return self.ffmpeg_path is not None

    @property
    def can_merge(self) -> bool:
        """
        Можно ли склеить видео со звуком.

        YouTube отдаёт картинку и звук раздельными потоками, и объединить их
        умеет только ffmpeg. Без него доступно лишь то, что уже лежит
        одним готовым файлом — а на YouTube такого практически не осталось.
        """
        return self.has_ffmpeg


def _fmt_size(num: float | None) -> str:
    """Байты в секунду → «12.4 МБ». Возвращает пустую строку, если нечего показывать."""
    if not num:
        return ""
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} ТБ"


def _fmt_eta(seconds: float | None) -> str:
    """Секунды → «2 мин 15 с». Пустая строка, если yt-dlp ещё не оценил время."""
    if not seconds:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} с"
    if seconds < 3600:
        return f"{seconds // 60} мин {seconds % 60} с"
    return f"{seconds // 3600} ч {(seconds % 3600) // 60} мин"


class _Logger:
    """
    Приёмник сообщений yt-dlp.

    yt-dlp ожидает объект с методами debug/info/warning/error. Мы подсовываем
    свой и перенаправляем всё в лог приложения, помечая уровень важности,
    чтобы интерфейс раскрасил строки: ошибки красным, предупреждения золотом.
    """

    def __init__(self, sink: Callable[[str, str], None]):
        self._sink = sink

    def debug(self, msg: str) -> None:
        # В debug() прилетает и служебная отладка, и обычные сообщения.
        # Настоящая отладка помечена префиксом — её отбрасываем, чтобы не засорять лог.
        if msg.startswith("[debug] "):
            return
        self._sink(msg, "info")

    def info(self, msg: str) -> None:
        self._sink(msg, "info")

    def warning(self, msg: str) -> None:
        self._sink(msg, "warn")

    def error(self, msg: str) -> None:
        self._sink(msg, "error")


class Engine:
    """Один экземпляр на всё приложение: помнит окружение и умеет качать."""

    def __init__(self) -> None:
        self.env = Environment()
        # Event, а не обычный bool: флаг ставится из потока интерфейса,
        # а читается из рабочего потока. Event делает это безопасно.
        self._cancel = threading.Event()
        self.last_file: str | None = None
        self._queue_total = 1        # сколько роликов в текущем задании
        self._queue_done = 0
        # Прокси общий для всех запросов движка, поэтому живёт на объекте,
        # а не ходит аргументом через каждый метод. Пусто — идём напрямую.
        self.proxy: str = ""
        self.detect()

    # ========================================================== ОКРУЖЕНИЕ
    def detect(self) -> Environment:
        """Пересканировать систему. Вызывается на старте и по кнопке обновления."""
        self.env = Environment(
            ffmpeg_path=pp.find_ffmpeg(),
            js_runtime=pp.find_js_runtime(),
            platform=pp.platform_name(),
            ytdlp_version=yt_dlp.version.__version__,
        )
        return self.env

    # =========================================================== ПЛЕЙЛИСТЫ
    @staticmethod
    def is_playlist_url(url: str) -> bool:
        """
        Похожа ли ссылка на плейлист.

        Ловим три формы, которые встречаются на YouTube:
            youtube.com/playlist?list=...
            youtube.com/watch?v=...&list=...
            youtu.be/...?list=...

        Третья появляется сама, когда включён автоплей, — именно из-за неё
        старые батники внезапно начинали качать двести роликов подряд.
        """
        low = (url or "").lower()
        if "list=" not in low:
            return False
        # Радиомиксы YouTube генерирует на лету, скачивать их целиком бессмысленно
        return not any(mark in low for mark in ("list=rd", "list=ul", "list=ytsearch"))

    def _apply_proxy(self, opts: dict) -> None:
        """
        Добавляет прокси в настройки запроса, если он задан.

        Отдельным методом, потому что путей два — чтение плейлиста
        и само скачивание, — и забыть один из них слишком легко.
        """
        if self.proxy:
            opts["proxy"] = self.proxy

    def scan_playlist(self, url: str, on_line: Callable[[str, str], None] | None = None
                      ) -> PlaylistInfo | None:
        """
        Читает состав плейлиста, ничего не скачивая.

        Работает быстро благодаря extract_flat: yt-dlp не заходит на страницу
        каждого ролика, а берёт названия и длительность из общего ответа.
        Девятнадцать позиций разбираются меньше чем за секунду.

        Возвращает None, если это не плейлист или он пустой.
        """
        sink = on_line or (lambda *_: None)
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            # in_playlist — не разворачивать вложенные плейлисты
            "extract_flat": "in_playlist",
            "logger": _Logger(sink),
        }
        if self.env.js_runtime:
            name, path = self.env.js_runtime
            opts["js_runtimes"] = {name: {"path": path} if path else {}}
            opts["remote_components"] = REMOTE_COMPONENTS
        self._apply_proxy(opts)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except DownloadError as exc:
            sink(_humanize(str(exc)), "error")
            return None
        except Exception as exc:
            sink(tr("error.playlist_read", message=exc), "error")
            return None

        if not info or info.get("_type") != "playlist":
            return None

        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            return None

        # В плоском режиме playlist_index не заполняется, поэтому нумеруем сами.
        # Именно эти номера потом уходят в yt-dlp как playlist_items.
        items = [
            PlaylistItem(
                index=position,
                title=str(entry.get("title") or tr("playlist.no_title")),
                duration=entry.get("duration"),
                video_id=str(entry.get("id") or ""),
            )
            for position, entry in enumerate(entries, start=1)
        ]
        return PlaylistInfo(title=str(info.get("title") or tr("playlist.default_title")), items=items)

    @staticmethod
    def _items_spec(items: list[PlaylistItem]) -> str:
        """
        Собирает строку выбранных позиций для yt-dlp: «1,3,5-7».

        Диапазоны склеиваем не для красоты: у плейлиста на две сотни роликов
        строка из отдельных номеров получается неприлично длинной.
        """
        numbers = sorted(i.index for i in items if i.selected)
        if not numbers:
            return ""

        parts: list[str] = []
        start = prev = numbers[0]
        for number in numbers[1:]:
            if number == prev + 1:
                prev = number
                continue
            parts.append(str(start) if start == prev else f"{start}-{prev}")
            start = prev = number
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        return ",".join(parts)

    # ============================================================= ФОРМАТ
    def format_selector(self, mode: Mode) -> str:
        """
        Собирает строку формата на языке yt-dlp.

        Синтаксис короткий, но плотный:
          `bestvideo+bestaudio` — взять лучшее видео и лучший звук и склеить;
          `[height<=720]`       — ограничение по высоте кадра;
          `[ext=mp4]`           — предпочесть конкретный контейнер;
          `/`                   — «если не вышло, попробуй следующее».

        То есть вся строка читается как цепочка запасных вариантов слева направо.

        Про режим без ffmpeg надо честно: на YouTube он почти бесполезен.
        Проверено на живом видео — 32 потока без звука, 11 без картинки
        и ни одного совмещённого. Но на многих других сайтах готовый файл
        со звуком есть, поэтому мы всё же пробуем, а не отказываемся заранее.
        """
        if mode.is_audio:
            # Для звука mp4-контейнер (m4a) удобнее: его ffmpeg жуёт быстрее всего.
            return "bestaudio[ext=m4a]/bestaudio"

        if not self.env.can_merge:
            cap = {Mode.BEST: "", Mode.P1080: "[height<=1080]", Mode.P720: "[height<=720]"}[mode]
            # Финальный `/best` — последняя надежда: пусть отдаст хоть что-нибудь цельное.
            return f"best{cap}[ext=mp4]/best{cap}/best"

        if mode is Mode.BEST:
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        height = 1080 if mode is Mode.P1080 else 720
        return (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        )

    def _outtmpl(self, mode: Mode) -> str:
        """
        Шаблон имени файла.

        `%(title)s` и `%(ext)s` — подстановки yt-dlp: название ролика и расширение.
        Для 720p и 1080p добавляем пометку в имя, как было в старых батниках.
        """
        suffix = {Mode.P1080: " [1080p]", Mode.P720: " [720p]"}.get(mode, "")
        return f"%(title)s{suffix}.%(ext)s"

    def build_opts(
        self,
        mode: Mode,
        outdir: Path,
        *,
        items: list[PlaylistItem] | None = None,
        threads: int = 4,
        on_line: Callable[[str, str], None] | None = None,
        on_progress: Callable[[Progress], None] | None = None,
    ) -> dict:
        """
        Собирает словарь настроек для YoutubeDL.

        Это прямой аналог аргументов командной строки, только без строк
        и экранирования. Имена ключей совпадают с внутренними именами опций
        yt-dlp (они же `dest` у параметров CLI).
        """
        # Если колбэки не передали — подставляем заглушки, чтобы дальше
        # не проверять на None в каждом хуке.
        sink = on_line or (lambda *_: None)
        report = on_progress or (lambda _: None)

        opts: dict = {
            "format": self.format_selector(mode),
            "outtmpl": {"default": self._outtmpl(mode)},

            # Куда складывать. Папку создаём сами в download() — см. BUG-8.
            "paths": {"home": str(outdir)},

            # BUG-7: ссылка вида ...&list=... раньше утаскивала весь плейлист целиком.
            # Теперь либо одно видео, либо ровно те позиции, что отметил человек.
            "noplaylist": not items,

            # BUG-10: длинные названия роликов упирались в предел длины пути Windows,
            # и скачивание падало у самого финиша. Подрезаем имя заранее.
            "trim_file_name": 180,
            "windowsfilenames": pp.IS_WINDOWS,

            # Сеть бывает нестабильной — пусть пробует несколько раз сам.
            "retries": 10,
            "fragment_retries": 10,

            # Скачивание кусками в несколько потоков заметно ускоряет процесс.
            "concurrent_fragment_downloads": max(1, min(16, threads)),

            # Наши перехватчики: прогресс скачивания и стадии постобработки.
            "progress_hooks": [self._make_progress_hook(report)],
            "postprocessor_hooks": [self._make_pp_hook(report)],

            "logger": _Logger(sink),

            # Текстовый прогресс-бар не нужен: проценты рисует интерфейс.
            "noprogress": True,
            "quiet": True,
            "no_warnings": False,     # предупреждения полезны, показываем
            "ignoreerrors": False,    # ошибку хотим видеть, а не проглатывать
        }

        # Плейлист: качаем только отмеченные позиции.
        if items:
            spec = self._items_spec(items)
            if spec:
                opts["playlist_items"] = spec
            # Номер позиции в начале имени файла. Без него ролики сваливаются
            # в папку без всякого порядка, и понять последовательность нельзя.
            opts["outtmpl"] = {"default": "%(playlist_index)02d. " + self._outtmpl(mode)}

        if self.env.has_ffmpeg:
            # Передаём полный путь к бинарнику, а не папку.
            # Проверено: бандл imageio-ffmpeg лежит под именем
            # ffmpeg-win-x86_64-v7.1.exe, и по папке yt-dlp его не находит.
            opts["ffmpeg_location"] = self.env.ffmpeg_path

        # Разрешаем догрузку решателя JS-challenge, см. REMOTE_COMPONENTS.
        opts["remote_components"] = REMOTE_COMPONENTS

        # BUG-3: в батниках было жёстко прописано `--js-runtimes deno`,
        # хотя deno в системе нет. yt-dlp молча терял часть форматов YouTube.
        # Теперь включаем тот движок, который реально установлен.
        # Важно: в библиотечном API это словарь {имя: {'path': ...}}, а не список.
        if self.env.js_runtime:
            name, path = self.env.js_runtime
            opts["js_runtimes"] = {name: {"path": path} if path else {}}

        self._apply_proxy(opts)

        if mode.is_audio:
            if self.env.has_ffmpeg:
                # Постпроцессоры выполняются по очереди после скачивания:
                # вытащить звук → записать теги → вшить обложку.
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
                    {"key": "FFmpegMetadata"},
                    {"key": "EmbedThumbnail"},
                ]
                opts["writethumbnail"] = True   # обложку надо сначала скачать
            # Без ffmpeg конвертировать нечем — сохраняем исходный звук как есть.
        else:
            if self.env.can_merge:
                opts["merge_output_format"] = "mp4"

        return opts

    # =============================================================== ХУКИ
    def _make_progress_hook(self, report: Callable[[Progress], None]):
        """
        Создаёт функцию, которую yt-dlp вызывает много раз в секунду
        по ходу скачивания. Замыкание нужно, чтобы протащить внутрь `report`.
        """

        def hook(d: dict) -> None:
            if self._cancel.is_set():
                # Единственный штатный способ прервать скачивание изнутри —
                # бросить это исключение. yt-dlp поймает его и корректно свернётся.
                raise DownloadCancelled("cancelled")

            status = d.get("status")

            if status == "downloading":
                # Точный размер известен не всегда, поэтому берём оценку как запасной вариант.
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes") or 0
                percent = (done / total * 100) if total else None
                speed = d.get("speed")
                info = d.get("info_dict") or {}
                report(
                    Progress(
                        percent=percent,
                        speed=f"{_fmt_size(speed)}/с" if speed else "",
                        eta=_fmt_eta(d.get("eta")),
                        filename=d.get("filename") or "",
                        # Для плейлиста показываем «видео 3 из 7»
                        item_index=int(info.get("playlist_autonumber") or 0),
                        item_total=self._queue_total,
                    )
                )
            elif status == "finished":
                # Срабатывает на каждый поток: отдельно на видео, отдельно на звук.
                self.last_file = d.get("filename") or self.last_file
                report(Progress(percent=100, stage=tr("stage.downloaded")))

        return hook

    def _make_pp_hook(self, report: Callable[[Progress], None]):
        """
        Хук стадий постобработки: склейка, конвертация, обложка.

        Прогресса в процентах здесь нет — ffmpeg о нём не сообщает.
        Поэтому просто показываем название стадии, а полоска крутится.
        """
        # Ключи локализации для каждого постпроцессора yt-dlp.
        names = {
            "FFmpegMerger": "stage.merging",
            "FFmpegVideoRemuxer": "stage.remux",
            "FFmpegExtractAudio": "stage.mp3",
            "EmbedThumbnail": "stage.thumbnail",
            "FFmpegMetadata": "stage.metadata",
            "MoveFiles": "stage.moving",
        }

        def hook(d: dict) -> None:
            if self._cancel.is_set():
                raise DownloadCancelled("cancelled")

            if d.get("status") != "started":
                # На завершении постпроцессора запоминаем итоговый путь —
                # он пригодится, чтобы открыть папку именно на этом файле.
                if d.get("status") == "finished":
                    info = d.get("info_dict") or {}
                    self.last_file = info.get("filepath") or self.last_file
                return

            key = names.get(d.get("postprocessor", ""), "")
            if key:
                report(Progress(percent=None, stage=tr(key)))

        return hook

    # ========================================================= СКАЧИВАНИЕ
    def download(
        self,
        url: str,
        mode: Mode,
        outdir: Path,
        *,
        items: list[PlaylistItem] | None = None,
        threads: int = 4,
        on_line: Callable[[str, str], None] | None = None,
        on_progress: Callable[[Progress], None] | None = None,
    ) -> tuple[bool, str]:
        """
        Качает одну ссылку. Блокирующий вызов — запускать в отдельном потоке.

        Возвращает пару (успех, сообщение). Исключения наружу принципиально
        не выпускаем: пользователю нужен понятный текст, а не трейсбек.
        """
        sink = on_line or (lambda *_: None)
        self._cancel.clear()      # сбрасываем флаг с прошлого запуска
        self.last_file = None

        # BUG-8: раньше папку требовалось создать вручную, иначе всё падало.
        outdir = Path(outdir)
        try:
            outdir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return False, tr("error.mkdir", folder=outdir, message=exc)

        # Предупреждаем заранее, до начала работы, чтобы не было сюрпризов.
        if mode.is_audio and not self.env.has_ffmpeg:
            sink(tr("warn.no_ffmpeg_audio"), "warn")
        elif not mode.is_audio and not self.env.can_merge:
            sink(tr("warn.no_ffmpeg_video"), "warn")

        chosen = [i for i in (items or []) if i.selected]
        if items and not chosen:
            return False, tr("status.nothing_selected")
        if chosen:
            sink(tr("playlist.queued", count=len(chosen)), "info")
            self._queue_total = len(chosen)
        else:
            self._queue_total = 1

        opts = self.build_opts(
            mode, outdir, items=chosen or None, threads=threads,
            on_line=on_line, on_progress=on_progress,
        )

        try:
            # Контекстный менеджер сам закроет соединения и подчистит временные файлы.
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except DownloadCancelled:
            return False, tr("status.cancelled")
        except DownloadError as exc:
            # Штатная ошибка yt-dlp — переводим на человеческий.
            return False, _humanize(str(exc))
        except Exception as exc:
            # Ловим вообще всё: упасть с трейсбеком в лицо пользователю — худший исход.
            return False, tr("error.unexpected", message=exc)

        if self._queue_total > 1:
            return True, tr("status.done_many", count=self._queue_total, folder=outdir)
        return True, tr("status.done", folder=outdir)

    def cancel(self) -> None:
        """
        Просит остановиться.

        Мгновенной остановки не будет: флаг проверяется в хуках,
        то есть прервётся на ближайшем обновлении прогресса. Это доли секунды.
        """
        self._cancel.set()


def _humanize(message: str) -> str:
    """
    Переводит техническую ошибку yt-dlp в понятную фразу.

    Смотрим на текст в нижнем регистре и ищем знакомые куски.
    Если ничего не узнали — отдаём исходное сообщение, убрав префикс «ERROR: ».
    """
    low = message.lower()
    if "is not a valid url" in low or "unsupported url" in low:
        return tr("error.bad_url")
    if "video unavailable" in low or "private video" in low:
        return tr("error.unavailable")
    if "sign in to confirm" in low or ("age" in low and "restricted" in low):
        return tr("error.age")
    if "ffmpeg" in low or "ffprobe" in low:
        return tr("error.ffmpeg")
    if "urlopen error" in low or "network" in low or "timed out" in low:
        return tr("error.network")
    return message.replace("ERROR: ", "").strip()
