# -*- coding: utf-8 -*-
"""
КОМПОНЕНТЫ ИНТЕРФЕЙСА
=====================

Готовые кусочки, из которых собирается экран: карточка режима, кнопки,
лог, чипы состояния.

Почему тут нет наследования от контролов Flet
---------------------------------------------
В Flet 0.8x контролы стали датаклассами. Наследоваться от них можно,
но это регулярно даёт сюрпризы с полями и инициализацией. Поэтому здесь
принят другой подход: каждый компонент — обычный питоновский класс,
который ВЛАДЕЕТ своим `ft.Container` и отдаёт его наружу через `.control`.

Из этого следует одно правило, которое надо помнить:
    в раскладку кладут `component.control`, а не сам `component`.

Как работает анимация
---------------------
Мы не анимируем ничего вручную. У контейнера выставлено поле `animate`,
и после этого Flet сам плавно проигрывает ЛЮБОЕ изменение цвета, рамки
или смещения. То есть код просто присваивает новое значение и вызывает
`update()`, а плавность появляется бесплатно — ровно как CSS transition.
"""
from __future__ import annotations

import inspect
from typing import Callable

import flet as ft

from .. import theme as t
from ..i18n import tr


def section(caption: str) -> ft.Container:
    """Подпись секции с отступами сверху и снизу — аналог h2 на сайте."""
    return ft.Container(content=t.label(caption), padding=ft.Padding(2, t.px(10), 2, t.px(4)))


def hint(caption: str) -> ft.Text:
    """Мелкая серая подсказка под полем ввода."""
    return ft.Text(caption, size=t.FS_TINY, color=t.FAINT, font_family=t.FONT)


def _fire(control: ft.Control, handler: Callable[[], object]) -> None:
    """
    Вызывает обработчик кнопки.

    Тонкость: часть обработчиков объявлена через `async def`, потому что
    сервисы Flet (буфер обмена, выбор папки) асинхронные. Если такую функцию
    просто позвать, она вернёт корутину, которую никто не выполнит,
    и кнопка молча ничего не сделает.

    Поэтому корутины отдаём в `page.run_task`, а обычные функции зовём как есть.
    """
    if inspect.iscoroutinefunction(handler):
        page = control.page
        if page is not None:
            page.run_task(handler)
        return
    handler()


def _is_over(e: ft.Event) -> bool:
    """
    Разбирает событие наведения мыши.

    Flet присылает в `e.data` строку "true"/"false", а не настоящий bool —
    отсюда эта проверка. Вынесена отдельно, чтобы не копировать её в каждый
    обработчик hover.
    """
    return e.data == "true" if isinstance(e.data, str) else bool(e.data)


class ModeCard:
    """
    Карточка выбора режима: Best / 1080p / 720p / MP3.

    Повторяет .card с сайта и добавляет состояние «выбрано».
    Три внешних вида: обычный, под курсором и выбранный.
    """

    def __init__(self, icon: str, name: str, desc: str, value, on_pick: Callable[[object], None]):
        self.value = value              # какой Mode эта карточка означает
        self._on_pick = on_pick         # что позвать при клике
        self._selected = False

        # Тексты держим отдельными ссылками: описание меняет цвет при выборе.
        self._icon = ft.Text(icon, size=t.px(21))
        self._name = ft.Text(name, size=t.FS_BODY, weight=ft.FontWeight.BOLD, color=t.GOLD,
                             font_family=t.FONT)
        self._desc = ft.Text(desc, size=t.FS_TINY, color=t.MUTED, font_family=t.FONT,
                             text_align=ft.TextAlign.CENTER)

        self.control = ft.Container(
            content=ft.Column(
                [self._icon, self._name, self._desc],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=2,
                tight=True,     # колонка не растягивается, занимает высоту содержимого
            ),
            height=t.px(82),
            bgcolor=t.GLASS,
            border=ft.Border.all(1, t.STROKE),
            border_radius=t.R_CARD,
            padding=ft.Padding(t.px(6), t.px(8), t.px(6), t.px(8)),
            alignment=ft.Alignment.CENTER,
            animate=t.ANIM,           # плавность цвета и рамки
            animate_offset=t.ANIM,    # плавность подъёма
            offset=ft.Offset(0, 0),
            on_click=self._clicked,
            on_hover=self._hovered,
            ink=False,                # без «чернильной» ряби Material — она не в стиле сайта
            # Адаптив: на узком экране (телефон) две карточки в ряд,
            # на широком — все четыре. Аналог @media (max-width: 768px) на сайте.
            col={"xs": 6, "md": 3},
        )

    def _clicked(self, _e: ft.Event) -> None:
        self._on_pick(self.value)

    def _hovered(self, e: ft.Event) -> None:
        """
        Подсветка под курсором.

        У выбранной карточки hover не трогаем: иначе она «моргает»
        и теряет вид выбранной, когда мышь проходит мимо.
        """
        if self._selected:
            return
        over = _is_over(e)
        # .card:hover { transform: translateY(-5px); border-color: #ffd700 }
        # offset в Flet измеряется в долях размера контрола, а не в пикселях,
        # поэтому -0.05 при высоте 82px даёт примерно те же 4 пикселя.
        self.control.offset = ft.Offset(0, -0.05 if over else 0)
        self.control.bgcolor = t.GLASS_HOVER if over else t.GLASS
        self.control.border = ft.Border.all(1, t.GOLD_EDGE if over else t.STROKE)
        self.control.update()

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        """
        Переключает вид на «выбрана» и обратно.

        Обновление экрана здесь НЕ вызывается специально: режим переключается
        сразу у четырёх карточек, и разумнее обновить страницу один раз
        после того, как все четыре поменяли вид.
        """
        self._selected = value
        self.control.bgcolor = t.GOLD_DIM if value else t.GLASS
        self.control.border = ft.Border.all(1, t.GOLD if value else t.STROKE)
        self.control.offset = ft.Offset(0, -0.03 if value else 0)
        self.control.shadow = t.glow(opacity=0.16, blur=26, dy=8) if value else None
        self._desc.color = t.WARM if value else t.MUTED


