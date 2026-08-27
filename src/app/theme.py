# -*- coding: utf-8 -*-
"""
ДИЗАЙН-СИСТЕМА
==============

Единственное место, где описан внешний вид программы.

Три оформления
--------------
`original` — как на сайте `index.html`: диагональный градиент, стеклянные
             карточки, золотые свечения под кнопками.
`dark`     — те же акцентные цвета, но всё плоское: без градиентов и свечений.
`light`    — те же акценты на светлом фоне, тоже плоское.

Акцентная гамма во всех трёх одна и та же — меняются фон, подложки
и насыщенность золота. На светлом фоне ярко-жёлтый текст нечитаем, поэтому
там надписи идут приглушённым золотом, а яркое остаётся для заливок.

Как это работает
----------------
Палитра — обычный датакласс. `set_theme()` подставляет её значения
в переменные уровня модуля, а `set_scale()` пересчитывает размеры шрифта.
Компоненты читают `t.GOLD`, `t.FS_BODY` и прочее в момент создания,
поэтому после смены темы или масштаба экран нужно собрать заново —
этим занимается `DownloaderApp._rebuild()`.

Правило: новый цвет сначала появляется здесь, и только потом используется.
"""
from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class Palette:
    """Один набор цветов. Все поля обязательны — забыть цвет нельзя."""

    key: str
    title: str            # как называется в настройках

    bg_1: str             # фон: начало градиента или сплошной цвет
    bg_2: str             # середина градиента
    bg_3: str             # конец градиента
    surface: str          # подложка карточек
    surface_hover: str    # она же под курсором
    stroke: str           # рамки

    gold: str             # основной акцент: рамки, прогресс, заливки
    gold_text: str        # золото для текста — на светлом фоне приглушённое
    gold_a: str           # начало градиента кнопки
    gold_b: str           # конец градиента кнопки
    gold_dim: str         # фон бейджа и выбранной карточки
    gold_edge: str        # золотая рамка
    ink: str              # текст поверх золотой кнопки

    text: str             # основной текст
    muted: str            # пояснения
    faint: str            # подсказки, копирайт
    warm: str             # тёплый акцент, на сайте это цвет h3
    code: str             # текст лога
    log_bg: str           # подложка лога

    danger: str
    success: str

    gradient: bool        # рисовать фон градиентом
    glow: bool            # рисовать свечения под кнопками


# ------------------------------------------------------------------ ПАЛИТРЫ
_ORIGINAL = Palette(
    key="original",
    title="Оригинал",
    # linear-gradient(135deg, #0f0c29, #302b63, #24243e) из body на сайте
    bg_1="#0f0c29", bg_2="#302b63", bg_3="#24243e",
    surface=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
    surface_hover=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
    stroke=ft.Colors.with_opacity(0.10, ft.Colors.WHITE),
    gold="#ffd700", gold_text="#ffd700", gold_a="#f7971e", gold_b="#ffd200",
    gold_dim=ft.Colors.with_opacity(0.15, "#ffd700"),
    gold_edge=ft.Colors.with_opacity(0.30, "#ffd700"),
    ink="#1a1a2e",
    text="#e0e0e0", muted="#aaaaaa", faint="#666666",
    warm="#f0c27f", code="#a8d8ea",
    log_bg=ft.Colors.with_opacity(0.40, ft.Colors.BLACK),
    danger="#ff4444", success="#6ee7a8",
    gradient=True, glow=True,
)

_DARK = Palette(
    key="dark",
    title="Тёмная",
    # Плоский тёмный фон без всякого перехода.
    bg_1="#16141f", bg_2="#16141f", bg_3="#16141f",
    surface="#201d2b",
    surface_hover="#2a2637",
    stroke="#332f40",
    gold="#ffd700", gold_text="#ffd700", gold_a="#f7971e", gold_b="#ffd200",
    gold_dim="#3a3320",
    gold_edge="#6b5a1f",
    ink="#16141f",
    text="#e6e6e6", muted="#9a97a5", faint="#847f91",
    warm="#f0c27f", code="#a8d8ea",
    log_bg="#100e17",
    danger="#ff5555", success="#5fd39a",
    gradient=False, glow=False,
)

