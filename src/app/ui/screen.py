# -*- coding: utf-8 -*-
"""
ГЛАВНЫЙ ЭКРАН
=============

Здесь собирается вся раскладка и связывается с движком.

Порядок сверху вниз, как на сайте:
    шапка → режимы → ссылка → папка → кнопки → прогресс → панели → футер

Почему экран пересобирается целиком
-----------------------------------
Раскладка строится функцией `_build()`, которая каждый раз создаёт контролы
заново и складывает их в страницу. Пересборка нужна в двух случаях:

  1. Пользователь поменял масштаб интерфейса. Размеры шрифтов у уже созданных
     контролов не пересчитываются сами, поэтому их надо создать заново.
  2. Пользователь открыл или закрыл панель настроек либо панель состояния.

Второй пункт принципиален. Раньше панели просто висели в раскладке
с `visible=False`, и место под них всё равно резервировалось —
под прогресс-баром получались два пустых серых прямоугольника.
Теперь закрытая панель физически отсутствует в списке контролов,
и занимать место ей нечем.

Чтобы при пересборке не терялся лог, все его строки хранятся отдельно
в `self._log_lines` и заново проигрываются в новый LogView.

Про потоки
----------
Скачивание блокирует поток, в котором работает. Если запустить его прямо
в обработчике клика, интерфейс замрёт до конца загрузки. Поэтому:

    клик → page.run_thread(...) → рабочий поток качает
                                    ↓ колбэки
                            обновляем контролы и зовём page.update()

Про async
---------
Сервисы Flet (буфер обмена, выбор папки, открытие ссылок) асинхронные,
поэтому часть обработчиков объявлена через `async def`. Обёртка кнопки
сама распознаёт корутины и отдаёт их в `page.run_task`.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import threading
from functools import partial
from pathlib import Path

import flet as ft

from .. import dns_bypass
from .. import platform_paths as pp
from .. import theme as t
from ..engine import Engine, Mode, PlaylistInfo, Progress
from .. import i18n
from ..i18n import tr
from ..settings import Settings
from . import components as c

# Версия показывается в бейдже шапки.
APP_VERSION = "2.1.2"


def normalize_proxy(value: str) -> str:
    """
    Приводит адрес прокси к виду, понятному yt-dlp.

    Без схемы yt-dlp адрес не примет, а набирать `socks5://` руками
    на телефоне мучительно. Поэтому голые `127.0.0.1:1080` дополняем
    сами — программы обхода почти всегда поднимают именно SOCKS5.
    Что получилось в итоге, пишем в лог, чтобы не гадать.
    """
    value = (value or "").strip()
    if not value:
        return ""
    if "://" not in value:
        return f"socks5://{value}"
    return value

# Ссылки автора для футера.
LINKS = [
    ("🟣  Twitch", "https://www.twitch.tv/randinlonescu"),
    ("🎥  YouTube", "https://www.youtube.com/@RandinLonescu"),
    ("💬  Telegram", "https://t.me/RandinLonescu"),
]

# Карточки режимов: иконка, название, подпись, значение.
# Карточки режимов. Подписи берутся из локализации по значению режима,
# поэтому здесь остались только иконки.
MODE_ICONS = {
    Mode.BEST: "🎬",
    Mode.P1080: "📺",
    Mode.P720: "📼",
    Mode.MP3: "🎵",
}


class DownloaderApp:
    """Экран целиком: и раскладка, и состояние, и обработчики."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.engine = Engine()              # осматривает систему прямо в конструкторе
        self.cfg = Settings.load()
        self.engine.proxy = normalize_proxy(self.cfg.proxy)
        self.mode = self.cfg.mode_enum      # режим, выбранный в прошлый раз
        self.busy = False                   # идёт ли сейчас скачивание
        self._lock = threading.Lock()       # защищает лог от одновременной записи

        # Что показано на экране прямо сейчас.
        self._show_details = False
        self._show_settings = False

        # Плейлист: результат сканирования и признак того, что он показан.
        self.playlist: PlaylistInfo | None = None
        self._scanning = False

        # Эти три вещи живут отдельно от контролов, чтобы пережить пересборку.
        # Язык, тему и масштаб применяем ПЕРВЫМ ДЕЛОМ.
        #
        # Порядок здесь важен: ниже вызывается tr() для стартового статуса,
        # и если язык ещё не установлен, статус останется на языке по умолчанию,
        # пока пользователь его чем-нибудь не перезапишет. Так и было — при
        # английском интерфейсе внизу висело русское «Готов к работе».
        if not self.cfg.language:
            # Первый запуск — угадываем по системе и запоминаем.
            self.cfg.language = i18n.detect_system_language()
            self.cfg.save()
        i18n.set_language(self.cfg.language)
        t.set_theme(self.cfg.theme)
        t.set_scale(self.cfg.ui_scale)

        # Эти значения живут отдельно от контролов, чтобы пережить пересборку.
        self._log_lines: list[tuple[str, str]] = []
        self._url_value = ""
        self._status_text = tr("status.ready")
        self._status_color = t.MUTED
        self._progress: float | None = 0.0

        # Диалог выбора папки — сервис, его надо зарегистрировать на странице,
        # иначе get_directory_path() просто ничего не сделает.
        self._picker = ft.FilePicker()
        page.services.append(self._picker)

        self._configure_window()
        self._build()
        # Обход ставим после сборки экрана: он пишет в лог, а лог до этого
        # момента ещё не существует. Само включение мгновенное — подмена
        # функции разрешения имён, без единого запроса в сеть.
        self._apply_dns_bypass(announce=False)
        self._report_environment()

    # ================================================================== ОКНО
    def _configure_window(self) -> None:
        """Свойства окна задаются один раз и при пересборке не трогаются."""
        page = self.page
        page.title = "Downloader3000"
        page.padding = 0

        # Фон окна.
        #
        # Тут были две ошибки подряд, поэтому объясняю подробно.
        # Сначала стоял page.bgcolor = TRANSPARENT — снизу просвечивала
        # стандартная серая подложка Material. Потом bgcolor стал сплошным,
        # но сплошной цвет рисуется ПОВЕРХ page.decoration и закрыл собой
        # весь градиент: страница превратилась в плоскую тёмную заливку.
        #
        # Рабочий вариант: decoration не используем вообще, а градиент кладём
        # на обычный контейнер, который занимает всё окно (см. _build).
        # bgcolor оставляем тёмным как подложку — просвечивать теперь нечему.
        # Цвета окна, режим темы и полоса прокрутки — всё в одном месте,
        # чтобы при смене оформления не забыть половину.
        self._apply_window_theme()

        # Размеры окна имеют смысл только на десктопе: на телефоне
        # окно во весь экран, и попытка его задать ничего не даёт.
        if not pp.IS_ANDROID:
            page.window.width = 980
            page.window.height = 700
            page.window.min_width = 440
            page.window.min_height = 520

    # =================================================================== ВИД
    def _build(self) -> None:
        """Создаёт все контролы заново и складывает их в страницу."""
        page = self.page

        # ---------------------------------------------------------- шапка
        # Слева бейдж, справа кнопка настроек и кнопка состояния.
        # Всё, что раньше висело отдельными строчками (версия yt-dlp, ffmpeg,
        # JS-движок, платформа), теперь живёт внутри кнопки состояния.
        self.status_btn = c.StatusButton(self._toggle_details)
        self.status_btn.set_open(self._show_details)
        self.settings_btn = c.IconButton("⚙", self._toggle_settings, tr("btn.settings"))
        self.env_row = ft.Row(spacing=t.px(8), wrap=True)

        header = ft.Column(
            [
                ft.Row(
                    [
                        t.badge(tr("app.badge", version=APP_VERSION)),
                        ft.Container(expand=True),          # распорка
                        self.settings_btn.control,
                        self.status_btn.control,
                    ],
                    spacing=t.px(8),
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(content=t.h1("Downloader3000"), padding=ft.Padding(0, t.px(2), 0, 0)),
                t.muted(tr("app.subtitle")),
            ],
            spacing=0,
            tight=True,
        )

        # --------------------------------------------------------- режимы
        self.cards = [
            c.ModeCard(icon, tr(f"mode.{mode.value}.name"), tr(f"mode.{mode.value}.desc"),
                       mode, self._select_mode)
            for mode, icon in MODE_ICONS.items()
        ]
        for card in self.cards:
            card.selected = card.value is self.mode
        modes_row = ft.ResponsiveRow(
            [card.control for card in self.cards], spacing=t.px(12), run_spacing=t.px(12)
        )

        # --------------------------------------------------------- ссылка
        self.url = ft.TextField(
            value=self._url_value,
            hint_text=tr("hint.url_placeholder"),
            hint_style=ft.TextStyle(color=t.FAINT, size=t.FS_BODY),
            text_style=ft.TextStyle(color=t.TEXT, size=t.FS_BODY, font_family=t.FONT),
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=t.STROKE,
            focused_border_color=t.GOLD_EDGE,
            cursor_color=t.GOLD,
            border_radius=t.R_CARD,
            content_padding=ft.Padding(t.px(14), t.px(11), t.px(14), t.px(11)),
            expand=True,
            disabled=self.busy,
            on_change=self._url_changed,
            on_submit=lambda _e: self._start(),   # Enter запускает скачивание
        )
        paste = c.GhostButton(tr("btn.paste"), self._paste, width=t.px(120))

        # Панель со списком роликов. Создаётся всегда, но в раскладку
        # попадает только после успешного сканирования.
        self.playlist_panel = c.PlaylistPanel(self._playlist_changed)
        if self.playlist:
            self.playlist_panel.fill(self.playlist.title, self.playlist.items)

        # Строка-подсказка под полем ссылки. Меняется в зависимости от того,
        # что вставлено: обычное видео, плейлист или идёт сканирование.
        self.scan_btn = c.GhostButton(tr("btn.show_list"), self._scan_playlist,
                                      width=t.px(160), height=t.px(34))
        self.scan_btn.enabled = not self._scanning

        # ---------------------------------------------------------- папка
        self.path_text = ft.Text(
            str(self.cfg.dir_for(self.mode)),
            size=t.FS_SMALL, color=t.WARM, font_family=t.FONT, no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        path_box = ft.Container(
            content=self.path_text,
            bgcolor=t.GLASS,
            border=ft.Border.all(1, t.STROKE),
            border_radius=t.R_CARD,
            padding=ft.Padding(t.px(14), t.px(10), t.px(14), t.px(10)),
            expand=True,
        )
        self.btn_change = c.GhostButton(tr("btn.change"), self._change_folder, width=t.px(108))
        self.btn_open = c.GhostButton(tr("btn.open"), self._open_folder, width=t.px(108))
        self.btn_change.enabled = not self.busy

        # ------------------------------------------------------- действия
        self.btn_go = c.GoldButton(
            tr("btn.downloading") if self.busy else tr("btn.download"), self._start)
        self.btn_go.enabled = not self.busy
        self.btn_cancel = c.GhostButton(
            tr("btn.cancel"), self._cancel, tint=t.DANGER, width=t.px(118), height=t.px(48)
        )
        self.btn_cancel.enabled = self.busy

        # ------------------------------------------------------- прогресс
        # value=None переводит полоску в бесконечный режим — используем,
        # когда процент неизвестен (склейка, конвертация).
        self.bar = ft.ProgressBar(
            value=self._progress, bar_height=t.px(8), color=t.GOLD,
            bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.BLACK),
            border_radius=t.px(8), expand=True,
        )
        self.status = ft.Text(
            self._status_text, size=t.FS_SMALL, color=self._status_color, font_family=t.FONT
        )

        # ------------------------------------------------------------ лог
        # Создаём заново и проигрываем сохранённые строки.
        self.log = c.LogView()
        for message, kind in self._log_lines:
            self.log.add(message, kind)

        # --------------------------------------------------------- футер
        # ВАЖНО про распорку и wrap.
        #
        # Здесь был баг, который дважды чинился вслепую. В строке одновременно
        # стояли `wrap=True` и распорка `ft.Container(expand=True)`.
        # Во Flutter виджет Wrap не умеет растягивающихся детей, и Flet рисовал
        # такой контейнер как БОЛЬШОЙ СВЕТЛО-СЕРЫЙ ПРЯМОУГОЛЬНИК на всю ширину,
        # который к тому же закрывал собой ссылки.
        #
        # Правило: `wrap=True` и `expand=True` в одной строке несовместимы.
        # Поэтому распорки тут нет, а края разводит alignment.
        footer = ft.Row(
            [
                ft.Row(
                    [
                        # Замыкание через lambda-обёртку: без неё все три кнопки
                        # захватили бы последнее значение url из цикла.
                        # partial связывает адрес сразу. Без него все три кнопки
                        # захватили бы последнее значение url из цикла.
                        c.GhostButton(cap, partial(self._open_url, url),
                                      height=t.px(34)).control
                        for cap, url in LINKS
                    ],
                    spacing=t.px(8),
                ),
                ft.Text(tr("app.author"), size=t.FS_TINY, color=t.FAINT, font_family=t.FONT),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            # На телефоне подпись автора не помещается рядом со ссылками
            # и обрезается многоточием. Разрешаем перенос на вторую строку.
            # Распорки здесь нет намеренно: wrap и expand несовместимы.
            wrap=True,
            run_spacing=t.px(8),
        )

        # ------------------------------------------------- сборка страницы
        # Панели попадают в список ТОЛЬКО когда открыты. Именно это избавляет
        # от пустых прямоугольников под прогресс-баром.
        controls: list[ft.Control] = [
            header,
            c.section(tr("section.mode")),
            modes_row,

            c.section(tr("section.url")),
            ft.Row([self.url, paste.control], spacing=t.px(10)),
            ft.Container(content=self._url_hint_row(), padding=ft.Padding(2, t.px(4), 2, 0)),

            *( [self.playlist_panel.control] if self.playlist else [] ),

            c.section(tr("section.folder")),
            ft.Row([path_box, self.btn_change.control, self.btn_open.control], spacing=t.px(10)),

            ft.Container(
                content=ft.Row([self.btn_go.control, self.btn_cancel.control], spacing=t.px(12)),
                padding=ft.Padding(0, t.px(12), 0, 0),
            ),
            ft.Container(content=self.bar, padding=ft.Padding(0, t.px(12), 0, t.px(5))),
            self.status,
        ]

        if self._show_settings:
            controls.append(self._settings_panel())
        if self._show_details:
            controls.append(self._details_panel())

        controls += [
            ft.Container(
                content=ft.Divider(height=1, color=t.STROKE),
                padding=ft.Padding(0, t.px(10), 0, t.px(8)),
            ),
            footer,
        ]

        # Двухслойная колонка — из-за полосы прокрутки.
        #
        # Полоса рисуется по правому краю ПРОКРУЧИВАЕМОЙ колонки и накрывает
        # собой всё, что там есть. Поэтому прокручивается внешняя колонка,
        # а весь контент лежит во вложенном контейнере с отступом справа:
        # получается отдельная дорожка под полосу, и она ничего не перекрывает.
        inner = ft.Column(controls, spacing=0, tight=True)

        content = ft.Column(
            [ft.Container(content=inner, padding=ft.Padding(0, 0, t.px(18), 0))],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # Корневой контейнер: именно он красит окно градиентом.
        # Правый отступ маленький — место справа занимает дорожка полосы.
        root = ft.Container(
            content=content,
            gradient=t.page_gradient(),
            padding=ft.Padding(t.px(24), t.px(14), t.px(6), t.px(12)),
            expand=True,
        )

        page.controls.clear()
        # SafeArea отодвигает содержимое от строки состояния, выреза камеры
        # и жестовой полосы внизу. Без неё на телефоне бейдж и кнопки
        # налезают на часы и индикатор батареи.
        page.add(ft.SafeArea(content=root, expand=True))

    # =========================================================== ПЛЕЙЛИСТЫ
    def _url_hint_row(self) -> ft.Control:
        """
        Строка под полем ссылки.

        Три состояния: обычная подсказка, предложение открыть список
        и сообщение о том, что сканирование идёт.
        """
        if self._scanning:
            return ft.Row(
                [
                    ft.ProgressRing(width=t.px(14), height=t.px(14),
                                    stroke_width=2, color=t.GOLD),
                    c.hint(tr("hint.scanning")),
                ],
                spacing=t.px(8),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        url = (self._url_value or "").strip()
        if url and self.engine.is_playlist_url(url) and not self.playlist:
            return ft.Row(
                [
                    ft.Text(tr("hint.playlist"),
                            size=t.FS_TINY, color=t.WARM, font_family=t.FONT),
                    self.scan_btn.control,
                ],
                spacing=t.px(10),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        # На телефоне нет клавиши Enter в привычном смысле, поэтому
        # подсказка там другая — про кнопку.
        return c.hint(tr("hint.url_mobile") if pp.IS_ANDROID else tr("hint.url"))

    def _scan_playlist(self) -> None:
        """Читает состав плейлиста в фоне: обращение к сети блокирует поток."""
        if self._scanning or self.busy:
            return
        url = (self.url.value or "").strip().strip(chr(34)).strip(chr(39))
        if not url:
            return
        self._url_value = url
        self._scanning = True
        self._rebuild()
        self.page.run_thread(self._scan_worker, url)

    def _scan_worker(self, url: str) -> None:
        """Тело фонового сканирования."""
        info = self.engine.scan_playlist(url, on_line=self._log)
        self._scanning = False
        if info is None:
            self.playlist = None
            self._set_status(tr("status.not_playlist"), t.WARM)
        else:
            self.playlist = info
            self._set_status(tr("status.playlist_found", count=len(info.items)), t.TEXT)
            self._log(tr("playlist.scanned", title=info.title, count=len(info.items)), "ok")
        self._rebuild()

    def _playlist_changed(self) -> None:
        """Галочку переключили — счётчик уже обновлён, надо только перерисовать."""
        self._safe_update()

    def _forget_playlist(self) -> bool:
        """Ссылку поменяли — старый список больше не актуален."""
        if self.playlist is not None:
            self.playlist = None
            return True
        return False

    # ============================================================== ПАНЕЛИ
    def _details_panel(self) -> ft.Control:
        """Панель состояния: чипы окружения и лог. Открывается кнопкой статуса."""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(content=self.env_row, padding=ft.Padding(0, 0, 0, t.px(8))),
                    self.log.control,
                ],
                spacing=0,
                tight=True,
            ),
            padding=ft.Padding(0, t.px(10), 0, 0),
        )

    def _settings_panel(self) -> ft.Control:
        """Панель настроек: масштаб интерфейса и поведение плейлистов."""
        percent = ft.Text(
            f"{round(t.SCALE * 100)}%",
            size=t.FS_BODY, color=t.GOLD, font_family=t.FONT, weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )

        scale_row = ft.Row(
            [
                ft.Text(tr("settings.scale"), size=t.FS_SMALL, color=t.TEXT, font_family=t.FONT),
                ft.Container(expand=True),
                c.IconButton("−", lambda: self._change_scale(-t.SCALE_STEP), tr("btn.zoom_out")).control,
                ft.Container(content=percent, width=t.px(54), alignment=ft.Alignment.CENTER),
                c.IconButton("+", lambda: self._change_scale(+t.SCALE_STEP), tr("btn.zoom_in")).control,
                c.GhostButton(tr("btn.reset"), lambda: self._set_scale(1.0),
                              width=t.px(80), height=t.px(34)).control,
            ],
            spacing=t.px(8),
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Выбор языка. Кнопки, а не выпадающий список: языков всего два,
        # и так нагляднее видно, какой сейчас активен.
        language_row = ft.Row(
            [
                ft.Text(tr("settings.language"), size=t.FS_SMALL, color=t.TEXT,
                        font_family=t.FONT),
                ft.Container(expand=True),
                *[
                    c.GhostButton(
                        title,
                        partial(self._set_language, code),
                        tint=t.GOLD if code == i18n.current_language() else t.MUTED,
                        width=t.px(96), height=t.px(34),
                    ).control
                    for code, title in i18n.LANGUAGES.items()
                ],
            ],
            spacing=t.px(8),
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Выбор оформления. Тоже кнопками: тем всего три, и видно,
        # какая активна, без раскрытия списка.
        theme_row = ft.Row(
            [
                ft.Text(tr("settings.theme"), size=t.FS_SMALL, color=t.TEXT,
                        font_family=t.FONT),
                ft.Container(expand=True),
                *[
                    c.GhostButton(
                        tr(f"theme.{key}"),
                        partial(self._set_theme, key),
                        tint=t.GOLD if key == t.current_theme() else t.MUTED,
                        width=t.px(104), height=t.px(34),
                    ).control
                    for key in t.THEMES
                ],
            ],
            spacing=t.px(8),
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Обход блокировки по именам. Кнопка нужна на случай, когда обход
        # мешает: в некоторых сетях внутренние адреса известны только
        # местному серверу имён, и публичный ответит «нет такого сайта».
        dns_row = ft.Row(
            [
                ft.Text(tr("settings.dns"), size=t.FS_SMALL, color=t.TEXT,
                        font_family=t.FONT),
                ft.Container(expand=True),
                *[
                    c.GhostButton(
                        tr("btn.on") if state else tr("btn.off"),
                        partial(self._set_dns_bypass, state),
                        tint=t.GOLD if state == self.cfg.dns_bypass else t.MUTED,
                        width=t.px(96), height=t.px(34),
                    ).control
                    for state in (True, False)
                ],
            ],
            spacing=t.px(8),
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Прокси. Поле, а не кнопки: адрес у каждого свой, угадать нечего.
        # Значение сохраняется по уходу с поля и по Enter, а не на каждой
        # букве: на телефоне это лишняя запись файла при каждом нажатии.
        proxy_field = ft.TextField(
            value=self.cfg.proxy,
            hint_text=tr("hint.proxy_placeholder"),
            hint_style=ft.TextStyle(color=t.FAINT, size=t.FS_SMALL),
            text_style=ft.TextStyle(color=t.TEXT, size=t.FS_SMALL, font_family=t.FONT),
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=t.STROKE,
            focused_border_color=t.GOLD_EDGE,
            cursor_color=t.GOLD,
            border_radius=t.R_CARD,
            content_padding=ft.Padding(t.px(12), t.px(8), t.px(12), t.px(8)),
            expand=True,
            on_blur=lambda e: self._set_proxy(e.control.value),
            on_submit=lambda e: self._set_proxy(e.control.value),
        )
        proxy_row = ft.Row(
            [
                ft.Text(tr("settings.proxy"), size=t.FS_SMALL, color=t.TEXT,
                        font_family=t.FONT),
                proxy_field,
            ],
            spacing=t.px(12),
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=ft.Column(
                [
                    scale_row,
                    ft.Divider(height=t.px(14), color=t.STROKE),
                    theme_row,
                    ft.Divider(height=t.px(14), color=t.STROKE),
                    language_row,
                    ft.Divider(height=t.px(14), color=t.STROKE),
                    dns_row,
                    c.hint(tr("hint.dns")),
                    ft.Divider(height=t.px(14), color=t.STROKE),
                    proxy_row,
                    c.hint(tr("hint.proxy")),
                    ft.Divider(height=t.px(14), color=t.STROKE),
                    c.hint(tr("hint.playlist_settings")),
                ],
                spacing=0,
                tight=True,
            ),
            bgcolor=t.GLASS,
            border=ft.Border.all(1, t.STROKE),
            border_radius=t.R_CARD,
            padding=ft.Padding(t.px(16), t.px(12), t.px(16), t.px(12)),
            margin=ft.Margin(0, t.px(12), 0, 0),
        )

    def _toggle_details(self) -> None:
        """Открывает и закрывает панель состояния."""
        self._show_details = not self._show_details
        if self._show_details:
            self._show_settings = False       # две панели сразу — уже каша
        self._rebuild()

    def _toggle_settings(self) -> None:
        """Открывает и закрывает панель настроек."""
        self._show_settings = not self._show_settings
        if self._show_settings:
            self._show_details = False
        self._rebuild()

    def _rebuild(self) -> None:
        """Пересобирает экран и заново заполняет чипы окружения."""
        self._build()
        self._fill_env_chips()
        self._safe_update()

    # ============================================================ НАСТРОЙКИ
    def _change_scale(self, delta: float) -> None:
        self._set_scale(t.SCALE + delta)

    def _set_scale(self, value: float) -> None:
        """
        Меняет масштаб интерфейса.

        У созданных контролов размеры шрифта не пересчитываются,
        поэтому после смены масштаба экран собирается заново.
        """
        t.set_scale(value)
        self.cfg.ui_scale = t.SCALE
        self.cfg.save()
        self._rebuild()

    def _apply_dns_bypass(self, announce: bool = True) -> None:
        """
        Приводит обход блокировки в состояние, записанное в настройках.

        Вынесено отдельно, потому что зовётся из двух мест: при запуске
        и при переключении кнопки. `announce` гасит запись в лог на старте —
        иначе первая строка лога всегда была бы про обход, а не про то,
        готова программа к работе или нет.
        """
        if self.cfg.dns_bypass:
            dns_bypass.enable(self._log)
        else:
            dns_bypass.disable()
        if announce:
            self._log(tr("dns.on") if self.cfg.dns_bypass else tr("dns.off"), "info")

    def _set_proxy(self, value: str) -> None:
        """
        Запоминает адрес прокси и сразу отдаёт его движку.

        Экран здесь НЕ пересобирается: пересборка отняла бы фокус у поля,
        и продолжить набор было бы нельзя.
        """
        value = (value or "").strip()
        if value == self.cfg.proxy:
            return
        self.cfg.proxy = value
        self.cfg.save()
        self.engine.proxy = normalize_proxy(value)
        if self.engine.proxy:
            self._log(tr("proxy.on", address=self.engine.proxy), "info")
        else:
            self._log(tr("proxy.off"), "info")

    def _set_dns_bypass(self, state: bool) -> None:
        """Включает или выключает обход блокировки по имени сайта."""
        if state == self.cfg.dns_bypass:
            return
        self.cfg.dns_bypass = state
        self.cfg.save()
        self._apply_dns_bypass()
        self._rebuild()

    def _set_theme(self, key: str) -> None:
        """
        Переключает оформление.

        Цвета читаются компонентами в момент создания, поэтому после смены
        темы экран собирается заново — как и при смене масштаба или языка.
        """
        t.set_theme(key)
        self.cfg.theme = t.current_theme()
        self.cfg.save()
        self._apply_window_theme()
        self._rebuild()

    def _apply_window_theme(self) -> None:
        """
        Подгоняет системные части окна под тему.

        Flet рисует своими средствами полосу прокрутки, курсор в поле ввода
        и всплывающие подсказки. Если не переключить режим темы, на светлом
        оформлении они останутся тёмными и будут выглядеть чужеродно.
        """
        page = self.page
        page.theme_mode = ft.ThemeMode.LIGHT if t.is_light() else ft.ThemeMode.DARK
        page.bgcolor = t.BG_1
        page.theme = ft.Theme(
            scrollbar_theme=ft.ScrollbarTheme(
                thickness=t.px(8),
                radius=t.px(4),
                thumb_color=ft.Colors.with_opacity(0.55, t.GOLD),
                track_color=ft.Colors.with_opacity(0.06, t.TEXT),
                track_visibility=False,
                thumb_visibility=False,
                cross_axis_margin=t.px(2),
                main_axis_margin=t.px(4),
                interactive=True,
            )
        )

    def _set_language(self, code: str) -> None:
        """
        Переключает язык.

        Все надписи создаются в момент сборки экрана, поэтому после смены
        языка экран собирается заново — перезапуск программы не нужен.
        Строки лога при этом остаются на том языке, на котором были записаны:
        переписывать историю задним числом было бы странно.
        """
        i18n.set_language(code)
        self.cfg.language = i18n.current_language()
        self.cfg.save()
        self._status_text = tr("status.ready")
        self._status_color = t.MUTED
        self._rebuild()

    def _toggle_playlist(self, e: ft.Event) -> None:
        self.cfg.playlist = bool(e.control.value)
        self.cfg.save()

    # ============================================================= ОКРУЖЕНИЕ
    def _fill_env_chips(self) -> None:
        """Наполняет строку чипов. Вызывается после каждой пересборки."""
        env = self.engine.env
        self.env_row.controls = [
            c.env_chip(True, f"yt-dlp {env.ytdlp_version}"),
            c.env_chip(env.has_ffmpeg,
                       tr("env.ffmpeg_ok") if env.has_ffmpeg else tr("env.ffmpeg_missing"),
                       warn_only=True),
            c.env_chip(env.js_runtime is not None,
                       tr("env.js_ok", name=env.js_runtime[0]) if env.js_runtime
                       else tr("env.js_missing"),
                       warn_only=True),
            c.env_chip(True, env.platform),
        ]
        self.status_btn.set_state(*self._status_badge())

    def _status_badge(self) -> tuple[str, str]:
        """
        Решает, каким цветом и с какой подписью показать кнопку состояния.

        Зелёный — всё нашлось, ограничений нет.
        Жёлтый  — чего-то не хватает, качать можно, но не всё.
        """
        env = self.engine.env
        problems = []
        if not env.has_ffmpeg:
            problems.append(tr("env.no_ffmpeg"))
        if env.js_runtime is None:
            problems.append(tr("env.no_js"))

        if not problems:
            return t.SUCCESS, tr("env.all_good")
        if len(problems) == 1:
            return t.GOLD, problems[0].capitalize()
        return t.GOLD, tr("env.problems", count=len(problems))

    def _report_environment(self) -> None:
        """Первичная проверка окружения: чипы, цвет кнопки и записи в лог."""
        env = self.engine.env
        self._fill_env_chips()

        if not env.has_ffmpeg:
            self._log(tr("env.warn_ffmpeg"), "warn")
        if env.js_runtime is None:
            self._log(tr("env.warn_js"), "warn")
        if env.has_ffmpeg and env.js_runtime is not None:
            self._log(tr("env.ok_line"), "ok")

        self._safe_update()

    # ================================================================ РЕЖИМЫ
    def _select_mode(self, mode: Mode) -> None:
        """Переключает режим. Во время скачивания игнорируется."""
        if self.busy:
            return
        self.mode = mode
        for card in self.cards:
            card.selected = card.value is mode
        self.cfg.mode = mode.value
        # У звука своя папка, поэтому строка пути обновляется вместе с режимом.
        self.path_text.value = str(self.cfg.dir_for(mode))
        self._safe_update()

    # =============================================================== ДЕЙСТВИЯ
    def _url_changed(self, e: ft.Event) -> None:
        """
        Запоминаем ссылку, чтобы она не потерялась при пересборке экрана.

        Заодно следим за сменой ссылки: если раньше был просканирован плейлист,
        он больше не относится к делу. И наоборот — как только появилась
        ссылка плейлиста, надо показать кнопку «Показать список».
        """
        previous = self._url_value
        self._url_value = e.control.value or ""

        was_playlist = self.engine.is_playlist_url(previous)
        now_playlist = self.engine.is_playlist_url(self._url_value)

        # Пересобираем экран только когда меняется его состав,
        # а не на каждое нажатие клавиши.
        if self._forget_playlist() or was_playlist != now_playlist:
            self._rebuild()

    async def _paste(self) -> None:
        """Вставляет ссылку из буфера обмена. Сервис асинхронный, отсюда async."""
        try:
            text = await self.page.clipboard.get()
        except Exception:
            text = None
        if text:
            self._url_value = text.strip()
            self.url.value = self._url_value
            self._forget_playlist()
            self._rebuild()

    async def _change_folder(self) -> None:
        """Открывает системный диалог выбора папки и запоминает результат."""
        try:
            chosen = await self._picker.get_directory_path(
                dialog_title=tr("dialog.choose_folder", mode=self.mode.title),
                initial_directory=str(self.cfg.dir_for(self.mode)),
            )
        except Exception as exc:
            self._log(tr("error.folder_dialog", message=exc), "error")
            return

        # chosen = None означает, что диалог закрыли без выбора.
        if chosen:
            self.cfg.set_dir_for(self.mode, chosen)
            self.cfg.save()
            self.path_text.value = chosen
            self._safe_update()

    def _open_folder(self) -> None:
        """Показывает папку в системном файловом менеджере."""
        target = self.cfg.dir_for(self.mode)
        try:
            target.mkdir(parents=True, exist_ok=True)
            if pp.IS_WINDOWS:
                os.startfile(str(target))
            elif pp.IS_MACOS:
                subprocess.Popen(["open", str(target)])
            elif pp.IS_ANDROID:
                self._log(tr("log.files_at", folder=target), "info")
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            self._log(tr("error.open_folder", message=exc), "error")

    def _open_url(self, url: str) -> None:
        """launch_url асинхронный, а обработчик обычный — отсюда run_task."""
        self.page.run_task(self.page.url_launcher.launch_url, url)

    def _cancel(self) -> None:
        """Останавливает скачивание. Флаг проверяется на ближайшем хуке прогресса."""
        if not self.busy:
            return
        self._log(tr("status.cancelling"), "warn")
        self.engine.cancel()

    # ============================================================ СКАЧИВАНИЕ
    def _start(self) -> None:
        """Проверяет ссылку и запускает скачивание в отдельном потоке."""
        if self.busy:
            return

        # Кавычки срезаем: при копировании из проводника они цепляются сами.
        url = (self.url.value or "").strip().strip('"').strip("'")

        if not url:
            self._set_status(tr("status.paste_url"), t.DANGER)
            self._safe_update()
            return
        if not url.lower().startswith(("http://", "https://")):
            self._set_status(tr("status.bad_url"), t.DANGER)
            self._safe_update()
            return

        if self.playlist and self.playlist_panel.selected_count == 0:
            self._set_status(tr("status.nothing_selected"), t.DANGER)
            self._safe_update()
            return

        self.cfg.save()
        self._log_lines.clear()
        self.log.clear()
        self._set_busy(True)
        self._progress = None                  # пока не знаем процентов
        self.bar.value = None
        self._set_status(tr("status.preparing", mode=self.mode.title), t.MUTED)
        self._safe_update()

        # Вот здесь работа уходит в фон, и интерфейс остаётся живым.
        items = self.playlist.items if self.playlist else None
        self.page.run_thread(self._worker, url, self.mode,
                             self.cfg.dir_for(self.mode), items)

    def _worker(self, url: str, mode: Mode, outdir: Path, items=None) -> None:
        """Тело рабочего потока. Всё, что здесь падает, движок уже перехватил."""
        ok, message = self.engine.download(
            url, mode, outdir,
            items=items,
            threads=self.cfg.threads,
            on_line=self._log,
            on_progress=self._on_progress,
        )
        self._set_busy(False)
        self._progress = 1.0 if ok else 0.0
        self.bar.value = self._progress
        self._set_status(message, t.SUCCESS if ok else t.DANGER)
        self._log(("✅ " if ok else "❌ ") + message, "ok" if ok else "error")

    # ------- колбэки движка: вызываются ИЗ РАБОЧЕГО ПОТОКА -------
    def _log(self, message: str, kind: str = "info") -> None:
        """
        Добавляет строку в лог.

        Строки дублируются в `_log_lines`, чтобы пережить пересборку экрана
        при смене масштаба или открытии панели.
        """
        if not message:
            return
        with self._lock:
            self._log_lines.append((message, kind))
            if len(self._log_lines) > c.LogView.MAX_LINES:
                del self._log_lines[: len(self._log_lines) - c.LogView.MAX_LINES]
            self.log.add(message, kind)
        self._safe_update()

    def _on_progress(self, p: Progress) -> None:
        """Обновление прогресса: либо проценты, либо название стадии."""
        if p.percent is None:
            self._progress = None              # бесконечная полоска
            self.bar.value = None
            if p.stage:
                self._set_status(p.stage, t.WARM)
        else:
            # ProgressBar ждёт долю от 0 до 1, а движок отдаёт проценты.
            self._progress = max(0.0, min(1.0, p.percent / 100))
            self.bar.value = self._progress
            parts = [f"{p.percent:.1f}%"]
            if p.item_total > 1 and p.item_index:
                parts.insert(0, tr("status.video_n_of_m", index=p.item_index, total=p.item_total))
            if p.speed:
                parts.append(p.speed)
            if p.eta:
                parts.append(tr("status.remaining", eta=p.eta))
            self._set_status("   ·   ".join(parts), t.TEXT)
        self._safe_update()

    # ================================================================ МЕЛОЧИ
    def _set_busy(self, value: bool) -> None:
        """Переводит интерфейс в режим «занят» и обратно."""
        self.busy = value
        self.btn_go.enabled = not value
        self.btn_go.caption = tr("btn.downloading") if value else tr("btn.download")
        self.btn_cancel.enabled = value
        self.btn_change.enabled = not value
        self.url.disabled = value

    def _set_status(self, text: str, color: str) -> None:
        """Меняет строку под прогресс-баром и запоминает её для пересборки."""
        self._status_text = text
        self._status_color = color
        self.status.value = text
        self.status.color = color

    def _safe_update(self) -> None:
        """
        Обновление экрана, которое не боится ничего.

        Вызов может прилететь из рабочего потока или уже после закрытия окна —
        в обоих случаях падать нельзя, скачивание тут ни при чём.
        """
        with contextlib.suppress(Exception):
            self.page.update()