class GoldButton:
    """
    Главная кнопка «СКАЧАТЬ» — .download-btn с сайта.

    Золотой градиент, форма таблетки, свечение снизу и подъём под курсором.
    """

    def __init__(self, caption: str, on_click: Callable[[], None], width: int | None = None):
        self._on_click = on_click
        self._enabled = True
        self._label = ft.Text(caption, size=t.px(16), weight=ft.FontWeight.BOLD, color=t.INK,
                              font_family=t.FONT)

        self.control = ft.Container(
            content=self._label,
            height=t.px(48),
            width=width,
            expand=width is None,     # без явной ширины кнопка тянется на всю строку
            gradient=t.gold_gradient(),
            border_radius=t.R_PILL,
            alignment=ft.Alignment.CENTER,
            shadow=t.glow(),
            animate=t.ANIM,
            animate_offset=t.ANIM,
            offset=ft.Offset(0, 0),
            on_click=self._clicked,
            on_hover=self._hovered,
        )

    def _clicked(self, _e: ft.Event) -> None:
        # Flet не умеет по-настоящему «выключать» Container, поэтому
        # состояние проверяем сами и просто игнорируем клик.
        if self._enabled:
            _fire(self.control, self._on_click)

    def _hovered(self, e: ft.Event) -> None:
        if not self._enabled:
            return
        over = _is_over(e)
        # .download-btn:hover — кнопка приподнимается, свечение усиливается.
        self.control.offset = ft.Offset(0, -0.05 if over else 0)
        self.control.shadow = t.glow(opacity=0.5, blur=50) if over else t.glow()
        self.control.update()

    @property
    def caption(self) -> str:
        return self._label.value

    @caption.setter
    def caption(self, value: str) -> None:
        self._label.value = value

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """
        Включает и выключает кнопку.

        В выключенном виде убираем градиент и тень и ставим тусклую заливку —
        сразу видно, что нажимать бесполезно.
        """
        self._enabled = value
        self.control.gradient = t.gold_gradient() if value else None
        self.control.bgcolor = None if value else ft.Colors.with_opacity(0.08, ft.Colors.WHITE)
        self.control.shadow = t.glow() if value else None
        self.control.offset = ft.Offset(0, 0)
        self._label.color = t.INK if value else t.FAINT