_LIGHT = Palette(
    key="light",
    title="Светлая",
    bg_1="#f4f4f7", bg_2="#f4f4f7", bg_3="#f4f4f7",
    surface="#ffffff",
    surface_hover="#f0eff5",
    stroke="#dedce6",
    # Ярко-жёлтый текст на белом не читается, поэтому надписи —
    # приглушённым золотом, а заливки остаются яркими.
    gold="#e0a800", gold_text="#9a6f00", gold_a="#f7971e", gold_b="#ffd200",
    gold_dim="#fff4d1",
    gold_edge="#e8c766",
    ink="#2b2410",
    text="#22212b", muted="#5f5d6b", faint="#74727f",
    warm="#a4711d", code="#1f5f7a",
    log_bg="#eceaf2",
    danger="#d13b3b", success="#1f8a5b",
    gradient=False, glow=False,
)

THEMES: dict[str, Palette] = {p.key: p for p in (_ORIGINAL, _DARK, _LIGHT)}
DEFAULT_THEME = "original"

_palette: Palette = _ORIGINAL

# ============================================================== ЦВЕТА
# Эти имена читает весь интерфейс. Значения подставляет set_theme().
BG_1 = BG_2 = BG_3 = ""
GOLD = GOLD_A = GOLD_B = INK = ""
TEXT = MUTED = FAINT = WARM = CODE = ""
DANGER = SUCCESS = ""
GLASS = GLASS_HOVER = STROKE = GOLD_DIM = GOLD_EDGE = PRE_BG = ""


def set_theme(key: str) -> str:
    """
    Переключает оформление.

    Возвращает код темы, которая реально применилась: если попросили
    неизвестную, откатимся на оформление по умолчанию.
    """
    global _palette
    _palette = THEMES.get(key, THEMES[DEFAULT_THEME])
    p = _palette
    globals().update(
        BG_1=p.bg_1, BG_2=p.bg_2, BG_3=p.bg_3,
        GOLD=p.gold_text, GOLD_A=p.gold_a, GOLD_B=p.gold_b, INK=p.ink,
        TEXT=p.text, MUTED=p.muted, FAINT=p.faint, WARM=p.warm, CODE=p.code,
        DANGER=p.danger, SUCCESS=p.success,
        GLASS=p.surface, GLASS_HOVER=p.surface_hover, STROKE=p.stroke,
        GOLD_DIM=p.gold_dim, GOLD_EDGE=p.gold_edge, PRE_BG=p.log_bg,
    )
    return p.key


def current_theme() -> str:
    return _palette.key


def palette() -> Palette:
    """Полная палитра — там, где плоских констант мало."""
    return _palette


def is_light() -> bool:
    """Светлое ли сейчас оформление. Нужно для системных контролов Flet."""
    return _palette.key == "light"


# ============================================================= РАЗМЕРЫ
R_CONTAINER = 24         # большой контейнер страницы
R_CARD = 12              # карточки, поля ввода, кнопки-контуры
R_PILL = 50              # главная кнопка: «таблетка»
R_BADGE = 20             # бейдж и чипы состояния

FONT = "Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"

# ------------------------------------------------------- МАСШТАБ
SCALE = 1.0
SCALE_MIN = 0.8
SCALE_MAX = 1.5
SCALE_STEP = 0.1

# Базовые размеры шрифта при масштабе 1.0.
# На сайте они в rem, здесь — в логических пикселях Flet.
_BASE_SIZES = {
    "FS_H1": 30,         # заголовок «Downloader3000»
    "FS_H2": 19,
    "FS_LABEL": 12,      # подписи секций капсом
    "FS_BODY": 14,       # основной текст и кнопки
    "FS_SMALL": 12,      # пояснения
    "FS_TINY": 11,       # подсказки и копирайт
    "FS_MONO": 12,       # лог
}

FS_H1 = 30
FS_H2 = 19
FS_LABEL = 12
FS_BODY = 14
FS_SMALL = 12
FS_TINY = 11
FS_MONO = 12

# Аналог CSS transition: all .3s ease.
ANIM = ft.Animation(250, ft.AnimationCurve.EASE_OUT)


def set_scale(value: float) -> None:
    """
    Меняет масштаб интерфейса и пересчитывает размеры шрифта.

    Значение зажимается: меньше 0.8 текст нечитаем, больше 1.5
    интерфейс перестаёт помещаться в окно.
    """
    global SCALE
    SCALE = max(SCALE_MIN, min(SCALE_MAX, round(value, 2)))
    g = globals()
    for name, base in _BASE_SIZES.items():
        g[name] = max(1, round(base * SCALE))


def px(value: float) -> int:
    """Масштабирует размер, заданный числом прямо в коде интерфейса."""
    return max(1, round(value * SCALE))


