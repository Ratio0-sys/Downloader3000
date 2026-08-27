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
    """
    Точка входа приложения.

    Всё обёрнуто в try: если что-то падает на старте, пользователь должен
    увидеть понятное сообщение, а не голый трейсбек во весь экран.
    Именно так выглядела ошибка на Android, когда приложение пыталось
    создать папку настроек там, где писать нельзя.
    """
    try:
        DownloaderApp(page)
    except Exception as exc:
        _show_failure(page, exc)


def _show_failure(page: ft.Page, exc: Exception) -> None:
    """Экран с ошибкой вместо падения. Текст можно скопировать и прислать."""
    import traceback

    details = "".join(traceback.format_exception(exc)).strip()
    page.controls.clear()
    page.bgcolor = "#0f0c29"
    page.add(
        ft.Container(
            content=ft.Column(
                [
                    ft.Text("Не удалось запустить", size=22,
                            weight=ft.FontWeight.BOLD, color="#ff4444"),
                    ft.Text(str(exc), size=14, color="#e0e0e0", selectable=True),
                    ft.Container(height=12),
                    ft.Text("Подробности:", size=12, color="#aaaaaa"),
                    ft.Container(
                        content=ft.Text(details, size=11, color="#a8d8ea",
                                        font_family="Consolas, monospace",
                                        selectable=True),
                        bgcolor="#00000066",
                        border_radius=8,
                        padding=12,
                    ),
                ],
                spacing=6,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=24,
            expand=True,
        )
    )
    page.update()


if __name__ == "__main__":
    ft.run(main)