class GhostButton:
    """
    Второстепенная кнопка-контур — .links a с сайта.

    Используется для «Вставить», «Сменить», «Открыть», «Отмена» и ссылок
    на соцсети. Цвет задаётся параметром tint: золотой обычно,
    красный для отмены.
    """

    def __init__(
        self,
        caption: str,
        on_click: Callable[[], None],
        *,
        tint: str | None = None,
        width: int | None = None,
        height: int | None = None,
        expand: bool = False,
    ):
        self._on_click = on_click
        # ВАЖНО: цвет НЕЛЬЗЯ ставить значением по умолчанию в сигнатуре.
        # Питон вычисляет такие значения один раз при импорте модуля,
        # и кнопка навсегда запомнила бы золото той темы, что была активна
        # в тот момент. На светлом оформлении это давало бледно-жёлтый текст
        # на белом фоне. Поэтому берём цвет здесь, в момент создания кнопки.
        self._tint = tint if tint is not None else t.GOLD
        self._enabled = True
        self._label = ft.Text(caption, size=t.FS_BODY, color=self._tint, font_family=t.FONT,
                              text_align=ft.TextAlign.CENTER, no_wrap=True)

        self.control = ft.Container(
            content=self._label,
            width=width,
            height=height if height is not None else t.px(46),
            expand=expand,
            # Заливка и рамка — тот же цвет, но с разной прозрачностью.
            bgcolor=ft.Colors.with_opacity(0.05, self._tint),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.30, self._tint)),
            border_radius=t.R_CARD,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding(t.px(14), 0, t.px(14), 0),
            animate=t.ANIM,
            on_click=self._clicked,
            on_hover=self._hovered,
        )

    def _clicked(self, _e: ft.Event) -> None:
        if self._enabled:
            _fire(self.control, self._on_click)

    def _hovered(self, e: ft.Event) -> None:
        if not self._enabled:
            return
        over = _is_over(e)
        # Под курсором просто поднимаем насыщенность заливки и рамки.
        self.control.bgcolor = ft.Colors.with_opacity(0.15 if over else 0.05, self._tint)
        self.control.border = ft.Border.all(1, ft.Colors.with_opacity(0.6 if over else 0.3, self._tint))
        self.control.update()

    @property
    def caption(self) -> str:
        return self._label.value

    @caption.setter
    def caption(self, value: str) -> None:
        self._label.value = value

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        self._label.color = self._tint if value else t.FAINT
        self.control.border = ft.Border.all(
            1, ft.Colors.with_opacity(0.3 if value else 0.12, self._tint)
        )


class IconButton:
    """
    Маленькая круглая кнопка с символом. Используется для настроек.

    Отдельный класс, а не GhostButton, потому что здесь нужна именно
    квадратная форма с одним знаком по центру, без текста и отступов.
    """

    def __init__(self, glyph: str, on_click: Callable[[], None], tooltip: str = ""):
        self._on_click = on_click
        self._label = ft.Text(glyph, size=t.px(15), color=t.MUTED)
        size = t.px(34)

        self.control = ft.Container(
            content=self._label,
            width=size,
            height=size,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
            border=ft.Border.all(1, t.STROKE),
            border_radius=size // 2,
            alignment=ft.Alignment.CENTER,
            animate=t.ANIM,
            on_click=lambda _e: _fire(self.control, self._on_click),
            on_hover=self._hovered,
            tooltip=tooltip or None,
        )

    def _hovered(self, e: ft.Event) -> None:
        over = _is_over(e)
        self.control.bgcolor = ft.Colors.with_opacity(0.14 if over else 0.05, t.GOLD)
        self.control.border = ft.Border.all(1, t.GOLD_EDGE if over else t.STROKE)
        self._label.color = t.GOLD if over else t.MUTED
        self.control.update()