# ==================================================== ГРАДИЕНТЫ И ТЕНИ
def page_gradient() -> ft.LinearGradient:
    """
    Фон окна.

    В оригинальном оформлении это linear-gradient(135deg, ...) с сайта.
    В плоских темах возвращаем тот же объект, но с одинаковыми цветами:
    вызывающий код не обрастает условиями, а фон получается ровным.
    """
    return ft.LinearGradient(
        begin=ft.Alignment.TOP_LEFT,
        end=ft.Alignment.BOTTOM_RIGHT,
        colors=[BG_1, BG_2, BG_3],
        stops=[0.0, 0.5, 1.0],
    )


def gold_gradient() -> ft.LinearGradient:
    """
    Заливка главной кнопки.

    Градиент кнопки оставлен во всех темах намеренно: именно он делает
    кнопку узнаваемой, и на плоском фоне читается как акцент, а не как шум.
    """
    return ft.LinearGradient(
        begin=ft.Alignment.TOP_LEFT,
        end=ft.Alignment.BOTTOM_RIGHT,
        colors=[GOLD_A, GOLD_B],
    )


def glow(color: str | None = None, opacity: float = 0.30,
         blur: int = 40, dy: int = 10) -> ft.BoxShadow | None:
    """
    Свечение под кнопкой — аналог box-shadow с сайта.

    В плоских темах возвращает None: свечений там нет по определению,
    а вызывающему коду ничего менять не нужно — Flet спокойно принимает
    `shadow=None`.
    """
    if not _palette.glow:
        return None
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=blur,
        color=ft.Colors.with_opacity(opacity, color or _palette.gold),
        offset=ft.Offset(0, dy),
    )


# ============================================================== ТЕКСТ
def h1(value: str, width: int = 340) -> ft.Text:
    """
    Заголовок, залитый золотым градиентом.

    На сайте это -webkit-background-clip: text. В Flet прямого аналога нет,
    поэтому текст закрашивается градиентной кистью через TextStyle.foreground.
    Осторожно: параметра Text(foreground=...) не существует.
    """
    return ft.Text(
        value,
        style=ft.TextStyle(
            size=FS_H1,
            weight=ft.FontWeight.BOLD,
            font_family=FONT,
            foreground=ft.Paint(
                gradient=ft.PaintLinearGradient(
                    begin=(0, 0), end=(width, FS_H1), colors=[GOLD_A, GOLD_B]
                )
            ),
        ),
    )


def label(value: str) -> ft.Text:
    """Подпись секции: мелкий золотой капс, аналог h2 с сайта."""
    return ft.Text(value, size=FS_LABEL, weight=ft.FontWeight.BOLD,
                   color=GOLD, font_family=FONT)


def body(value: str, color: str | None = None, size: int | None = None, **kw) -> ft.Text:
    """Обычный текст. **kw пробрасывается в Flet."""
    return ft.Text(value, size=size or FS_BODY, color=color or TEXT,
                   font_family=FONT, **kw)


def muted(value: str, size: int | None = None, **kw) -> ft.Text:
    """Приглушённый текст для пояснений."""
    return ft.Text(value, size=size or FS_SMALL, color=MUTED, font_family=FONT, **kw)


# ========================================================== КОНТЕЙНЕРЫ
def glass(content: ft.Control, radius: int = R_CARD, padding=16, **kw) -> ft.Container:
    """
    Панель-подложка — .card / .container / .step на сайте.

    В оригинальном оформлении это полупрозрачная белая заливка поверх
    цветного градиента, отсюда эффект стекла. В плоских темах — обычный
    сплошной цвет, и стекла не получается, что и требуется.
    """
    return ft.Container(
        content=content,
        bgcolor=GLASS,
        border=ft.Border.all(1, STROKE),
        border_radius=radius,
        padding=padding,
        **kw,
    )


def badge(value: str) -> ft.Container:
    """Золотая пилюля-бейдж из шапки — .badge на сайте."""
    return ft.Container(
        content=ft.Text(value, size=FS_SMALL, color=GOLD, font_family=FONT),
        bgcolor=GOLD_DIM,
        border=ft.Border.all(1, GOLD_EDGE),
        border_radius=R_BADGE,
        padding=ft.Padding(14, 5, 14, 5),
    )


# Тема по умолчанию применяется сразу, чтобы константы не остались пустыми,
# если к ним обратятся до первой настройки.
set_theme(DEFAULT_THEME)
