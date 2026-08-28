# -*- coding: utf-8 -*-
"""
ОБХОД БЛОКИРОВКИ ПО ИМЕНАМ
==========================

Зачем это нужно
---------------
Некоторые операторы блокируют сайты самым дешёвым способом: не пускают
соединение, а просто не отвечают на запрос «какой IP у youtube.com».
Само соединение при этом проходит — если IP уже известен.

Проверено на живом телефоне: `github.com`, `google.com` и `cloudflare.com`
разрешались нормально, `youtube.com` — нет, а TCP до его серверов
устанавливался без проблем.

Браузеры давно обходят это шифрованным разрешением имён: спрашивают IP
не у оператора, а у публичного сервера по HTTPS. Оператор видит только
соединение с этим сервером и не может понять, о каком имени речь.
Здесь делается то же самое.

Как это встроено
----------------
Python спрашивает адреса через `socket.getaddrinfo`. Мы подменяем эту
функцию своей: сначала пробуем обычным путём, а если система ответила
«имя не найдено» — переспрашиваем по HTTPS и возвращаем результат
в том же виде, какой ожидает стандартная библиотека.

Из этого следуют два важных свойства:

  * пока всё работает, наш код вообще не вмешивается — обычное
    разрешение имён быстрее, и мы идём по нему;
  * подмена действует на весь процесс, а значит и на yt-dlp,
    который ничего про неё не знает.

Чего этот способ НЕ умеет
-------------------------
Если оператор режет не имена, а сами соединения — по имени сервера
внутри TLS или по адресам — обход не поможет. Тогда нужен прокси
или VPN. Программа это различает и пишет в лог, что именно не вышло.
"""
from __future__ import annotations

import json
import socket
import ssl
import threading
import urllib.parse
import urllib.request
from typing import Any

# Публичные серверы, умеющие отвечать на запросы имён по HTTPS.
# Два разных оператора: если первый недоступен, спрашиваем у второго.
RESOLVERS = (
    ("https://cloudflare-dns.com/dns-query", "1.1.1.1"),
    ("https://dns.google/resolve", "8.8.8.8"),
)

# Сколько ждать ответа. Пользователь и так уже ждёт — затягивать нельзя.
TIMEOUT = 6

_original_getaddrinfo = None
_cache: dict[str, list[str]] = {}
_lock = threading.Lock()
_log: Any = None


def _resolve_over_https(host: str) -> list[str]:
    """
    Спрашивает адреса имени у публичного сервера по HTTPS.

    Возвращает список адресов или пустой список, если не вышло.
    Ошибки наружу не пускаем: неудача обхода — это просто «не помогло»,
    а не повод уронить скачивание.
    """
    for endpoint, server_ip in RESOLVERS:
        try:
            url = f"{endpoint}?name={urllib.parse.quote(host)}&type=A"
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/dns-json",
                    "User-Agent": "Downloader3000",
                },
            )
            # Проверку сертификата не отключаем: смысл в том, чтобы
            # ответ пришёл именно от того сервера, у которого спрашивали.
            context = ssl.create_default_context()
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
                data = json.load(response)

            addresses = [
                answer["data"]
                for answer in data.get("Answer", [])
                # Тип 1 — это обычный адрес IPv4. Записи-переадресации
                # (тип 5) пропускаем: нас интересует конечный адрес.
                if answer.get("type") == 1 and answer.get("data")
            ]
            if addresses:
                if _log:
                    _log(f"Имя {host} разрешено через {server_ip}: {addresses[0]}", "info")
                return addresses
        except Exception:
            continue
    return []


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """
    Замена стандартного разрешения имён.

    Сначала пробуем как обычно. Вмешиваемся только когда система
    ответила «имя не найдено» — то есть ровно в случае блокировки.
    """
    assert _original_getaddrinfo is not None
    try:
        return _original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        pass

    if not isinstance(host, str) or not host:
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    with _lock:
        addresses = _cache.get(host)
    if addresses is None:
        addresses = _resolve_over_https(host)
        with _lock:
            _cache[host] = addresses

    if not addresses:
        raise socket.gaierror(socket.EAI_NONAME, f"Name or service not known: {host}")

    # Собираем ответ в том же виде, в каком его отдаёт стандартная функция:
    # список кортежей (семейство, тип, протокол, каноническое имя, адрес).
    results = []
    for address in addresses:
        results.append((
            socket.AF_INET,
            type or socket.SOCK_STREAM,
            proto or 0,
            "",
            (address, port if isinstance(port, int) else 0),
        ))
    return results


def enable(log: Any = None) -> None:
    """
    Включает обход. Вызывать один раз при запуске.

    Повторные вызовы безопасны: подмена ставится только если её ещё нет.
    """
    global _original_getaddrinfo, _log
    _log = log
    if _original_getaddrinfo is not None:
        return
    _original_getaddrinfo = socket.getaddrinfo
    socket.getaddrinfo = _patched_getaddrinfo


def disable() -> None:
    """Возвращает обычное разрешение имён."""
    global _original_getaddrinfo
    if _original_getaddrinfo is None:
        return
    socket.getaddrinfo = _original_getaddrinfo
    _original_getaddrinfo = None
    with _lock:
        _cache.clear()


def is_enabled() -> bool:
    return _original_getaddrinfo is not None