class StatusButton:
    """
    Кнопка состояния в правом верхнем углу.

    Показывает одним взглядом, всё ли в порядке:
        зелёная  — всё найдено, можно качать что угодно;
        жёлтая   — чего-то не хватает, работать можно, но с ограничениями;
        красная  — сломано совсем.

    По нажатию разворачивает панель с подробностями и логом,
    поэтому в свёрнутом виде окно остаётся компактным.
    """

    def __init__(self, on_click: Callable[[], None]):
        self._on_click = on_click
        self._color = t.SUCCESS
        self._open = False

        self._dot = ft.Container(
            width=t.px(8), height=t.px(8), bgcolor=t.SUCCESS, border_radius=t.px(4), animate=t.ANIM,
        )
        self._label = ft.Text("Всё готово", size=t.FS_SMALL, color=t.SUCCESS,
                              font_family=t.FONT, no_wrap=True)
        self._chevron = ft.Text("▾", size=t.px(10), color=t.SUCCESS)

        self.control = ft.Container(
            content=ft.Row([self._dot, self._label, self._chevron], spacing=8, tight=True),
            bgcolor=ft.Colors.with_opacity(0.06, t.SUCCESS),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.28, t.SUCCESS)),
            border_radius=t.R_BADGE,
            padding=ft.Padding(t.px(12), t.px(7), t.px(12), t.px(7)),
            animate=t.ANIM,
            on_click=lambda _e: _fire(self.control, self._on_click),
            on_hover=self._hovered,
            tooltip=tr("btn.status_tooltip"),
        )

    def _hovered(self, e: ft.Event) -> None:
        over = _is_over(e)
        self.control.bgcolor = ft.Colors.with_opacity(0.14 if over else 0.06, self._color)
        self.control.update()

    def set_state(self, color: str, caption: str) -> None:
        """Перекрашивает кнопку. color — SUCCESS, GOLD или DANGER из темы."""
        self._color = color
        self._dot.bgcolor = color
        self._label.value = caption
        self._label.color = color
        self._chevron.color = color
        self.control.bgcolor = ft.Colors.with_opacity(0.06, color)
        self.control.border = ft.Border.all(1, ft.Colors.with_opacity(0.28, color))

    def set_open(self, is_open: bool) -> None:
        """Разворачивает стрелку, когда панель подробностей открыта."""
        self._open = is_open
        self._chevron.value = "▴" if is_open else "▾"


class LogView:
    """
    Лог работы — аналог блока <pre> с сайта.

    Тёмная подложка, моноширинный шрифт, автопрокрутка вниз.
    Строки раскрашены по важности: ошибки красным, предупреждения золотом.
    """

    # Держать в памяти весь вывод yt-dlp незачем: на длинном плейлисте
    # это тысячи строк и заметная просадка интерфейса.
    MAX_LINES = 500

    @staticmethod
    def _color_for(kind: str) -> str:
        """
        Цвет строки лога по её важности.

        Раньше это был словарь-атрибут класса. Так делать нельзя: атрибуты
        класса вычисляются ОДИН РАЗ при импорте модуля, и после смены
        оформления лог продолжал краситься цветами старой темы.
        Тот же подвох, что и с цветом в значении аргумента по умолчанию.
        """
        return {
            "info": t.CODE,
            "warn": t.GOLD,
            "error": t.DANGER,
            "ok": t.SUCCESS,
        }.get(kind, t.CODE)

    def __init__(self, height: int | None = None):
        # auto_scroll сам держит окно прокрутки внизу при добавлении строк.
        self._list = ft.ListView(spacing=1, auto_scroll=True, expand=True)
        self.control = ft.Container(
            content=self._list,
            height=height if height is not None else t.px(150),
            bgcolor=t.PRE_BG,
            border=ft.Border.all(1, t.STROKE),
            border_radius=t.R_CARD,
            padding=ft.Padding(t.px(14), t.px(10), t.px(14), t.px(10)),
        )

    def add(self, message: str, kind: str = "info") -> None:
        """Добавляет строку. kind — один из ключей COLORS."""
        self._list.controls.append(
            ft.Text(
                message,
                size=t.FS_MONO,
                color=self._color_for(kind),
                font_family="Consolas, Menlo, monospace",
                selectable=True,     # чтобы текст ошибки можно было скопировать
            )
        )
        # Срезаем самое старое, оставляя последние MAX_LINES строк.
        if len(self._list.controls) > self.MAX_LINES:
            del self._list.controls[: len(self._list.controls) - self.MAX_LINES]

    def clear(self) -> None:
        self._list.controls.clear()


