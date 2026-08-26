# -*- coding: utf-8 -*-
"""
Downloader3000 — точка входа.

Запуск при разработке:
    .venv/Scripts/python.exe src/main.py
    .venv/Scripts/flet.exe run --hot src/main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Когда main.py запускают напрямую (а не как модуль пакета), Python не знает
# про папку src/, и `from app...` не находится. Добавляем её в путь руками.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flet as ft  # noqa: E402

from app.ui.screen import DownloaderApp  # noqa: E402


def main(page: ft.Page) -> None:
    # Тема тёмная всегда: светлого варианта у дизайна с сайта просто нет.
    page.theme_mode = ft.ThemeMode.DARK
    DownloaderApp(page)


if __name__ == "__main__":
    ft.run(main)
