<div align="center">

# 🎬 Downloader3000

**Вставил ссылку — получил файл.**
Видео и музыка с YouTube и сотен других сайтов.

[![Версия](https://img.shields.io/badge/версия-2.1.2-ffd700?style=flat-square)](https://github.com/Ratio0-sys/Downloader3000/releases/latest)
[![Платформы](https://img.shields.io/badge/Windows%20·%20Linux%20·%20macOS%20·%20Android-302b63?style=flat-square)](https://ratio0-sys.github.io/Downloader3000/)
[![Python](https://img.shields.io/badge/Python-3.12+-0f0c29?style=flat-square)](https://www.python.org/)
[![Лицензия](https://img.shields.io/badge/лицензия-MIT-24243e?style=flat-square)](LICENSE)

### **[🌐 Сайт проекта](https://ratio0-sys.github.io/Downloader3000/)** · **[📦 Скачать](https://github.com/Ratio0-sys/Downloader3000/releases/latest)** · **[📝 Изменения](CHANGELOG.md)**

<img src="docs/screenshots/original.png" alt="Главное окно Downloader3000" width="840">

</div>

---

Раньше это были четыре `.bat`-файла, которые приходилось править блокнотом.
Теперь одно приложение на четырёх платформах — и ставить к нему ничего не нужно.

## Скачать

Полное описание, скриншоты и решение проблем —
**[на сайте проекта](https://ratio0-sys.github.io/Downloader3000/)**.
Готовые сборки — на [странице релизов](https://github.com/Ratio0-sys/Downloader3000/releases/latest).

| Система | Файл | Требования |
| --- | --- | --- |
| Windows | `*-windows-x64.exe` | 10 и новее, один файл |
| Linux | `*-linux-x64.tar.gz` | Ubuntu 20.04+, Debian 11+ |
| macOS | `*-macos-universal.zip` | 11 и новее |
| Android | `*-android-arm64-v8a.apk` | 6.0 и новее |

## Что умеет

Четыре режима: **Best**, **1080p**, **720p** и **MP3** с обложкой.

- **Плейлисты по выбору** — список с галочками, качается только отмеченное
- **Два языка** и **три оформления**, масштаб интерфейса 80–150 %
- **Обход блокировки** — если провайдер не отдаёт адрес сайта, программа
  спросит его по шифрованному каналу; для более грубых блокировок
  в настройках есть поле прокси
- Прогресс со скоростью и временем, работающая отмена
- Живой лог: при ошибке видно причину, а не «попробуйте позже»
- Оригинальные имена файлов, включая русские буквы

<div align="center">
<img src="docs/screenshots/dark.png" alt="Тёмное оформление" width="410">
<img src="docs/screenshots/light.png" alt="Светлое оформление" width="410">
</div>

## Ограничения

Это не баги, а вещи, которые обойти нельзя.

**Windows 7 и 8.1 не поддерживаются.** Движок yt-dlp требует Python 3.10+,
а он на эти системы не ставится. Официальные сборки yt-dlp тоже давно
требуют Windows 10.

**ffmpeg обязателен для видео.** YouTube отдаёт картинку и звук раздельными
потоками — проверено на живом ролике: 32 потока без звука, 11 без картинки,
ни одного совмещённого. Во все сборки, включая Android, ffmpeg и QuickJS
уже вшиты — ставить ничего не нужно.

**На Android есть APK только под arm64 и arm32.** Под x86_64 бинарники
для телефона не кладутся, поэтому в эмуляторе склейка и MP3 не работают.
На настоящих телефонах это не мешает: там почти всегда arm64.

## Из исходников

```bash
git clone https://github.com/Ratio0-sys/Downloader3000.git
cd Downloader3000

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux / macOS

pip install -e "src[dev]"
python tools/fetch_quickjs.py
python src/main.py
```

### Собрать

```bash
# Windows — через PyInstaller, один самодостаточный файл
flet pack src/main.py --name Downloader3000 --icon tools/app.ico \
    --distpath build_exe --add-data "src/assets;assets" \
    "--pyinstaller-build-args=--collect-all=imageio_ffmpeg" -y

flet build apk   src --split-per-abi
flet build linux src
flet build macos src
```

Windows собирается через `flet pack`, а не `flet build windows`: второй
требует Visual Studio с компонентом C++. Все четыре платформы разом
собирает [workflow](.github/workflows/build.yml).

## Устройство

```text
docs/     сайт проекта и скриншоты
src/      код приложения
├── app/theme.py           палитры и размеры
├── app/engine.py          обёртка над yt-dlp
├── app/i18n.py            локализация
├── app/platform_paths.py  различия платформ
└── app/ui/                интерфейс
tools/    скрипты разработки и проверки
```

Код прокомментирован по-русски: открываете любой файл и понимаете,
что там происходит и почему именно так.

## Участие

Правки приветствуются — [CONTRIBUTING.md](CONTRIBUTING.md).
Об ошибках пишите в [issues](https://github.com/Ratio0-sys/Downloader3000/issues).

## Лицензия

[MIT](LICENSE). Сделано для личного использования.
Эльфы не несут ответственности за нарушение авторских прав.

<div align="center">

🧝 **by RandinLonescu** 🧝

[Twitch](https://www.twitch.tv/randinlonescu) ·
[YouTube](https://www.youtube.com/@RandinLonescu) ·
[Telegram](https://t.me/RandinLonescu)

</div>