class PlaylistPanel:
    """
    Список видео из плейлиста с галочками.

    Показывается, когда в поле вставлена ссылка на плейлист и человек
    нажал «Показать список». Позволяет отметить только нужные ролики,
    а не качать всё подряд — именно так вели себя старые батники.

    Список прокручивается и ограничен по высоте: в плейлисте бывает
    и двести позиций, растянуть их на всё окно нельзя.
    """

    def __init__(self, on_change: Callable[[], None]):
        self._on_change = on_change
        self.items: list = []          # список PlaylistItem из движка

        self._title = ft.Text("", size=t.FS_BODY, weight=ft.FontWeight.BOLD,
                              color=t.GOLD, font_family=t.FONT, no_wrap=True,
                              overflow=ft.TextOverflow.ELLIPSIS)
        self._counter = ft.Text("", size=t.FS_SMALL, color=t.MUTED, font_family=t.FONT)
        self._list = ft.ListView(spacing=t.px(2), height=t.px(190))

        self._toggle_all = GhostButton(tr("btn.deselect_all"), self._flip_all,
                                       width=t.px(116), height=t.px(32))

        self.control = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(content=self._title, expand=True),
                            self._toggle_all.control,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(content=self._counter, padding=ft.Padding(0, t.px(2), 0, t.px(6))),
                    self._list,
                ],
                spacing=0,
                tight=True,
            ),
            bgcolor=t.GLASS,
            border=ft.Border.all(1, t.STROKE),
            border_radius=t.R_CARD,
            padding=ft.Padding(t.px(14), t.px(12), t.px(14), t.px(12)),
            margin=ft.Margin(0, t.px(10), 0, 0),
        )

    # ------------------------------------------------------------ наполнение
    def fill(self, title: str, items: list) -> None:
        """Заполняет панель результатом сканирования."""
        self.items = items
        self._title.value = title
        self._list.controls = [self._row(item) for item in items]
        self._refresh()

    def _row(self, item) -> ft.Control:
        """Одна строка: галочка, номер, название, длительность."""
        check = ft.Checkbox(
            value=item.selected,
            active_color=t.GOLD,
            check_color=t.INK,
            on_change=lambda e, it=item: self._picked(it, e.control.value),
        )
        return ft.Container(
            content=ft.Row(
                [
                    check,
                    ft.Text(f"{item.index}.", size=t.FS_TINY, color=t.FAINT,
                            font_family=t.FONT, width=t.px(30)),
                    ft.Container(
                        content=ft.Text(item.title, size=t.FS_SMALL, color=t.TEXT,
                                        font_family=t.FONT, no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                        expand=True,
                    ),
                    ft.Text(item.duration_text, size=t.FS_TINY, color=t.MUTED,
                            font_family=t.FONT),
                ],
                spacing=t.px(4),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(t.px(4), 0, t.px(8), 0),
            border_radius=t.px(6),
        )

    # -------------------------------------------------------------- действия
    def _picked(self, item, value: bool) -> None:
        item.selected = bool(value)
        self._refresh()
        self._on_change()

    def _flip_all(self) -> None:
        """
        Одна кнопка на два действия.

        Если отмечено хоть что-то — снимаем всё. Если пусто — отмечаем всё.
        Так не нужно держать две кнопки и гадать, какая сейчас нужна.
        """
        target = not any(i.selected for i in self.items)
        for item in self.items:
            item.selected = target
        # Перерисовываем строки, чтобы галочки отразили новое состояние
        self._list.controls = [self._row(item) for item in self.items]
        self._refresh()
        self._on_change()

    def _refresh(self) -> None:
        chosen = sum(1 for i in self.items if i.selected)
        total = len(self.items)
        seconds = sum(i.duration or 0 for i in self.items if i.selected)

        parts = [tr("playlist.counter", chosen=chosen, total=total)]
        if seconds:
            hours, rest = divmod(int(seconds), 3600)
            minutes = rest // 60
            parts.append(tr("playlist.duration_h", hours=hours, minutes=minutes)
                         if hours else tr("playlist.duration_m", minutes=minutes))
        self._counter.value = "   ·   ".join(parts)
        # Одна кнопка на два действия, поэтому подпись зависит от состояния.
        self._toggle_all.caption = tr("btn.deselect_all") if chosen else tr("btn.select_all")

    @property
    def selected_count(self) -> int:
        return sum(1 for i in self.items if i.selected)


def env_chip(ok: bool, caption: str, warn_only: bool = False) -> ft.Container:
    """
    Индикатор состояния окружения: yt-dlp, ffmpeg, JS-движок, платформа.

    Три вида:
      ok=True                     — зелёная галочка, всё на месте;
      ok=False, warn_only=True    — жёлтое предупреждение, работать можно,
                                    но с ограничениями;
      ok=False, warn_only=False   — красный крест, работать нельзя.
    """
    if ok:
        icon, color = "✅", t.SUCCESS
    elif warn_only:
        icon, color = "⚠️", t.GOLD
    else:
        icon, color = "❌", t.DANGER

    return ft.Container(
        content=ft.Row(
            [
                ft.Text(icon, size=t.px(11)),
                ft.Text(caption, size=t.FS_TINY, color=color, font_family=t.FONT, no_wrap=True),
            ],
            spacing=6,
            tight=True,
        ),
        bgcolor=ft.Colors.with_opacity(0.06, color),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.22, color)),
        border_radius=t.R_BADGE,
        padding=ft.Padding(t.px(10), t.px(5), t.px(12), t.px(5)),
    )
