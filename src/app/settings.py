# -*- coding: utf-8 -*-
"""
НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ
======================

Обычный JSON-файл рядом с программой. Никаких реестров и системных хранилищ:
так настройки переносятся вместе с папкой, и программа остаётся портабельной.

Главный принцип: сломанные или отсутствующие настройки никогда не должны
ронять приложение. Любая ошибка чтения молча приводит к значениям по умолчанию,
любая ошибка записи просто игнорируется.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from . import platform_paths as pp
from .engine import Mode


@dataclass
class Settings:
    """
    Все сохраняемые настройки.

    Пустые строки в путях — это маркер «ещё не задано»: подставить реальный
    путь в объявлении поля нельзя, потому что он вычисляется во время работы
    и зависит от платформы. Поэтому подстановка происходит в __post_init__.
    """

    video_dir: str = ""
    audio_dir: str = ""
    mode: str = Mode.BEST.value
    playlist: bool = False      # качать плейлист целиком, если он есть в ссылке
    threads: int = 4            # сколько кусков файла тянуть одновременно
    ui_scale: float = 1.0       # масштаб интерфейса, меняется в настройках
    language: str = ""          # код языка; пусто = определить по системе
    theme: str = "original"     # оформление: original / dark / light

    def __post_init__(self) -> None:
        """Датакласс зовёт этот метод сразу после создания — доопределяем пути."""
        if not self.video_dir:
            self.video_dir = str(pp.default_video_dir())
        if not self.audio_dir:
            self.audio_dir = str(pp.default_audio_dir())

    # ================================================================ ЧТЕНИЕ
    @classmethod
    def load(cls) -> "Settings":
        """
        Читает настройки с диска.

        Из файла берём только те ключи, которые реально существуют в классе.
        Это защищает от двух бед сразу: от мусора в файле и от старых настроек,
        оставшихся от прошлых версий программы.
        """
        path = pp.config_path()
        try:
            if path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
                known = {f: raw[f] for f in cls.__dataclass_fields__ if f in raw}
                return cls(**known)
        except Exception:
            # Битый JSON, нет прав на чтение, кривая кодировка — неважно.
            # Настройки не та вещь, ради которой стоит падать.
            pass
        return cls()

    def save(self) -> None:
        """
        Пишет настройки на диск.

        ensure_ascii=False — чтобы русские пути остались читаемыми,
        а не превратились в \\uXXXX. indent=2 — чтобы файл можно было
        поправить руками в блокноте.
        """
        try:
            path = pp.config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            # Программу положили в Program Files, и писать туда нельзя.
            # Настройки просто не сохранятся — работать это не мешает.
            pass

    # ============================================================== ПОМОЩЬ
    @property
    def mode_enum(self) -> Mode:
        """
        Строка из файла обратно в Mode.

        Если в файле оказалась чушь (например, режим из будущей версии),
        тихо откатываемся на режим по умолчанию.
        """
        try:
            return Mode(self.mode)
        except ValueError:
            return Mode.BEST

    def dir_for(self, mode: Mode) -> Path:
        """Папка для конкретного режима: у звука своя, у видео своя."""
        return Path(self.audio_dir if mode.is_audio else self.video_dir)

    def set_dir_for(self, mode: Mode, value: str) -> None:
        """Запомнить новую папку для режима — вызывается после выбора в диалоге."""
        if mode.is_audio:
            self.audio_dir = value
        else:
            self.video_dir = value
